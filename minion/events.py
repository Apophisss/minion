"""In-process publish/subscribe bus for live updates (web UI, CLI, logs).

Events are small JSON-serialisable dicts: ``{"type": "...", "ts": ..., **data}``.
Event types used across Minion (prefix = area):

* ``server.status`` / ``server.tools``      - MCP hub changes
* ``tools.changed``                         - the aggregated tool set changed
* ``agent.status`` / ``agent.log``          - agent containers
* ``desktop.status``                        - built-in desktop
* ``container.build``                       - image build progress lines
* ``brain.event``                           - a brain run event (session_id + event)
* ``evolve.*`` / ``update.*`` / ``contrib.*`` - self-modification lifecycle
* ``schedule.run``                          - automations
* ``notify``                                - human-facing notification {level, title, message}
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import Any, AsyncIterator

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self, history: int = 200, queue_size: int = 1000):
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._queue_size = queue_size

    def publish(self, type: str, **data: Any) -> dict[str, Any]:
        event = {"type": type, "ts": time.time(), **data}
        self._history.append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop its oldest event rather than block publishers.
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(event)
        return event

    def notify(self, title: str, message: str = "", level: str = "info") -> None:
        self.publish("notify", level=level, title=title, message=message)

    def recent(self, limit: int = 100, prefix: str | None = None) -> list[dict[str, Any]]:
        items = [e for e in self._history if prefix is None or e["type"].startswith(prefix)]
        return items[-limit:]

    async def subscribe(self, prefix: str | None = None) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                if prefix is None or event["type"].startswith(prefix):
                    yield event
        finally:
            self._subscribers.discard(q)
