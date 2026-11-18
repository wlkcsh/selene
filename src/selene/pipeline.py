"""Streaming LLM -> Kokoro TTS -> Metal RVC -> CoreAudio pipeline & clause splitter."""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
from typing import TYPE_CHECKING

from selene.persona import clean_for_speech

if TYPE_CHECKING:
    from selene.voice_engine import GaplessSpeaker, KokoroTTSEngine, MetalRVCEngine

SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")
CLAUSE_SPLIT = re.compile(r"(?<=[,;:\u2014])\s+")


def extract_chunk_parts(chunk) -> tuple[str, list[str]]:
    """Safely extract spoken text and tool-call names without triggering chunk.text warnings."""
    texts: list[str] = []
    tool_names: list[str] = []
    for cand in getattr(chunk, "candidates", None) or []:
        parts = getattr(getattr(cand, "content", None), "parts", None) or []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                tool_names.append(str(fc.name))
            part_text = getattr(part, "text", None)
            if part_text and not getattr(part, "thought", False):
                texts.append(part_text)
    return "".join(texts), tool_names


def split_first_clause(text_buffer: str) -> tuple[str | None, str]:
    """Split an early opening clause (>= 20 chars) once buffer >= 35 chars for faster speech start."""
    if len(text_buffer) < 35:
        return None, text_buffer
    for match in CLAUSE_SPLIT.finditer(text_buffer):
        if match.start() >= 20:
            return text_buffer[: match.start()].strip(), text_buffer[match.end() :]
    return None, text_buffer


async def speak_once(
    text: str,
    kokoro: KokoroTTSEngine,
    rvc: MetalRVCEngine,
    speaker: GaplessSpeaker,
    tts_executor: concurrent.futures.ThreadPoolExecutor,
    rvc_executor: concurrent.futures.ThreadPoolExecutor,
) -> None:
    """Synthesize and play a single short utterance (used for reminders & goodbyes)."""
    cleaned = clean_for_speech(text)
    if not cleaned:
        return
    loop = asyncio.get_running_loop()
    pcm_16k = await loop.run_in_executor(tts_executor, kokoro.synthesize_16k, cleaned)
    if pcm_16k is None:
        return
    pcm_48k = await loop.run_in_executor(rvc_executor, rvc.convert_pcm16k, pcm_16k)
    speaker.reset()
    speaker.play_chunk(pcm_48k)
    while (
        not speaker.pcm_queue.empty() or speaker.is_speaking.is_set()
    ) and not speaker.interrupt_event.is_set():
        await asyncio.sleep(0.04)


async def stream_and_speak(
    chat,
    user_text: str,
    kokoro: KokoroTTSEngine,
    rvc: MetalRVCEngine,
    speaker: GaplessSpeaker,
    tts_executor: concurrent.futures.ThreadPoolExecutor,
    rvc_executor: concurrent.futures.ThreadPoolExecutor,
    muted: bool = False,
) -> str:
    """Two-stage concurrent pipeline with first-clause fast-start: Gemini -> Kokoro -> RVC -> Speakers."""
    speaker.reset()
    sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
    rvc_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    async def tts_worker() -> None:
        while True:
            sent = await sentence_queue.get()
            if sent is None or speaker.interrupt_event.is_set():
                sentence_queue.task_done()
                await rvc_queue.put(None)
                break
            try:
                cleaned = clean_for_speech(sent)
                if cleaned:
                    pcm_16k = await loop.run_in_executor(
                        tts_executor, kokoro.synthesize_16k, cleaned
                    )
                    if pcm_16k is not None and not speaker.interrupt_event.is_set():
                        await rvc_queue.put(pcm_16k)
            except Exception as err:
                print(f"\n[TTS warning: {err}]", flush=True)
            sentence_queue.task_done()

    async def rvc_worker() -> None:
        while True:
            pcm_16k = await rvc_queue.get()
            if pcm_16k is None or speaker.interrupt_event.is_set():
                rvc_queue.task_done()
                break
            try:
                pcm_48k = await loop.run_in_executor(rvc_executor, rvc.convert_pcm16k, pcm_16k)
                if pcm_48k is not None and not speaker.interrupt_event.is_set():
                    speaker.play_chunk(pcm_48k)
            except Exception as err:
                print(f"\n[RVC warning: {err}]", flush=True)
            rvc_queue.task_done()

    tts_task = None if muted else asyncio.create_task(tts_worker())
    rvc_task = None if muted else asyncio.create_task(rvc_worker())

    text_buffer = ""
    full_reply: list[str] = []
    printed_header = False
    sent_first_chunk = False

    try:
        response_stream = await chat.send_message_stream(user_text)
        async for chunk in response_stream:
            if speaker.interrupt_event.is_set():
                print(" [Interrupted]", flush=True)
                break
            delta, tool_names = extract_chunk_parts(chunk)
            for name in tool_names:
                print(f"\n🛠️  [Checking via {name}...]", flush=True)
            if not delta:
                continue
            if not printed_header:
                print("\nSelene: ", end="", flush=True)
                printed_header = True
            print(delta, end="", flush=True)
            text_buffer += delta
            full_reply.append(delta)

            if not muted:
                if not sent_first_chunk:
                    first_clause, remainder = split_first_clause(text_buffer)
                    if first_clause:
                        await sentence_queue.put(first_clause)
                        text_buffer = remainder
                        sent_first_chunk = True
                if len(text_buffer) >= 20:
                    parts = SENTENCE_SPLIT.split(text_buffer)
                    if len(parts) > 1:
                        for complete_sentence in parts[:-1]:
                            await sentence_queue.put(complete_sentence)
                            sent_first_chunk = True
                        text_buffer = parts[-1]

        if not muted and text_buffer.strip() and not speaker.interrupt_event.is_set():
            await sentence_queue.put(text_buffer.strip())

        print("\n")
        if not muted and tts_task and rvc_task:
            await sentence_queue.put(None)
            await asyncio.gather(tts_task, rvc_task)
            while (
                not speaker.pcm_queue.empty() or speaker.is_speaking.is_set()
            ) and not speaker.interrupt_event.is_set():
                await asyncio.sleep(0.04)

    except (KeyboardInterrupt, asyncio.CancelledError):
        speaker.interrupt()
        if tts_task and rvc_task:
            tts_task.cancel()
            rvc_task.cancel()
            await asyncio.gather(tts_task, rvc_task, return_exceptions=True)
        print("\n[Interrupted]\n")
    except Exception as err:
        speaker.interrupt()
        if tts_task and rvc_task:
            tts_task.cancel()
            rvc_task.cancel()
            await asyncio.gather(tts_task, rvc_task, return_exceptions=True)
        print(f"\n⚠️ Error: {err}\n")

    return "".join(full_reply).strip()
