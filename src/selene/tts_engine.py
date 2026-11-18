"""Apple Silicon Kokoro-MLX TTS engine with PyTorch CPU fallback and fast polyphase resampling."""

import os
import time
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from selene.config import SeleneConfig


def _clear_mlx_cache(mx_mod) -> None:
    """Release MLX Metal allocator cache cleanly across MLX versions."""
    if hasattr(mx_mod, "clear_cache"):
        mx_mod.clear_cache()
    elif hasattr(mx_mod, "metal") and hasattr(mx_mod.metal, "clear_cache"):
        mx_mod.metal.clear_cache()


def resample_24k_to_16k(audio_24k: np.ndarray) -> np.ndarray:
    """Fast exact rational polyphase resample from 24 kHz to 16 kHz (< 0.4 ms)."""
    arr = np.asarray(audio_24k, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return arr
    return np.asarray(resample_poly(arr, up=2, down=3), dtype=np.float32)


def is_kokoro_cached() -> bool:
    """Return True if PyTorch Kokoro-82M weights exist in local HF cache."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return any(hub.glob("models--hexgrad--Kokoro-82M/snapshots/*/kokoro-v1_0.pth"))


def is_kokoro_mlx_cached(repo_id: str = "mlx-community/Kokoro-82M-bf16") -> bool:
    """Return True if Kokoro-MLX weights already exist in local HF cache."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    repo_dir = f"models--{repo_id.replace('/', '--')}"
    return any(hub.glob(f"{repo_dir}/snapshots/*/*.safetensors")) or any(
        hub.glob(f"{repo_dir}/snapshots/*/*.npz")
    )


class KokoroMLXEngine:
    """Apple Silicon MLX Kokoro-82M TTS (~120–220 ms first clause) -> 16 kHz float32 for RVC."""

    backend_label = "Kokoro-MLX"

    def __init__(self, cfg: SeleneConfig | None = None):
        active_cfg = cfg or SeleneConfig()
        t0 = time.time()
        print(
            f"🗣️  Loading Kokoro-MLX ({active_cfg.kokoro_voice} | {active_cfg.kokoro_mlx_repo})...",
            flush=True,
        )

        self.voice = active_cfg.kokoro_voice
        self.speed = active_cfg.kokoro_speed
        self.repo_id = active_cfg.kokoro_mlx_repo

        prev_offline = os.environ.get("HF_HUB_OFFLINE")
        hf_const = None
        prev_const_offline = None
        if not is_kokoro_mlx_cached(self.repo_id):
            os.environ.pop("HF_HUB_OFFLINE", None)
            try:
                import huggingface_hub.constants as _hf_const

                hf_const = _hf_const
                prev_const_offline = _hf_const.HF_HUB_OFFLINE
                _hf_const.HF_HUB_OFFLINE = False
            except Exception:
                pass
        else:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")

        try:
            import mlx.core as mx
            from kokoro_mlx import KokoroTTS

            self._mx = mx
            self.tts = KokoroTTS.from_pretrained(self.repo_id)
            self.synthesize_16k("Hello.")
        finally:
            if prev_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
            if hf_const is not None and prev_const_offline is not None:
                hf_const.HF_HUB_OFFLINE = prev_const_offline

        print(f"✨ Kokoro-MLX ready in {time.time() - t0:.2f}s!", flush=True)

    def synthesize_16k(self, text: str) -> np.ndarray | None:
        """Synthesize text at 24 kHz via MLX and resample to 16 kHz float32 in memory."""
        if not text.strip():
            return None
        try:
            result = self.tts.generate(
                text,
                voice=self.voice,
                speed=self.speed,
                sample_rate=24000,
            )
            audio_24k = np.asarray(result.audio, dtype=np.float32)
            if audio_24k.size == 0:
                return None
            return resample_24k_to_16k(audio_24k)
        finally:
            _clear_mlx_cache(self._mx)


class KokoroTTSEngine:
    """100% local Kokoro-82M TTS on PyTorch CPU -> resampled in RAM to 16 kHz float32 for RVC."""

    backend_label = "Kokoro-CPU"

    def __init__(self, cfg: SeleneConfig | None = None):
        active_cfg = cfg or SeleneConfig()
        t0 = time.time()
        print(f"🗣️  Loading local Kokoro-82M ({active_cfg.kokoro_voice}) on CPU...", flush=True)

        if is_kokoro_cached():
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        import torch
        from kokoro import KPipeline

        self._torch = torch
        self.voice = active_cfg.kokoro_voice
        self.speed = active_cfg.kokoro_speed
        self.pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cpu")
        self.synthesize_16k("Hello.")

        print(f"✨ Kokoro-82M ready in {time.time() - t0:.2f}s!", flush=True)

    def synthesize_16k(self, text: str) -> np.ndarray | None:
        """Synthesize text at 24 kHz and resample to 16 kHz float32 in memory."""
        if not text.strip():
            return None
        chunks: list[np.ndarray] = []
        for _, _, audio in self.pipeline(text, voice=self.voice, speed=self.speed):
            if audio is not None and len(audio) > 0:
                if isinstance(audio, self._torch.Tensor):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return None
        return resample_24k_to_16k(np.concatenate(chunks))


def create_tts_engine(cfg: SeleneConfig | None = None) -> KokoroMLXEngine | KokoroTTSEngine:
    """Instantiate configured TTS engine (MLX preferred, with automatic PyTorch CPU fallback)."""
    active_cfg = cfg or SeleneConfig()
    if active_cfg.tts_backend.strip().lower() == "mlx":
        try:
            return KokoroMLXEngine(active_cfg)
        except Exception as err:
            print(
                f"⚠️  Kokoro-MLX unavailable ({err}) — falling back to PyTorch CPU Kokoro.",
                flush=True,
            )
    return KokoroTTSEngine(active_cfg)
