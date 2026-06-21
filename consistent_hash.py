"""
consistent_hash.py  –  Distributed cache using consistent hashing
"""
from __future__ import annotations
import hashlib
from bisect import bisect_right, insort
from typing import Any


class ConsistentHashRing:
    """
    A consistent-hash ring with virtual nodes (vnodes).
    Each physical cache node is replicated *replicas* times around the ring.
    """

    def __init__(self, nodes: list[str], replicas: int = 150):
        self.replicas = replicas
        self._ring: list[int] = []          # sorted hash positions
        self._map: dict[int, str] = {}      # position → node name

        for node in nodes:
            self.add_node(node)

    # ──────────────────────────────────────────
    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    # ──────────────────────────────────────────
    def add_node(self, node: str):
        for i in range(self.replicas):
            h = self._hash(f"{node}:{i}")
            if h not in self._map:
                insort(self._ring, h)
                self._map[h] = node

    # ──────────────────────────────────────────
    def remove_node(self, node: str):
        for i in range(self.replicas):
            h = self._hash(f"{node}:{i}")
            if h in self._map:
                self._ring.remove(h)
                del self._map[h]

    # ──────────────────────────────────────────
    def get_node(self, key: str) -> str:
        """Return the cache node responsible for *key*."""
        if not self._ring:
            raise RuntimeError("No nodes in ring")
        h = self._hash(key)
        idx = bisect_right(self._ring, h) % len(self._ring)
        return self._map[self._ring[idx]]

    # ──────────────────────────────────────────
    def get_all_nodes(self) -> list[str]:
        return list(set(self._map.values()))

    # ──────────────────────────────────────────
    def debug_info(self, key: str) -> dict:
        """Return debug information about which node handles a key."""
        node = self.get_node(key)
        h = self._hash(key)
        node_hashes = sorted([
            p for p, n in self._map.items() if n == node
        ])
        return {
            "key": key,
            "key_hash": h,
            "assigned_node": node,
            "node_virtual_positions": len(node_hashes),
            "all_nodes": self.get_all_nodes(),
        }
