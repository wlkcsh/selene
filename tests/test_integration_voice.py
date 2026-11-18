"""Live Apple Silicon GPU, Kokoro TTS, Metal RVC, and MLX-Whisper integration test.

Excluded from default `uv run pytest` runs. Run explicitly with:
    uv run pytest -m integration -v -s
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TORCH_CPP_LOG_LEVEL", "ERROR")

import time

import numpy as np
import pytest

from selene.config import load_config
from selene.screen_vision import capture_screen_jpeg


@pytest.mark.integration
async def test_live_parallel_boot_stt_and_rvc_coexistence():
    # Import voice_engine FIRST so faiss loads before torch on macOS
    from selene.voice_engine import boot_voice_engines  # isort: skip
    from selene.ear_engine import EarEngine  # isort: skip

    cfg = load_config()
    kokoro, rvc = boot_voice_engines(use_index=False, cfg=cfg)
    assert rvc.tgt_sr == 48000

    ear = EarEngine(on_barge_in=lambda: None, chimes_enabled=False, cfg=cfg)
    try:
        await ear.warmup()

        # Verify RMS silence gate rejects dead silence
        ear.mic_available = True
        ear.is_recording.set()
        ear._frames = [np.zeros(cfg.sample_rate, dtype=np.float32)]
        ear.stop_capture()
        assert ear.try_get_utterance() is None

        # Verify Kokoro (MLX) + post-MLX Metal RVC + MLX-Whisper coexistence & benchmark
        t_tts0 = time.perf_counter()
        speech_16k = kokoro.synthesize_16k(
            "Selene, remember that my favorite Python framework is FastAPI."
        )
        t_tts = time.perf_counter() - t_tts0
        assert speech_16k is not None
        print(
            f"\n⚡ [{getattr(kokoro, 'backend_label', 'TTS')}] Synthesis latency: {t_tts*1000:.1f}ms",
            flush=True,
        )

        transcript = await ear.transcribe(speech_16k)
        assert "fastapi" in transcript.lower()

        t_rvc0 = time.perf_counter()
        rvc_pcm_skip = rvc.convert_pcm16k(speech_16k, skip_index=True)
        t_rvc_skip = time.perf_counter() - t_rvc0
        print(f"⚡ [RVC Clause-1 Skip-Index] Latency: {t_rvc_skip*1000:.1f}ms", flush=True)

        assert len(rvc_pcm_skip) > 0
        assert int(np.abs(rvc_pcm_skip).max()) > 5000

        # Verify native macOS screen capture returns valid JPEG header
        jpeg_bytes = capture_screen_jpeg(scope="display", max_edge=800, quality=70)
        assert jpeg_bytes.startswith(b"\xff\xd8\xff")
        print(f"⚡ [Screen Capture JPEG] Size: {len(jpeg_bytes)/1024:.1f} KB", flush=True)
    finally:
        ear.close()
