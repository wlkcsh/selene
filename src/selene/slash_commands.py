"""Interactive terminal slash commands for Selene."""

from selene.config import SeleneConfig, format_config_summary
from selene.memory_store import MemoryStore
from selene.timers import list_timers


async def handle_slash_command(
    raw_text: str,
    memory: MemoryStore,
    state: dict,
    ear,
    client,
    cfg: SeleneConfig,
) -> str | None:
    """Process a terminal slash command.

    Returns:
      - None if `raw_text` is not a slash command.
      - 'reset_chat' if the caller should recreate the Gemini chat session.
      - 'handled' otherwise.
    """
    stripped = raw_text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if cmd == "/help":
        print(
            "\n📖 Selene Commands:\n"
            "  /memory       — View pinned facts, rolling summary & recent turn count\n"
            "  /timers       — List active study timers\n"
            "  /config       — Inspect active model, voice, pitch & path settings\n"
            "  /mute         — Toggle quiet text-only mode (mutes voice & chimes)\n"
            "  /compact      — Compact recent turns into long-term summary now\n"
            "  /forget       — Clear chat history & summary (add 'all' to also wipe facts)\n"
            "  /help         — Show this help message\n"
            "  quit / exit   — Say goodbye and shut down\n"
        )
        return "handled"

    if cmd == "/memory":
        facts = memory.list_facts()
        summary = memory.get_summary()
        count = memory.unsummarized_count()
        print("\n🧠 Selene Memory Snapshot:")
        print(f"  • Unsummarized messages: {count}")
        if facts:
            print("  • Pinned facts:")
            for k, v in facts:
                print(f"      - {k}: {v}")
        else:
            print("  • Pinned facts: (none yet — say 'Remember that ...')")
        print(f"  • Rolling summary: {summary or '(none yet)'}\n")
        return "handled"

    if cmd == "/timers":
        print(f"\n⏰ {list_timers()}\n")
        return "handled"

    if cmd == "/config":
        print("\n⚙️  Selene Active Configuration:")
        print(format_config_summary(cfg))
        print()
        return "handled"

    if cmd == "/mute":
        state["muted"] = not state.get("muted", False)
        if ear is not None:
            ear.chimes_enabled = not state["muted"]
        status = "ON (quiet text-only mode)" if state["muted"] else "OFF (voice & chimes active)"
        print(f"\n🔇 Mute mode: {status}\n")
        return "handled"

    if cmd == "/compact":
        print("\n🧠 Compacting recent turns into long-term summary...", flush=True)
        did = await memory.maybe_compact(client, cfg.model_id, force=True)
        if did:
            print("✨ Memory compacted cleanly!\n")
        else:
            print("ℹ️  Not enough unsummarized turns to compact yet.\n")
        return "handled"

    if cmd == "/forget":
        include_facts = arg == "all"
        memory.clear_all(include_facts=include_facts)
        scope = (
            "all chat history, summary, and pinned facts"
            if include_facts
            else "chat history & summary (pinned facts kept)"
        )
        print(f"\n🧹 Cleared {scope}. Starting a fresh conversation!\n")
        return "reset_chat"

    print(f"\nℹ️  Unknown command '{cmd}'. Type /help to see available commands.\n")
    return "handled"
