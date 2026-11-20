"""Tests for Selene's immutable TOML + env configuration."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from selene.config import SeleneConfig, format_config_summary, load_config


def test_default_config_is_frozen():
    cfg = SeleneConfig()
    assert cfg.model_id == "gemini-3.5-flash-lite"
    assert cfg.kokoro_voice == "af_heart"
    assert cfg.tts_backend == "mlx"
    assert cfg.rvc_clause1_skip_index is True
    assert cfg.passive_context_enabled is True
    assert cfg.screen_vision_max_edge == 1568
    assert cfg.rvc_pitch == 0
    assert cfg.whisper_language == "auto"
    assert cfg.reply_policy == "match"
    with pytest.raises(FrozenInstanceError):
        cfg.rvc_pitch = 2  # type: ignore[misc]


def test_load_config_from_toml_and_env_precedence(tmp_path: Path, monkeypatch):
    toml_path = tmp_path / "custom.toml"
    toml_path.write_text(
        '[llm]\nmodel_id = "gemini-2.5-pro"\ntemperature = 0.5\n'
        '[voice]\nkokoro_voice = "af_bella"\nrvc_pitch = -2\ntts_backend = "pytorch"\n'
        'rvc_clause1_skip_index = false\n'
        '[ears]\nmin_rms_energy = 0.01\nwhisper_language = "es"\n'
        '[memory]\nwindow_size = 20\n'
        '[context]\npassive_context_enabled = false\npassive_selection_max_chars = 900\n'
        'screen_vision_max_edge = 1280\nscreen_vision_jpeg_quality = 75\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SELENE_RVC_PITCH", "3")
    monkeypatch.setenv("SELENE_MODEL_ID", "gemini-3.5-flash")
    monkeypatch.setenv("SELENE_TTS_BACKEND", "mlx")
    monkeypatch.setenv("SELENE_WHISPER_LANGUAGE", "fr")
    monkeypatch.setenv("SELENE_REPLY_POLICY", "force_en")

    cfg = load_config(toml_path)
    assert cfg.model_id == "gemini-3.5-flash"  # env beats TOML
    assert cfg.rvc_pitch == 3  # env beats TOML
    assert cfg.tts_backend == "mlx"  # env beats TOML
    assert cfg.whisper_language == "fr"  # env beats TOML
    assert cfg.reply_policy == "force_en"  # env beats default
    assert cfg.rvc_clause1_skip_index is False  # from TOML
    assert cfg.temperature == 0.5  # from TOML
    assert cfg.kokoro_voice == "af_bella"  # from TOML
    assert cfg.min_rms_energy == 0.01  # from TOML
    assert cfg.window_size == 20  # from TOML
    assert cfg.passive_context_enabled is False  # from TOML
    assert cfg.passive_selection_max_chars == 900  # from TOML
    assert cfg.screen_vision_max_edge == 1280  # from TOML
    assert cfg.screen_vision_jpeg_quality == 75  # from TOML


def test_load_config_explicit_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.toml")


def test_format_config_summary_includes_key_fields():
    summary = format_config_summary(SeleneConfig())
    assert "gemini-3.5-flash-lite" in summary
    assert "af_heart" in summary
    assert "pitch=0" in summary
    assert "lang=auto" in summary
    assert "policy=match" in summary


def test_config_decoupling_fields(tmp_path: Path, monkeypatch):
    toml_path = tmp_path / "decoupled.toml"
    toml_path.write_text(
        '[voice]\nrvc_enabled = false\nrussian_speaker = "kseniya"\n'
        '[languages.ru]\nstyle_directive = "friendly tutor"\n'
        '[languages.en]\nstyle_directive = "clear and concise"\n',
        encoding="utf-8",
    )
    cfg = load_config(toml_path)
    assert cfg.rvc_enabled is False
    assert cfg.russian_speaker == "kseniya"
    assert cfg.russian_style_directive == "friendly tutor"
    assert cfg.english_style_directive == "clear and concise"

    # Environment variables override
    monkeypatch.setenv("SELENE_RVC_ENABLED", "1")
    monkeypatch.setenv("SELENE_RUSSIAN_SPEAKER", "baya")
    monkeypatch.setenv("SELENE_RUSSIAN_STYLE_DIRECTIVE", "override tone")
    cfg2 = load_config(toml_path)
    assert cfg2.rvc_enabled is True
    assert cfg2.russian_speaker == "baya"
    assert cfg2.russian_style_directive == "override tone"
