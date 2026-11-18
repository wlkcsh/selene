"""Tests for interactive terminal slash commands."""

from types import SimpleNamespace
from unittest.mock import patch

from selene.config import SeleneConfig
from selene.memory_store import MemoryStore
from selene.slash_commands import handle_slash_command
from selene.study_cards import StudyCardStore


async def test_non_slash_returns_none(memory_store: MemoryStore, isolated_cfg: SeleneConfig):
    res = await handle_slash_command("hello selene", memory_store, {}, None, None, isolated_cfg)
    assert res is None


async def test_help_memory_timers_config_and_unknown(
    memory_store: MemoryStore, isolated_cfg: SeleneConfig, capsys
):
    memory_store.remember_fact("stack", "FastAPI + React")
    state = {"muted": False}

    assert await handle_slash_command("/help", memory_store, state, None, None, isolated_cfg) == "handled"
    assert await handle_slash_command("/memory", memory_store, state, None, None, isolated_cfg) == "handled"
    assert await handle_slash_command("/timers", memory_store, state, None, None, isolated_cfg) == "handled"
    assert await handle_slash_command("/config", memory_store, state, None, None, isolated_cfg) == "handled"
    assert await handle_slash_command("/bogus", memory_store, state, None, None, isolated_cfg) == "handled"

    out = capsys.readouterr().out
    assert "/config" in out
    assert "FastAPI + React" in out
    assert "No active timers" in out
    assert "gemini-3.5-flash-lite" in out
    assert "Unknown command '/bogus'" in out


async def test_mute_toggles_state_and_ear_chimes(
    memory_store: MemoryStore, isolated_cfg: SeleneConfig
):
    ear = SimpleNamespace(chimes_enabled=True)
    state = {"muted": False}

    assert await handle_slash_command("/mute", memory_store, state, ear, None, isolated_cfg) == "handled"
    assert state["muted"] is True
    assert ear.chimes_enabled is False

    assert await handle_slash_command("/mute", memory_store, state, ear, None, isolated_cfg) == "handled"
    assert state["muted"] is False
    assert ear.chimes_enabled is True


async def test_forget_preserves_facts_and_forget_all_wipes_them(
    memory_store: MemoryStore, isolated_cfg: SeleneConfig
):
    memory_store.append_turn("hi", "hello")
    memory_store.remember_fact("coffee", "oat latte")
    state = {"muted": False}

    res = await handle_slash_command("/forget", memory_store, state, None, None, isolated_cfg)
    assert res == "reset_chat"
    assert memory_store.unsummarized_count() == 0
    assert memory_store.list_facts() == [("coffee", "oat latte")]

    res_all = await handle_slash_command("/forget all", memory_store, state, None, None, isolated_cfg)
    assert res_all == "reset_chat"
    assert memory_store.list_facts() == []


async def test_cards_and_screen_slash_commands(
    memory_store: MemoryStore,
    study_cards: StudyCardStore,
    isolated_cfg: SeleneConfig,
    capsys,
):
    study_cards.add_card("SQL", "What does EXPLAIN ANALYZE show?", "Execution plan & real timings.")
    state = {"muted": False}

    res = await handle_slash_command(
        "/cards", memory_store, state, None, None, isolated_cfg, study_cards=study_cards
    )
    assert res == "handled"
    out = capsys.readouterr().out
    assert "EXPLAIN ANALYZE" in out

    fake_jpeg = b"\xff\xd8\xff\xe0fakejpeg"
    with patch("selene.slash_commands.capture_screen_jpeg", return_value=fake_jpeg) as mock_cap:
        screen_res = await handle_slash_command(
            "/screen Why is this failing?",
            memory_store,
            state,
            None,
            None,
            isolated_cfg,
            study_cards=study_cards,
        )
    assert screen_res == ("screen", "Why is this failing?", fake_jpeg)
    mock_cap.assert_called_once()

    with patch("selene.slash_commands.capture_screen_jpeg", side_effect=RuntimeError("no perm")):
        err_res = await handle_slash_command(
            "/screen", memory_store, state, None, None, isolated_cfg, study_cards=study_cards
        )
    assert err_res == "handled"
    assert "Screen capture failed" in capsys.readouterr().out
