"""Tests for Apple native apps automations (Calendar, Reminders, Notes) and natural date parsing."""

import datetime
from unittest.mock import MagicMock, patch

from selene.apple_automations import (
    create_apple_note,
    create_calendar_event,
    create_reminder,
    list_calendar_events,
    list_reminders,
    parse_natural_datetime,
)


def test_parse_natural_datetime_relative_english_and_russian():
    now = datetime.datetime.now()

    # Tomorrow in English
    tmr = parse_natural_datetime("tomorrow at 15:00")
    expected_tmr_day = (now + datetime.timedelta(days=1)).day
    assert tmr.day == expected_tmr_day
    assert tmr.hour == 15
    assert tmr.minute == 0

    # Tomorrow in Russian
    tmr_ru = parse_natural_datetime("завтра в 18:30")
    assert tmr_ru.day == expected_tmr_day
    assert tmr_ru.hour == 18
    assert tmr_ru.minute == 30

    # Day after tomorrow in Russian
    day_after = parse_natural_datetime("послезавтра в 10:00")
    expected_after_day = (now + datetime.timedelta(days=2)).day
    assert day_after.day == expected_after_day
    assert day_after.hour == 10

    # Exact ISO date
    exact = parse_natural_datetime("2026-12-25 20:00")
    assert exact.year == 2026
    assert exact.month == 12
    assert exact.day == 25
    assert exact.hour == 20


def test_create_calendar_event_validation_and_dispatch():
    # Empty title
    assert "provide an event title" in create_calendar_event(None, "", "tomorrow at 3pm")

    # Mock dispatch
    mock_ipc = MagicMock()
    with patch("selene.apple_automations.dispatch_automation") as mock_dispatch:
        mock_dispatch.return_value = {
            "ok": True,
            "id": "EVENT-123",
            "calendar": "Home",
        }
        res = create_calendar_event(
            mock_ipc,
            title="Team Sync",
            start_time="2026-11-25 10:00",
            calendar_name="Home",
            notes="Quarterly review",
        )
        assert "Successfully scheduled 'Team Sync'" in res
        assert "Home" in res
        mock_dispatch.assert_called_once()
        args = mock_dispatch.call_args[0][3]
        assert args[0] == "Team Sync"
        assert int(args[1]) > 1_000_000_000_000  # Epoch milliseconds
        assert int(args[2]) > int(args[1])
        assert args[3] == "Home"
        assert args[4] == "Quarterly review"


def test_list_calendar_events_empty_and_populated():
    with patch("selene.apple_automations.dispatch_automation") as mock_dispatch:
        # Empty
        mock_dispatch.return_value = {"ok": True, "events": []}
        res = list_calendar_events(None, days_ahead=5)
        assert "No upcoming events found" in res

        # Populated
        mock_dispatch.return_value = {
            "ok": True,
            "events": [
                {
                    "calendar": "Work",
                    "summary": "Project Review",
                    "start": "2026-11-22T14:00:00Z",
                    "location": "Zoom",
                }
            ],
        }
        res2 = list_calendar_events(None, days_ahead=7)
        assert "Upcoming Calendar Events" in res2
        assert "Project Review" in res2
        assert "[Work]" in res2
        assert "@ Zoom" in res2


def test_create_reminder_validation_and_dispatch():
    assert "provide a reminder title" in create_reminder(None, "")

    with patch("selene.apple_automations.dispatch_automation") as mock_dispatch:
        mock_dispatch.return_value = {
            "ok": True,
            "id": "REM-456",
            "list": "Reminders",
        }
        res = create_reminder(
            None,
            title="Buy coffee beans",
            due_date="завтра в 11:00",
            priority=1,
        )
        assert "Created reminder 'Buy coffee beans'" in res
        assert "Reminders" in res
        args = mock_dispatch.call_args[0][3]
        assert args[0] == "Buy coffee beans"
        assert int(args[1]) > 1_000_000_000_000  # Due epoch ms
        assert args[4] == "1"


def test_list_reminders_formatting():
    with patch("selene.apple_automations.dispatch_automation") as mock_dispatch:
        mock_dispatch.return_value = {
            "ok": True,
            "reminders": [
                {
                    "name": "Submit paper",
                    "list": "Uni",
                    "dueDate": "2026-11-24T18:00:00Z",
                    "priority": 1,
                }
            ],
        }
        res = list_reminders(None)
        assert "Pending Reminders:" in res
        assert "Submit paper" in res
        assert "[Uni]" in res
        assert "❗️" in res


def test_create_apple_note_validation_and_dispatch():
    assert "provide a note title" in create_apple_note(None, "")

    with patch("selene.apple_automations.dispatch_automation") as mock_dispatch:
        mock_dispatch.return_value = {
            "ok": True,
            "id": "NOTE-789",
            "folder": "Notes",
        }
        res = create_apple_note(
            None,
            title="Ideas for Selene",
            body="Add voice cloning & <script>alert(1)</script>",
        )
        assert "Created note 'Ideas for Selene'" in res
        assert "Notes" in res
        args = mock_dispatch.call_args[0][3]
        assert args[0] == "Ideas for Selene"
        assert "&lt;script&gt;" in args[1]
        assert "&amp;" in args[1]
