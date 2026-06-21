"""
batch_writer.py  –  Collects search events and flushes them in batches.

Design
------
* Incoming search events are pushed to an in-memory deque (buffer).
* A background thread flushes the buffer every FLUSH_INTERVAL seconds
  OR whenever the buffer reaches BATCH_SIZE entries.
* Repeated queries within a batch are aggregated (count only once per batch).
* Failure trade-off: if the process crashes before a flush, the buffered
  events are lost (at-most-once delivery).  This is acceptable for a
  search-count use-case where losing a few counts is not catastrophic.
  For stronger guarantees, the buffer could be persisted to a WAL file.
"""

from __future__ import annotations
import threading
import time
import logging
from collections import defaultdict, deque
from typing import Callable

logger = logging.getLogger(__name__)

BATCH_SIZE     = 50       # flush after this many events
FLUSH_INTERVAL = 5.0      # seconds between automatic flushes


class BatchWriter:
    """
    Buffers search events and calls *flush_callback* with an aggregated
    dict of {query: count_delta} when a flush occurs.
    """

    def __init__(
        self,
        flush_callback: Callable[[dict[str, int]], None],
        batch_size: int = BATCH_SIZE,
        flush_interval: float = FLUSH_INTERVAL,
    ):
        self._callback      = flush_callback
        self._batch_size    = batch_size
        self._flush_interval = flush_interval

        self._buffer: deque[str] = deque()
        self._lock   = threading.Lock()

        # Metrics
        self.total_events_received = 0
        self.total_batches_flushed = 0
        self.total_db_writes_saved = 0   # events buffered that weren't individual writes
        self.flush_log: list[dict] = []  # last 20 flush records for the UI

        # Start background flusher
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._background_flush, daemon=True)
        self._thread.start()

    # ──────────────────────────────────────────
    def add(self, query: str):
        """Add a single search event to the buffer."""
        with self._lock:
            self._buffer.append(query.lower().strip())
            self.total_events_received += 1
            size = len(self._buffer)

        if size >= self._batch_size:
            self._flush()

    # ──────────────────────────────────────────
    def _flush(self):
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        # Aggregate
        aggregated: dict[str, int] = defaultdict(int)
        for q in batch:
            aggregated[q] += 1

        unique_queries = len(aggregated)
        events_in_batch = len(batch)
        saved = events_in_batch - unique_queries

        self.total_batches_flushed += 1
        self.total_db_writes_saved += saved

        record = {
            "batch_id": self.total_batches_flushed,
            "events": events_in_batch,
            "unique_queries": unique_queries,
            "writes_saved": saved,
            "timestamp": time.strftime("%H:%M:%S"),
            "queries": dict(aggregated),
        }
        self.flush_log.append(record)
        if len(self.flush_log) > 20:
            self.flush_log.pop(0)

        logger.info(
            "Batch flush #%d: %d events → %d unique queries (%d writes saved)",
            self.total_batches_flushed, events_in_batch, unique_queries, saved
        )

        try:
            self._callback(dict(aggregated))
        except Exception as exc:
            logger.error("Flush callback error: %s", exc)

    # ──────────────────────────────────────────
    def _background_flush(self):
        while not self._stop_event.is_set():
            time.sleep(self._flush_interval)
            self._flush()

    # ──────────────────────────────────────────
    def force_flush(self):
        """Manually trigger a flush (useful for shutdown or testing)."""
        self._flush()

    def stop(self):
        self._stop_event.set()
        self._flush()

    # ──────────────────────────────────────────
    @property
    def stats(self) -> dict:
        with self._lock:
            pending = len(self._buffer)
        return {
            "total_events_received": self.total_events_received,
            "total_batches_flushed": self.total_batches_flushed,
            "total_db_writes_saved": self.total_db_writes_saved,
            "pending_in_buffer": pending,
            "batch_size_config": self._batch_size,
            "flush_interval_config": self._flush_interval,
            "recent_flushes": self.flush_log[-5:],
        }
