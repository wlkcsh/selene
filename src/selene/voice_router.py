"""Bilingual clause-level TTS router: Kokoro-82M MLX for English and Silero v5 CPU for Russian."""

import html
import re
import threading

import numpy as np
import torch

from selene.tts_engine import resample_24k_to_16k, trim_silence_16k

CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
LATIN_RE = re.compile(r"[a-zA-Z]")

# Common developer loanwords with explicit pre-vowel stress markers for Silero v5
RUSSIAN_LOANWORDS_STRESS = {
    "бэкэнд": "бэк+энд",
    "бэкенд": "бэк+енд",
    "фронтэнд": "фронт+энд",
    "фронтенд": "фронт+енд",
    "апишка": "ап+ишка",
    "коммит": "комм+ит",
    "коммита": "комм+ита",
    "дебажить": "деб+ажить",
    "деплой": "депл+ой",
    "деплоить": "депл+оить",
}


def format_russian_ssml(clause: str, rate: str = "98%") -> str:
    """Shapes Russian text into natural, mentor-paced Silero v5 SSML."""
    text = clause.strip()
    # Strip markdown formatting while preserving punctuation
    text = re.sub(r"[`_#*]", "", text)
    text = html.escape(text)

    # Turn dramatic pauses into explicit acoustic breaths
    text = re.sub(r"\.\.\.|…", '<break time="280ms"/>', text)
    text = re.sub(r"\s+[—–]\s+", ' <break time="200ms"/> ', text)

    # Disambiguate developer loanwords with explicit stress markers
    words = text.split()
    for idx, w in enumerate(words):
        clean_w = w.lower().strip(".,!?;:\"'()[]")
        if clean_w in RUSSIAN_LOANWORDS_STRESS:
            words[idx] = w.replace(clean_w, RUSSIAN_LOANWORDS_STRESS[clean_w])
    text = " ".join(words)

    return f'<speak><prosody rate="{rate}">{text}</prosody></speak>'


class BilingualTTSRouter:
    """Routes English clauses to Kokoro-82M MLX and Russian clauses to lazy-loaded Silero v5 CPU.
    
    Both frontends produce 16 kHz mono float32 PCM, which is subsequently converted by
    MetalRVCEngine to maintain Selene's exact same anime vocal timbre in both languages.
    """

    def __init__(self, kokoro_engine, russian_speaker: str = "baya"):
        self.kokoro = kokoro_engine
        self.russian_speaker = russian_speaker
        self._silero_model = None
        self._silero_lock = threading.Lock()

    def _ensure_silero(self):
        if self._silero_model is None:
            with self._silero_lock:
                if self._silero_model is None:
                    from silero import silero_tts

                    torch.set_num_threads(2)
                    model, _ = silero_tts(language="ru", speaker="v5_ru")
                    self._silero_model = model
        return self._silero_model

    def prewarm_silero(self) -> None:
        """Asynchronously pre-warm Silero in background so the first Russian turn is instant."""
        def _warmup() -> None:
            try:
                model = self._ensure_silero()
                _ = model.apply_tts(
                    ssml_text='<speak><prosody rate="slow">Привет</prosody></speak>',
                    speaker=self.russian_speaker,
                    sample_rate=24000,
                    put_accent=True,
                    put_yo=True,
                )
            except Exception:
                pass

        threading.Thread(target=_warmup, daemon=True, name="silero-prewarm").start()

    @staticmethod
    def detect_clause_lang(clause: str) -> str:
        cyr = len(CYRILLIC_RE.findall(clause))
        lat = len(LATIN_RE.findall(clause))
        if cyr == 0:
            return "en"
        return "ru" if (cyr / max(cyr + lat, 1)) >= 0.25 else "en"

    def synthesize_16k(self, clause: str, reply_policy: str = "match") -> np.ndarray | None:
        """Synthesize 16 kHz mono float32 PCM ready for MetalRVCEngine."""
        if not clause or not clause.strip():
            return None

        if reply_policy == "force_en":
            return self.kokoro.synthesize_16k(clause)

        lang = self.detect_clause_lang(clause)
        if lang == "en":
            return self.kokoro.synthesize_16k(clause)

        # Russian synthesis via Silero v5 CPU (soft kseniya speaker + SSML pacing)
        model = self._ensure_silero()
        clean = re.sub(r"[`_#*]", "", clause).strip()
        if not clean:
            return None

        try:
            ssml = format_russian_ssml(clause, rate="98%")
            audio_24k = model.apply_tts(
                ssml_text=ssml,
                speaker=self.russian_speaker,
                sample_rate=24000,
                put_accent=True,
                put_yo=True,
            ).numpy()
            return trim_silence_16k(resample_24k_to_16k(audio_24k), text=clause)
        except Exception:
            try:
                audio_24k = model.apply_tts(
                    text=clean,
                    speaker=self.russian_speaker,
                    sample_rate=24000,
                    put_accent=True,
                    put_yo=True,
                ).numpy()
                return trim_silence_16k(resample_24k_to_16k(audio_24k), text=clause)
            except Exception:
                # Fallback to Kokoro if Silero fails completely
                return self.kokoro.synthesize_16k(clause)
