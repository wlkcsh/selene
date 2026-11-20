"""Unit tests for BilingualTTSRouter clause detection and synthesis."""

from unittest.mock import MagicMock

import numpy as np

from selene.voice_router import BilingualTTSRouter


def test_clause_language_detection():
    mock_kokoro = MagicMock()
    router = BilingualTTSRouter(mock_kokoro)

    # Pure English
    assert router.detect_clause_lang("Hello darling, how is your day?") == "en"
    assert router.detect_clause_lang("Let's build a native Swift 6 HUD.") == "en"

    # Pure Russian
    assert router.detect_clause_lang("Привет, как твои дела?") == "ru"
    assert router.detect_clause_lang("Открой терминал и проверь статус батареи.") == "ru"

    # Mixed with Russian dominant
    assert router.detect_clause_lang("Мы используем FastAPI и React.") == "ru"


def test_force_en_policy_always_routes_to_kokoro():
    mock_kokoro = MagicMock()
    mock_kokoro.synthesize_16k.return_value = np.zeros(16000, dtype=np.float32)
    router = BilingualTTSRouter(mock_kokoro)

    res = router.synthesize_16k("Привет, Селена!", reply_policy="force_en")
    assert res is not None
    mock_kokoro.synthesize_16k.assert_called_once_with("Привет, Селена!")


def test_format_russian_ssml():
    from selene.voice_router import format_russian_ssml

    raw = "Привет, дорогой... Как твой бэкенд — всё работает?"
    ssml = format_russian_ssml(raw, rate="95%")

    assert ssml.startswith('<speak><prosody rate="95%">')
    assert ssml.endswith('</prosody></speak>')
    assert '<break time="280ms"/>' in ssml  # from "..."
    assert '<break time="200ms"/>' in ssml  # from " — "
    assert "бэк+енд" in ssml  # loanword stress disambiguation


def test_rvc_profiles_and_donor_conditioning():
    from selene.voice_engine import RVC_PROFILES, condition_donor_16k

    # Verification of Neon-recommended bilingual profiles
    assert RVC_PROFILES["en"].index_rate == 0.65
    assert RVC_PROFILES["en"].protect == 0.33

    assert RVC_PROFILES["ru"].index_rate == 0.0  # English index corruption eliminated
    assert RVC_PROFILES["ru"].protect == 0.25  # Voiceless consonant protection active (<0.5)
    assert RVC_PROFILES["ru"].pitch_offset == -3  # Calibrated to Kokoro 193Hz from baya 233.8Hz
    assert RVC_PROFILES["ru"].rms_mix_rate == 0.32

    # Conditioning tests: 80Hz HPF, active RMS normalization, tanh limiter, and 120ms padding
    sample_rate = 16000
    donor = np.sin(2 * np.pi * 220 * np.linspace(0, 1.0, sample_rate, dtype=np.float32)) * 0.5
    padded, pad_len = condition_donor_16k(donor, pad_ms=120)

    expected_pad = int(sample_rate * 0.12)
    assert pad_len == expected_pad
    assert len(padded) == len(donor) + 2 * expected_pad
    # Soft limiter guarantees maximum amplitude is bounded within [-0.85, 0.85]
    assert np.abs(padded).max() <= 0.86
