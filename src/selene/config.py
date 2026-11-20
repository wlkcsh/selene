"""Immutable centralized configuration for Selene (defaults -> config.toml -> env overrides)."""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from selene import PROJECT_ROOT

DEFAULT_WHISPER_PROMPT = (
    "Selene, Jarvis, macOS, Apple Silicon, Python, TypeScript, React, "
    "FastAPI, Next.js, Tailwind, pnpm, uv, Git, GitHub, VS Code, Kitty, Kokoro, RVC, Spotify."
)


@dataclass(frozen=True)
class SeleneConfig:
    """Frozen runtime configuration for all Selene subsystems."""

    # LLM
    model_id: str = "gemini-3.5-flash-lite"
    temperature: float = 0.75

    # Voice (Kokoro + Metal RVC)
    rvc_enabled: bool = True
    tts_backend: str = "mlx"  # "mlx" (Apple Silicon) or "pytorch" (CPU fallback)
    kokoro_voice: str = "af_heart"
    kokoro_speed: float = 1.0
    kokoro_mlx_repo: str = "mlx-community/Kokoro-82M-bf16"
    russian_speaker: str = "baya"
    rvc_pitch: int = 0
    rvc_index_rate: float = 0.75
    rvc_protect: float = 0.5
    rvc_clause1_skip_index: bool = True
    applio_resources: str = "/Applications/Applio.app/Contents/Resources"
    model_workdir: Path = Path.home() / "selene" / "models" / "custom_voice"
    rvc_model_path: str = "model.pth"
    rvc_index_path: str = "model.index"

    # Languages & Style Directives (Git-neutral; customized in config.toml)
    russian_style_directive: str = ""
    english_style_directive: str = ""

    # Ears (CoreAudio + Quartz PTT + STT)
    sample_rate: int = 16000
    min_audio_sec: float = 0.35
    min_rms_energy: float = 0.0012
    whisper_repo: str = "mlx-community/whisper-large-v3-turbo-q4"
    whisper_language: str = "auto"
    reply_policy: str = "match"
    whisper_initial_prompt: str = DEFAULT_WHISPER_PROMPT
    chime_open_sound: str = "Tink"
    chime_open_vol: float = 0.18
    chime_close_sound: str = "Pop"
    chime_close_vol: float = 0.20
    prefer_builtin_mic: bool = True
    stt_idle_unload_sec: int = 180
    stt_preload_on_ptt: bool = True

    # Memory Optimization & Apple Silicon Eco Mode
    turn_end_reclaim: bool = True
    mlx_cache_limit_mb: int = 64
    mps_high_watermark_ratio: float = 0.18
    mps_low_watermark_ratio: float = 0.10

    # Passive Workspace Context & Screen Vision
    passive_context_enabled: bool = True
    passive_selection_max_chars: int = 1500
    screen_vision_max_edge: int = 1568
    screen_vision_jpeg_quality: int = 80

    # Native HUD IPC
    ipc_enabled: bool = True
    socket_path: Path = Path("/tmp/selene.sock")

    # Spotify / Media Automation (optional, falls back to zero-credential iTunes/Odesli)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # Memory & Paths
    window_size: int = 16
    compact_threshold: int = 24
    compact_batch: int = 12
    persona_path: Path = Path.home() / ".gemini" / "GEMINI.md"
    db_path: Path = Path.home() / ".gemini" / "selene_memory.db"
    notes_dir: Path = Path.home() / "selene" / "notes"


def _expand_path(raw: str | Path) -> Path:
    return Path(raw).expanduser()


def _apply_toml(cfg: SeleneConfig, data: dict) -> SeleneConfig:
    updates: dict = {}

    llm = data.get("llm", {})
    if "model_id" in llm:
        updates["model_id"] = str(llm["model_id"])
    if "temperature" in llm:
        updates["temperature"] = float(llm["temperature"])

    voice = data.get("voice", {})
    for key, cast in (
        ("rvc_enabled", bool),
        ("tts_backend", str),
        ("kokoro_voice", str),
        ("kokoro_speed", float),
        ("kokoro_mlx_repo", str),
        ("russian_speaker", str),
        ("rvc_pitch", int),
        ("rvc_index_rate", float),
        ("rvc_protect", float),
        ("rvc_clause1_skip_index", bool),
        ("applio_resources", str),
        ("model_workdir", _expand_path),
        ("rvc_model_path", str),
        ("rvc_index_path", str),
    ):
        if key in voice:
            updates[key] = cast(voice[key])

    ears = data.get("ears", {})
    for key, cast in (
        ("sample_rate", int),
        ("min_audio_sec", float),
        ("min_rms_energy", float),
        ("whisper_repo", str),
        ("whisper_language", str),
        ("reply_policy", str),
        ("whisper_initial_prompt", str),
        ("chime_open_sound", str),
        ("chime_open_vol", float),
        ("chime_close_sound", str),
        ("chime_close_vol", float),
        ("prefer_builtin_mic", bool),
    ):
        if key in ears:
            updates[key] = cast(ears[key])

    context = data.get("context", {})
    for key, cast in (
        ("passive_context_enabled", bool),
        ("passive_selection_max_chars", int),
        ("screen_vision_max_edge", int),
        ("screen_vision_jpeg_quality", int),
    ):
        if key in context:
            updates[key] = cast(context[key])

    ipc = data.get("ipc", {})
    if "ipc_enabled" in ipc:
        updates["ipc_enabled"] = bool(ipc["ipc_enabled"])
    if "socket_path" in ipc:
        updates["socket_path"] = _expand_path(ipc["socket_path"])

    memory = data.get("memory", {})
    for key in ("window_size", "compact_threshold", "compact_batch"):
        if key in memory:
            updates[key] = int(memory[key])

    paths = data.get("paths", {})
    for key in ("persona_path", "db_path", "notes_dir"):
        if key in paths:
            updates[key] = _expand_path(paths[key])

    spotify = data.get("spotify", {})
    if "client_id" in spotify:
        updates["spotify_client_id"] = str(spotify["client_id"]).strip()
    if "client_secret" in spotify:
        updates["spotify_client_secret"] = str(spotify["client_secret"]).strip()

    languages = data.get("languages", {})
    if isinstance(languages, dict):
        ru_cfg = languages.get("ru", {})
        if isinstance(ru_cfg, dict) and "style_directive" in ru_cfg:
            updates["russian_style_directive"] = str(ru_cfg["style_directive"]).strip()
        en_cfg = languages.get("en", {})
        if isinstance(en_cfg, dict) and "style_directive" in en_cfg:
            updates["english_style_directive"] = str(en_cfg["style_directive"]).strip()

    return replace(cfg, **updates) if updates else cfg


