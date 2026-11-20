"""Push-to-Talk CoreAudio 16kHz recorder, passive Quartz Right-Option tap, chimes, and MLX/Groq STT."""

import asyncio
import collections
import io
import os
import queue
import subprocess
import threading
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import sounddevice as sd

from selene.config import SeleneConfig

try:
    import Quartz
    from ApplicationServices import AXIsProcessTrusted

    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

SAMPLE_RATE = 16000
RIGHT_OPTION_KEYCODE = 0x3D
RIGHT_OPTION_MASK = 0x00000040  # Device-dependent Right Option bit on macOS

WHISPER_PROMPTS = {
    "en": "Selene, macOS, Xcode, Cursor, SwiftUI, Spotify, Safari, Terminal, Python, MLX, Kokoro, RVC.",
    "ru": "Селена, привет. Открой Терминал, Сафари, Спотифай, Настройки, экран, проверь код и карточки памяти.",
}


def _clear_mlx_cache(mx_mod) -> None:
    """Release MLX Metal allocator cache cleanly across MLX versions."""
    if hasattr(mx_mod, "clear_cache"):
        mx_mod.clear_cache()
    elif hasattr(mx_mod, "metal") and hasattr(mx_mod.metal, "clear_cache"):
        mx_mod.metal.clear_cache()


def is_whisper_cached(whisper_repo: str = "mlx-community/whisper-large-v3-turbo") -> bool:
    """Return True if Whisper weights already exist in local HF cache."""
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    repo_dir = f"models--{whisper_repo.replace('/', '--')}"
    return any(hub.glob(f"{repo_dir}/snapshots/*/weights.*")) or any(
        hub.glob(f"{repo_dir}/snapshots/*/*.safetensors")
    )


