"""Tests for SQLite MemoryStore hydration, pinned facts, search, and clear_all."""

from selene.memory_store import MemoryStore


def test_append_and_hydrate_chronological_order(memory_store: MemoryStore):
    memory_store.append_turn("First question", "First answer")
    memory_store.append_turn("Second question", "Second answer")

    assert memory_store.unsummarized_count() == 4
    history = memory_store.hydrate_history(limit=4)
    assert [c.role for c in history] == ["user", "model", "user", "model"]
    assert history[0].parts[0].text == "First question"
    assert history[-1].parts[0].text == "Second answer"


def test_pinned_facts_case_insensitive_upsert_and_delete(memory_store: MemoryStore):
    msg = memory_store.remember_fact("Framework", "Django")
    assert "Remembered pinned fact 'Framework'" in msg

    memory_store.remember_fact("framework", "FastAPI")
    facts = memory_store.list_facts()
    assert len(facts) == 1
    assert facts[0][1] == "FastAPI"
    assert "- " in memory_store.format_facts_block()

    assert memory_store.forget_fact("FRAMEWORK") is True
    assert memory_store.forget_fact("nonexistent") is False
    assert memory_store.list_facts() == []


def test_search_messages_and_clear_all_fact_preservation(memory_store: MemoryStore):
    memory_store.append_turn("Tell me about FastAPI routing", "FastAPI uses decorators.")
    memory_store.remember_fact("exam", "Friday")

    hits = memory_store.search_messages("FastAPI")
    assert len(hits) == 2

    # Default clear wipes turns but preserves pinned facts
    memory_store.clear_all(include_facts=False)
    assert memory_store.unsummarized_count() == 0
    assert memory_store.list_facts() == [("exam", "Friday")]

    # Full clear wipes pinned facts too
    memory_store.clear_all(include_facts=True)
    assert memory_store.list_facts() == []
