"""Unit tests verifying complete persona decoupling and neutral engine defaults."""

import numpy as np

from selene import PROJECT_ROOT
from selene.config import DEFAULT_WHISPER_PROMPT, SeleneConfig, load_config
from selene.voice_engine import PassthroughRVCEngine, boot_voice_engines


def test_default_config_has_no_personal_catchphrases():
    cfg = SeleneConfig()
    assert "Ara ara" not in cfg.whisper_initial_prompt
    assert "Ara ara" not in DEFAULT_WHISPER_PROMPT
    assert cfg.russian_style_directive == ""
    assert cfg.english_style_directive == ""


def test_example_toml_is_neutral_and_rvc_disabled():
    example_path = PROJECT_ROOT / "config.example.toml"
    assert example_path.exists()
    content = example_path.read_text(encoding="utf-8")
    assert "Ara ara" not in content
    assert "милый" not in content
    assert "умничка" not in content
    assert "rvc_enabled = false" in content

    cfg = load_config(example_path)
    assert cfg.rvc_enabled is False
    assert cfg.russian_style_directive == ""


def test_passthrough_rvc_engine_converts_cleanly():
    engine = PassthroughRVCEngine()
    assert engine.tgt_sr == 16000
    assert engine.use_index is False

    empty = engine.convert_pcm16k(np.empty(0, dtype=np.float32))
    assert len(empty) == 0

    test_audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    converted = engine.convert_pcm16k(test_audio)
    assert converted.dtype == np.int16
    assert len(converted) == len(test_audio)
    assert converted[3] == 32767
    assert converted[4] == -32767


def test_boot_voice_engines_fallback_to_passthrough_when_rvc_disabled(monkeypatch):
    cfg = SeleneConfig(rvc_enabled=False)
    kokoro, rvc = boot_voice_engines(use_index=False, cfg=cfg)
    assert isinstance(rvc, PassthroughRVCEngine)
    assert rvc.tgt_sr == 16000


def test_prompt_directive_neutral_vs_styled():
    # 1. Neutral configuration (public Git default)
    neutral_cfg = SeleneConfig(russian_style_directive="")
    detected_lang = "ru"
    lang_mode = "auto"
    reply_policy = "match"

    target_lang_name = "Russian" if detected_lang == "ru" and reply_policy == "match" else "English"
    style = neutral_cfg.russian_style_directive.strip()

    directive_parts = [
        f"language_mode={lang_mode}",
        f"stt_detected={detected_lang}",
        f"reply_policy={reply_policy}",
        f"-> Respond naturally and idiomatically in {target_lang_name} for spoken audio.",
    ]
    if style:
        directive_parts.append(f"Style guidance: {style}")
    neutral_directive = f"[RUNTIME_DIRECTIVE: {' | '.join(directive_parts)}]"

    assert "Style guidance:" not in neutral_directive
    assert "Respond naturally and idiomatically in Russian for spoken audio." in neutral_directive

    # 2. User configured custom style (local config.toml)
    styled_cfg = SeleneConfig(russian_style_directive="friendly mentor tone")
    style2 = styled_cfg.russian_style_directive.strip()
    directive_parts2 = [
        f"language_mode={lang_mode}",
        f"stt_detected={detected_lang}",
        f"reply_policy={reply_policy}",
        f"-> Respond naturally and idiomatically in {target_lang_name} for spoken audio.",
    ]
    if style2:
        directive_parts2.append(f"Style guidance: {style2}")
    styled_directive = f"[RUNTIME_DIRECTIVE: {' | '.join(directive_parts2)}]"

    assert "Style guidance: friendly mentor tone" in styled_directive
