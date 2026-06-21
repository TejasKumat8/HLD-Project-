"""
database.py  –  SQLite-backed persistent query-count store
"""
from __future__ import annotations
import sqlite3
import threading
import logging
import time

logger = logging.getLogger(__name__)

DB_PATH = "data/queries.db"


class Database:
    """Thread-safe SQLite wrapper for query counts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._write_count = 0
        self._read_count  = 0
        self._init_db()

    # ──────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")   # better concurrent reads
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    query TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_count ON queries(count DESC)")
            conn.commit()
            conn.close()

    # ──────────────────────────────────────────
    def bulk_insert(self, rows: list[tuple[str, int]]):
        """Insert many (query, count) rows – used during initial data load."""
        with self._lock:
            conn = self._connect()
            conn.executemany(
                "INSERT OR IGNORE INTO queries (query, count, updated_at) VALUES (?,?,?)",
                [(q, c, time.time()) for q, c in rows]
            )
            conn.commit()
            conn.close()
        self._write_count += len(rows)

    # ──────────────────────────────────────────
    def increment_counts(self, deltas: dict[str, int]):
        """
        Batch-update counts.  Called by BatchWriter flush callback.
        Uses INSERT OR REPLACE so new queries are auto-added.
        """
        now = time.time()
        with self._lock:
            conn = self._connect()
            for query, delta in deltas.items():
                conn.execute("""
                    INSERT INTO queries (query, count, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(query)
                    DO UPDATE SET count = count + ?, updated_at = ?
                """, (query, delta, now, delta, now))
            conn.commit()
            conn.close()
        self._write_count += 1   # 1 batch write regardless of dict size

    # ──────────────────────────────────────────
    def get_count(self, query: str) -> int:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT count FROM queries WHERE query = ?", (query.lower(),)
            ).fetchone()
            conn.close()
        self._read_count += 1
        return row[0] if row else 0

    # ──────────────────────────────────────────
    def get_prefix_matches(self, prefix: str, limit: int = 10) -> list[tuple[str, int]]:
        """Fallback DB query for cache misses."""
        prefix = prefix.lower()
        with self._lock:
            conn = self._connect()
            rows = conn.execute("""
                SELECT query, count FROM queries
                WHERE query LIKE ? ESCAPE '\\'
                ORDER BY count DESC
                LIMIT ?
            """, (prefix.replace("%", r"\%").replace("_", r"\_") + "%", limit)
            ).fetchall()
            conn.close()
        self._read_count += 1
        return rows

    # ──────────────────────────────────────────
    def get_all(self) -> list[tuple[str, int]]:
        """Return all (query, count) pairs – used to build the Trie."""
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT query, count FROM queries").fetchall()
            conn.close()
        return rows

    # ──────────────────────────────────────────
    @property
    def stats(self) -> dict:
        return {
            "write_count": self._write_count,
            "read_count":  self._read_count,
        }
