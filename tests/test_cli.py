"""Tests for Selene CLI argument parsing and event dispatch."""

import queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from selene.cli import parse_args, wait_for_event


def test_parse_args_defaults():
    args = parse_args([])
    assert not args.fast
    assert not args.no_chimes
    assert not args.daemon
    assert args.config is None


def test_parse_args_daemon_and_fast():
    args = parse_args(["--fast", "--daemon", "--no-chimes", "--config", "custom.toml"])
    assert args.fast
    assert args.daemon
    assert args.no_chimes
    assert args.config == Path("custom.toml")


@pytest.mark.asyncio
async def test_wait_for_event_ipc_command():
    ear = MagicMock()
    ear.try_get_utterance.return_value = None
    ear.global_ptt_active = True

    rem_q = queue.Queue()
    ipc_q = queue.Queue()

    # Post an IPC text command
    ipc_q.put(("text", "Hello darling"))

    kind, payload = await wait_for_event(
        ear, rem_q, ipc_q, muted=False, daemon_mode=True
    )
    assert kind == "text"
    assert payload == "Hello darling"


@pytest.mark.asyncio
async def test_wait_for_event_reminder():
    ear = MagicMock()
    ear.try_get_utterance.return_value = None
    ear.global_ptt_active = True

    rem_q = queue.Queue()
    ipc_q = queue.Queue()

    rem_q.put("Time to stretch, darling~")

    kind, payload = await wait_for_event(
        ear, rem_q, ipc_q, muted=False, daemon_mode=True
    )
    assert kind == "reminder"
    assert payload == "Time to stretch, darling~"
