"""
trending.py  –  Recency-aware trending search scoring

Design
------
We combine two signals:
  1. all_time_count   – total searches ever recorded (historical popularity)
  2. recent_score     – exponentially decaying sum of recent searches

Scoring formula
---------------
  score = all_time_count * W_HISTORICAL  +  recent_score * W_RECENT

Where:
  recent_score uses a sliding time-window (WINDOW_SECONDS) with exponential
  decay so that a query searched 5 minutes ago contributes more than one
  searched 2 hours ago.

  decay_weight(t) = exp(-λ * age_in_seconds)
  λ = ln(2) / HALF_LIFE_SECONDS   (score halves every HALF_LIFE_SECONDS)

Eviction of stale recent data
------------------------------
  Entries older than WINDOW_SECONDS are pruned on each update to avoid
  unbounded memory growth.  This prevents short-term viral queries from
  permanently dominating rankings.

Trade-offs
----------
  * Freshness  vs Stability   : lower HALF_LIFE → more responsive to trends
                                 higher HALF_LIFE → more stable suggestions
  * Latency    : scoring is O(1) per query; no expensive aggregations at
                  query time.  The Trie is updated asynchronously after a
                  batch flush.
  * Complexity : simple enough to reason about and tune without ML overhead.
"""

from __future__ import annotations
import math
import time
from collections import defaultdict, deque
from threading import Lock

# ──────────── tuneable constants ────────────
WINDOW_SECONDS   = 3600        # look at searches in the last 1 hour
HALF_LIFE_SECONDS = 600        # score halves every 10 minutes
W_HISTORICAL     = 1.0         # weight for all-time count
W_RECENT         = 5000.0      # weight multiplier for recent score
                               # (high because recent_score is a small decimal)
# ────────────────────────────────────────────

LAMBDA = math.log(2) / HALF_LIFE_SECONDS


class TrendingTracker:
    """Tracks recent searches and computes recency-aware scores."""

    def __init__(self):
        # query → deque of timestamps (recent events within WINDOW_SECONDS)
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    # ──────────────────────────────────────────
    def record(self, query: str, count: int = 1):
        """Record *count* occurrences of *query* at the current time."""
        now = time.time()
        with self._lock:
            dq = self._events[query.lower()]
            for _ in range(count):
                dq.append(now)
            self._prune(query.lower(), now)

    # ──────────────────────────────────────────
    def _prune(self, query: str, now: float):
        cutoff = now - WINDOW_SECONDS
        dq = self._events[query]
        while dq and dq[0] < cutoff:
            dq.popleft()

    # ──────────────────────────────────────────
    def recent_score(self, query: str) -> float:
        """
        Return a decayed sum of recent events.
        Each event contributes exp(-λ * age) to the score.
        """
        now = time.time()
        query = query.lower()
        with self._lock:
            self._prune(query, now)
            dq = self._events.get(query, deque())
            return sum(math.exp(-LAMBDA * (now - t)) for t in dq)

    # ──────────────────────────────────────────
    def blended_score(self, query: str, all_time_count: float) -> float:
        """
        Combine historical count + recent activity into a single score
        used to rank suggestions in the Trie.
        """
        rs = self.recent_score(query)
        return W_HISTORICAL * all_time_count + W_RECENT * rs

    # ──────────────────────────────────────────
    def trending_queries(self, top_n: int = 10) -> list[dict]:
        """Return the top-N queries by recent_score (pure recency ranking)."""
        now = time.time()
        with self._lock:
            scores = []
            for q, dq in self._events.items():
                self._prune(q, now)
                if dq:
                    rs = sum(math.exp(-LAMBDA * (now - t)) for t in dq)
                    scores.append((q, rs, len(dq)))
        scores.sort(key=lambda x: -x[1])
        return [
            {"query": q, "recent_score": round(rs, 4), "recent_count": cnt}
            for q, rs, cnt in scores[:top_n]
        ]

    # ──────────────────────────────────────────
    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "tracked_queries": len(self._events),
                "window_seconds": WINDOW_SECONDS,
                "half_life_seconds": HALF_LIFE_SECONDS,
                "w_historical": W_HISTORICAL,
                "w_recent": W_RECENT,
            }
