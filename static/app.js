/**
 * SearchIQ – app.js
 * Frontend logic: debounced typeahead, search submission,
 * cache debug, batch monitor, trending panel.
 */

const API = "";   // same origin – Flask serves static files too

// ── STATE ────────────────────────────────────────
let currentMode    = "basic";
let selectedIndex  = -1;
let suggestions    = [];
let debounceTimer  = null;
let statsInterval  = null;
let trendInterval  = null;

// ── DOM REFS ─────────────────────────────────────
const searchInput      = document.getElementById("searchInput");
const searchBtn        = document.getElementById("searchBtn");
const suggestionsPanel = document.getElementById("suggestionsPanel");
const suggestionsList  = document.getElementById("suggestionsList");
const loadingSpinner   = document.getElementById("loadingSpinner");
const noResults        = document.getElementById("noResults");
const noResultsQuery   = document.getElementById("noResultsQuery");
const sourceLabel      = document.getElementById("sourceLabel");
const suggCount        = document.getElementById("suggCount");
const latencyChip      = document.getElementById("latencyChip");
const latencyValue     = document.getElementById("latencyValue");
const resultBanner     = document.getElementById("searchResultBanner");
const resultQuery      = document.getElementById("resultQuery");
const resultClose      = document.getElementById("resultClose");
const trendingList     = document.getElementById("trendingList");
const trendingRefresh  = document.getElementById("trendingRefresh");
const cacheBadge       = document.getElementById("cacheBadge");
const statsRefresh     = document.getElementById("statsRefresh");
const cacheDebugInput  = document.getElementById("cacheDebugInput");
const cacheDebugBtn    = document.getElementById("cacheDebugBtn");
const cacheResult      = document.getElementById("cacheResult");
const cacheResultGrid  = document.getElementById("cacheResultGrid");
const nodeViz          = document.getElementById("nodeViz");
const manualFlushBtn   = document.getElementById("manualFlushBtn");
const batchStatsRow    = document.getElementById("batchStatsRow");
const flushLogEntries  = document.getElementById("flushLogEntries");

// ── MODE TABS ─────────────────────────────────────
document.querySelectorAll(".mode-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".mode-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    currentMode = tab.dataset.mode;
    // Re-fetch suggestions with new mode
    const q = searchInput.value.trim();
    if (q) fetchSuggestions(q);
  });
});

// ── SEARCH INPUT ──────────────────────────────────
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  const q = searchInput.value.trim();
  selectedIndex = -1;

  if (!q) {
    hideSuggestions();
    return;
  }

  debounceTimer = setTimeout(() => fetchSuggestions(q), 180); // 180ms debounce
});

// ── KEYBOARD NAVIGATION ───────────────────────────
searchInput.addEventListener("keydown", e => {
  if (!suggestionsPanel.style.display || suggestionsPanel.style.display === "none") {
    if (e.key === "Enter") submitSearch(searchInput.value.trim());
    return;
  }

  if (e.key === "ArrowDown") {
    e.preventDefault();
    selectedIndex = Math.min(selectedIndex + 1, suggestions.length - 1);
    highlightItem(selectedIndex);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    selectedIndex = Math.max(selectedIndex - 1, -1);
    highlightItem(selectedIndex);
    if (selectedIndex === -1) searchInput.value = searchInput.dataset.original || "";
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (selectedIndex >= 0 && suggestions[selectedIndex]) {
      searchInput.value = suggestions[selectedIndex].query;
    }
    submitSearch(searchInput.value.trim());
  } else if (e.key === "Escape") {
    hideSuggestions();
  }
});

function highlightItem(idx) {
  const items = suggestionsList.querySelectorAll("li");
  items.forEach((li, i) => li.classList.toggle("active", i === idx));
  if (idx >= 0 && suggestions[idx]) {
    searchInput.value = suggestions[idx].query;
  }
}

// ── SEARCH BUTTON ─────────────────────────────────
searchBtn.addEventListener("click", () => submitSearch(searchInput.value.trim()));

// ── CLOSE RESULT BANNER ───────────────────────────
resultClose.addEventListener("click", () => { resultBanner.style.display = "none"; });

// ── CLICK OUTSIDE ─────────────────────────────────
document.addEventListener("click", e => {
  if (!e.target.closest("#searchContainer")) hideSuggestions();
});

// ─────────────────────────────────────────────────
// FETCH SUGGESTIONS
// ─────────────────────────────────────────────────
async function fetchSuggestions(prefix) {
  showLoading(true);
  searchInput.dataset.original = prefix;

  try {
    const res  = await fetch(`${API}/suggest?q=${encodeURIComponent(prefix)}&mode=${currentMode}`);
    const data = await res.json();

    suggestions = data.suggestions || [];
    const source = data.source || "trie";
    const latMs  = data.latency_ms || 0;

    // Show latency chip
    latencyValue.textContent = latMs.toFixed(1);
    latencyChip.style.display = "flex";

    renderSuggestions(prefix, suggestions, source);
  } catch (err) {
    console.error("Suggest error:", err);
    showLoading(false);
    hideSuggestions();
  }
}

