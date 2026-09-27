"""追踪：一次问答的每一步、耗时、错误都记下来，调试面板用。"""

from __future__ import annotations

import threading
import time
import traceback
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class Trace:
    trace_id: str
    question: str
    session_id: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="milliseconds"))
    steps: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter)

    def step(self, name: str, payload: Any = None, started: Optional[float] = None) -> None:
        now = time.perf_counter()
        self.steps.append(
            {
                "step": name,
                "at_ms": round((now - self._t0) * 1000, 1),
                "took_ms": round((now - started) * 1000, 1) if started else None,
                "detail": payload,
            }
        )

    def error(self, where: str, exc: BaseException) -> None:
        """真实原因要留下来：类型、消息、堆栈，一个都不少。"""
        self.errors.append(
            {
                "where": where,
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            }
        )

    def llm(self, payload: dict) -> None:
        self.llm_calls.append(payload)

    def as_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "question": self.question,
            "started_at": self.started_at,
            "total_ms": round((time.perf_counter() - self._t0) * 1000, 1),
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
        }


class TraceStore:
    def __init__(self, capacity: int = 200, directory: Optional[Path] = None) -> None:
        self._data: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()
        self.capacity = capacity
        self._counter = 0
        self.directory = Path(directory).resolve() if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Keep generated IDs monotonic across service restarts.
            for path in self.directory.glob("t-*-*.json"):
                try:
                    self._counter = max(self._counter, int(path.stem.rsplit("-", 1)[1]))
                except (ValueError, IndexError):
                    continue

    def new_id(self, today: str) -> str:
        with self._lock:
            self._counter += 1
            return "t-%s-%04d" % (today.replace("-", ""), self._counter)

    def save(self, trace: Trace) -> None:
        payload = trace.as_dict()
        with self._lock:
            self._data[trace.trace_id] = payload
            self._data.move_to_end(trace.trace_id)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)
            if self.directory:
                target = self.directory / (trace.trace_id + ".json")
                temporary = target.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                temporary.replace(target)

    def get(self, trace_id: str) -> Optional[dict]:
        if not trace_id or Path(trace_id).name != trace_id:
            return None
        with self._lock:
            cached = self._data.get(trace_id)
            if cached is not None:
                return cached
            if not self.directory:
                return None
            path = self.directory / (trace_id + ".json")
            if not path.is_file():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            self._data[trace_id] = payload
            self._data.move_to_end(trace_id)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)
            return payload
