"""Tests for interactive terminal slash commands."""

from types import SimpleNamespace

from selene.config import SeleneConfig
from selene.memory_store import MemoryStore
from selene.slash_commands import handle_slash_command


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
