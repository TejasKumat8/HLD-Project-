"""
cache.py  –  Distributed in-memory cache with TTL and consistent hashing
"""
from __future__ import annotations
import time
import threading
from typing import Any, Optional
from consistent_hash import ConsistentHashRing


class CacheNode:
    """A single logical cache node (in-memory dict with TTL)."""

    def __init__(self, name: str, max_size: int = 5000, ttl: int = 300):
        self.name = name
        self.max_size = max_size
        self.ttl = ttl          # seconds
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expire_at)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                value, expire_at = self._store[key]
                if time.time() < expire_at:
                    self.hits += 1
                    return value
                else:
                    del self._store[key]   # expired
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl or self.ttl
        with self._lock:
            if len(self._store) >= self.max_size:
                self._evict_lru()
            self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def _evict_lru(self):
        # Evict 10 % of entries with earliest expiry
        if not self._store:
            return
        n_evict = max(1, len(self._store) // 10)
        sorted_keys = sorted(self._store, key=lambda k: self._store[k][1])
        for k in sorted_keys[:n_evict]:
            del self._store[k]

    @property
    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "name": self.name,
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


# ─────────────────────────────────────────────────────────────────────────────

NODE_NAMES = ["cache-node-1", "cache-node-2", "cache-node-3", "cache-node-4"]


class DistributedCache:
    """
    Wraps multiple CacheNodes behind a consistent-hash ring.
    The cache key is always the *prefix* string.
    """

    def __init__(self, node_names: list[str] = NODE_NAMES, ttl: int = 300):
        self._nodes: dict[str, CacheNode] = {
            name: CacheNode(name, ttl=ttl) for name in node_names
        }
        self._ring = ConsistentHashRing(node_names)
        self._ttl = ttl

    # ──────────────────────────────────────────
    def _node_for(self, prefix: str) -> CacheNode:
        name = self._ring.get_node(prefix)
        return self._nodes[name]

    # ──────────────────────────────────────────
    def get(self, prefix: str) -> Optional[list]:
        return self._node_for(prefix).get(prefix)

    def set(self, prefix: str, value: list, ttl: Optional[int] = None):
        self._node_for(prefix).set(prefix, value, ttl)

    def invalidate(self, prefix: str):
        """Invalidate a specific prefix key."""
        self._node_for(prefix).delete(prefix)

    def invalidate_all_prefixes_of(self, query: str):
        """
        When a query's score changes, invalidate all cached prefixes
        that are prefixes of that query (up to length 10 to stay fast).
        """
        q = query.lower().strip()
        for i in range(1, min(len(q), 10) + 1):
            pfx = q[:i]
            self.invalidate(pfx)

    # ──────────────────────────────────────────
    def debug(self, prefix: str) -> dict:
        node = self._node_for(prefix)
        cached = node.get(prefix)
        ring_info = self._ring.debug_info(prefix)
        return {
            "prefix": prefix,
            "assigned_node": node.name,
            "cache_hit": cached is not None,
            "cached_results": cached,
            "ring_info": ring_info,
            "node_stats": node.stats,
            "all_node_stats": [n.stats for n in self._nodes.values()],
        }

    # ──────────────────────────────────────────
    @property
    def global_stats(self) -> dict:
        nodes = [n.stats for n in self._nodes.values()]
        total_hits   = sum(n["hits"]   for n in nodes)
        total_misses = sum(n["misses"] for n in nodes)
        total = total_hits + total_misses
        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "overall_hit_rate": round(total_hits / total, 4) if total else 0.0,
            "nodes": nodes,
        }
