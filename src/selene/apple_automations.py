import asyncio
import concurrent.futures
import datetime
import html
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from dateutil import parser

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTOMATIONS_DIR = PROJECT_ROOT / "hud" / "Resources" / "Automations"


def parse_natural_datetime(text: str) -> datetime.datetime:
    """Parse natural language or ISO date/time strings in English or Russian into a datetime."""
    now = datetime.datetime.now()
    t = text.lower().strip()

    day_offset = 0
    if any(k in t for k in ("послезавтра", "day after tomorrow")):
        day_offset = 2
    elif any(k in t for k in ("завтра", "tomorrow")):
        day_offset = 1
    elif any(k in t for k in ("сегодня", "today")):
        day_offset = 0

    base = (now + datetime.timedelta(days=day_offset)).replace(second=0, microsecond=0)

    clean_t = t
    for word in (
        "послезавтра",
        "завтра",
        "сегодня",
        "day after tomorrow",
        "tomorrow",
        "today",
        "at",
        "в",
        "на",
    ):
        clean_t = clean_t.replace(word, " ")
    clean_t = " ".join(clean_t.split())

    if clean_t:
        try:
            parsed = parser.parse(clean_t, fuzzy=True, default=base)
            return parsed.replace(second=0, microsecond=0)
        except Exception:
            pass
    return base


def run_automation_script(app: str, action: str, args: list[str], timeout: float = 12.0) -> dict[str, Any]:
    """Fallback runner for direct osascript execution when Swift HUD IPC is unavailable."""
    js_path = AUTOMATIONS_DIR / app / f"{action}.js"
    applescript_path = AUTOMATIONS_DIR / app / f"{action}.applescript"

    if js_path.exists():
        cmd = ["osascript", "-l", "JavaScript", str(js_path), *args]
    elif applescript_path.exists():
        cmd = ["osascript", str(applescript_path), *args]
    else:
        return {"ok": False, "error": f"Script not found for {app}.{action}"}

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        stdout = res.stdout.strip()
        if res.returncode != 0:
            return {"ok": False, "error": res.stderr.strip() or f"Script failed with code {res.returncode}"}
        if not stdout:
            return {"ok": True}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"ok": True, "output": stdout}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Script execution timed out for {app}.{action}"}
    except Exception as err:
        return {"ok": False, "error": str(err)}


