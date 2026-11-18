"""Thread-safe macOS study timer registry with banner notifications and spoken callbacks."""

import re
import subprocess
import threading
import time
from collections.abc import Callable

_TIMER_LOCK = threading.Lock()
_ACTIVE_TIMERS: dict[int, dict] = {}
_NEXT_TIMER_ID = 1
_REMINDER_CALLBACK: Callable[[str], None] | None = None


def register_reminder_callback(callback: Callable[[str], None] | None) -> None:
    """Register a thread-safe callback invoked when a study timer finishes."""
    global _REMINDER_CALLBACK
    _REMINDER_CALLBACK = callback


def _fire_reminder(timer_id: int, safe_label: str) -> None:
    with _TIMER_LOCK:
        _ACTIVE_TIMERS.pop(timer_id, None)
    script = (
        f'display notification "Time is up for: {safe_label}" '
        f'with title "Selene Reminder" sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)
    if _REMINDER_CALLBACK is not None:
        _REMINDER_CALLBACK(
            f"Time is up for {safe_label}, sweetheart! "
            "Come take a quick stretch and grab a sip of water."
        )


def set_study_timer(minutes: int, label: str = "Study Break") -> str:
    """Schedule a macOS banner + spoken Selene voice reminder (1 to 180 minutes)."""
    global _NEXT_TIMER_ID
    clamped = max(1, min(180, int(minutes)))
    safe_label = re.sub(r"[^a-zA-Z0-9 _-]", "", label).strip()[:40] or "Study Timer"

    with _TIMER_LOCK:
        tid = _NEXT_TIMER_ID
        _NEXT_TIMER_ID += 1

    timer = threading.Timer(clamped * 60.0, _fire_reminder, args=(tid, safe_label))
    timer.daemon = True
    with _TIMER_LOCK:
        _ACTIVE_TIMERS[tid] = {
            "id": tid,
            "label": safe_label,
            "due_at": time.time() + clamped * 60.0,
            "timer": timer,
        }
    timer.start()
    return f"Timer #{tid} set for {clamped} minute(s) labeled '{safe_label}'."


def list_timers() -> str:
    """List all currently active study timers with remaining time."""
    now = time.time()
    with _TIMER_LOCK:
        if not _ACTIVE_TIMERS:
            return "No active timers right now."
        lines = []
        for tid, info in sorted(_ACTIVE_TIMERS.items()):
            rem_sec = max(0, int(info["due_at"] - now))
            mins, secs = divmod(rem_sec, 60)
            lines.append(f"#{tid}: {info['label']} ({mins}m {secs}s left)")
        return "Active timers: " + "; ".join(lines)


def cancel_timer(timer_id: int) -> str:
    """Cancel an active study timer by its numeric ID."""
    with _TIMER_LOCK:
        info = _ACTIVE_TIMERS.pop(int(timer_id), None)
    if not info:
        return f"No active timer found with ID #{timer_id}."
    info["timer"].cancel()
    return f"Cancelled timer #{timer_id} ('{info['label']}')."


def clear_all_timers() -> None:
    """Cancel and clear all active timers and reset ID counter (used on shutdown/tests)."""
    global _NEXT_TIMER_ID
    with _TIMER_LOCK:
        for info in _ACTIVE_TIMERS.values():
            info["timer"].cancel()
        _ACTIVE_TIMERS.clear()
        _NEXT_TIMER_ID = 1