function renderSuggestions(prefix, items, source) {
  showLoading(false);
  suggestionsPanel.style.display = "block";

  // Source label
  sourceLabel.textContent = source === "cache" ? "⚡ Cache Hit" : source === "trie" ? "🌳 Trie" : "—";
  sourceLabel.className = "source-label " + (source === "cache" ? "source-cache" : source === "trie" ? "source-trie" : "source-empty");
  suggCount.textContent = `${items.length} result${items.length !== 1 ? "s" : ""}`;

  suggestionsList.innerHTML = "";
  noResults.style.display = "none";

  if (items.length === 0) {
    noResultsQuery.textContent = prefix;
    noResults.style.display = "block";
    return;
  }

  items.forEach((item, i) => {
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    li.setAttribute("id", `sugg-item-${i}`);

    const highlighted = highlightPrefix(item.query, prefix);
    li.innerHTML = `
      <span class="sugg-query">${highlighted}</span>
      <span class="sugg-score">${formatScore(item.score)}</span>
    `;
    li.addEventListener("click", () => {
      searchInput.value = item.query;
      hideSuggestions();
      submitSearch(item.query);
    });
    suggestionsList.appendChild(li);
  });
}

function highlightPrefix(query, prefix) {
  const p = prefix.toLowerCase();
  const q = query.toLowerCase();
  const idx = q.indexOf(p);
  if (idx === -1) return escapeHtml(query);
  return (
    escapeHtml(query.slice(0, idx)) +
    `<span class="highlight">${escapeHtml(query.slice(idx, idx + prefix.length))}</span>` +
    escapeHtml(query.slice(idx + prefix.length))
  );
}

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function formatScore(s) {
  if (s >= 1_000_000) return (s / 1_000_000).toFixed(1) + "M";
  if (s >= 1_000)     return (s / 1_000).toFixed(1) + "K";
  return s.toFixed ? s.toFixed(0) : String(s);
}

function hideSuggestions() {
  suggestionsPanel.style.display = "none";
  suggestions = [];
  selectedIndex = -1;
}

function showLoading(on) {
  loadingSpinner.style.display = on ? "flex" : "none";
  if (on) suggestionsPanel.style.display = "block";
}

