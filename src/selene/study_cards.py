"""SQLite SM-2 spaced-repetition coding & study cards stored alongside Selene's memory."""

import datetime
import sqlite3
import threading
from pathlib import Path

from selene.config import SeleneConfig

RATING_TO_QUALITY = {
    "again": 1,
    "hard": 3,
    "good": 4,
    "easy": 5,
}


def compute_sm2(
    ease_factor: float,
    interval_days: float,
    repetitions: int,
    quality: int,
) -> tuple[float, float, int]:
    """Pure SM-2 spaced-repetition update returning (new_ease, new_interval_days, new_reps)."""
    q = max(0, min(5, int(quality)))
    if q < 3:
        new_reps = 0
        new_interval = 1.0
    else:
        if repetitions == 0:
            new_interval = 1.0
        elif repetitions == 1:
            new_interval = 6.0
        else:
            new_interval = round(interval_days * ease_factor, 2)
        new_reps = repetitions + 1

    delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    new_ease = round(max(1.3, ease_factor + delta), 2)
    return new_ease, new_interval, new_reps


class StudyCardStore:
    """Thread-safe SQLite store for spaced-repetition study/coding cards."""

    def __init__(self, db_path: Path | None = None, cfg: SeleneConfig | None = None):
        active_cfg = cfg or SeleneConfig()
        resolved = db_path if db_path is not None else active_cfg.db_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = resolved
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(resolved, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS study_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    ease_factor REAL NOT NULL DEFAULT 2.5,
                    interval_days REAL NOT NULL DEFAULT 1.0,
                    repetitions INTEGER NOT NULL DEFAULT 0,
                    due_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_card(self, topic: str, question: str, answer: str) -> str:
        """Create a new study card due immediately for initial reinforcement."""
        clean_topic = topic.strip()[:80] or "General"
        clean_q = question.strip()[:400]
        clean_a = answer.strip()[:600]
        if not clean_q or not clean_a:
            return "Both a question and answer are required for a study card."

        now_iso = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO study_cards (topic, question, answer, due_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_topic, clean_q, clean_a, now_iso),
            )
            card_id = cur.lastrowid
        return f"Logged study card #{card_id} under '{clean_topic}': {clean_q}"

    def due_cards(self, limit: int = 5) -> list[dict]:
        """Return cards currently due for review, oldest-due first."""
        now_iso = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
        clamped = max(1, min(20, int(limit)))
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT id, topic, question, answer, ease_factor, interval_days, repetitions, due_at
                FROM study_cards
                WHERE due_at <= ?
                ORDER BY due_at ASC, id ASC
                LIMIT ?
                """,
                (now_iso, clamped),
            ).fetchall()
            return [dict(r) for r in rows]

    def due_count(self) -> int:
        now_iso = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS cnt FROM study_cards WHERE due_at <= ?",
                (now_iso,),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def total_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS cnt FROM study_cards").fetchone()
            return int(row["cnt"]) if row else 0

    def review_card(self, card_id: int, rating: str) -> str:
        """Record a review rating ('again', 'hard', 'good', 'easy') and schedule next due date."""
        norm = rating.strip().lower()
        if norm not in RATING_TO_QUALITY:
            allowed = ", ".join(RATING_TO_QUALITY)
            return f"Invalid rating '{rating}'. Use one of: {allowed}."

        with self._lock:
            row = self.conn.execute(
                "SELECT id, topic, ease_factor, interval_days, repetitions FROM study_cards WHERE id = ?",
                (int(card_id),),
            ).fetchone()
            if row is None:
                return f"No study card found with ID #{card_id}."

            new_ease, new_interval, new_reps = compute_sm2(
                float(row["ease_factor"]),
                float(row["interval_days"]),
                int(row["repetitions"]),
                RATING_TO_QUALITY[norm],
            )
            next_due = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=new_interval)
            next_due_iso = next_due.strftime("%Y-%m-%d %H:%M:%S")
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE study_cards
                    SET ease_factor = ?, interval_days = ?, repetitions = ?, due_at = ?
                    WHERE id = ?
                    """,
                    (new_ease, new_interval, new_reps, next_due_iso, int(card_id)),
                )
        return (
            f"Reviewed card #{card_id} ({row['topic']}) as '{norm}' — "
            f"next review in {new_interval:g} day(s)."
        )

    def format_due_summary(self, limit: int = 5) -> str:
        """Format due cards for /cards display or gentle session check-in hint."""
        due = self.due_cards(limit=limit)
        total = self.total_count()
        if not due:
            return f"No study cards due right now ({total} total saved)."
        lines = [f"Due study cards ({len(due)} shown of {self.due_count()} due / {total} total):"]
        for c in due:
            lines.append(f"  - #{c['id']} [{c['topic']}]: {c['question']}")
        return "\n".join(lines)

    def close(self) -> None:
        with self._lock:
            self.conn.close()
