"""Local Kokoro-82M (CPU, offline-cached) + Apple Silicon Metal GPU RVC + CoreAudio Speaker."""

import concurrent.futures
import importlib.machinery
import os
import queue
import sys
import threading
import time
import types as _pytypes
from pathlib import Path

# CRITICAL macOS invariant: import faiss BEFORE torch to prevent OpenMP conflicts
import faiss  # isort: skip
import numpy as np
import sounddevice as sd
import soxr
import torch

from selene.config import SeleneConfig


def _register_rvc_namespace(applio_resources: str) -> None:
    """Expose ONLY Applio's `rvc` package without adding APPLIO_RESOURCES to sys.path.

    Adding APPLIO_RESOURCES to sys.path leaks Applio's bundled `aiohttp` and `pytz`
    stubs into unrelated libraries (google-genai, kokoro/babel) during parallel boot.
    """
    if "rvc" in sys.modules:
        return
    rvc_dir = os.path.join(applio_resources, "rvc")
    spec = importlib.machinery.ModuleSpec("rvc", loader=None, is_package=True)
    spec.submodule_search_locations = [rvc_dir]
    pkg = _pytypes.ModuleType("rvc")
    pkg.__spec__ = spec
    pkg.__path__ = [rvc_dir]
    sys.modules["rvc"] = pkg


