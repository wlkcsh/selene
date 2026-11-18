"""Passive <3 ms macOS active-app & selected-text context via NSWorkspace + AXUIElement."""

from dataclasses import dataclass

try:
    import AppKit
    import ApplicationServices as AS

    HAS_AX = True
except ImportError:
    HAS_AX = False

_SENSITIVE_APPS = {
    "1password",
    "passwords",
    "keychain access",
    "bitwarden",
    "keepassxc",
    "lastpass",
    "dashlane",
}
_SENSITIVE_WINDOW_TOKENS = (
    ".env",
    "secret",
    "password",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credential",
)
_SELF_TERMINAL_APPS = {
    "terminal",
    "kitty",
    "iterm2",
    "warp",
    "alacritty",
    "wezterm",
}


@dataclass(frozen=True)
class WorkspaceContext:
    """Snapshot of the active macOS application, window title, and highlighted selection."""

    app_name: str
    window_title: str = ""
    selected_text: str = ""


def is_sensitive_context(app_name: str, window_title: str = "") -> bool:
    """Return True if the active app or window title may contain secrets or passwords."""
    low_app = app_name.strip().lower()
    if any(blocked in low_app for blocked in _SENSITIVE_APPS):
        return True
    low_win = window_title.strip().lower()
    return any(tok in low_win for tok in _SENSITIVE_WINDOW_TOKENS)


def _ax_attr(element, attr: str):
    """Safely read an Accessibility attribute from an AXUIElement."""
    if not HAS_AX or element is None:
        return None
    err, val = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return val if err == 0 else None


def capture_workspace_context(max_selection_chars: int = 1500) -> WorkspaceContext | None:
    """Capture frontmost app, window title, and selected text in < 3 ms (privacy-filtered)."""
    if not HAS_AX:
        return None
    try:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        app_name = str(app.localizedName() or "").strip()
        if not app_name:
            return None

        if is_sensitive_context(app_name):
            return None

        window_title = ""
        selected_text = ""

        if AS.AXIsProcessTrusted():
            ax_app = AS.AXUIElementCreateApplication(int(app.processIdentifier()))
            focused_win = _ax_attr(ax_app, AS.kAXFocusedWindowAttribute)
            raw_title = _ax_attr(focused_win, AS.kAXTitleAttribute)
            if isinstance(raw_title, str):
                window_title = raw_title.strip()[:160]

            if is_sensitive_context(app_name, window_title):
                return None

            # Try system-wide focused element first (reaches inside Electron / Monaco editors)
            raw_sel = None
            if hasattr(AS, "AXUIElementCreateSystemWide"):
                sys_wide = AS.AXUIElementCreateSystemWide()
                focused_elem = _ax_attr(sys_wide, AS.kAXFocusedUIElementAttribute)
                if focused_elem is not None:
                    raw_sel = _ax_attr(focused_elem, AS.kAXSelectedTextAttribute)

            if raw_sel is None:
                focused_elem = _ax_attr(ax_app, AS.kAXFocusedUIElementAttribute)
                raw_sel = _ax_attr(focused_elem, AS.kAXSelectedTextAttribute)

            if raw_sel is None and focused_win is not None:
                raw_sel = _ax_attr(focused_win, AS.kAXSelectedTextAttribute)

            if isinstance(raw_sel, str) and raw_sel.strip():
                limit = max(100, min(4000, int(max_selection_chars)))
                selected_text = raw_sel.strip()[:limit]

        # Skip redundant header when user is focused on Selene's own terminal with nothing selected
        if app_name.lower() in _SELF_TERMINAL_APPS and not selected_text:
            return None

        return WorkspaceContext(
            app_name=app_name,
            window_title=window_title,
            selected_text=selected_text,
        )
    except Exception:
        return None


def format_context_prefix(ctx: WorkspaceContext | None) -> str:
    """Format a compact 1–2 line workspace context prefix for Gemini prompts."""
    if ctx is None:
        return ""
    header = f"[Active Context — App: {ctx.app_name}"
    if ctx.window_title:
        header += f" | Window: {ctx.window_title}"
    if ctx.selected_text:
        return f"{header}]\n[Selected Text]:\n{ctx.selected_text}\n[End Context]\n\n"
    return f"{header}]\n\n"
