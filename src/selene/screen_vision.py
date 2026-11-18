"""On-demand macOS Screen Vision using native screencapture + sips and Gemini multimodal."""

import subprocess
import tempfile
from pathlib import Path

from google import genai
from google.genai import types

from selene.config import SeleneConfig

try:
    import AppKit
    import Quartz

    HAS_MAC_WINDOW_API = True
except ImportError:
    HAS_MAC_WINDOW_API = False


def _find_frontmost_window_id() -> int | None:
    """Resolve the CGWindowID of the frontmost normal-layer macOS window."""
    if not HAS_MAC_WINDOW_API:
        return None
    try:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        pid = int(app.processIdentifier())
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        for win in windows:
            if int(win.get("kCGWindowOwnerPID", -1)) != pid:
                continue
            if int(win.get("kCGWindowLayer", -1)) != 0:
                continue
            bounds = win.get("kCGWindowBounds") or {}
            if float(bounds.get("Width", 0)) >= 80 and float(bounds.get("Height", 0)) >= 80:
                wid = win.get("kCGWindowNumber")
                if wid is not None:
                    return int(wid)
    except Exception:
        return None
    return None


def capture_screen_jpeg(
    scope: str = "front_window",
    max_edge: int = 1568,
    quality: int = 80,
) -> bytes:
    """Capture a single silent macOS screenshot, downscale to JPEG <= max_edge, and clean up /tmp."""
    norm_scope = scope.strip().lower()
    if norm_scope not in {"front_window", "display"}:
        norm_scope = "front_window"

    clamped_edge = max(512, min(2048, int(max_edge)))
    clamped_quality = max(40, min(95, int(quality)))

    with tempfile.NamedTemporaryFile(prefix="selene_screen_", suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        captured = False
        if norm_scope == "front_window":
            wid = _find_frontmost_window_id()
            if wid is not None:
                res = subprocess.run(
                    ["screencapture", "-x", "-o", "-t", "jpg", "-l", str(wid), str(tmp_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                captured = res.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0

        if not captured:
            res = subprocess.run(
                ["screencapture", "-x", "-t", "jpg", str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
                stderr = res.stderr.strip() or "Empty screenshot"
                raise RuntimeError(
                    f"macOS screen capture failed ({stderr}). Grant Screen Recording access in "
                    "System Settings -> Privacy & Security -> Screen & System Audio Recording."
                )

        subprocess.run(
            [
                "sips",
                "-Z",
                str(clamped_edge),
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(clamped_quality),
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        data = tmp_path.read_bytes()
        if not data:
            raise RuntimeError("Captured screenshot was empty.")
        return data
    finally:
        tmp_path.unlink(missing_ok=True)


def inspect_screen(
    question: str = "Describe what is currently visible on screen and help with any error or task.",
    scope: str = "front_window",
    cfg: SeleneConfig | None = None,
) -> str:
    """Capture one on-demand screenshot and analyze it with Gemini multimodal vision."""
    active_cfg = cfg or SeleneConfig()
    try:
        jpeg_bytes = capture_screen_jpeg(
            scope=scope,
            max_edge=active_cfg.screen_vision_max_edge,
            quality=active_cfg.screen_vision_jpeg_quality,
        )
    except Exception as err:
        return f"Could not inspect screen: {err}"

    q = question.strip() or "Describe what is currently visible on screen."
    prompt = (
        "Analyze this macOS screenshot accurately and concisely so a spoken voice assistant can "
        f"answer the user's request. Focus on visible code, errors, UI elements, or text.\n\n"
        f"User request: {q}"
    )
    try:
        client = genai.Client()
        resp = client.models.generate_content(
            model=active_cfg.model_id,
            contents=[
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (resp.text or "No visual summary returned.").strip()
    except Exception as err:
        return f"Vision analysis failed: {err}"
