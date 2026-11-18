"""Tests for study timers clamping, sanitization, listing, cancellation, and callbacks."""

from unittest.mock import patch

from selene.timers import (
    _fire_reminder,
    cancel_timer,
    list_timers,
    register_reminder_callback,
    set_study_timer,
)


def test_timer_clamps_duration_sanitizes_label_and_cancels():
    assert list_timers() == "No active timers right now."

    msg = set_study_timer(999, "Water; rm -rf / Break!")
    assert "180 minute(s)" in msg
    assert "Water rm -rf  Break" in msg
    assert "Active timers: #1:" in list_timers()

    msg_low = set_study_timer(0, "Short")
    assert "1 minute(s)" in msg_low

    assert "Cancelled timer #1" in cancel_timer(1)
    assert "No active timer found with ID #1" in cancel_timer(1)
    assert "Cancelled timer #2" in cancel_timer(2)
    assert list_timers() == "No active timers right now."


def test_fire_reminder_invokes_registered_callback():
    spoken: list[str] = []
    register_reminder_callback(spoken.append)

    with patch("selene.timers.subprocess.run") as mock_run:
        _fire_reminder(42, "Hydration Break")
        mock_run.assert_called_once()

    assert len(spoken) == 1
    assert "Hydration Break" in spoken[0]
