"""Tests for Selene's immutable TOML + env configuration."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from selene.config import SeleneConfig, format_config_summary, load_config


def test_default_config_is_frozen():
    cfg = SeleneConfig()
    assert cfg.model_id == "gemini-3.5-flash-lite"
    assert cfg.kokoro_voice == "af_heart"
    assert cfg.rvc_pitch == 0
    with pytest.raises(FrozenInstanceError):
        cfg.rvc_pitch = 2  # type: ignore[misc]


def test_load_config_from_toml_and_env_precedence(tmp_path: Path, monkeypatch):
    toml_path = tmp_path / "custom.toml"
    toml_path.write_text(
        '[llm]\nmodel_id = "gemini-2.5-pro"\ntemperature = 0.5\n'
        '[voice]\nkokoro_voice = "af_bella"\nrvc_pitch = -2\n'
        '[ears]\nmin_rms_energy = 0.01\n'
        '[memory]\nwindow_size = 20\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SELENE_RVC_PITCH", "3")
    monkeypatch.setenv("SELENE_MODEL_ID", "gemini-3.5-flash")

    cfg = load_config(toml_path)
    assert cfg.model_id == "gemini-3.5-flash"  # env beats TOML
    assert cfg.rvc_pitch == 3  # env beats TOML
    assert cfg.temperature == 0.5  # from TOML
    assert cfg.kokoro_voice == "af_bella"  # from TOML
    assert cfg.min_rms_energy == 0.01  # from TOML
    assert cfg.window_size == 20  # from TOML


def test_load_config_explicit_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.toml")


def test_format_config_summary_includes_key_fields():
    summary = format_config_summary(SeleneConfig())
    assert "gemini-3.5-flash-lite" in summary
    assert "af_heart" in summary
    assert "pitch=0" in summary