def dispatch_automation(
    ipc_server: Any,
    app: str,
    action: str,
    args: list[str],
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Execute an automation action via Swift host IPC, falling back to direct osascript."""
    if ipc_server is not None and getattr(ipc_server, "_clients", None):
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    rpc_res = pool.submit(
                        asyncio.run,
                        ipc_server.call_automation(
                            app=app,
                            action=action,
                            args=args,
                            timeout=timeout,
                        ),
                    ).result(timeout=timeout + 1.0)
            else:
                rpc_res = asyncio.run(
                    ipc_server.call_automation(
                        app=app,
                        action=action,
                        args=args,
                        timeout=timeout,
                    )
                )

            if rpc_res.get("ok"):
                raw_output = rpc_res.get("output", "")
                if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
                    try:
                        return json.loads(raw_output)
                    except json.JSONDecodeError:
                        pass
                return {"ok": True, "output": raw_output}
            else:
                logger.warning(
                    "IPC automation %s.%s returned error: %s. Falling back to direct script.",
                    app,
                    action,
                    rpc_res.get("error_message"),
                )
        except Exception as err:
            logger.warning("IPC automation call failed: %s. Falling back to direct script.", err)

    return run_automation_script(app, action, args, timeout=timeout)


def create_calendar_event(
    ipc_server: Any,
    title: str,
    start_time: str,
    end_time: str = "",
    calendar_name: str = "",
    notes: str = "",
    location: str = "",
) -> str:
    """Create a new event in Apple Calendar."""
    clean_title = title.strip()
    if not clean_title:
        return "Please provide an event title."

    try:
        start_dt = parse_natural_datetime(start_time)
        start_epoch_ms = int(start_dt.timestamp() * 1000)
    except Exception as err:
        return f"Could not understand start date '{start_time}': {err}"

    if end_time.strip():
        try:
            end_dt = parse_natural_datetime(end_time)
            end_epoch_ms = int(end_dt.timestamp() * 1000)
        except Exception:
            end_epoch_ms = start_epoch_ms + 3600000
    else:
        end_epoch_ms = start_epoch_ms + 3600000

    args = [
        clean_title,
        str(start_epoch_ms),
        str(end_epoch_ms),
        calendar_name.strip() or "none",
        notes.strip() or "none",
        location.strip() or "none",
    ]

    res = dispatch_automation(ipc_server, "calendar", "create_event", args, timeout=10.0)
    if not res.get("ok"):
        return f"Could not create calendar event: {res.get('error') or res.get('error_message', 'Unknown error')}"

    cal = res.get("calendar", calendar_name or "Calendar")
    date_str = start_dt.strftime("%A, %b %d at %H:%M")
    return f"Successfully scheduled '{clean_title}' in your {cal} calendar for {date_str}."


def list_calendar_events(
    ipc_server: Any,
    days_ahead: int = 7,
    calendar_name: str = "",
) -> str:
    """List upcoming events from Apple Calendar."""
    clamped_days = max(1, min(30, int(days_ahead)))
    now = datetime.datetime.now()
    start_dt = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
    end_dt = start_dt + datetime.timedelta(days=clamped_days)
    start_epoch_ms = int(start_dt.timestamp() * 1000)
    end_epoch_ms = int(end_dt.timestamp() * 1000)

    args = [str(start_epoch_ms), str(end_epoch_ms), calendar_name.strip() or "none"]

    res = dispatch_automation(ipc_server, "calendar", "list_events", args, timeout=12.0)
    if not res.get("ok"):
        return f"Could not retrieve calendar events: {res.get('error') or res.get('error_message', 'Unknown error')}"

    events = res.get("events", [])
    if not events:
        target = f"in '{calendar_name}'" if calendar_name else "on your calendar"
        return f"No upcoming events found {target} for the next {clamped_days} days."

    lines = [f"Upcoming Calendar Events (next {clamped_days} days):"]
    for ev in events:
        try:
            start_dt = parser.isoparse(ev["start"]).astimezone()
            time_str = start_dt.strftime("%a %b %d, %H:%M")
        except Exception:
            time_str = ev.get("start", "")
        cal_str = f" [{ev.get('calendar')}]" if ev.get("calendar") else ""
        loc_str = f" @ {ev.get('location')}" if ev.get("location") else ""
        lines.append(f"• {time_str}: {ev.get('summary', 'Untitled')}{cal_str}{loc_str}")

    return "\n".join(lines)


def create_reminder(
    ipc_server: Any,
    title: str,
    due_date: str = "",
    list_name: str = "",
    notes: str = "",
    priority: int = 0,
) -> str:
    """Create a new task in Apple Reminders."""
    clean_title = title.strip()
    if not clean_title:
        return "Please provide a reminder title."

    due_epoch_ms = "none"
    formatted_due = ""
    if due_date.strip():
        try:
            due_dt = parse_natural_datetime(due_date)
            due_epoch_ms = str(int(due_dt.timestamp() * 1000))
            formatted_due = due_dt.strftime(" (due %a %b %d at %H:%M)")
        except Exception:
            pass

    args = [
        clean_title,
        due_epoch_ms,
        list_name.strip() or "none",
        notes.strip() or "none",
        str(max(0, min(9, int(priority)))),
    ]

    res = dispatch_automation(ipc_server, "reminders", "create_reminder", args, timeout=12.0)
    if not res.get("ok"):
        return f"Could not create reminder: {res.get('error') or res.get('error_message', 'Unknown error')}"

    target_list = res.get("list", list_name or "Reminders")
    return f"Created reminder '{clean_title}' in your '{target_list}' list{formatted_due}."


def list_reminders(
    ipc_server: Any,
    list_name: str = "",
    include_completed: bool = False,
) -> str:
    """List tasks from Apple Reminders."""
    args = [list_name.strip() or "none", "true" if include_completed else "false"]

    res = dispatch_automation(ipc_server, "reminders", "list_reminders", args, timeout=12.0)
    if not res.get("ok"):
        return f"Could not retrieve reminders: {res.get('error') or res.get('error_message', 'Unknown error')}"

    rems = res.get("reminders", [])
    if not rems:
        target = f" in '{list_name}'" if list_name else ""
        return f"No pending reminders found{target}."

    lines = ["Pending Reminders:"]
    for r in rems[:25]:
        due_str = ""
        if r.get("dueDate"):
            try:
                d = parser.isoparse(r["dueDate"]).astimezone()
                due_str = f" (due {d.strftime('%b %d %H:%M')})"
            except Exception:
                due_str = f" (due {r.get('dueDate')})"
        list_str = f" [{r.get('list')}]" if r.get("list") else ""
        prio_str = " ❗️" if r.get("priority", 0) == 1 else ""
        lines.append(f"• {r.get('name', 'Untitled')}{list_str}{due_str}{prio_str}")

    return "\n".join(lines)


def create_apple_note(
    ipc_server: Any,
    title: str,
    body: str = "",
    folder: str = "",
) -> str:
    """Create a new note in the native Apple Notes application."""
    clean_title = title.strip()
    if not clean_title:
        return "Please provide a note title."

    # HTML-escape plain text body to prevent Notes DOM corruption
    clean_body = html.escape(body.strip()) if body.strip() else ""

    args = [
        clean_title,
        clean_body or "none",
        folder.strip() or "none",
    ]

    res = dispatch_automation(ipc_server, "notes", "create_note", args, timeout=12.0)
    if not res.get("ok"):
        return f"Could not create note: {res.get('error') or res.get('error_message', 'Unknown error')}"

    f = res.get("folder", folder or "Notes")
    return f"Created note '{clean_title}' in Apple Notes ('{f}' folder)."
