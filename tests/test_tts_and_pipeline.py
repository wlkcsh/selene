"""Tests for polyphase resampling, TTS engine fallback, and pipeline index skipping."""

import concurrent.futures
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from selene.config import SeleneConfig
from selene.pipeline import stream_and_speak
from selene.tts_engine import create_tts_engine, resample_24k_to_16k


def test_resample_24k_to_16k_exact_lengths():
    empty = np.zeros(0, dtype=np.float32)
    assert resample_24k_to_16k(empty).size == 0

    one_sec_24k = np.ones(24000, dtype=np.float32)
    res_16k = resample_24k_to_16k(one_sec_24k)
    assert res_16k.size == 16000
    assert res_16k.dtype == np.float32


def test_create_tts_engine_mlx_fallback_to_pytorch(isolated_cfg: SeleneConfig):
    # When mlx raises, smoothly falls back to KokoroTTSEngine
    mock_pytorch_tts = MagicMock()
    with patch(
        "selene.tts_engine.KokoroMLXEngine", side_effect=RuntimeError("MLX unavailable")
    ), patch("selene.tts_engine.KokoroTTSEngine", return_value=mock_pytorch_tts):
        engine = create_tts_engine(isolated_cfg)
        assert engine is mock_pytorch_tts


async def test_stream_and_speak_clause1_skips_index():
    chat = SimpleNamespace(
        send_message_stream=AsyncMock(
            return_value=async_iter([
                SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                parts=[
                                    SimpleNamespace(
                                        text="Ara ara, good evening darling! How was your day today?",
                                        thought=False,
                                        function_call=None,
                                    )
                                ]
                            )
                        )
                    ]
                )
            ])
        )
    )

    kokoro = MagicMock()
    kokoro.synthesize_16k.return_value = np.zeros(1600, dtype=np.float32)

    converted_calls = []

    def mock_convert(audio, *, skip_index=False):
        converted_calls.append(skip_index)
        return np.zeros(1600, dtype=np.int16)

    rvc = MagicMock()
    rvc.convert_pcm16k.side_effect = mock_convert

    speaker = MagicMock()
    speaker.interrupt_event.is_set.return_value = False
    speaker.pcm_queue.empty.return_value = True
    speaker.is_speaking.is_set.return_value = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as tts_exec, concurrent.futures.ThreadPoolExecutor(
        max_workers=1
    ) as rvc_exec:
        reply = await stream_and_speak(
            chat,
            "Hello",
            kokoro,
            rvc,
            speaker,
            tts_exec,
            rvc_exec,
            skip_first_index=True,
        )

    assert "Ara ara" in reply
    # At least two chunks produced (Clause 1 + remainder)
    assert len(converted_calls) >= 2
    # Clause 1 must have skip_index=True
    assert converted_calls[0] is True
    # Clause 2+ must have skip_index=False
    assert converted_calls[1] is False


async def test_stream_and_speak_with_image_bytes():
    mock_stream = AsyncMock(
        return_value=async_iter([
            SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[
                                SimpleNamespace(
                                    text="I see a terminal with a green test suite, darling!",
                                    thought=False,
                                    function_call=None,
                                )
                            ]
                        )
                    )
                ]
            )
        ])
    )
    chat = SimpleNamespace(send_message_stream=mock_stream)

    kokoro = MagicMock()
    kokoro.synthesize_16k.return_value = None
    rvc = MagicMock()
    speaker = MagicMock()
    speaker.interrupt_event.is_set.return_value = False
    speaker.pcm_queue.empty.return_value = True
    speaker.is_speaking.is_set.return_value = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as tts_exec, concurrent.futures.ThreadPoolExecutor(
        max_workers=1
    ) as rvc_exec:
        reply = await stream_and_speak(
            chat,
            "Look at this screenshot",
            kokoro,
            rvc,
            speaker,
            tts_exec,
            rvc_exec,
            image_bytes=b"\xff\xd8\xfffake",
        )

    assert "green test suite" in reply
    args, _ = mock_stream.call_args
    # First argument must be a list of [Part, text]
    assert isinstance(args[0], list)
    assert len(args[0]) == 2
    assert args[0][1] == "Look at this screenshot"


async def async_iter(items):
    for item in items:
        yield item
