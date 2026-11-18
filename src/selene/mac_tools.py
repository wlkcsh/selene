"""Safe macOS Jarvis tools and Gemini tool-bundle builder for Selene."""

import datetime
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from selene.config import SeleneConfig
from selene.persona import clean_for_speech, ensure_api_key, load_persona
from selene.screen_vision import inspect_screen as _inspect_screen
from selene.timers import (
    cancel_timer,
    list_timers,
    register_reminder_callback,
    set_study_timer,
)
from selene.web_search import web_search as _web_search

_BLOCKED_DIR_PARTS = {".ssh", ".aws", ".gnupg", ".kube", ".docker"}
_BLOCKED_FILENAMES = {
    ".zshrc",
    ".bashrc",
    ".bash_profile",
    ".zprofile",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
}
_BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
DEFAULT_NOTES_DIR = Path.home() / "selene" / "notes"


def get_mac_status() -> str:
    """Get current MacBook battery level, charging status, and available disk space."""
    batt = subprocess.run(
        ["pmset", "-g", "batt"], capture_output=True, text=True, check=False
    ).stdout.strip()
    disk = subprocess.run(
        ["df", "-h", "/"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return f"Battery:\n{batt}\n\nDisk:\n{disk}"


def open_mac_app(app_name: str) -> str:
    """Open a macOS application by name (e.g., Safari, Spotify, Notes, Calendar, Visual Studio Code)."""
    result = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return f"Successfully opened {app_name}."
    return f"Could not open {app_name}: {result.stderr.strip()}"


def list_directory(path: str = "~") -> str:
    """List files/folders on the user's Mac sorted by most recently modified first (with timestamps)."""
    target = Path(path).expanduser()
    if not target.exists():
        return f"Folder does not exist: {target}"
    entries = []
    for p in target.iterdir():
        if p.name.startswith("."):
            continue
        try:
            mtime = p.stat().st_mtime
            ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            kind = "dir" if p.is_dir() else "file"
            entries.append((mtime, f"{p.name}{'/' if p.is_dir() else ''} [{kind}, modified {ts}]"))
        except OSError:
            continue
    entries.sort(key=lambda item: item[0], reverse=True)
    formatted = [label for _, label in entries[:30]]
    return (
        f"Contents of {target} (newest first): "
        f"{', '.join(formatted) if formatted else '(empty)'}"
    )


def read_text_file(path: str, max_chars: int = 4000) -> str:
    """Safely read a UTF-8 text/code file inside the user's home folder (blocks secrets & binaries)."""
    home = Path.home().resolve()
    try:
        target = Path(path).expanduser().resolve()
    except OSError as err:
        return f"Invalid path: {err}"

    if not target.is_relative_to(home):
        return f"Rejected path outside home directory: {path}"
    if not target.exists() or not target.is_file():
        return f"File not found: {target}"

    lower_name = target.name.lower()
    if any(part.lower() in _BLOCKED_DIR_PARTS for part in target.parts):
        return f"Rejected sensitive directory for security: {target.name}"
    if (
        lower_name in _BLOCKED_FILENAMES
        or lower_name == ".env"
        or lower_name.startswith((".env.", "id_rsa", "id_ed25519"))
        or target.suffix.lower() in _BLOCKED_SUFFIXES
        or any(tok in lower_name for tok in ("secret", "credential", "api_key"))
    ):
        return f"Rejected sensitive file for security: {target.name}"

    try:
        head = target.read_bytes()[:1024]
        if b"\x00" in head:
            return f"Rejected binary file: {target.name}"
        limit = max(200, min(6000, int(max_chars)))
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return f"Could not read file: {err}"

    if len(text) > limit:
        return f"{text[:limit]}\n\n[...truncated at {limit} of {len(text)} chars]"
    return text or "(File is empty)"


def get_frontmost_app() -> str:
    """Return the currently active macOS application name and front window title (if available)."""
    script = (
        'tell application "System Events"\n'
        "  set frontApp to first application process whose frontmost is true\n"
        "  set appName to name of frontApp\n"
        "  try\n"
        "    set winTitle to name of front window of frontApp\n"
        '    return appName & " — " & winTitle\n'
        "  on error\n"
        "    return appName\n"
        "  end try\n"
        "end tell"
    )
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if res.returncode == 0 and res.stdout.strip():
        return f"Frontmost app: {res.stdout.strip()}"
    return "Could not determine the active application."


def save_note(filename: str, content: str, notes_dir: Path = DEFAULT_NOTES_DIR) -> str:
    """Save a text or markdown note to ~/selene/notes/<filename>."""
    notes_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    out_path = notes_dir / safe_name
    out_path.write_text(content, encoding="utf-8")
    return f"Saved note to {out_path}"


def control_media(action: str, volume_percent: int = -1) -> str:
    """Control macOS audio volume or Apple Music/Spotify playback.
    action must be one of: 'play_pause', 'next', 'previous', 'mute', 'unmute', 'volume'.
    Pass volume_percent (0 to 100) when setting volume.
    """
    allowed = {"play_pause", "next", "previous", "mute", "unmute", "volume"}
    act = action.strip().lower()
    if act not in allowed:
        return f"Rejected invalid media action '{action}'. Allowed: {', '.join(sorted(allowed))}."

    if act == "volume":
        clamped = max(0, min(100, int(volume_percent)))
        script = f"set volume output volume {clamped}"
    elif act == "play_pause":
        script = (
            'if application "Spotify" is running then\n'
            '  tell application "Spotify" to playpause\n'
            'else if application "Music" is running then\n'
            '  tell application "Music" to playpause\n'
            "else\n"
            '  return "No music app running"\n'
            "end if"
        )
    else:
        scripts = {
            "mute": "set volume with output muted",
            "unmute": "set volume without output muted",
            "next": 'tell application "Music" to next track',
            "previous": 'tell application "Music" to previous track',
        }
        script = scripts[act]

    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return f"Media command failed: {res.stderr.strip()}"
    if act == "volume":
        return f"Set system volume to {max(0, min(100, int(volume_percent)))}%."
    return res.stdout.strip() or f"Executed media action: {act}."


def clipboard_study_helper(action: str = "read", text: str = "") -> str:
    """Read ('read') or write ('write') the macOS clipboard (truncated to 4,000 chars)."""
    act = action.strip().lower()
    if act == "read":
        res = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
        content = res.stdout[:4000]
        return content if content.strip() else "(Clipboard is empty)"
    if act == "write":
        subprocess.run(["pbcopy"], input=text[:4000], text=True, check=True)
        return "Copied text to your macOS clipboard."
    return "Invalid action: use 'read' or 'write'."


def open_url(url: str) -> str:
    """Open an http or https URL in the default macOS web browser."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return f"Rejected unsafe or invalid URL: {url}"
    subprocess.run(["open", url.strip()], check=True)
    return f"Opened {url.strip()} in your browser."


def web_search(query: str) -> str:
    """Search the live web using Google Search grounding with zero-quota fallback."""
    return _web_search(query)


def build_jarvis_tools(
    memory,
    cfg: SeleneConfig | None = None,
    study_cards=None,
) -> list:
    """Bind live MemoryStore, Screen Vision & config-aware tools alongside stateless macOS tools."""
    active_cfg = cfg or SeleneConfig()

    def save_note_tool(filename: str, content: str) -> str:
        """Save a text or markdown note to Selene's notes folder."""
        return save_note(filename, content, notes_dir=active_cfg.notes_dir)

    save_note_tool.__name__ = "save_note"

    def web_search_tool(query: str) -> str:
        """Search the live web using Google Search grounding with zero-quota fallback."""
        return _web_search(query, model_id=active_cfg.model_id)

    web_search_tool.__name__ = "web_search"

    def remember_fact(key: str, value: str) -> str:
        """Save a permanent pinned fact about the user (e.g., exam date, favorite stack, preference)."""
        return memory.remember_fact(key, value)

    def forget_fact(key: str) -> str:
        """Delete a permanent pinned fact by its key name."""
        removed = memory.forget_fact(key)
        return f"Forgot pinned fact '{key}'." if removed else f"No pinned fact named '{key}'."

    def search_memory(query: str) -> str:
        """Search past conversation history for a keyword or topic."""
        hits = memory.search_messages(query, limit=6)
        if not hits:
            return f"No past messages matched '{query}'."
        return "\n".join(f"[{ts}] {role}: {content[:200]}" for role, content, ts in hits)

    def inspect_screen_tool(
        question: str = "Describe what is on screen and help with any visible error or task.",
        scope: str = "front_window",
    ) -> str:
        """Capture the user's macOS screen and inspect visible code, errors, or UI with Gemini Vision."""
        return _inspect_screen(question=question, scope=scope, cfg=active_cfg)

    inspect_screen_tool.__name__ = "inspect_screen"

    tools = [
        get_mac_status,
        open_mac_app,
        list_directory,
        read_text_file,
        get_frontmost_app,
        save_note_tool,
        control_media,
        set_study_timer,
        list_timers,
        cancel_timer,
        clipboard_study_helper,
        open_url,
        web_search_tool,
        remember_fact,
        forget_fact,
        search_memory,
        inspect_screen_tool,
    ]

    if study_cards is not None:

        def log_study_card(topic: str, question: str, answer: str) -> str:
            """Save a new coding or study concept card for spaced-repetition review."""
            return study_cards.add_card(topic, question, answer)

        def list_due_study_cards() -> str:
            """List spaced-repetition coding/study cards that are due for review."""
            due = study_cards.due_cards(limit=5)
            if not due:
                return "No study cards are due right now."
            return "\n".join(
                f"#{c['id']} [{c['topic']}]: {c['question']} (Answer: {c['answer']})"
                for c in due
            )

        def review_study_card(card_id: int, rating: str) -> str:
            """Record a review rating for a study card (rating: 'again', 'hard', 'good', 'easy')."""
            return study_cards.review_card(card_id, rating)

        tools.extend([log_study_card, list_due_study_cards, review_study_card])

    return tools


__all__ = [
    "build_jarvis_tools",
    "cancel_timer",
    "clean_for_speech",
    "clipboard_study_helper",
    "control_media",
    "ensure_api_key",
    "get_frontmost_app",
    "get_mac_status",
    "list_directory",
    "list_timers",
    "load_persona",
    "open_mac_app",
    "open_url",
    "read_text_file",
    "register_reminder_callback",
    "save_note",
    "set_study_timer",
    "web_search",
]
