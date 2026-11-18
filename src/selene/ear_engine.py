"""Push-to-Talk CoreAudio 16kHz recorder, passive Quartz Right-Option tap, chimes, and MLX/Groq STT."""

import asyncio
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


def _clear_mlx_cache(mx_mod) -> None:
    """Release MLX Metal allocator cache cleanly across MLX versions."""
    if hasattr(mx_mod, "clear_cache"):
        mx_mod.clear_cache()
    elif hasattr(mx_mod, "metal") and hasattr(mx_mod.metal, "clear_cache"):
        mx_mod.metal.clear_cache()


def is_whisper_cached(whisper_repo: str = "mlx-community/whisper-base-mlx") -> bool:
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


class EarEngine:
    """Thread-safe 16kHz CoreAudio recorder with passive Quartz Right-Option PTT & MLX/Groq STT."""

    def __init__(
        self,
        on_barge_in: Callable[[], None],
        chimes_enabled: bool = True,
        cfg: SeleneConfig | None = None,
    ):
        self.cfg = cfg or SeleneConfig()
        self.on_barge_in = on_barge_in
        self.chimes_enabled = chimes_enabled
        self.is_recording = threading.Event()
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stt_lock = asyncio.Lock()
        self._utterances: queue.Queue[np.ndarray] = queue.Queue()
        self.global_ptt_active = False
        self.mic_available = False
        self._stream: sd.InputStream | None = None

        try:
            # Persistent 16kHz mono stream; <0.1% CPU when is_recording is unset
            self._stream = sd.InputStream(
                samplerate=self.cfg.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=512,
                callback=self._mic_callback,
            )
            self._stream.start()
            self.mic_available = True
        except Exception as err:
            print(f"⚠️  Mic stream unavailable ({err}) — continuing in text-only mode.", flush=True)

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if self.is_recording.is_set():
            with self._lock:
                self._frames.append(indata[:, 0].copy())

    def start_capture(self) -> None:
        if not self.mic_available or self.is_recording.is_set():
            return
        self.on_barge_in()  # Flush GaplessSpeaker & cancel in-flight reply (<20ms)
        if self.chimes_enabled:
            _play_chime(self.cfg.chime_open_sound, volume=self.cfg.chime_open_vol)
        with self._lock:
            self._frames.clear()
        self.is_recording.set()
        hint = "release Right Option" if self.global_ptt_active else "press Enter"
        print(f"\n🎙️  [Listening... {hint} to send]", flush=True)

    def stop_capture(self) -> None:
        if not self.is_recording.is_set():
            return
        self.is_recording.clear()
        with self._lock:
            if not self._frames:
                return
            audio = np.concatenate(self._frames)
            self._frames.clear()

        if len(audio) < int(self.cfg.sample_rate * self.cfg.min_audio_sec):
            print("🎙️  [Too short — ignored]", flush=True)
            return

        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
        if rms < self.cfg.min_rms_energy:
            print("🎙️  [Silence — ignored]", flush=True)
            return

        if self.chimes_enabled:
            _play_chime(self.cfg.chime_close_sound, volume=self.cfg.chime_close_vol)
        self._utterances.put(audio)

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
                        self.stop_capture()
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
        try:
            result = mlx_whisper.transcribe(
                audio_f32,
                path_or_hf_repo=self.cfg.whisper_repo,
                fp16=True,
                initial_prompt=self.cfg.whisper_initial_prompt,
                condition_on_previous_text=False,
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

        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            files={"file": ("speech.wav", buf.getvalue(), "audio/wav")},
            data={
                "model": "whisper-large-v3-turbo",
                "response_format": "text",
                "prompt": self.cfg.whisper_initial_prompt,
            },
            timeout=8.0,
        )
        resp.raise_for_status()
        return resp.text.strip()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