def is_kokoro_cached() -> bool:
    """Return True if Kokoro-82M weights exist in local HF cache."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return any(hub.glob("models--hexgrad--Kokoro-82M/snapshots/*/kokoro-v1_0.pth"))


def enable_offline_hub_if_cached() -> bool:
    """Lock Hugging Face Hub into instant offline mode once Kokoro weights exist locally."""
    if is_kokoro_cached():
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        return True
    return False


class KokoroTTSEngine:
    """100% local Kokoro-82M TTS on CPU -> resampled in RAM to 16kHz float32 for RVC."""

    def __init__(self, cfg: SeleneConfig | None = None):
        active_cfg = cfg or SeleneConfig()
        t0 = time.time()
        print(f"🗣️  Loading local Kokoro-82M ({active_cfg.kokoro_voice}) on CPU...", flush=True)

        if is_kokoro_cached():
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        from kokoro import KPipeline

        self.voice = active_cfg.kokoro_voice
        self.speed = active_cfg.kokoro_speed
        self.pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cpu")
        self.synthesize_16k("Hello.")

        print(f"✨ Kokoro-82M ready in {time.time() - t0:.2f}s!", flush=True)

    def synthesize_16k(self, text: str) -> np.ndarray | None:
        """Synthesize text at 24kHz and resample to 16kHz float32 in memory."""
        if not text.strip():
            return None
        chunks: list[np.ndarray] = []
        for _, _, audio in self.pipeline(text, voice=self.voice, speed=self.speed):
            if audio is not None and len(audio) > 0:
                if isinstance(audio, torch.Tensor):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return None
        audio_24k = np.concatenate(chunks)
        audio_16k = soxr.resample(audio_24k, 24000, 16000, quality="HQ")
        return np.asarray(audio_16k, dtype=np.float32)


class MetalRVCEngine:
    """Keeps ContentVec, cached FCPE, custom_voice (.pth), and optional FAISS index hot on MPS."""

    def __init__(self, use_index: bool = True, cfg: SeleneConfig | None = None):
        self.cfg_data = cfg or SeleneConfig()
        t0 = time.time()
        mode_label = "Full FAISS" if use_index else "Fast Pure .pth"
        print(
            f"🚀 Booting custom_voice RVC Engine ({mode_label}) on Apple Silicon Metal GPU...",
            flush=True,
        )

        self.use_index = use_index
        if Path.cwd() != self.cfg_data.model_workdir:
            os.chdir(str(self.cfg_data.model_workdir))

        _register_rvc_namespace(self.cfg_data.applio_resources)

        import rvc.infer.pipeline as rvc_pipeline_mod
        from rvc.configs.config import Config
        from rvc.infer.pipeline import Pipeline
        from rvc.lib.algorithm.synthesizers import Synthesizer
        from rvc.lib.utils import load_embedding

        self.cfg = Config()
        self.cfg.device = "mps" if torch.backends.mps.is_available() else "cpu"

        _orig_fcpe_cls = rvc_pipeline_mod.FCPE
        _cached_fcpe = _orig_fcpe_cls(device=self.cfg.device, sample_rate=16000, hop_size=160)
        rvc_pipeline_mod.FCPE = lambda *args, **kwargs: _cached_fcpe

        if self.use_index:
            self._cached_index = faiss.read_index(self.cfg_data.rvc_index_path)
            self._cached_big_npy = self._cached_index.reconstruct_n(0, self._cached_index.ntotal)
            faiss.read_index = lambda _p: self._cached_index
            self._cached_index.reconstruct_n = lambda _a, _b: self._cached_big_npy
        else:
            self._cached_index = None
            self._cached_big_npy = None

        cpt = torch.load(self.cfg_data.rvc_model_path, map_location="cpu", weights_only=True)
        self.tgt_sr = cpt["config"][-1]
        cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]
        self.use_f0 = cpt.get("f0", 1)
        self.version = cpt.get("version", "v2")

        self.net_g = Synthesizer(
            *cpt["config"],
            use_f0=self.use_f0,
            text_enc_hidden_dim=768 if self.version == "v2" else 256,
            vocoder=cpt.get("vocoder", "HiFi-GAN"),
        )
        del self.net_g.enc_q
        self.net_g.load_state_dict(cpt["weight"], strict=False)
        self.net_g = self.net_g.to(self.cfg.device).float().eval()

        self.hubert = load_embedding("contentvec").to(self.cfg.device).float().eval()

        self.vc = Pipeline(self.tgt_sr, self.cfg)
        dummy = np.zeros(16000, dtype=np.float32)
        with torch.no_grad():
            self.convert_pcm16k(dummy)

        print(
            f"✨ RVC Engine ready on [{self.cfg.device.upper()} | {mode_label}] in {time.time() - t0:.2f}s!",
            flush=True,
        )

    def convert_pcm16k(self, audio_16k_float32: np.ndarray) -> np.ndarray:
        """Convert 16kHz float32 audio into custom_voice voice at self.tgt_sr (int16)."""
        audio_max = np.abs(audio_16k_float32).max() / 0.95
        if audio_max > 1.0:
            audio_16k_float32 = audio_16k_float32 / audio_max

        with torch.no_grad():
            audio_opt = self.vc.pipeline(
                model=self.hubert,
                net_g=self.net_g,
                sid=0,
                audio=audio_16k_float32,
                pitch=self.cfg_data.rvc_pitch,
                f0_method="fcpe",
                file_index=self.cfg_data.rvc_index_path if self.use_index else "",
                index_rate=self.cfg_data.rvc_index_rate if self.use_index else 0.0,
                pitch_guidance=self.use_f0,
                volume_envelope=1.0,
                version=self.version,
                protect=self.cfg_data.rvc_protect,
                f0_autotune=False,
                f0_autotune_strength=1.0,
                proposed_pitch=False,
                proposed_pitch_threshold=155.0,
            )

        audio_arr = np.asarray(audio_opt, dtype=np.float32)
        if np.abs(audio_arr).max() <= 1.5:
            audio_arr = np.clip(audio_arr, -1.0, 1.0) * 32767.0
        return audio_arr.astype(np.int16)


class GaplessSpeaker:
    """Thread-safe CoreAudio stereo player with instant sub-20ms flush/interrupt."""

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.pcm_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.interrupt_event = threading.Event()
        self.is_speaking = threading.Event()
        self._leftover = np.empty(0, dtype=np.int16)

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=2,
            dtype="int16",
            blocksize=1024,
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        if self.interrupt_event.is_set():
            outdata.fill(0)
            self._leftover = np.empty(0, dtype=np.int16)
            self.is_speaking.clear()
            return

        written = 0
        while written < frames:
            if len(self._leftover) == 0:
                try:
                    self._leftover = self.pcm_queue.get_nowait()
                    self.is_speaking.set()
                except queue.Empty:
                    outdata[written:] = 0
                    if written == 0:
                        self.is_speaking.clear()
                    return

            needed = frames - written
            take = min(needed, len(self._leftover))
            chunk = self._leftover[:take]
            outdata[written : written + take, 0] = chunk
            outdata[written : written + take, 1] = chunk
            self._leftover = self._leftover[take:]
            written += take

    def play_chunk(self, pcm_int16: np.ndarray) -> None:
        if not self.interrupt_event.is_set():
            self.pcm_queue.put(pcm_int16)

    def interrupt(self) -> None:
        self.interrupt_event.set()
        while not self.pcm_queue.empty():
            try:
                self.pcm_queue.get_nowait()
            except queue.Empty:
                break
        self._leftover = np.empty(0, dtype=np.int16)
        self.is_speaking.clear()

    def reset(self) -> None:
        self.interrupt_event.clear()

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


def boot_voice_engines(
    use_index: bool = True,
    cfg: SeleneConfig | None = None,
) -> tuple[KokoroTTSEngine, MetalRVCEngine]:
    """Pre-import lazy Python packages on main thread, then load CPU + MPS models in parallel."""
    active_cfg = cfg or SeleneConfig()
    enable_offline_hub_if_cached()
    os.chdir(str(active_cfg.model_workdir))
    _register_rvc_namespace(active_cfg.applio_resources)

    # Pre-import lazy-loading modules on main thread & silence progress bar spam
    import rvc.infer.pipeline  # noqa: F401
    from kokoro import KPipeline  # noqa: F401
    from rvc.lib.utils import load_embedding  # noqa: F401
    from transformers import HubertModel  # noqa: F401
    from transformers.utils import logging as hf_logging

    hf_logging.disable_progress_bar()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_kokoro = pool.submit(KokoroTTSEngine, active_cfg)
        fut_rvc = pool.submit(MetalRVCEngine, use_index, active_cfg)
        return fut_kokoro.result(), fut_rvc.result()
