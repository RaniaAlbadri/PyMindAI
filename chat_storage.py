"""Local SQLite chat history for PyMind's Telegram assistant.

Messages are stored per Telegram chat ID. Only the most recent N messages are
loaded into the Groq prompt, but all stored messages remain until /clear.
"""

from contextlib import closing
from pathlib import Path
import sqlite3

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "pymind_chats.sqlite3"


class ChatStore:
    """Simple transaction-safe persistent store for private Telegram chats."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        """Create tables on first startup; do not erase an existing database."""
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    )
                    """
                )
                conn.execute(
                    """CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id_id
                       ON chat_messages(chat_id, id)"""
                )

    def recent(self, chat_id: int, limit: int) -> list[dict[str, str]]:
        """Read recent user + assistant turns, ordered oldest to newest."""
        if limit <= 0:
            return []
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            rows = conn.execute(
                """SELECT role, content FROM chat_messages
                   WHERE chat_id = ? ORDER BY id DESC LIMIT ?""",
                (chat_id, limit),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def save_exchange(self, chat_id: int, question: str, answer: str) -> None:
        """Save a complete user/assistant exchange in one transaction."""
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            with conn:
                conn.executemany(
                    "INSERT INTO chat_messages (chat_id, role, content) VALUES (?, ?, ?)",
                    [
                        (chat_id, "user", question),
                        (chat_id, "assistant", answer),
                    ],
                )

    def clear(self, chat_id: int) -> None:
        """Delete only one chat's saved history (used by /clear)."""
        with closing(sqlite3.connect(self.db_path, timeout=10)) as conn:
            with conn:
                conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
