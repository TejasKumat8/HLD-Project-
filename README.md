# SearchIQ – Search Typeahead System

A full-stack, production-quality search typeahead system built from scratch. Features a compressed Trie for O(prefix) lookups, a 4-node distributed cache using **Consistent Hashing**, exponential-decay **Trending Search** scoring, and a **Batch Writer** that dramatically reduces primary-store writes.

---

## Architecture Overview

```
User Browser
    │
    ▼
┌─────────────────────────────────┐
│         Flask API Server        │
│  /suggest  /search  /trending   │
│  /cache/debug  /stats           │
└────────────┬────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌──────────┐   ┌────────────────────────────┐
│  Trie    │   │  Distributed Cache (4 nodes)│
│ (in-mem) │   │  Consistent Hash Ring       │
└──────────┘   └────────────────────────────┘
                         │ miss
                         ▼
               ┌─────────────────┐
               │  SQLite (data/) │◄──── Batch Writer
               └─────────────────┘      (50 events / 5s)
                                         └── TrendingTracker
```

### Components

| File | Responsibility |
|---|---|
| `app.py` | Flask server, route handlers, startup orchestration |
| `trie.py` | Compressed Trie with per-node top-K cache (O(prefix_len) suggestion) |
| `consistent_hash.py` | MD5-based consistent hash ring with 150 virtual nodes per cache node |
| `cache.py` | 4-node distributed in-memory cache with TTL + LRU eviction |
| `database.py` | Thread-safe SQLite wrapper (WAL mode for concurrent reads) |
| `batch_writer.py` | Buffers search events; flushes aggregated counts every 5s or 50 events |
| `trending.py` | Exponential-decay scoring: `score = W_hist * count + W_recent * Σ e^(-λ*age)` |
| `generate_dataset.py` | Generates 100,000+ synthetic queries with Zipf-distributed counts |
| `static/index.html` | Main SPA page |
| `static/style.css` | Glassmorphism dark-mode UI |
| `static/app.js` | Debounced typeahead, keyboard nav, live metrics panels |

---

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### 1. Install dependencies

```bash
pip install flask flask-cors
```

### 2. Generate dataset (one-time)

```bash
python generate_dataset.py
```

This creates `data/queries.csv` with **120,000+** queries.

### 3. Start the server

```bash
python app.py
```

The server loads the dataset into SQLite (first run ~10s), builds the Trie, and starts listening on **http://localhost:5000**.

---

## API Reference

### `GET /suggest?q=<prefix>[&mode=basic|trending]`
Returns up to 10 prefix-matching suggestions.

**Example:**
```
GET /suggest?q=iphone&mode=trending
```
```json
{
  "suggestions": [
    {"query": "iphone 15", "score": 85432.5},
    {"query": "iphone charger", "score": 61020.0}
  ],
  "source": "cache",
  "latency_ms": 0.32
}
```

### `POST /search`
Submit a search query. Returns dummy response + triggers batch write.

```json
// Request
{ "query": "iphone 15 pro" }

// Response
{ "message": "Searched", "query": "iphone 15 pro" }
```

### `GET /cache/debug?prefix=<prefix>`
Inspect consistent-hash routing and cache state.

```json
{
  "prefix": "iphone",
  "assigned_node": "cache-node-2",
  "cache_hit": true,
  "ring_info": { "key_hash": 123456789, "node_virtual_positions": 150 },
  "node_stats": { "hits": 42, "misses": 8, "hit_rate": 0.84 }
}
```

### `GET /trending`
Top-10 queries sorted by recent activity score.

### `GET /stats`
Aggregate metrics: DB reads/writes, cache hit rate, latency (p50/p95), batch stats.

### `POST /batch/flush`
Manually trigger a batch flush.

---

## Data Storage Design

### Primary Store (SQLite)
- Table: `queries(query TEXT PK, count INTEGER, updated_at REAL)`
- WAL journal mode for concurrent read/write
- Index on `count DESC` for fast top-N queries

### Cache Layer
- 4 logical cache nodes (in-memory dicts with TTL=300s)
- Consistent hash ring: 150 virtual nodes per physical node
- Invalidation: when a query's score changes, all prefix-keys (len 1–10) are invalidated
- Eviction: LRU (10% eviction when node reaches 5000 entries)

### Trie (Primary Suggestion Engine)
- Each Trie node stores a **top-10 min-heap** of (score, query)
- Insertion/update: O(query_len × log(10)) ≈ O(query_len)
- Lookup: O(prefix_len) — just traverse to prefix node, read heap

---

## Trending Search Design

```
score(q) = 1.0 × all_time_count(q)  +  5000 × Σ e^(-λ × age_i)
           ─────────────────────────   ─────────────────────────
                 historical weight          recency weight
```

- **λ = ln(2) / 600** → score halves every 10 minutes
- **Window**: Only events within the last 3600 seconds are considered
- **Effect**: A query searched 5× in the last minute overtakes a historically popular query that hasn't been searched recently
- **Stale protection**: Events older than WINDOW_SECONDS are pruned on each access, so short-term viral queries naturally decay

---

## Batch Write Design

```
Search Request → BatchWriter.add(query)
                      │
                      ▼
                  In-memory buffer (deque)
                      │
          ┌───────────┴────────────┐
          │ size ≥ 50?             │ timer fires (5s)?
          ▼                        ▼
      Flush batch              Flush batch
          │
          ▼
    Aggregate: {query: count_delta}
          │
          ▼
    DB.increment_counts()  ← 1 write per batch
          │
          ▼
    Trie.update_score()
    Cache.invalidate_prefixes()
```

**Write reduction example:** 50 searches for "python" → 1 DB write instead of 50. **98% reduction.**

**Failure trade-off:** At-most-once delivery. Events in buffer are lost on crash. Acceptable for search-count use-case. For stronger guarantees, write events to a WAL file before buffering.

---

## Performance

| Metric | Typical Value |
|---|---|
| Suggestion latency (cache hit) | < 1ms |
| Suggestion latency (trie lookup) | 1–5ms |
| Suggestion latency (DB fallback) | 10–30ms |
| Trie build time (120k queries) | ~3–5 seconds |
| Cache hit rate (warm) | 70–90% |
| Batch write reduction | 80–98% |

Run `/stats` endpoint to see live p50/p95 latency and cache hit rate.

---

## Consistent Hashing Details

- **Ring size**: 2^128 (MD5 hash space)
- **Virtual nodes**: 150 per physical node → uniform distribution
- **Node assignment**: Clockwise successor of `MD5(prefix)`
- **Load balance**: With 4 nodes × 150 vnodes, each node handles ~25% of traffic ±5%
- **Adding a node**: Only ~25% of keys remap (vs 100% with modular hashing)

View routing with: `GET /cache/debug?prefix=<your_prefix>`

---

## Dataset

- **Source**: Synthetically generated using Zipf distribution
- **Size**: 120,000+ queries
- **Domains**: Tech products, tutorials, e-commerce, entertainment, health, general
- **Distribution**: Zipf law with ±20% noise — realistic search frequency distribution

---

## Screenshots

![SearchIQ Screenshot](screenshot.png)

---

## License
MIT