// ─────────────────────────────────────────────────
// SUBMIT SEARCH
// ─────────────────────────────────────────────────
async function submitSearch(query) {
  if (!query) return;
  hideSuggestions();

  try {
    const res  = await fetch(`${API}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();

    resultQuery.textContent = `"${query}" – ${data.message}`;
    resultBanner.style.display = "flex";

    // Auto-hide banner after 4 s
    setTimeout(() => { resultBanner.style.display = "none"; }, 4000);

    // Refresh trending immediately
    fetchTrending();
    fetchStats();
    fetchBatchStats();
  } catch (err) {
    console.error("Search error:", err);
  }
}

// ─────────────────────────────────────────────────
// TRENDING
// ─────────────────────────────────────────────────
async function fetchTrending() {
  try {
    const res  = await fetch(`${API}/trending`);
    const data = await res.json();
    renderTrending(data.trending || []);
  } catch (err) {
    console.error("Trending error:", err);
  }
}

function renderTrending(items) {
  trendingList.innerHTML = "";
  if (items.length === 0) {
    trendingList.innerHTML = '<li class="trending-empty">No trending searches yet!</li>';
    return;
  }
  items.forEach((item, i) => {
    const li = document.createElement("li");
    const rankClass = i < 3 ? "trending-rank top3" : "trending-rank";
    li.innerHTML = `
      <span class="${rankClass}">${i + 1}</span>
      <span class="trending-query">${escapeHtml(item.query)}</span>
      <span class="trending-score">↑${item.recent_count}</span>
    `;
    li.addEventListener("click", () => {
      searchInput.value = item.query;
      fetchSuggestions(item.query);
    });
    trendingList.appendChild(li);
  });
}

trendingRefresh.addEventListener("click", fetchTrending);

// ─────────────────────────────────────────────────
// STATS
// ─────────────────────────────────────────────────
async function fetchStats() {
  try {
    const res  = await fetch(`${API}/stats`);
    const data = await res.json();

    const hr = data.cache?.overall_hit_rate ?? 0;
    document.getElementById("statHitRate").textContent = (hr * 100).toFixed(1) + "%";
    document.getElementById("statP95").textContent = (data.latency?.p95_ms ?? 0).toFixed(1) + "ms";
    document.getElementById("statBatches").textContent = data.batch?.total_batches_flushed ?? 0;
    document.getElementById("statWritesSaved").textContent = data.batch?.total_db_writes_saved ?? 0;

    cacheBadge.textContent = "Cache: " + (hr * 100).toFixed(0) + "%";
  } catch (err) {
    console.error("Stats error:", err);
  }
}

statsRefresh.addEventListener("click", fetchStats);

// ─────────────────────────────────────────────────
// CACHE DEBUG
// ─────────────────────────────────────────────────
cacheDebugBtn.addEventListener("click", fetchCacheDebug);
cacheDebugInput.addEventListener("keydown", e => { if (e.key === "Enter") fetchCacheDebug(); });

async function fetchCacheDebug() {
  const prefix = cacheDebugInput.value.trim();
  if (!prefix) return;

  try {
    const res  = await fetch(`${API}/cache/debug?prefix=${encodeURIComponent(prefix)}`);
    const data = await res.json();
    renderCacheDebug(data);
  } catch (err) {
    console.error("Cache debug error:", err);
  }
}

function renderCacheDebug(data) {
  cacheResult.style.display = "block";

  const hit = data.cache_hit;
  cacheResultGrid.innerHTML = `
    <div class="cache-info-card">
      <div class="cache-info-label">Prefix</div>
      <div class="cache-info-value">"${escapeHtml(data.prefix)}"</div>
    </div>
    <div class="cache-info-card">
      <div class="cache-info-label">Assigned Node</div>
      <div class="cache-info-value" style="color:var(--accent-3)">${data.assigned_node}</div>
    </div>
    <div class="cache-info-card">
      <div class="cache-info-label">Cache Status</div>
      <div class="cache-info-value ${hit ? "hit" : "miss"}">${hit ? "✅ HIT" : "❌ MISS"}</div>
    </div>
    <div class="cache-info-card">
      <div class="cache-info-label">Key Hash</div>
      <div class="cache-info-value" style="font-size:.72rem">${data.ring_info?.key_hash?.toString(16).slice(0,12)}…</div>
    </div>
  `;

  // Node visualization
  const allStats = data.all_node_stats || [];
  nodeViz.innerHTML = "";
  allStats.forEach(ns => {
    const pill = document.createElement("div");
    pill.className = "node-pill" + (ns.name === data.assigned_node ? " active" : "");
    const hr = ns.hits + ns.misses > 0 ? ((ns.hits / (ns.hits + ns.misses)) * 100).toFixed(0) : 0;
    pill.innerHTML = `${ns.name}<span class="node-stat">size:${ns.size} | hits:${hr}%</span>`;
    nodeViz.appendChild(pill);
  });
}

// ─────────────────────────────────────────────────
// BATCH WRITER MONITOR
// ─────────────────────────────────────────────────
async function fetchBatchStats() {
  try {
    const res  = await fetch(`${API}/stats`);
    const data = await res.json();
    const b    = data.batch || {};
    renderBatchStats(b);
  } catch (err) {
    console.error("Batch stats error:", err);
  }
}

function renderBatchStats(b) {
  batchStatsRow.innerHTML = `
    <div class="batch-stat">
      <div class="batch-stat-value">${b.total_events_received ?? 0}</div>
      <div class="batch-stat-label">Events Received</div>
    </div>
    <div class="batch-stat">
      <div class="batch-stat-value">${b.total_batches_flushed ?? 0}</div>
      <div class="batch-stat-label">Batches Flushed</div>
    </div>
    <div class="batch-stat">
      <div class="batch-stat-value">${b.total_db_writes_saved ?? 0}</div>
      <div class="batch-stat-label">Writes Saved</div>
    </div>
    <div class="batch-stat">
      <div class="batch-stat-value">${b.pending_in_buffer ?? 0}</div>
      <div class="batch-stat-label">Pending (Buffer)</div>
    </div>
  `;

  const recent = b.recent_flushes || [];
  if (recent.length === 0) {
    flushLogEntries.innerHTML = '<div class="flush-empty">No flushes yet. Submit some searches!</div>';
  } else {
    flushLogEntries.innerHTML = "";
    [...recent].reverse().forEach(f => {
      const div = document.createElement("div");
      div.className = "flush-entry";
      div.innerHTML = `
        <span class="flush-badge">Batch #${f.batch_id}</span>
        <span class="flush-detail">${f.events} events → ${f.unique_queries} unique queries</span>
        <span class="flush-saved">💾 ${f.writes_saved} writes saved</span>
        <span class="flush-time">${f.timestamp}</span>
      `;
      flushLogEntries.appendChild(div);
    });
  }
}

manualFlushBtn.addEventListener("click", async () => {
  try {
    await fetch(`${API}/batch/flush`, { method: "POST" });
    await fetchBatchStats();
    await fetchStats();
  } catch (err) {
    console.error("Flush error:", err);
  }
});

// ─────────────────────────────────────────────────
// AUTO-REFRESH
// ─────────────────────────────────────────────────
function startAutoRefresh() {
  fetchStats();
  fetchTrending();
  fetchBatchStats();

  statsInterval = setInterval(() => {
    fetchStats();
    fetchBatchStats();
  }, 5000);

  trendInterval = setInterval(fetchTrending, 10000);
}

// ─────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  startAutoRefresh();
  searchInput.focus();
});
