# Step 3 — Unified Keyword Review: Redesign Spec
**Date:** 2026-03-25
**Status:** Approved for implementation

---

## Overview

Replace the current flat keyword table in Step 3 (KeywordWorkflow.jsx) with a **Score Dashboard + Pillar Sidebar + Sortable Table** layout, backed by a new **KeywordScoringEngine** that estimates KD and volume from free signals (with DataForSEO fallback).

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Layout | Score Dashboard + Pillar Sidebar + Flat sortable table (Option B) |
| Score source | Free signals first; DataForSEO if `DATAFORSEO_LOGIN` env is set |
| KD signals | SERP result count · Autosuggest position · Big-brand domain proxy · Exact-match title count |
| Bulk actions | Accept · Reject · Edit keyword text · Move to pillar · Delete permanently |
| Score trigger | On-demand — "⚡ Score Keywords" button in Step 3 header |
| KD column | Use existing `difficulty` column (INTEGER DEFAULT 50) — alias as `kd` in API responses only |
| Opp score scale | Store as **0–100 float** going forward. Update `_free_enrich` and all consumers to use 0–100. |
| Score jobs | In-memory dict `_score_jobs` in `main.py` — same pattern as `_research_jobs`. No new DB table needed. |
| Status filter "All" | When `status="all"` or omitted, do NOT filter by status in the SQL query. |

---

