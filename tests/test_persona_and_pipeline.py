"""Tests for persona loading, speech text cleaning, clause splitting, and chunk parsing."""

from pathlib import Path
from types import SimpleNamespace

from selene.persona import clean_for_speech, load_persona
from selene.pipeline import extract_chunk_parts, split_first_clause


def test_clean_for_speech_strips_markdown_code_and_stage_directions():
    raw = (
        "Ara ara~ *(Checks your Mac)* Here's **your** code:\n"
        "```python\nprint('secret')\n```\n"
        "All done, sweetheart! 💖"
    )
    cleaned = clean_for_speech(raw)
    assert "Checks your Mac" not in cleaned
    assert "print" not in cleaned
    assert "*" not in cleaned
    assert "Ara ara" in cleaned
    assert "All done, sweetheart!" in cleaned


def test_load_persona_injects_facts_and_summary(tmp_path: Path):
    persona_file = tmp_path / "GEMINI.md"
    persona_file.write_text("You are Selene.", encoding="utf-8")

    prompt = load_persona(
        long_term_summary="Studied FastAPI yesterday.",
        pinned_facts="- stack: FastAPI + React",
        persona_path=persona_file,
    )
    assert "You are Selene." in prompt
    assert "[PINNED LONG-TERM FACTS]:\n- stack: FastAPI + React" in prompt
    assert "[LONG-TERM MEMORY & STUDY CONTEXT]:\nStudied FastAPI yesterday." in prompt


def test_split_first_clause_skips_short_interjection_and_splits_first_full_clause():
    text = "Ara ara, hello there sweetheart, how is your evening going today?"
    clause, remainder = split_first_clause(text)
    assert clause == "Ara ara, hello there sweetheart,"
    assert remainder == "how is your evening going today?"


def test_split_first_clause_waits_for_minimum_buffer_length():
    clause, remainder = split_first_clause("Ara ara, hi there,")
    assert clause is None
    assert remainder == "Ara ara, hi there,"


def test_extract_chunk_parts_skips_thoughts_and_collects_tool_calls():
    chunk = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="internal reasoning", thought=True, function_call=None),
                        SimpleNamespace(
                            text=None,
                            thought=False,
                            function_call=SimpleNamespace(name="get_mac_status"),
                        ),
                        SimpleNamespace(
                            text="Your battery is at 88%!",
                            thought=False,
                            function_call=None,
                        ),
                    ]
                )
            )
        ]
    )
    text, tools = extract_chunk_parts(chunk)
    assert text == "Your battery is at 88%!"
    assert tools == ["get_mac_status"]
