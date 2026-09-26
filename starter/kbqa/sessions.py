"""对话历史。"""

from __future__ import annotations

import threading
from typing import Optional

MAX_TURNS = 6
MAX_SESSIONS = 500


class SessionStore:
    """最近几轮对话，够解追问就行。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS, max_turns: int = MAX_TURNS) -> None:
        self._turns: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.max_turns = max_turns

    def history(self, session_id: Optional[str]) -> list[dict]:
        if not session_id:
            return []
        with self._lock:
            return list(self._turns.get(session_id, []))

    def append(self, session_id: Optional[str], turn: dict) -> None:
        if not session_id:
            return
        with self._lock:
            turns = self._turns.setdefault(session_id, [])
            turns.append(turn)
            del turns[: max(0, len(turns) - self.max_turns)]
            if len(self._turns) > self.max_sessions:
                oldest = next(iter(self._turns))
                del self._turns[oldest]

    def clear(self) -> None:
        with self._lock:
            self._turns = {}