## Frontend — `StepReview` component

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Step 3 header + ⚡ Score Keywords button            │
├──────────────────────────────────────────────────────┤
│  [Total] [Pending] [Accepted] [Rejected] [Quick Wins*] [Avg KD*]  │
│  * shows "—" before scoring; updates after scoring runs           │
├──────────────────────────────────────────────────────┤
│  PILLAR SIDEBAR (160px)  │  KEYWORD TABLE (flex:1)   │
│  All pillars (200)       │  ┌ Toolbar ─────────────┐ │
│  cinnamon (38)           │  │ ☐ selectAll  Accept   │ │
│    Opp:72 · KD:34        │  │ Reject  Edit  Move    │ │
│  turmeric (38)           │  │ Delete  │ Filters     │ │
│    Opp:68 · KD:29        │  └─────────────────────┘ │
│  clove (38)              │  Table: keyword · pillar  │
│    Opp:51 · KD:48        │  source · intent · KD     │
│  ─────────────────       │  volume · opp score bar   │
│  KD Legend               │  status · ✓✕ actions      │
│  ■ 0-20 Easy             │                           │
│  ■ 21-50 Medium          │  ← pagination              │
│  ■ 51+ Hard              │                           │
└──────────────────────────┴───────────────────────────┘
```

### Stat Cards (6)

- **Total** — total keywords in session
- **Pending** — `status='pending'` count
- **Accepted** — `status='accepted'` count
- **Rejected** — `status='rejected'` count
- **Quick Wins** — keywords where `difficulty <= 20 AND volume_estimate >= 100`. Shows "—" before scoring runs (i.e., when all `difficulty = 50` default).
- **Avg KD** — average `difficulty` across all keywords. Shows "—" when all values are the default 50.

### Pillar Sidebar

- Lists each pillar with keyword count, avg Opp Score, avg KD (pulled from enhanced `by-pillar` endpoint)
- Active pillar highlighted with teal left border
- Click pillar → filters table to that pillar only
- "All pillars" option at top
- KD legend at bottom (Easy/Medium/Hard color chips)

### Bulk Toolbar

- **Select all** checkbox (selects current page)
- Count indicator: "N selected"
- Bulk buttons (enabled when ≥1 row selected):
  - ✓ Accept — sets `status='accepted'` for selected items
  - ✕ Reject — sets `status='rejected'` for selected items
  - ✎ Edit — opens modal with one text input per selected keyword (pre-filled). Lines map to `item_id`s by index. User edits text. On save, calls the existing `/review/{session_id}/action` endpoint once per keyword with `action=edit`. If user adds/removes lines, warn and abort (line count must match selection count).
  - ⇄ Move Pillar — shows dropdown of available pillars. On confirm, calls `/review/{session_id}/action` with `action=move_pillar` + `new_pillar` for each selected item.
  - 🗑 Delete — confirm dialog ("Delete N keywords permanently?"). On confirm, calls `DELETE /api/ki/{project_id}/review/{session_id}/items` with `{"item_ids": [...]}`.
- Filters (always visible): Status select (All/Pending/Accepted/Rejected) · Intent select · Sort select

### Table Columns

| Column | Notes |
|--------|-------|
| ☐ | Row checkbox |
| Keyword | font-weight:500, editable on double-click (single-item edit inline) |
| Pillar | teal color, from `pillar_keyword` field |
| Source | colored badge (User×=purple, Suggest=blue, Gap=amber, Site=green, Template=gray, Strategy=teal) |
| Intent | colored badge (transactional=blue, commercial=amber, informational=gray, navigational=purple) |
| KD | `difficulty` value, color-coded: ≤20 green, 21–50 amber, 51+ red. Tooltip: "Keyword Difficulty (0–100). Lower = easier to rank." |
| Vol | `volume_estimate` field. ≥1000 shown as "1.2K". Color: purple ≥500, teal ≥200, gray otherwise. |
| Opp Score | `opportunity_score` field (0–100). Progress bar + number. Color: green ≥75, amber ≥50, red <50. |
| Status | badge |
| Actions | ✓ (if not accepted) + ✕ (if not rejected) |

### Sorting

URL param `sort_by`: `opp_desc` (default) | `kd_asc` | `vol_desc` | `kw_asc`. Clicking column headers toggles this param.

### Score Engine Panel (right drawer)

Opens when user clicks **⚡ Score Keywords**:

```
Signal             Weight    Role
SERP result count   35%      KD signal
Big-brand domains   35%      KD signal
Exact-match titles  30%      KD signal
Autosuggest pos.    100%     Volume proxy (separate from KD)
```

- DataForSEO status chip (configured / not configured)
- Example breakdown for first keyword in session
- Progress bar while scoring runs (polls `GET /api/ki/{project_id}/score/{session_id}/{job_id}`)
- On complete: table auto-refreshes

### Continue Button

- Disabled if 0 accepted keywords
- Shows accepted count in label: "Continue to AI Check → (42 accepted)"

---

## Backend — Keyword Scoring Engine

### New File: `engines/annaseo_keyword_scorer.py`

**Class: `KeywordScoringEngine`**

```python
class KeywordScoringEngine:
    BIG_BRAND_DOMAINS = ["wikipedia", "amazon", "flipkart", "healthline",
                         "webmd", "nhs.uk", ".gov.", ".edu.", "youtube", "reddit"]

    def score_batch(self, keywords: List[dict], on_progress=None) -> List[dict]:
        """Score keywords. Each dict must have 'keyword', 'relevance_score'.
        Returns same list with difficulty, volume_estimate, opportunity_score updated.
        Calls on_progress(scored_count, total) after each item if provided."""
        if os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"):
            return self._dataforseo_score(keywords)
        return self._free_score(keywords, on_progress)

    def _free_score(self, keywords, on_progress=None) -> List[dict]:
        for i, kw_item in enumerate(keywords):
            signals = self._score_one_free(kw_item["keyword"])
            kw_item["difficulty"] = signals["kd"]
            kw_item["volume_estimate"] = signals["volume"]
            rel = kw_item.get("relevance_score", 50) / 100
            vol_n = min(signals["volume"] / 1000, 1.0)
            kd_n = signals["kd"] / 100
            kw_item["opportunity_score"] = round(vol_n * (1 - kd_n) * rel * 100, 1)
            kw_item["score_signals"] = json.dumps(signals)
            if on_progress:
                on_progress(i + 1, len(keywords))
            time.sleep(0.5)  # rate limit
        return keywords

    def _score_one_free(self, keyword: str) -> dict:
        serp_score = self._serp_result_score(keyword)
        autosuggest_vol = self._autosuggest_volume(keyword)
        brand_score = self._big_brand_score(keyword)
        title_score = self._exact_title_score(keyword)
        kd = round(serp_score * 0.35 + brand_score * 0.35 + title_score * 0.30)
        return {
            "kd": kd, "volume": autosuggest_vol,
            "serp_score": serp_score, "brand_score": brand_score,
            "title_score": title_score, "autosuggest_vol": autosuggest_vol,
        }
```

**Signal formulas:**

| Signal | Method | 0-100 output |
|--------|--------|-------------|
| SERP result count | DuckDuckGo HTML search, parse result count | <100K=20, 100K–1M=45, 1M–10M=65, >10M=85 |
| Autosuggest position | Google Autosuggest, position 1-10 in suggestions | pos1-3=600vol, pos4-7=250vol, pos8-10=80vol, missing=30vol |
| Big-brand domain count | DuckDuckGo top-10, count BIG_BRAND_DOMAINS matches | 0=10, 1=30, 2-3=55, 4+=80 |
| Exact-match title count | Same DuckDuckGo top-10 fetch (reused), count exact keyword in `<title>` | 0=10, 1-2=35, 3-5=60, 6+=80 |

Note: The DuckDuckGo SERP fetch for brand count and title count is **one shared HTTP call** per keyword (not two). Reuse the response.

### DB Column: `score_signals`

Add to `keyword_universe_items` in `_init_db()` inside `engines/annaseo_keyword_input.py`:

```python
# In the ALTER TABLE migration guard block:
try:
    con.execute("ALTER TABLE keyword_universe_items ADD COLUMN score_signals TEXT DEFAULT '{}'")
except Exception:
    pass
