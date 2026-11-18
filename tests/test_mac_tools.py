"""Tests for macOS Jarvis tools security guardrails and tool bundle binding."""

import time
from pathlib import Path

from selene.config import SeleneConfig
from selene.mac_tools import (
    build_jarvis_tools,
    control_media,
    list_directory,
    open_url,
    read_text_file,
    save_note,
)
from selene.memory_store import MemoryStore


def test_read_text_file_blocks_outside_home_and_secrets():
    assert "outside home" in read_text_file("/etc/hosts").lower()
    assert "sensitive file" in read_text_file("~/.zshrc").lower()


def test_read_text_file_blocks_env_binary_and_truncates_safe_text():
    scratch_dir = Path.home() / "selene" / ".pytest_tmp_read_check"
    scratch_dir.mkdir(exist_ok=True)
    try:
        env_file = scratch_dir / ".env.local"
        env_file.write_text("API_KEY=nope", encoding="utf-8")
        assert "sensitive file" in read_text_file(str(env_file)).lower()

        bin_file = scratch_dir / "sample.bin"
        bin_file.write_bytes(b"\x89PNG\r\n\x00\x00binary")
        assert "binary file" in read_text_file(str(bin_file)).lower()

        long_file = scratch_dir / "notes.txt"
        long_file.write_text("A" * 500, encoding="utf-8")
        out = read_text_file(str(long_file), max_chars=250)
        assert "truncated at 250 of 500 chars" in out
    finally:
        for child in scratch_dir.glob("*"):
            child.unlink(missing_ok=True)
        scratch_dir.rmdir()


def test_open_url_and_control_media_reject_unsafe_inputs():
    assert "Rejected unsafe" in open_url("file:///etc/passwd")
    assert "Rejected unsafe" in open_url("javascript:alert(1)")
    assert "Rejected invalid media action" in control_media("rm -rf /")


def test_list_directory_sorts_newest_first(tmp_path: Path):
    old_file = tmp_path / "older.txt"
    new_file = tmp_path / "newer.txt"
    old_file.write_text("old", encoding="utf-8")
    time.sleep(0.02)
    new_file.write_text("new", encoding="utf-8")

    listing = list_directory(str(tmp_path))
    assert listing.index("newer.txt") < listing.index("older.txt")


def test_save_note_clamps_path_traversal(tmp_path: Path):
    res = save_note("../../evil.md", "hello", notes_dir=tmp_path)
    assert "Saved note to" in res
    assert (tmp_path / "evil.md").read_text(encoding="utf-8") == "hello"


def test_build_jarvis_tools_exposes_16_named_tools(
    memory_store: MemoryStore, isolated_cfg: SeleneConfig
):
    tools = build_jarvis_tools(memory_store, cfg=isolated_cfg)
    names = [fn.__name__ for fn in tools]
    assert len(names) == 16
    assert "save_note" in names
    assert "web_search" in names
    assert "remember_fact" in names
    assert "forget_fact" in names
    assert "search_memory" in names