def _apply_env(cfg: SeleneConfig) -> SeleneConfig:
    env_map: list[tuple[str, str, type | object]] = [
        ("SELENE_MODEL_ID", "model_id", str),
        ("SELENE_TEMPERATURE", "temperature", float),
        ("SELENE_TTS_BACKEND", "tts_backend", str),
        ("SELENE_RVC_ENABLED", "rvc_enabled", lambda v: v.lower() not in {"0", "false", "no"}),
        ("SELENE_RUSSIAN_SPEAKER", "russian_speaker", str),
        ("SELENE_RUSSIAN_STYLE_DIRECTIVE", "russian_style_directive", str),
        ("SELENE_ENGLISH_STYLE_DIRECTIVE", "english_style_directive", str),
        ("SELENE_KOKORO_VOICE", "kokoro_voice", str),
        ("SELENE_KOKORO_SPEED", "kokoro_speed", float),
        ("SELENE_KOKORO_MLX_REPO", "kokoro_mlx_repo", str),
        ("SELENE_RVC_PITCH", "rvc_pitch", int),
        ("SELENE_RVC_CLAUSE1_SKIP_INDEX", "rvc_clause1_skip_index", lambda v: v.lower() not in {"0", "false", "no"}),
        ("SELENE_PASSIVE_CONTEXT", "passive_context_enabled", lambda v: v.lower() not in {"0", "false", "no"}),
        ("SELENE_IPC_ENABLED", "ipc_enabled", lambda v: v.lower() not in {"0", "false", "no"}),
        ("SELENE_SOCKET_PATH", "socket_path", _expand_path),
        ("SELENE_WHISPER_REPO", "whisper_repo", str),
        ("SELENE_WHISPER_LANGUAGE", "whisper_language", str),
        ("SELENE_REPLY_POLICY", "reply_policy", str),
        ("SELENE_PREFER_BUILTIN_MIC", "prefer_builtin_mic", lambda v: v.lower() not in {"0", "false", "no"}),
        ("SELENE_DB_PATH", "db_path", _expand_path),
        ("SELENE_PERSONA_PATH", "persona_path", _expand_path),
        ("SELENE_NOTES_DIR", "notes_dir", _expand_path),
        ("SPOTIFY_CLIENT_ID", "spotify_client_id", str),
        ("SPOTIFY_CLIENT_SECRET", "spotify_client_secret", str),
    ]
    updates: dict = {}
    for env_key, field_name, cast in env_map:
        val = os.environ.get(env_key)
        if val is not None and val.strip():
            updates[field_name] = cast(val.strip())  # type: ignore[operator]
    return replace(cfg, **updates) if updates else cfg


def load_config(config_path: Path | None = None) -> SeleneConfig:
    """Load SeleneConfig from defaults, optional TOML file, and SELENE_* env vars."""
    cfg = SeleneConfig()
    target = config_path.expanduser() if config_path is not None else PROJECT_ROOT / "config.toml"
    if target.exists() and target.is_file():
        with target.open("rb") as fh:
            data = tomllib.load(fh)
        cfg = _apply_toml(cfg, data)
    elif config_path is not None:
        raise FileNotFoundError(f"Config file not found: {target}")
    return _apply_env(cfg)


def format_config_summary(cfg: SeleneConfig) -> str:
    """Format a concise human-readable summary of active runtime configuration."""
    clause1_str = "fast pure .pth" if cfg.rvc_clause1_skip_index else "full index"
    ctx_str = "on" if cfg.passive_context_enabled else "off"
    rvc_str = (
        f"+ RVC pitch={cfg.rvc_pitch}, index_rate={cfg.rvc_index_rate} (clause1={clause1_str})"
        if cfg.rvc_enabled
        else "(RVC bypassed, pure TTS)"
    )
    return (
        f"  • LLM Model: {cfg.model_id} (temp={cfg.temperature})\n"
        f"  • Voice: Kokoro-{cfg.tts_backend.upper()} '{cfg.kokoro_voice}' (speed={cfg.kokoro_speed}) "
        f"{rvc_str} | Russian: Silero '{cfg.russian_speaker}'\n"
        f"  • Ears: {cfg.whisper_repo} (lang={cfg.whisper_language or 'auto'}, policy={cfg.reply_policy}, RMS gate={cfg.min_rms_energy}, "
        f"chimes={cfg.chime_open_sound}/{cfg.chime_close_sound})\n"
        f"  • Passive Context: {ctx_str} | Screen Vision: max {cfg.screen_vision_max_edge}px\n"
        f"  • Memory DB: {cfg.db_path} (window={cfg.window_size}, compact>{cfg.compact_threshold})\n"
        f"  • Persona: {cfg.persona_path}"
    )