def _play_chime(sound_name: str, volume: float = 0.18) -> None:
    """Fire a subtle, non-blocking macOS system sound chime."""
    sound_path = Path("/System/Library/Sounds") / f"{sound_name}.aiff"
    if not sound_path.exists():
        return
    try:
        subprocess.Popen(
            ["afplay", "-v", f"{volume:.2f}", str(sound_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def find_builtin_input_device() -> int | str | None:
    """Find the MacBook internal/built-in microphone to prevent Bluetooth SCO quality degradation."""
    try:
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = str(dev.get("name", "")).lower()
                if any(term in name for term in ("macbook", "built-in", "internal")):
                    return idx
    except Exception:
        pass
    return None


class EarEngine:
    """Thread-safe 16kHz CoreAudio recorder with passive Quartz Right-Option PTT & MLX/Groq STT."""

    def __init__(
        self,
        on_barge_in: Callable[[], None],
        chimes_enabled: bool = True,
        cfg: SeleneConfig | None = None,
        on_capture_start: Callable[[], None] | None = None,
        on_rms: Callable[[float], None] | None = None,
    ):
        self.cfg = cfg or SeleneConfig()
        self.language_mode = (getattr(self.cfg, "whisper_language", "auto") or "auto").strip().lower()
        self.last_detected_lang = "en"
        self._whisper_model = None
        self.on_barge_in = on_barge_in
        self.on_capture_start = on_capture_start
        self.on_rms = on_rms
        self.chimes_enabled = chimes_enabled
        self.is_recording = threading.Event()
        self._frames: list[np.ndarray] = []
        self._preroll: collections.deque[np.ndarray] = collections.deque(maxlen=5)  # ~160ms pre-roll
        self._stop_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._stt_lock = asyncio.Lock()
        self._utterances: queue.Queue[np.ndarray] = queue.Queue()
        self.global_ptt_active = False
        self.mic_available = False
        self.mic_gate_open = True
        self._stream: sd.InputStream | None = None

        device = None
        if getattr(self.cfg, "prefer_builtin_mic", True):
            builtin_dev = find_builtin_input_device()
            if builtin_dev is not None:
                device = builtin_dev

        try:
            # Persistent 16kHz mono stream; <0.1% CPU when is_recording is unset
            self._stream = sd.InputStream(
                samplerate=self.cfg.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=512,
                device=device,
                callback=self._mic_callback,
            )
            self._stream.start()
            self.mic_available = True
        except Exception as err:
            print(f"⚠️  Mic stream unavailable ({err}) — continuing in text-only mode.", flush=True)

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if not self.mic_gate_open:
            return
        mono = indata[:, 0].copy()
        if self.is_recording.is_set():
            with self._lock:
                self._frames.append(mono)
            if self.on_rms is not None:
                self._rms_counter = getattr(self, "_rms_counter", 0) + 1
                if self._rms_counter % 2 == 0:
                    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
                    try:
                        self.on_rms(rms)
                    except Exception:
                        pass
        else:
            with self._lock:
                self._preroll.append(mono)

    def start_capture(self) -> None:
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
        if not self.mic_available or self.is_recording.is_set():
            return
        self.on_barge_in()  # Flush GaplessSpeaker & cancel in-flight reply (<20ms)
        self.ensure_model_loaded()  # Speculative warmup while user is speaking
        if self.on_capture_start is not None:
            try:
                self.on_capture_start()
            except Exception:
                pass
        if self.chimes_enabled:
            _play_chime(self.cfg.chime_open_sound, volume=self.cfg.chime_open_vol)
        with self._lock:
            self._frames = list(self._preroll)
            self._preroll.clear()
        self.is_recording.set()
        hint = "release Right Option" if self.global_ptt_active else "press Enter"
        print(f"\n🎙️  [Listening... {hint} to send]", flush=True)

    def stop_capture(self) -> None:
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
        if not self.is_recording.is_set():
            return
        self.is_recording.clear()
        with self._lock:
            if not self._frames:
                return
            audio = np.concatenate(self._frames)
            self._frames.clear()
            self._preroll.clear()

        if len(audio) < int(self.cfg.sample_rate * self.cfg.min_audio_sec):
            print("🎙️  [Too short — ignored]", flush=True)
            return

        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
        if rms < self.cfg.min_rms_energy:
            print(f"🎙️  [Silence — ignored (RMS {rms:.5f} < {self.cfg.min_rms_energy})]", flush=True)
            return

        if self.chimes_enabled:
            _play_chime(self.cfg.chime_close_sound, volume=self.cfg.chime_close_vol)
        self._utterances.put(audio)

    def cancel_capture(self) -> None:
        """Discard in-flight recording immediately without processing or queuing."""
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
            self.is_recording.clear()
            self._frames.clear()
            self._preroll.clear()

    def schedule_stop_capture(self, delay: float = 0.22) -> None:
        """Schedule stop_capture with a small hangover so ending words are never clipped."""
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
            self._stop_timer = threading.Timer(delay, self.stop_capture)
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def try_get_utterance(self) -> np.ndarray | None:
        """Non-blocking pop of next recorded utterance (returns None if empty)."""
        try:
            return self._utterances.get_nowait()
        except queue.Empty:
            return None

    def start_ptt_listener(self) -> bool:
        """Start passive listen-only Quartz tap on Right Option if Accessibility is granted."""
        if not self.mic_available:
            return False
        if not HAS_QUARTZ or not AXIsProcessTrusted():
            print(
                "ℹ️  [PTT] Accessibility not granted to Terminal — using Enter-toggle mic mode\n"
                "   (press Enter on an empty prompt to start/stop recording, or enable Terminal in\n"
                "    System Settings -> Privacy & Security -> Accessibility for global Right Option PTT).",
                flush=True,
            )
            return False

        def _tap_callback(proxy, event_type, event, refcon):
            if event_type == Quartz.kCGEventFlagsChanged:
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                if keycode == RIGHT_OPTION_KEYCODE:
                    flags = Quartz.CGEventGetFlags(event)
                    is_down = (
                        bool(flags & RIGHT_OPTION_MASK)
                        if (flags & 0x60)
                        else bool(flags & Quartz.kCGEventFlagMaskAlternate)
                    )
                    if is_down:
                        self.start_capture()
                    else:
                        self.schedule_stop_capture(delay=0.22)
            return event

        def _run_tap() -> None:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,  # Passive: never freezes macOS input
                Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
                _tap_callback,
                None,
            )
            if not tap:
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(run_loop, source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            self.global_ptt_active = True
            Quartz.CFRunLoopRun()

        threading.Thread(target=_run_tap, daemon=True, name="quartz-ptt").start()
        threading.Event().wait(0.05)
        return self.global_ptt_active

    async def warmup(self) -> None:
        """Pre-warm local MLX-Whisper weights in background so the 1st voice turn hits ~130ms."""
        if os.environ.get("GROQ_API_KEY") or not is_whisper_cached(self.cfg.whisper_repo):
            return
        async with self._stt_lock:
            try:
                dummy = np.zeros(int(self.cfg.sample_rate * 0.25), dtype=np.float32)
                await asyncio.to_thread(self._transcribe_mlx, dummy)
            except Exception:
                pass

    async def transcribe(self, audio_f32: np.ndarray) -> str:
        """Transcribe via Groq Whisper if GROQ_API_KEY is set, else local MLX-Whisper."""
        # Audio normalization: scale quiet audio to 0.6 peak so Whisper receives crisp phonemes
        if len(audio_f32) > 0:
            max_val = float(np.max(np.abs(audio_f32)))
            if 0.001 < max_val < 0.55:
                audio_f32 = audio_f32 * (0.6 / max_val)

        async with self._stt_lock:
            if os.environ.get("GROQ_API_KEY"):
                try:
                    return await asyncio.to_thread(self._transcribe_groq, audio_f32)
                except Exception as err:
                    print(
                        f"[STT] Groq failed ({err}), falling back to local MLX-Whisper...",
                        flush=True,
                    )
            return await asyncio.to_thread(self._transcribe_mlx, audio_f32)

    def set_language_mode(self, mode: str) -> None:
        """Update active language mode ('en', 'ru', 'auto') dynamically without restart."""
        cleaned = mode.strip().lower()
        if cleaned in ("en", "english"):
            self.language_mode = "en"
            self.last_detected_lang = "en"
        elif cleaned in ("ru", "russian"):
            self.language_mode = "ru"
            self.last_detected_lang = "ru"
        elif cleaned == "auto":
            self.language_mode = "auto"

    def ensure_model_loaded(self) -> None:
        """Speculatively pre-warm Whisper weights in Unified Memory during PTT key-down."""
        if self._whisper_model is None:
            def _preload():
                from mlx_whisper.load_models import load_model
                try:
                    self._whisper_model = load_model(self.cfg.whisper_repo)
                except Exception as err:
                    print(f"[EarEngine] Speculative preload warning: {err}", flush=True)

            threading.Thread(target=_preload, daemon=True, name="whisper-preload").start()

    def unload_model(self) -> None:
        """Evict Whisper model from Unified Memory when idle to reclaim ~464MB RAM."""
        with self._lock:
            if self._whisper_model is not None:
                del self._whisper_model
                self._whisper_model = None
        from selene.memory_reclaimer import reclaim_idle_memory
        reclaim_idle_memory()

    def _detect_en_or_ru(self, audio_f32: np.ndarray) -> str:
        """Acoustic-only language ID restricted strictly to English vs Russian."""
        import mlx.core as mx
        from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim
        from mlx_whisper.load_models import load_model

        if self._whisper_model is None:
            self._whisper_model = load_model(self.cfg.whisper_repo)

        mel = log_mel_spectrogram(
            pad_or_trim(mx.array(audio_f32)), n_mels=self._whisper_model.dims.n_mels
        )
        _, probs = self._whisper_model.detect_language(mel)
        p_en = float(probs.get("en", 0.0))
        p_ru = float(probs.get("ru", 0.0))
        total = p_en + p_ru + 1e-9
        norm_en = p_en / total
        norm_ru = p_ru / total

        if max(norm_en, norm_ru) < 0.65:
            return self.last_detected_lang
        target = "ru" if norm_ru > norm_en else "en"
        self.last_detected_lang = target
        return target

    def _transcribe_mlx(self, audio_f32: np.ndarray) -> str:
        import mlx.core as mx
        import mlx_whisper

        prev_offline = os.environ.get("HF_HUB_OFFLINE")
        hf_const = None
        prev_const_offline = None
        if not is_whisper_cached(self.cfg.whisper_repo):
            os.environ.pop("HF_HUB_OFFLINE", None)
            try:
                import huggingface_hub.constants as _hf_const

                hf_const = _hf_const
                prev_const_offline = _hf_const.HF_HUB_OFFLINE
                _hf_const.HF_HUB_OFFLINE = False
            except Exception:
                pass

        mode = (self.language_mode or "en").strip().lower()
        if mode == "auto":
            try:
                target_lang = self._detect_en_or_ru(audio_f32)
            except Exception:
                target_lang = self.last_detected_lang
        elif mode in ("ru", "russian"):
            target_lang = "ru"
            self.last_detected_lang = "ru"
        else:
            target_lang = "en"
            self.last_detected_lang = "en"

        prompt = WHISPER_PROMPTS.get(target_lang, WHISPER_PROMPTS["en"])
        kwargs: dict[str, object] = {
            "path_or_hf_repo": self.cfg.whisper_repo,
            "fp16": True,
            "temperature": 0.0,
            "language": target_lang,
            "initial_prompt": prompt,
            "condition_on_previous_text": False,
        }

        try:
            result = mlx_whisper.transcribe(
                audio_f32,
                **kwargs,
            )
        finally:
            if prev_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
            if hf_const is not None and prev_const_offline is not None:
                hf_const.HF_HUB_OFFLINE = prev_const_offline
            _clear_mlx_cache(mx)
        return str(result.get("text", "")).strip()

    def _transcribe_groq(self, audio_f32: np.ndarray) -> str:
        import httpx

        pcm16 = (np.clip(audio_f32, -1.0, 1.0) * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.cfg.sample_rate)
            wf.writeframes(pcm16.tobytes())

        mode = (self.language_mode or "en").strip().lower()
        data: dict[str, str] = {
            "model": "whisper-large-v3-turbo",
            "response_format": "text",
        }
        if mode == "auto":
            pass  # Cloud API single-pass auto-detect; omit prompt
        elif mode in ("ru", "russian"):
            data["language"] = "ru"
            data["prompt"] = WHISPER_PROMPTS["ru"]
            self.last_detected_lang = "ru"
        else:
            data["language"] = "en"
            data["prompt"] = WHISPER_PROMPTS["en"]
            self.last_detected_lang = "en"

        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            files={"file": ("speech.wav", buf.getvalue(), "audio/wav")},
            data=data,
            timeout=8.0,
        )
        resp.raise_for_status()
        return resp.text.strip()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
