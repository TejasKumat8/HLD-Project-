"""
app.py  –  Flask backend for the Search Typeahead System
"""
from __future__ import annotations
import csv
import os
import time
import logging
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from trie        import Trie
from cache       import DistributedCache
from database    import Database
from batch_writer import BatchWriter
from trending    import TrendingTracker

# ──────────── Logging ────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────── Flask setup ─────────
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ──────────── Global objects ──────
db      = Database()
trie    = Trie()
cache   = DistributedCache(ttl=300)
trending = TrendingTracker()

# Latency tracking
_latency_log: list[float] = []
_latency_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP: load dataset → DB → Trie
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(csv_path: str = "data/queries.csv"):
    """Load CSV into SQLite (if not already loaded), then build the Trie."""
    import sqlite3

    # Check if DB already has data
    conn = sqlite3.connect("data/queries.db")
    count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    conn.close()

    if count == 0:
        logger.info("Loading dataset from %s …", csv_path)
        if not os.path.exists(csv_path):
            logger.warning("Dataset not found – generating …")
            import generate_dataset
            generate_dataset.main()

        batch = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    batch.append((row["query"].lower().strip(), int(row["count"])))
                except (KeyError, ValueError):
                    continue
                if len(batch) >= 5000:
                    db.bulk_insert(batch)
                    batch.clear()
        if batch:
            db.bulk_insert(batch)
        logger.info("Dataset loaded: %d queries", db.stats["write_count"])
    else:
        logger.info("DB already populated (%d queries) – skipping CSV load", count)


def build_trie():
    """Build the in-memory Trie from DB data."""
    logger.info("Building Trie …")
    t0 = time.time()
    all_rows = db.get_all()
    for query, count in all_rows:
        score = trending.blended_score(query, count)
        trie.insert(query, score)
    logger.info("Trie built in %.2fs (%d entries)", time.time() - t0, len(all_rows))


# ──────────── Batch-flush callback ───────────

def on_batch_flush(deltas: dict[str, int]):
    """Called by BatchWriter when a batch is ready to be persisted."""
    # 1. Persist to DB
    db.increment_counts(deltas)

    # 2. Update Trie scores + invalidate cache
    for query, delta in deltas.items():
        new_count = db.get_count(query)
        new_score = trending.blended_score(query, new_count)
        trie.update_score(query, new_score)
        cache.invalidate_all_prefixes_of(query)

    logger.info("Batch flushed: %d unique queries updated", len(deltas))


batch_writer = BatchWriter(flush_callback=on_batch_flush, batch_size=50, flush_interval=5.0)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── GET /suggest?q=<prefix>[&mode=trending] ──────────────────────────────────
@app.route("/suggest")
def suggest():
    t0  = time.perf_counter()
    q   = request.args.get("q", "").strip().lower()
    mode = request.args.get("mode", "basic")   # "basic" | "trending"

    if not q:
        latency_ms = (time.perf_counter() - t0) * 1000
        _record_latency(latency_ms)
        return jsonify({"suggestions": [], "source": "empty", "latency_ms": round(latency_ms, 2)})

    cache_key = f"{mode}:{q}"

    # 1. Try cache
    cached = cache.get(cache_key)
    if cached is not None:
        latency_ms = (time.perf_counter() - t0) * 1000
        _record_latency(latency_ms)
        return jsonify({
            "suggestions": cached,
            "source": "cache",
            "latency_ms": round(latency_ms, 2),
        })

    # 2. Trie lookup
    results = trie.search(q)       # list[(query, score)]

    if mode == "trending":
        # Re-rank: compute blended score (already in trie for recently updated,
        # but recalculate to ensure freshest recent score)
        reranked = []
        for query, base_score in results:
            base_count = base_score   # approximate: trie stores blended score
            fresh_score = trending.blended_score(query, db.get_count(query))
            reranked.append((query, fresh_score))
        reranked.sort(key=lambda x: -x[1])
        results = reranked

    suggestions = [
        {"query": r[0], "score": round(r[1], 2)} for r in results[:10]
    ]

    # 3. Cache miss → fall back to DB if trie gives nothing
    if not suggestions:
        db_rows = db.get_prefix_matches(q, limit=10)
        suggestions = [{"query": r[0], "score": r[1]} for r in db_rows]

    cache.set(cache_key, suggestions)
    latency_ms = (time.perf_counter() - t0) * 1000
    _record_latency(latency_ms)

    return jsonify({
        "suggestions": suggestions,
        "source": "trie",
        "latency_ms": round(latency_ms, 2),
    })


# ── POST /search ─────────────────────────────────────────────────────────────
@app.route("/search", methods=["POST"])
def search():
    data  = request.get_json(force=True)
    query = data.get("query", "").strip().lower()

    if not query:
        return jsonify({"error": "query is required"}), 400

    # Record in trending tracker immediately (before batch flush)
    trending.record(query)

    # Buffer the event in BatchWriter (async DB write)
    batch_writer.add(query)

    return jsonify({"message": "Searched", "query": query})


# ── GET /trending ─────────────────────────────────────────────────────────────
@app.route("/trending")
def get_trending():
    top = trending.trending_queries(top_n=10)
    return jsonify({"trending": top})


# ── GET /cache/debug?prefix=<prefix> ─────────────────────────────────────────
@app.route("/cache/debug")
def cache_debug():
    prefix = request.args.get("prefix", "").strip().lower()
    if not prefix:
        return jsonify({"error": "prefix is required"}), 400
    info = cache.debug(prefix)
    return jsonify(info)


# ── GET /stats ────────────────────────────────────────────────────────────────
@app.route("/stats")
def stats():
    with _latency_lock:
        lats = list(_latency_log)

    p50 = p95 = avg = 0.0
    if lats:
        s = sorted(lats)
        p50 = s[int(len(s) * 0.50)]
        p95 = s[int(len(s) * 0.95)]
        avg = sum(s) / len(s)

    return jsonify({
        "db":     db.stats,
        "cache":  cache.global_stats,
        "batch":  batch_writer.stats,
        "trending": trending.stats,
        "latency": {
            "samples": len(lats),
            "avg_ms":  round(avg, 2),
            "p50_ms":  round(p50, 2),
            "p95_ms":  round(p95, 2),
        },
    })


# ── POST /batch/flush (manual trigger) ───────────────────────────────────────
@app.route("/batch/flush", methods=["POST"])
def manual_flush():
    batch_writer.force_flush()
    return jsonify({"message": "Flush triggered", "stats": batch_writer.stats})


# ─────────────────────────────────────────────────────────────────────────────

def _record_latency(ms: float):
    with _latency_lock:
        _latency_log.append(ms)
        if len(_latency_log) > 10000:
            _latency_log.pop(0)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    load_dataset()
    build_trie()
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
