"""Asynchronous ingestion pipeline between the listeners and PostgreSQL.

Listeners hand raw datagrams/frames to :meth:`IngestionPipeline.submit`,
which enqueues them onto a bounded queue. Worker tasks drain the queue and
run the synchronous parse → normalize → store path in a thread so the
event loop (UDP/TCP sockets, future WebSocket fan-out) is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.services.event_service import save_event
from app.syslog.parser import parse_syslog

logger = logging.getLogger(__name__)


def process_message(raw: bytes, source_ip: str) -> object:
    """Parse, normalize, store and run detection for one syslog message.

    Raises:
        ValueError: on an empty message (counted as a parse error).
    """
    from app.detection.engine import get_detection_engine

    parsed = parse_syslog(raw)
    with SessionLocal() as db:
        event = save_event(db, parsed, source_ip, datetime.now(timezone.utc))
        # Detection failures must never lose the event: the engine already
        # guards each rule; this guard covers engine-level errors.
        try:
            get_detection_engine().process(event, db)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Detection failed for event %s", event.id)
            db.rollback()
        return event


class IngestionStats:
    """Thread-safe counters exposed by the health endpoint."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.submitted = 0
        self.stored = 0
        self.parse_errors = 0
        self.failed = 0
        self.dropped = 0

    def increment(self, field: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + amount)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "submitted": self.submitted,
                "stored": self.stored,
                "parse_errors": self.parse_errors,
                "failed": self.failed,
                "dropped": self.dropped,
            }


class IngestionPipeline:
    """Bounded-queue, multi-worker ingestion pipeline."""

    def __init__(self, maxsize: int = 10_000, workers: int = 4) -> None:
        self._maxsize = maxsize
        self._worker_count = max(1, workers)
        self._queue: asyncio.Queue[tuple[bytes, str]] | None = None
        self._tasks: list[asyncio.Task] = []
        self.stats = IngestionStats()

    @property
    def running(self) -> bool:
        return bool(self._tasks)

    async def start(self) -> None:
        if self.running:
            return
        self._queue = asyncio.Queue(maxsize=self._maxsize)
        self._tasks = [
            asyncio.create_task(self._worker(), name=f"ingest-worker-{index}")
            for index in range(self._worker_count)
        ]
        logger.info("Ingestion pipeline started with %s workers", self._worker_count)

    async def stop(self, drain_timeout: float = 5.0) -> None:
        if not self.running:
            return
        try:
            await asyncio.wait_for(self._drain(), timeout=drain_timeout)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("Pipeline drain timed out; cancelling workers")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("Ingestion pipeline stopped; stats=%s", self.stats.snapshot())

    def submit(self, raw: bytes, source_ip: str) -> None:
        """Non-blocking enqueue of one raw message (safe from sync callbacks)."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait((raw, source_ip))
            self.stats.increment("submitted")
        except asyncio.QueueFull:
            self.stats.increment("dropped")
            logger.warning(
                "Ingestion queue full — dropping message from %s", source_ip
            )

    async def _drain(self) -> None:
        if self._queue is not None:
            await self._queue.join()

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            raw, source_ip = await self._queue.get()
            try:
                await asyncio.to_thread(process_message, raw, source_ip)
                self.stats.increment("stored")
            except ValueError as exc:
                self.stats.increment("parse_errors")
                logger.warning("Parse error from %s: %s", source_ip, exc)
            except Exception:
                self.stats.increment("failed")
                logger.exception("Failed to ingest message from %s", source_ip)
            finally:
                self._queue.task_done()
