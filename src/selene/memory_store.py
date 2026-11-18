"""Persistent SQLite conversation memory with sliding window, rolling compaction & pinned facts."""

import sqlite3
import threading
from pathlib import Path

from google import genai
from google.genai import types

from selene.config import SeleneConfig

DEFAULT_DB_PATH = Path.home() / ".gemini" / "selene_memory.db"


class MemoryStore:
    """Stores Selene's conversation turns, rolling summary, and permanent pinned facts."""

    def __init__(
        self,
        db_path: Path | None = None,
        cfg: SeleneConfig | None = None,
    ):
        active_cfg = cfg or SeleneConfig()
        resolved_path = db_path if db_path is not None else active_cfg.db_path
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = resolved_path
        self.window_size = active_cfg.window_size
        self.compact_threshold = active_cfg.compact_threshold
        self.compact_batch = active_cfg.compact_batch
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(resolved_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL CHECK(role IN ('user', 'model')),
                    content TEXT NOT NULL,
                    summarized INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS memory_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def append_turn(self, user_text: str, model_text: str) -> None:
        """Persist a completed user + model turn atomically."""
        u = user_text.strip()
        m = model_text.strip()
        if not u or not m:
            return
        with self._lock, self.conn:
            self.conn.executemany(
                "INSERT INTO messages (role, content) VALUES (?, ?)",
                [("user", u), ("model", m)],
            )

    def get_summary(self) -> str:
        """Return the current rolling long-term summary (empty string if none yet)."""
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM memory_state WHERE key = 'rolling_summary'"
            ).fetchone()
            return str(row["value"]) if row else ""

    def hydrate_history(self, limit: int | None = None) -> list[types.Content]:
        """Load the most recent unsummarized turns in chronological order for Gemini chat."""
        eff_limit = self.window_size if limit is None else limit
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT role, content FROM messages
                WHERE summarized = 0
                ORDER BY id DESC LIMIT ?
                """,
                (eff_limit,),
            ).fetchall()

        return [
            types.Content(
                role=row["role"],
                parts=[types.Part.from_text(text=row["content"])],
            )
            for row in reversed(rows)
        ]

    def unsummarized_count(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE summarized = 0"
            ).fetchone()
            return int(row["cnt"]) if row else 0

    # --- Pinned Long-Term Facts (immune to rolling compaction) ---

    def remember_fact(self, key: str, value: str) -> str:
        """Upsert a permanent pinned fact by case-insensitive key."""
        clean_key = key.strip()[:80]
        clean_val = value.strip()[:300]
        if not clean_key or not clean_val:
            return "Both a fact key and value are required."
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO facts (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (clean_key, clean_val),
            )
        return f"Remembered pinned fact '{clean_key}': {clean_val}"

    def forget_fact(self, key: str) -> bool:
        """Delete a pinned fact by case-insensitive key. Returns True if removed."""
        clean_key = key.strip()
        if not clean_key:
            return False
        with self._lock, self.conn:
            cur = self.conn.execute("DELETE FROM facts WHERE key = ?", (clean_key,))
            return cur.rowcount > 0

    def list_facts(self) -> list[tuple[str, str]]:
        """Return all pinned facts sorted alphabetically by key."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT key, value FROM facts ORDER BY key COLLATE NOCASE ASC"
            ).fetchall()
            return [(str(r["key"]), str(r["value"])) for r in rows]

    def format_facts_block(self) -> str:
        """Format pinned facts as bullet lines for system prompt injection."""
        facts = self.list_facts()
        if not facts:
            return ""
        return "\n".join(f"- {k}: {v}" for k, v in facts)

    def search_messages(self, query: str, limit: int = 8) -> list[tuple[str, str, str]]:
        """Search past conversation history by keyword (newest matches first)."""
        q = query.strip()
        if not q:
            return []
        clamped = max(1, min(20, int(limit)))
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE content LIKE ?
                ORDER BY id DESC LIMIT ?
                """,
                (f"%{q}%", clamped),
            ).fetchall()
            return [(str(r["role"]), str(r["content"]), str(r["created_at"])) for r in rows]

    def clear_all(self, include_facts: bool = False) -> None:
        """Clear recent messages and rolling summary (and optionally pinned facts)."""
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM messages")
            self.conn.execute("DELETE FROM memory_state WHERE key = 'rolling_summary'")
            if include_facts:
                self.conn.execute("DELETE FROM facts")

    async def maybe_compact(
        self, client: genai.Client, model_id: str, force: bool = False
    ) -> bool:
        """Fold oldest unsummarized turns into rolling_summary once threshold is exceeded."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, role, content FROM messages WHERE summarized = 0 ORDER BY id ASC"
            ).fetchall()

        if not force and len(rows) <= self.compact_threshold:
            return False
        if force and len(rows) < 2:
            return False

        batch_size = min(self.compact_batch, len(rows)) if not force else len(rows)
        to_compact = rows[:batch_size]
        transcript = "\n".join(f"{r['role'].upper()}: {r['content']}" for r in to_compact)
        existing_summary = self.get_summary()

        prompt = (
            "Update Selene's concise long-term memory notes (max 220 words) by merging the "
            "existing summary with the new conversation turns. Preserve the user's preferences, "
            "study/coding topics covered, and ongoing tasks.\n\n"
            f"EXISTING SUMMARY:\n{existing_summary or 'None'}\n\n"
            f"NEW TURNS:\n{transcript}"
        )

        resp = await client.aio.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        new_summary = (resp.text or "").strip()
        if not new_summary:
            return False

        ids = [(r["id"],) for r in to_compact]
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO memory_state (key, value, updated_at)
                VALUES ('rolling_summary', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (new_summary,),
            )
            self.conn.executemany("UPDATE messages SET summarized = 1 WHERE id = ?", ids)
        return True

    def close(self) -> None:
        with self._lock:
            self.conn.close()
