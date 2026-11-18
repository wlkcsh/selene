"""Selene persona loading, API key resolution, and spoken-text sanitization."""

import os
import re
from pathlib import Path

DEFAULT_PERSONA_PATH = Path.home() / ".gemini" / "GEMINI.md"


def ensure_api_key() -> None:
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
    raise RuntimeError("GEMINI_API_KEY not found in environment or ~/.zshrc.")


def load_persona(
    long_term_summary: str = "",
    pinned_facts: str = "",
    persona_path: Path = DEFAULT_PERSONA_PATH,
) -> str:
    """Load Selene's master persona instructions plus pinned facts and SQLite rolling memory."""
    if persona_path.exists():
        base = persona_path.read_text(encoding="utf-8").strip()
    else:
        base = (
            "You are Selene, a mature, doting, and playfully teasing anime mentor "
            "and personal Jarvis assistant."
        )

    voice_rules = (
        "\n\n[SPOKEN VOICE MODE]: Your replies are streamed directly into your spoken voice. "
        "Keep answers warm, affectionate, natural, and conversational "
        "(2 to 4 concise sentences unless teaching a deeper topic). "
        "Avoid raw markdown symbols, asterisks, emojis, code fences, bullet lists, "
        "or narrating tool calls and stage directions like *(Calls ...)* "
        "so your voice flows naturally."
    )
    prompt = base + voice_rules
    if pinned_facts.strip():
        prompt += f"\n\n[PINNED LONG-TERM FACTS]:\n{pinned_facts.strip()}"
    if long_term_summary.strip():
        prompt += f"\n\n[LONG-TERM MEMORY & STUDY CONTEXT]:\n{long_term_summary.strip()}"
    return prompt


def clean_for_speech(text: str) -> str:
    """Strip markdown formatting, stage directions, and non-spoken symbols so TTS reads naturally."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\*?\([^)]*\)\*?", " ", text)
    text = re.sub(r"[*_`#>~]", "", text)
    text = re.sub(r"[^\w\s.,!?;:'\"-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
