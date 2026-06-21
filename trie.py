"""
trie.py  –  Compressed Trie for prefix-based suggestion lookups
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrieNode:
    children: dict[str, "TrieNode"] = field(default_factory=dict)
    # list of (score, query) – kept as a heap with at most TOP_K entries
    top_results: list[tuple[float, str]] = field(default_factory=list)
    is_end: bool = False
    count: float = 0.0


TOP_K = 10  # how many results we store per node


class Trie:
    """
    Stores search queries.  Each node keeps a cached list of the top-TOP_K
    queries (by score) rooted at that prefix, so suggestions are O(prefix_len).
    """

    def __init__(self):
        self.root = TrieNode()

    # ──────────────────────────────────────────
    def insert(self, query: str, score: float):
        """Insert or update a query with a given score."""
        query = query.lower().strip()
        node = self.root
        self._update_top(node, score, query)
        for ch in query:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
            self._update_top(node, score, query)
        node.is_end = True
        node.count = score

    # ──────────────────────────────────────────
    def _update_top(self, node: TrieNode, score: float, query: str):
        import heapq
        # Check if query already in list (update in place)
        for i, (s, q) in enumerate(node.top_results):
            if q == query:
                node.top_results[i] = (score, query)
                # re-heapify
                heapq.heapify(node.top_results)
                return
        if len(node.top_results) < TOP_K:
            heapq.heappush(node.top_results, (score, query))
        elif score > node.top_results[0][0]:
            heapq.heapreplace(node.top_results, (score, query))

    # ──────────────────────────────────────────
    def search(self, prefix: str) -> list[tuple[str, float]]:
        """Return up to TOP_K suggestions for *prefix*, sorted by score desc."""
        prefix = prefix.lower().strip()
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]
        results = sorted(node.top_results, key=lambda x: -x[0])
        return [(q, s) for s, q in results]

    # ──────────────────────────────────────────
    def update_score(self, query: str, new_score: float):
        """Re-insert a query with an updated score."""
        self.insert(query, new_score)
