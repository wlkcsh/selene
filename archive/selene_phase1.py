# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "google-genai>=1.0.0",
#     "edge-tts>=7.0.0",
#     "sounddevice>=0.5.1",
#     "miniaudio>=1.61",
#     "numpy>=2.0.0",
# ]
# ///

import asyncio
import os
import queue
import re
import select
import sys
import threading
from pathlib import Path

import edge_tts
import miniaudio
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

# --- Configuration ---
MODEL_ID = "gemini-3.5-flash-lite"
PERSONA_PATH = Path.home() / ".gemini" / "GEMINI.md"

# Mature, warm, and soothing voices:
# Option 1 (Default): "en-US-AvaMultilingualNeural" -> Deep, velvety, composed & mature (Top recommendation)
# Option 2: "en-US-JennyNeural" -> Warm, gentle, affectionate mentor
# Option 3: "en-GB-SoniaNeural" -> Elegant, aristocratic, softly teasing (Lisa / Kafka vibe)
TTS_VOICE = "en-US-AvaMultilingualNeural"
TTS_RATE = "+0%"    # Calm, natural pacing
TTS_PITCH = "-1Hz"  # Slightly deeper, grounded and soothing (anti-childish)
SAMPLE_RATE = 24000

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:\n])\s+")


def ensure_api_key():
    """Ensure GEMINI_API_KEY is available, falling back to ~/.zshrc if needed."""
    if os.environ.get("GEMINI_API_KEY"):
        return
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        for line in zshrc.read_text(encoding="utf-8").splitlines():
            if "GEMINI_API_KEY=" in line and not line.strip().startswith("#"):
                match = re.search(r'GEMINI_API_KEY=["\']?([^"\']+)["\']?', line)
                if match:
                    os.environ["GEMINI_API_KEY"] = match.group(1).strip()
                    return
    raise RuntimeError(
        "GEMINI_API_KEY not found in environment or ~/.zshrc. "
        "Please export GEMINI_API_KEY='your_key'."
    )


def load_persona() -> str:
    """Load Selene's master persona instructions from ~/.gemini/GEMINI.md."""
    if PERSONA_PATH.exists():
        content = PERSONA_PATH.read_text(encoding="utf-8").strip()
        voice_addendum = (
            "\n\n[VOICE OUTPUT MODE]: Your responses are being streamed directly to speech audio. "
            "Keep phrasing natural, conversational, deeply warm, and affectionate. "
            "Avoid markdown tables, code blocks, or raw symbols unless explicitly asked."
        )
        return content + voice_addendum
    return (
        "You are Selene, a mature, doting, and playfully teasing anime mentor and Jarvis assistant. "
        "Keep responses concise, warm, and natural for spoken voice output."
    )


