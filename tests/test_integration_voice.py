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

import numpy as np
import pytest

from selene.config import load_config


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

        # Verify MLX-Whisper + post-MLX Metal RVC coexistence
        speech_16k = kokoro.synthesize_16k(
            "Selene, remember that my favorite Python framework is FastAPI."
        )
        assert speech_16k is not None
        transcript = await ear.transcribe(speech_16k)
        assert "fastapi" in transcript.lower()

        rvc_pcm = rvc.convert_pcm16k(speech_16k)
        assert len(rvc_pcm) > 0
        assert int(np.abs(rvc_pcm).max()) > 5000
    finally:
        ear.close()
