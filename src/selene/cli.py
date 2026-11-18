"""Main CLI entrypoint and multi-threaded conversation loop for Selene."""

import os

# CRITICAL: Set BEFORE importing faiss / torch to prevent macOS OpenMP conflicts & noisy logs
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"

import argparse
import asyncio
import concurrent.futures
import logging
import queue
import select
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
for _noisy in (
    "transformers",
    "huggingface_hub",
    "google_genai.types",
    "torch.distributed",
    "torch.distributed.elastic.multiprocessing.redirects",
):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from selene.config import SeleneConfig, load_config  # noqa: E402
from selene.mac_tools import build_jarvis_tools  # noqa: E402
from selene.memory_store import MemoryStore  # noqa: E402
from selene.persona import ensure_api_key, load_persona  # noqa: E402
from selene.pipeline import speak_once, stream_and_speak  # noqa: E402
from selene.slash_commands import handle_slash_command  # noqa: E402
from selene.timers import register_reminder_callback  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse selene-voice command-line flags."""
    parser = argparse.ArgumentParser(
        prog="selene-voice",
        description="Voice-in / voice-out macOS anime AI mentor and personal Jarvis assistant.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip 375MB FAISS index for faster startup & conversion",
    )
    parser.add_argument(
        "--no-chimes",
        action="store_true",
        help="Disable subtle Right-Option PTT audio chimes",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to a custom TOML config file (defaults to ~/selene/config.toml)",
    )
    return parser.parse_args(argv)


async def wait_for_event(
    ear,
    reminder_queue: queue.Queue[str],
    muted: bool,
) -> tuple[str, object]:
    """Non-blocking race between Right-Option PTT voice, timer reminders, and terminal stdin."""
    mute_tag = " [MUTED]" if muted else ""
    prompt_label = (
        f"You{mute_tag} (type, /help, or hold Right Option): "
        if ear.global_ptt_active
        else f"You{mute_tag} (type, /help, or press Enter for mic): "
    )
    print(prompt_label, end="", flush=True)

    while True:
        try:
            rem = reminder_queue.get_nowait()
            return ("reminder", rem)
        except queue.Empty:
            pass

        utt = ear.try_get_utterance()
        if utt is not None:
            return ("voice", utt)

        rlist, _, _ = select.select([sys.stdin], [], [], 0.04)
        if rlist:
            line = sys.stdin.readline()
            if line == "":
                return ("eof", None)
            return ("text", line.strip())

        await asyncio.sleep(0.01)


def _create_chat(client: genai.Client, memory: MemoryStore, tools: list, cfg: SeleneConfig):
    """Build a Gemini chat session hydrated with pinned facts, rolling summary, and recent turns."""
    summary = memory.get_summary()
    facts_block = memory.format_facts_block()
    history = memory.hydrate_history()
    chat = client.aio.chats.create(
        model=cfg.model_id,
        config=types.GenerateContentConfig(
            system_instruction=load_persona(summary, facts_block, persona_path=cfg.persona_path),
            temperature=cfg.temperature,
            tools=tools,
        ),
        history=history,
    )
    return chat, len(history), len(memory.list_facts())


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    # Load config BEFORE voice_engine triggers os.chdir(model_workdir)
    cfg = load_config(args.config)
    ensure_api_key()

    # Import voice_engine FIRST so faiss loads cleanly before torch on macOS
    from selene.voice_engine import GaplessSpeaker, boot_voice_engines  # isort: skip
    from selene.ear_engine import EarEngine  # isort: skip

    use_index = not args.fast
    chimes_enabled = not args.no_chimes
    t_boot = time.time()

    kokoro, rvc = boot_voice_engines(use_index=use_index, cfg=cfg)
    speaker = GaplessSpeaker(rvc.tgt_sr)
    memory = MemoryStore(cfg=cfg)
    tools = build_jarvis_tools(memory, cfg=cfg)

    main_loop = asyncio.get_running_loop()
    active_turn: dict[str, asyncio.Task | None] = {"task": None}
    reminder_queue: queue.Queue[str] = queue.Queue()
    register_reminder_callback(reminder_queue.put)

    def handle_barge_in() -> None:
        speaker.interrupt()
        task = active_turn.get("task")
        if task is not None and not task.done():
            main_loop.call_soon_threadsafe(task.cancel)

    ear = EarEngine(on_barge_in=handle_barge_in, chimes_enabled=chimes_enabled, cfg=cfg)
    ear.start_ptt_listener()

    client = genai.Client()
    chat, n_hist, n_facts = _create_chat(client, memory, tools, cfg)
    state = {"muted": False}

    mode_str = "Fast Pure .pth" if not use_index else "Full FAISS"
    ptt_str = "Global Right Option" if ear.global_ptt_active else "Enter-Toggle Mic"
    print("\n============================================================")
    print(f"  💖 Selene Phase 2.5 — Parallel Boot in {time.time() - t_boot:.1f}s")
    print(f"  🎙️  Ears: {ptt_str} | Voice: {mode_str}")
    print(f"  🧠 Memory: {n_hist} recent turns | {n_facts} pinned facts")
    print("============================================================")
    print("• Hold Right Option (or press Enter on empty line) to speak.")
    print("• Holding Right Option while she talks interrupts immediately.")
    print("• Type /help for commands (/memory, /config, /mute, /timers, /forget).\n")

    tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kokoro")
    rvc_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="rvc-mps")
    bg_tasks: set[asyncio.Task] = set()

    warmup_task = asyncio.create_task(ear.warmup())
    bg_tasks.add(warmup_task)
    warmup_task.add_done_callback(bg_tasks.discard)

    try:
        while True:
            kind, payload = await wait_for_event(ear, reminder_queue, state["muted"])
            if kind == "eof":
                print("\nSelene: Take good care of yourself, darling~ Goodbye! 💖")
                break

            if kind == "reminder":
                msg = str(payload)
                print(f"\n⏰ Selene (Reminder): {msg}\n")
                if not state["muted"]:
                    await speak_once(msg, kokoro, rvc, speaker, tts_executor, rvc_executor)
                continue

            if kind == "voice":
                print("📝 [Transcribing...]", end="\r", flush=True)
                user_text = await ear.transcribe(payload)
                print("                    ", end="\r", flush=True)
                if not user_text:
                    continue
                print(f"\nYou (Voice): {user_text}")
            else:
                raw = str(payload)
                if not raw:
                    if not ear.global_ptt_active and ear.mic_available:
                        ear.start_capture()
                        await asyncio.to_thread(sys.stdin.readline)
                        ear.stop_capture()
                        utt = ear.try_get_utterance()
                        if utt is None:
                            continue
                        print("📝 [Transcribing...]", end="\r", flush=True)
                        user_text = await ear.transcribe(utt)
                        print("                    ", end="\r", flush=True)
                        if not user_text:
                            continue
                        print(f"You (Voice): {user_text}")
                    else:
                        continue
                else:
                    slash_res = await handle_slash_command(raw, memory, state, ear, client, cfg)
                    if slash_res == "reset_chat":
                        chat, _, _ = _create_chat(client, memory, tools, cfg)
                        continue
                    if slash_res == "handled":
                        continue
                    user_text = raw

            if user_text.lower() in {"exit", "quit", "goodbye", "bye"}:
                goodbye = (
                    "Take good care of yourself, my sweet darling. "
                    "I'll remember our chat for next time."
                )
                print(f"\nSelene: {goodbye}\n")
                if not state["muted"]:
                    await speak_once(goodbye, kokoro, rvc, speaker, tts_executor, rvc_executor)
                break

            turn_task = asyncio.create_task(
                stream_and_speak(
                    chat,
                    user_text,
                    kokoro,
                    rvc,
                    speaker,
                    tts_executor,
                    rvc_executor,
                    muted=state["muted"],
                )
            )
            active_turn["task"] = turn_task
            reply = await turn_task
            active_turn["task"] = None

            if reply:
                memory.append_turn(user_text, reply)
                compact_task = asyncio.create_task(memory.maybe_compact(client, cfg.model_id))
                bg_tasks.add(compact_task)
                compact_task.add_done_callback(bg_tasks.discard)
    finally:
        register_reminder_callback(None)
        for task in bg_tasks:
            task.cancel()
        tts_executor.shutdown(wait=False)
        rvc_executor.shutdown(wait=False)
        ear.close()
        speaker.close()
        memory.close()


def run() -> None:
    """Console script entrypoint registered as `selene-voice`."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPowering down...")


if __name__ == "__main__":
    run()
