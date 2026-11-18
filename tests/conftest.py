"""Shared pytest fixtures for Selene unit tests."""

from pathlib import Path

import pytest

from selene.config import SeleneConfig
from selene.memory_store import MemoryStore
from selene.timers import clear_all_timers, register_reminder_callback


@pytest.fixture
def isolated_cfg(tmp_path: Path) -> SeleneConfig:
    """Return an isolated SeleneConfig writing all files under tmp_path."""
    return SeleneConfig(
        db_path=tmp_path / "memory.db",
        notes_dir=tmp_path / "notes",
        persona_path=tmp_path / "GEMINI.md",
    )


@pytest.fixture
def memory_store(isolated_cfg: SeleneConfig):
    """Provide a fresh SQLite MemoryStore backed by a temporary DB."""
    store = MemoryStore(cfg=isolated_cfg)
    yield store
    store.close()


@pytest.fixture(autouse=True)
def clean_timers():
    """Ensure timers and reminder callbacks never leak between tests."""
    clear_all_timers()
    register_reminder_callback(None)
    yield
    clear_all_timers()
    register_reminder_callback(None)
