"""Live web search via Gemini Google Search grounding with zero-quota DuckDuckGo/Wiki fallback."""

import re

import httpx
from google import genai
from google.genai import types

DEFAULT_SEARCH_MODEL = "gemini-3.5-flash-lite"


def _web_search_fallback(query: str) -> str:
    """Zero-quota fallback search via DuckDuckGo Instant Answer & Wikipedia summary."""
    headers = {"User-Agent": "SeleneAssistant/2.5 (macOS)"}
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers=headers,
            timeout=6.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            snippets = [
                data.get("AbstractText", ""),
                data.get("Answer", ""),
                *[
                    t.get("Text", "")
                    for t in data.get("RelatedTopics", [])[:3]
                    if isinstance(t, dict) and t.get("Text")
                ],
            ]
            joined = "\n".join(s.strip() for s in snippets if s and s.strip())
            if joined:
                return joined[:2000]
    except Exception:
        pass

    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
                "utf8": 1,
            },
            headers=headers,
            timeout=6.0,
        )
        if resp.status_code == 200:
            hits = resp.json().get("query", {}).get("search", [])
            if hits:
                lines = [
                    f"{h.get('title', '')}: {re.sub(r'<[^>]+>', '', h.get('snippet', ''))}"
                    for h in hits
                ]
                return "\n".join(lines)[:2000]
    except Exception:
        pass

    return "Web search is temporarily unavailable."


def web_search(query: str, model_id: str = DEFAULT_SEARCH_MODEL) -> str:
    """Search the live web using Google Search grounding with zero-quota fallback."""
    q = query.strip()
    if not q:
        return "Empty search query."
    try:
        client = genai.Client()
        resp = client.models.generate_content(
            model=model_id,
            contents=f"Answer concisely with verified facts for: {q}",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            ),
        )
        if resp.text and resp.text.strip():
            return resp.text.strip()
    except Exception:
        pass
    return _web_search_fallback(q)
