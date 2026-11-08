"""Minimal anti-spam protection without a daily/per-user message quota.

One active reply per private chat and an 8-second duplicate-message window.
All other messages remain unlimited from the app's perspective.
"""

import time


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


class MessageGuard:
    def __init__(self, duplicate_window_seconds: float = 8.0):
        self.duplicate_window_seconds = duplicate_window_seconds
        self.busy_chats: set[int] = set()
        self.last_completed: dict[int, tuple[str, float]] = {}
        self._attempts = 0

    def begin(self, chat_id: int, message: str, now: float | None = None) -> str | None:
        """Return 'busy'/'duplicate', or None if processing may begin."""
        now = time.monotonic() if now is None else now
        if chat_id in self.busy_chats:
            return "busy"

        last = self.last_completed.get(chat_id)
        if last is not None:
            last_text, last_time = last
            if normalize_text(message) == last_text and 0 <= now - last_time < self.duplicate_window_seconds:
                return "duplicate"

        self.busy_chats.add(chat_id)
        self._attempts += 1
        if self._attempts % 200 == 0:
            self._prune(now)
        return None

    def finish(self, chat_id: int, message: str, successful: bool, now: float | None = None) -> None:
        """Always unblock chat; only successful replies trigger duplicate protection."""
        self.busy_chats.discard(chat_id)
        if successful:
            now = time.monotonic() if now is None else now
            self.last_completed[chat_id] = (normalize_text(message), now)

    def is_busy(self, chat_id: int) -> bool:
        return chat_id in self.busy_chats

    def clear(self, chat_id: int) -> None:
        self.last_completed.pop(chat_id, None)

    def _prune(self, now: float) -> None:
        # Avoid retaining IDs of people who used the bot only once indefinitely.
        stale = [cid for cid, (_, ts) in self.last_completed.items() if now - ts > 600]
        for cid in stale:
            del self.last_completed[cid]