class AudioPlaybackEngine:
    """Thread-safe CoreAudio PCM player supporting sub-20ms barge-in."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.pcm_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.interrupt_event = threading.Event()
        self.is_speaking = threading.Event()
        self._leftover = np.empty(0, dtype=np.int16)

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=480,  # 20ms frames at 24kHz for snappy interruption
            callback=self._audio_callback,
        )
        self.stream.start()

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status):
        if self.interrupt_event.is_set():
            outdata.fill(0)
            self._leftover = np.empty(0, dtype=np.int16)
            self.is_speaking.clear()
            return

        written = 0
        while written < frames:
            if len(self._leftover) == 0:
                try:
                    self._leftover = self.pcm_queue.get_nowait()
                    self.is_speaking.set()
                except queue.Empty:
                    outdata[written:] = 0
                    if written == 0:
                        self.is_speaking.clear()
                    return

            needed = frames - written
            take = min(needed, len(self._leftover))
            outdata[written : written + take, 0] = self._leftover[:take]
            self._leftover = self._leftover[take:]
            written += take

    def enqueue_pcm(self, pcm_int16: np.ndarray):
        if not self.interrupt_event.is_set():
            self.pcm_queue.put(pcm_int16)

    def interrupt(self):
        """Immediately halt audio playback and flush pending PCM buffers."""
        self.interrupt_event.set()
        while not self.pcm_queue.empty():
            try:
                self.pcm_queue.get_nowait()
            except queue.Empty:
                break
        self._leftover = np.empty(0, dtype=np.int16)
        self.is_speaking.clear()

    def reset(self):
        self.interrupt_event.clear()

    def close(self):
        self.stream.stop()
        self.stream.close()


class SeleneAssistant:
    def __init__(self):
        ensure_api_key()
        self.client = genai.Client()
        self.persona = load_persona()
        self.audio = AudioPlaybackEngine(SAMPLE_RATE)
        self.chat = self.client.aio.chats.create(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=self.persona,
                temperature=0.7,
            ),
        )

    async def _synthesize_sentence(self, text: str):
        """Stream MP3 from Edge-TTS, decode to 24kHz PCM in memory, and enqueue."""
        clean_text = re.sub(r"[*_`#~]", "", text).strip()
        if not clean_text or self.audio.interrupt_event.is_set():
            return

        communicate = edge_tts.Communicate(
            clean_text, voice=TTS_VOICE, rate=TTS_RATE, pitch=TTS_PITCH
        )
        mp3_buffer = bytearray()

        try:
            async for chunk in communicate.stream():
                if self.audio.interrupt_event.is_set():
                    return
                if chunk["type"] == "audio":
                    mp3_buffer.extend(chunk["data"])
        except Exception:
            return

        if mp3_buffer and not self.audio.interrupt_event.is_set():
            decoded = miniaudio.decode(
                bytes(mp3_buffer),
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=SAMPLE_RATE,
            )
            pcm_array = np.frombuffer(decoded.samples, dtype=np.int16)
            self.audio.enqueue_pcm(pcm_array)

    async def _tts_worker(self, sentence_queue: asyncio.Queue[str | None]):
        while True:
            sentence = await sentence_queue.get()
            if sentence is None or self.audio.interrupt_event.is_set():
                sentence_queue.task_done()
                break
            await self._synthesize_sentence(sentence)
            sentence_queue.task_done()

    async def respond(self, user_text: str):
        self.audio.reset()
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        tts_task = asyncio.create_task(self._tts_worker(sentence_queue))

        text_buffer = ""
        print("\nSelene: ", end="", flush=True)

        try:
            response_stream = await self.chat.send_message_stream(user_text)
            async for chunk in response_stream:
                if self.audio.interrupt_event.is_set():
                    print(" [Interrupted]", flush=True)
                    break

                delta = chunk.text or ""
                print(delta, end="", flush=True)
                text_buffer += delta

                # Clause/sentence chunking for sub-second TTFA
                if len(text_buffer) >= 25:
                    parts = SENTENCE_BOUNDARY.split(text_buffer)
                    if len(parts) > 1:
                        for complete_sentence in parts[:-1]:
                            await sentence_queue.put(complete_sentence)
                        text_buffer = parts[-1]

            if text_buffer.strip() and not self.audio.interrupt_event.is_set():
                await sentence_queue.put(text_buffer.strip())

        except asyncio.CancelledError:
            pass
        finally:
            await sentence_queue.put(None)
            await tts_task
            print()

        # Wait until playback finishes or user interrupts
        while (
            not self.audio.pcm_queue.empty() or self.audio.is_speaking.is_set()
        ) and not self.audio.interrupt_event.is_set():
            await asyncio.sleep(0.04)


async def main():
    assistant = SeleneAssistant()
    print("==================================================")
    print("   💖 Selene Voice Assistant (Mature Voice)       ")
    print("==================================================")
    print(f"• Current Voice: {TTS_VOICE}")
    print("• Type your message and press Enter.")
    print("• While Selene speaks, press Enter anytime to interrupt.")
    print("• Type 'quit' or 'exit' to power down.\n")

    try:
        while True:
            loop = asyncio.get_running_loop()
            user_input = await loop.run_in_executor(None, input, "You: ")

            clean_input = user_input.strip()
            if clean_input.lower() in {"exit", "quit"}:
                print("\nSelene: Take good care of yourself, darling~ Goodbye! 💖")
                break
            if not clean_input:
                continue

            respond_task = asyncio.create_task(assistant.respond(clean_input))

            while not respond_task.done():
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    sys.stdin.readline()
                    print("\n[Barge-In] Interrupting Selene...", flush=True)
                    assistant.audio.interrupt()
                    respond_task.cancel()
                    await asyncio.gather(respond_task, return_exceptions=True)
                    break
                await asyncio.sleep(0.02)

            await asyncio.gather(respond_task, return_exceptions=True)
            print()

    finally:
        assistant.audio.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPowering down...")
