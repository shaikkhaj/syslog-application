"""Thread-safe fan-out of alert updates to WebSocket subscribers.

The detection engine runs inside ingestion worker threads, while WebSockets
live on the main event loop — ``emit`` therefore hops onto the bound loop
with ``call_soon_threadsafe``. When no loop is bound (unit tests, CLI), the
emit is a safe no-op.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_QUEUE = 200


class AlertBroadcaster:
    """Publishes alert JSON payloads to all subscribed WebSocket queues."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()

    # Lifecycle -----------------------------------------------------------

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def unbind(self) -> None:
        self._loop = None
        self._subscribers.clear()

    # Subscriptions --------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # Publishing -------------------------------------------------------------

    def emit(self, payload: dict[str, Any]) -> None:
        """Emit from any thread; delivery happens on the bound loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, payload)
        except RuntimeError:  # loop closed between the check and the call
            logger.debug("Broadcaster loop unavailable; dropping alert update")

    def _fanout(self, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Slow alert subscriber; dropping update")


alert_broadcaster = AlertBroadcaster()