```

### Opportunity Score Scale Migration

The existing `GoogleKeywordEnricher._free_enrich` in `engines/annaseo_keyword_input.py` computes `opportunity_score` as a **0–1 float**. The `StepReview` component currently multiplies by 100 to display. **Change:**

1. Update `GoogleKeywordEnricher._free_enrich` to store 0–100 directly (multiply by 100 before rounding).
2. Remove the `* 100` multiplication in `StepReview` display code.
3. Update `KeywordScoringEngine` to store 0–100 (already done in formula above).

### Score Job Tracking

In `main.py`, add:

```python
_score_jobs: dict = {}   # job_id → {status, scored, total, error}
```

Follow the same pattern as `_research_jobs`. No new DB table needed.

### New API Endpoints

```
POST /api/ki/{project_id}/score/{session_id}
```
- Reads all `keyword_universe_items` for session from KI DB
- Creates `job_id = f"score_{uuid.uuid4().hex[:12]}"`
- Stores `_score_jobs[job_id] = {status:"running", scored:0, total:N, error:""}`
- Runs `KeywordScoringEngine().score_batch()` as `BackgroundTask`
  - On each item: updates KI DB row + increments `_score_jobs[job_id]["scored"]`
  - On complete: sets `status="completed"`
- Returns `{"job_id": job_id, "total": N}`

```
GET /api/ki/{project_id}/score/{session_id}/{job_id}
```
- Returns `_score_jobs.get(job_id)` or 404 if not found
- Shape: `{"status": "running"|"completed"|"failed", "scored": N, "total": N, "error": ""}`

```
DELETE /api/ki/{project_id}/review/{session_id}/items
Body: {"item_ids": ["ki_...", ...]}
```
- Deletes rows from `keyword_universe_items` in KI DB where `item_id IN (...)` AND `session_id = ?`
- Returns `{"deleted": N}`

### Enhanced Endpoints

**`GET /api/ki/{project_id}/review/{session_id}`** — add params:

| New param | Type | Default | Behaviour |
|-----------|------|---------|-----------|
| `sort_by` | str | `opp_desc` | `opp_desc`, `kd_asc`, `vol_desc`, `kw_asc` |
| `intent` | str | (none) | filter by `intent` column |
| `status` | str | (none) | if omitted or `"all"`, do NOT filter by status |

Return shape gains two new fields in `stats`:

```json
{
  "keywords": [...],
  "total": 200,
  "stats": {
    "total": 200, "pending": 200, "accepted": 0, "rejected": 0,
    "quick_wins": 42,
    "avg_kd": 34
  }
}
```

`quick_wins` = COUNT WHERE `difficulty <= 20 AND volume_estimate >= 100`.
`avg_kd` = AVG(`difficulty`). Both queries run on the KI DB.

Each keyword object in the response must include `difficulty` (renamed to `kd` in frontend mapping), `score_signals`.

Note: `ReviewManager.get_review_queue()` in `annaseo_keyword_input.py` must also be updated to accept `sort_by` and `intent` params and omit the status filter when `status` is None. The SQL sort maps: `opp_desc → ORDER BY opportunity_score DESC`, `kd_asc → ORDER BY difficulty ASC`, `vol_desc → ORDER BY volume_estimate DESC`, `kw_asc → ORDER BY keyword ASC`.

**`GET /api/ki/{project_id}/universe/{session_id}/by-pillar`** — enhance to include averages:

```json
{
  "pillars": [
    {
      "pillar": "cinnamon",
      "total": 38, "accepted": 0, "rejected": 0, "pending": 38,
      "avg_opp_score": 72.4,
      "avg_kd": 34
    }
  ]
}
```

Use `AVG(opportunity_score)` and `AVG(difficulty)` in the SQL query, grouped by `pillar_keyword`.

---

## Files Changed

| File | Change |
|------|--------|
| `engines/annaseo_keyword_scorer.py` | **CREATE** — `KeywordScoringEngine` class |
| `engines/annaseo_keyword_input.py` | ADD `score_signals` column in `_init_db()` migration guard; UPDATE `GoogleKeywordEnricher._free_enrich` to store opp_score as 0–100; UPDATE `ReviewManager.get_review_queue()` to accept `sort_by`, `intent`, optional `status` |
| `main.py` | ADD `_score_jobs` dict; ADD `POST/GET /api/ki/{id}/score/{session_id}/{job_id}`; ADD `DELETE /api/ki/{id}/review/{session_id}/items`; ENHANCE `ki_review_queue` (sort_by, intent, status optional, quick_wins + avg_kd in stats, kd/score_signals in response); ENHANCE `ki_by_pillar` (avg_opp_score, avg_kd); import `KeywordScoringEngine` |
| `frontend/src/KeywordWorkflow.jsx` | **REPLACE** `StepReview` component with new design; remove `* 100` from opp_score display |
