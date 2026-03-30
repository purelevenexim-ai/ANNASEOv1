# Step 3 Keyword Review Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat keyword review table in Step 3 with a Score Dashboard + Pillar Sidebar + sortable table layout, backed by a new KeywordScoringEngine with 4 free signals and DataForSEO fallback.

**Architecture:** New `engines/annaseo_keyword_scorer.py` handles scoring logic (SERP count + autosuggest + brand proxy + title proxy). The backend gains 3 new endpoints (score POST/GET, bulk delete) and 2 enhanced endpoints (review queue with sort/filter, by-pillar with averages). The frontend `StepReview` component in `KeywordWorkflow.jsx` is replaced entirely.

**Tech Stack:** Python 3.12 · FastAPI · SQLite (KI engine's own DB at `annaseo.db`) · React 18 · react-query · DuckDuckGo HTML search (no API key) · Google Autosuggest (no API key) · DataForSEO API (optional)

**Spec:** `docs/superpowers/specs/2026-03-25-step3-keyword-review-redesign.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `engines/annaseo_keyword_scorer.py` | **CREATE** | `KeywordScoringEngine` class — all scoring logic |
| `engines/annaseo_keyword_input.py` | **MODIFY** lines ~91–170, ~721–732 | Add `score_signals` column migration; fix opp_score to 0–100; update `ReviewManager.get_review_queue()` to accept `sort_by`, `intent`, optional `status` |
| `main.py` | **MODIFY** lines ~1259, ~1088–1210 | Add `_score_jobs` dict; add 3 new endpoints; enhance `ki_review_queue` and `ki_by_pillar` |
| `frontend/src/KeywordWorkflow.jsx` | **MODIFY** — replace `StepReview` function (~line 437–610) | New Score Dashboard + Pillar Sidebar + sortable table UI |
| `tests/test_keyword_scorer.py` | **CREATE** | Unit tests for `KeywordScoringEngine` |

---

## Task 1: Create `KeywordScoringEngine` (scoring logic only, no HTTP calls in tests)

**Files:**
- Create: `engines/annaseo_keyword_scorer.py`
- Create: `tests/test_keyword_scorer.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/test_keyword_scorer.py`:

```python
"""Tests for KeywordScoringEngine."""
import pytest
from unittest.mock import patch, MagicMock


def test_score_batch_returns_all_fields():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    keywords = [{"keyword": "organic cinnamon", "relevance_score": 80}]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 25, "volume": 300,
        "serp_score": 40, "brand_score": 20, "title_score": 30, "autosuggest_vol": 300
    }):
        result = engine.score_batch(keywords)
    assert len(result) == 1
    kw = result[0]
    assert "difficulty" in kw
    assert "volume_estimate" in kw
    assert "opportunity_score" in kw
    assert "score_signals" in kw
    assert isinstance(kw["opportunity_score"], float)
    assert 0 <= kw["opportunity_score"] <= 100


def test_opp_score_is_0_to_100():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    keywords = [{"keyword": "buy turmeric", "relevance_score": 90}]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 20, "volume": 500,
        "serp_score": 20, "brand_score": 20, "title_score": 20, "autosuggest_vol": 500
    }):
        result = engine.score_batch(keywords)
    score = result[0]["opportunity_score"]
    assert 0 <= score <= 100, f"Expected 0-100 but got {score}"


def test_kd_from_weighted_signals():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    # kd = round(40*0.35 + 60*0.35 + 50*0.30) = round(14+21+15) = round(50) = 50
    with patch.object(engine, "_serp_result_score", return_value=40), \
         patch.object(engine, "_big_brand_score", return_value=60), \
         patch.object(engine, "_exact_title_score", return_value=50), \
         patch.object(engine, "_autosuggest_volume", return_value=200):
        signals = engine._score_one_free("test keyword")
    assert signals["kd"] == 50


def test_serp_result_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._serp_count_to_score(50_000) == 20
    assert engine._serp_count_to_score(500_000) == 45
    assert engine._serp_count_to_score(5_000_000) == 65
    assert engine._serp_count_to_score(50_000_000) == 85


def test_brand_count_to_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._brand_count_to_score(0) == 10
    assert engine._brand_count_to_score(1) == 30
    assert engine._brand_count_to_score(3) == 55
    assert engine._brand_count_to_score(5) == 80


def test_title_count_to_score_buckets():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    assert engine._title_count_to_score(0) == 10
    assert engine._title_count_to_score(2) == 35
    assert engine._title_count_to_score(4) == 60
    assert engine._title_count_to_score(7) == 80


def test_progress_callback_called():
    from engines.annaseo_keyword_scorer import KeywordScoringEngine
    engine = KeywordScoringEngine()
    calls = []
    keywords = [
        {"keyword": "kw1", "relevance_score": 70},
        {"keyword": "kw2", "relevance_score": 70},
    ]
    with patch.object(engine, "_score_one_free", return_value={
        "kd": 30, "volume": 200, "serp_score": 30,
        "brand_score": 30, "title_score": 30, "autosuggest_vol": 200
    }), patch("time.sleep"):  # skip rate-limit sleep in tests
        engine.score_batch(keywords, on_progress=lambda scored, total: calls.append((scored, total)))
    assert calls == [(1, 2), (2, 2)]
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /root/ANNASEOv1 && ./venv/bin/python -m pytest tests/test_keyword_scorer.py -v 2>&1 | tail -20
```
Expected: `ImportError` or `ModuleNotFoundError` — engine doesn't exist yet.

- [ ] **Step 1.3: Create `engines/annaseo_keyword_scorer.py`**

```python
"""
engines/annaseo_keyword_scorer.py
KeywordScoringEngine — estimates KD and volume from free SERP signals.
Falls back to DataForSEO if DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD are set.
"""
from __future__ import annotations
import os, json, time, logging, re
from typing import List, Callable, Optional
import requests as _req

log = logging.getLogger("annaseo.keyword_scorer")

BIG_BRAND_DOMAINS = [
    "wikipedia.org", "amazon.", "flipkart.", "healthline.com",
    "webmd.com", "nhs.uk", ".gov.", ".edu.", "youtube.com",
    "reddit.com", "nykaa.com",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


class KeywordScoringEngine:
    """Score keywords using free SERP signals or DataForSEO (if configured)."""

    def score_batch(self, keywords: List[dict],
                    on_progress: Optional[Callable] = None) -> List[dict]:
        """Score keywords in-place. Each dict needs 'keyword' and 'relevance_score'.
        Returns same list with difficulty, volume_estimate, opportunity_score, score_signals updated."""
        if os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"):
            return self._dataforseo_score(keywords, on_progress)
        return self._free_score(keywords, on_progress)

    # ── Free scoring ──────────────────────────────────────────────────────────

    def _free_score(self, keywords: List[dict],
                    on_progress: Optional[Callable] = None) -> List[dict]:
        for i, kw_item in enumerate(keywords):
            try:
                signals = self._score_one_free(kw_item["keyword"])
            except Exception as e:
                log.warning(f"[Scorer] Error scoring '{kw_item['keyword']}': {e}")
                signals = {"kd": 50, "volume": 20, "serp_score": 50,
                           "brand_score": 50, "title_score": 50, "autosuggest_vol": 20}
            kw_item["difficulty"] = signals["kd"]
            kw_item["volume_estimate"] = signals["volume"]
            rel = kw_item.get("relevance_score", 50) / 100
            vol_n = min(signals["volume"] / 1000, 1.0)
            kd_n = signals["kd"] / 100
            kw_item["opportunity_score"] = round(vol_n * (1 - kd_n) * rel * 100, 1)
            kw_item["score_signals"] = json.dumps(signals)
            if on_progress:
                on_progress(i + 1, len(keywords))
            time.sleep(0.5)  # rate-limit to avoid blocks
        return keywords

    def _score_one_free(self, keyword: str) -> dict:
        autosuggest_vol = self._autosuggest_volume(keyword)
        serp_html, serp_count = self._fetch_duckduckgo(keyword)
        serp_score = self._serp_count_to_score(serp_count)
        brand_score = self._big_brand_score_from_html(serp_html, keyword)
        title_score = self._exact_title_score_from_html(serp_html, keyword)
        kd = round(serp_score * 0.35 + brand_score * 0.35 + title_score * 0.30)
        return {
            "kd": kd, "volume": autosuggest_vol,
            "serp_score": serp_score, "brand_score": brand_score,
            "title_score": title_score, "autosuggest_vol": autosuggest_vol,
        }

    def _fetch_duckduckgo(self, keyword: str) -> tuple[str, int]:
        """Fetch DuckDuckGo HTML search results. Returns (html, result_count)."""
        try:
            r = _req.get(
                "https://html.duckduckgo.com/html/",
                params={"q": keyword},
                headers=HEADERS,
                timeout=8,
            )
            if not r.ok:
                return "", 0
            html = r.text
            # Parse result count from "About X results" text
            m = re.search(r"About ([\d,]+) results", html)
            count = int(m.group(1).replace(",", "")) if m else 500_000
            return html, count
        except Exception as e:
            log.debug(f"[Scorer] DDG fetch failed: {e}")
            return "", 500_000

    def _serp_count_to_score(self, count: int) -> int:
        """Map result count to 0-100 KD signal."""
        if count < 100_000:   return 20
        if count < 1_000_000: return 45
        if count < 10_000_000: return 65
        return 85

    def _big_brand_score_from_html(self, html: str, keyword: str) -> int:
        """Count big-brand domains in DDG top results and map to 0-100 score."""
        count = sum(1 for domain in BIG_BRAND_DOMAINS if domain in html[:8000])
        return self._brand_count_to_score(count)

    def _brand_count_to_score(self, count: int) -> int:
        if count == 0: return 10
        if count == 1: return 30
        if count <= 3: return 55
        return 80

    def _exact_title_score_from_html(self, html: str, keyword: str) -> int:
        """Count pages with keyword in <title> tags in DDG results."""
        titles = re.findall(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        kl = keyword.lower()
        count = sum(1 for t in titles if kl in t.lower())
        return self._title_count_to_score(count)

    def _title_count_to_score(self, count: int) -> int:
        if count == 0: return 10
        if count <= 2: return 35
        if count <= 5: return 60
        return 80

    def _autosuggest_volume(self, keyword: str) -> int:
        """Estimate monthly volume from Google Autosuggest position."""
        words = keyword.split()
        if len(words) < 2:
            return 30
        prefix = " ".join(words[:-1])
        try:
            r = _req.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "q": prefix},
                headers=HEADERS,
                timeout=5,
            )
            if r.ok:
                suggestions = r.json()[1] if len(r.json()) > 1 else []
                kl = keyword.lower()
                for i, s in enumerate(suggestions[:10]):
                    if kl in str(s).lower() or str(s).lower() in kl:
                        if i < 3:   return 600
                        if i < 7:   return 250
                        return 80
        except Exception as e:
            log.debug(f"[Scorer] Autosuggest failed: {e}")
        return 30

    # ── Testable bucket methods (exposed for unit tests) ─────────────────────

    def _serp_result_score(self, keyword: str) -> int:
        _, count = self._fetch_duckduckgo(keyword)
        return self._serp_count_to_score(count)

    def _big_brand_score(self, keyword: str) -> int:
        html, _ = self._fetch_duckduckgo(keyword)
        return self._big_brand_score_from_html(html, keyword)

    def _exact_title_score(self, keyword: str) -> int:
        html, _ = self._fetch_duckduckgo(keyword)
        return self._exact_title_score_from_html(html, keyword)

    # ── DataForSEO fallback ───────────────────────────────────────────────────

    def _dataforseo_score(self, keywords: List[dict],
                          on_progress: Optional[Callable] = None) -> List[dict]:
        import base64
        login = os.getenv("DATAFORSEO_LOGIN")
        pwd = os.getenv("DATAFORSEO_PASSWORD")
        token = base64.b64encode(f"{login}:{pwd}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        kw_list = [k["keyword"] for k in keywords]
        batches = [kw_list[i:i+100] for i in range(0, len(kw_list), 100)]
        kw_map = {}
        for batch in batches[:5]:
            try:
                r = _req.post(
                    "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live",
                    headers=headers,
                    json=[{"keywords": batch, "language_name": "English", "location_code": 2356}],
                    timeout=30,
                )
                if r.ok:
                    for task in r.json().get("tasks", []):
                        for item in task.get("result", []) or []:
                            kw_map[item.get("keyword", "")] = {
                                "vol": item.get("search_volume", 0) or 0,
                                "kd": item.get("competition_index", 50) or 50,
                            }
            except Exception as e:
                log.warning(f"[Scorer] DataForSEO batch failed: {e}")
        for i, kw_item in enumerate(keywords):
            data = kw_map.get(kw_item["keyword"], {"vol": 30, "kd": 50})
            kw_item["difficulty"] = data["kd"]
            kw_item["volume_estimate"] = data["vol"]
            rel = kw_item.get("relevance_score", 50) / 100
            vol_n = min(data["vol"] / 1000, 1.0)
            kd_n = data["kd"] / 100
            kw_item["opportunity_score"] = round(vol_n * (1 - kd_n) * rel * 100, 1)
            kw_item["score_signals"] = json.dumps({"source": "dataforseo", **data})
            if on_progress:
                on_progress(i + 1, len(keywords))
        return keywords
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
cd /root/ANNASEOv1 && ./venv/bin/python -m pytest tests/test_keyword_scorer.py -v 2>&1 | tail -20
```
Expected: All 7 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
cd /root/ANNASEOv1
git add engines/annaseo_keyword_scorer.py tests/test_keyword_scorer.py
git commit -m "feat(scorer): add KeywordScoringEngine with 4 free SERP signals + DataForSEO fallback"
```

---

## Task 2: Migrate KI engine DB — add `score_signals` column + fix opp_score scale

**Files:**
- Modify: `engines/annaseo_keyword_input.py` lines ~160–167 (`_db()` function, after `con.commit()`)
- Modify: `engines/annaseo_keyword_input.py` lines ~515–530 (`GoogleKeywordEnricher._free_enrich`)

- [ ] **Step 2.1: Add `score_signals` column migration to `_db()` in `annaseo_keyword_input.py`**

After the `con.commit()` line inside `_db()` (around line 167), add:

```python
    # Migration: add columns introduced after initial schema
    for _sql in [
        "ALTER TABLE keyword_universe_items ADD COLUMN ai_score REAL DEFAULT 0.0",
        "ALTER TABLE keyword_universe_items ADD COLUMN ai_flags TEXT DEFAULT '[]'",
        "ALTER TABLE keyword_universe_items ADD COLUMN score_signals TEXT DEFAULT '{}'",
    ]:
        try:
            con.execute(_sql)
            con.commit()
        except Exception:
            pass  # column already exists
    return con
```

> Note: The `ai_score` and `ai_flags` migrations may already exist in `main.py`'s `_init_db`. Adding them here too (with try/except) is safe and ensures the KI DB is always up to date when `_db()` is called.

- [ ] **Step 2.2: Fix `GoogleKeywordEnricher._free_enrich` to store opp_score as 0–100**

Find `_free_enrich` in `annaseo_keyword_input.py` (around line 515). Change:
```python
            kw_item["opportunity_score"] = round(
                (vol / 100) * (1 - diff / 100) * (rel / 100) * 100, 1
            )
```
to:
```python
            kw_item["opportunity_score"] = round(
                min(vol / 1000, 1.0) * (1 - diff / 100) * (rel / 100) * 100, 1
            )
```
This makes the stored value 0–100 (previously it was already ~0–100 but used a different volume scale — this aligns it with the new scorer's formula).

- [ ] **Step 2.3: Verify DB migration runs without error**

```bash
cd /root/ANNASEOv1 && ./venv/bin/python3 -c "
from engines.annaseo_keyword_input import _db
db = _db()
cols = [row[1] for row in db.execute('PRAGMA table_info(keyword_universe_items)').fetchall()]
print('Columns:', cols)
assert 'score_signals' in cols, 'score_signals column missing!'
print('OK — score_signals column present')
db.close()
"
```
Expected output: `OK — score_signals column present`

- [ ] **Step 2.4: Commit**

```bash
cd /root/ANNASEOv1
git add engines/annaseo_keyword_input.py
git commit -m "feat(ki-db): add score_signals column migration + fix opp_score to 0-100 scale"
```

---

## Task 3: Update `ReviewManager.get_review_queue()` — add sort_by, intent filter, optional status

**Files:**
- Modify: `engines/annaseo_keyword_input.py` — `ReviewManager.get_review_queue()` method (~line 721)

- [ ] **Step 3.1: Replace `get_review_queue` method**

Find the current method (around line 721):
```python
    def get_review_queue(self, session_id: str, pillar: str = None,
                          status: str = "pending", limit: int = 100,
                          offset: int = 0) -> List[dict]:
        con = _db()
        q = "SELECT * FROM keyword_universe_items WHERE session_id=? AND status=?"
        p = [session_id, status]
        if pillar:
            q += " AND pillar_keyword=?"
            p.append(pillar)
        q += " ORDER BY opportunity_score DESC, relevance_score DESC LIMIT ? OFFSET ?"
        p += [limit, offset]
        return [dict(r) for r in con.execute(q, p).fetchall()]
```

Replace with:
```python
    def get_review_queue(self, session_id: str, pillar: str = None,
                          status: str = None, intent: str = None,
                          sort_by: str = "opp_desc",
                          limit: int = 100, offset: int = 0) -> List[dict]:
        con = _db()
        q = "SELECT * FROM keyword_universe_items WHERE session_id=?"
        p: list = [session_id]
        if status and status != "all":
            q += " AND status=?"
            p.append(status)
        if pillar:
            q += " AND pillar_keyword=?"
            p.append(pillar)
        if intent:
            q += " AND intent=?"
            p.append(intent)
        sort_map = {
            "opp_desc": "opportunity_score DESC, relevance_score DESC",
            "kd_asc":   "difficulty ASC",
            "vol_desc":  "volume_estimate DESC",
            "kw_asc":    "keyword ASC",
        }
        q += f" ORDER BY {sort_map.get(sort_by, 'opportunity_score DESC')} LIMIT ? OFFSET ?"
        p += [limit, offset]
        return [dict(r) for r in con.execute(q, p).fetchall()]
```

- [ ] **Step 3.2: Verify the change with a quick test**

```bash
cd /root/ANNASEOv1 && ./venv/bin/python3 -c "
from engines.annaseo_keyword_input import ReviewManager
rm = ReviewManager()
# Calling with no status should not crash
result = rm.get_review_queue('nonexistent_session', status=None, sort_by='kd_asc')
print('OK — returns:', result)
# Calling with sort_by='vol_desc'
result2 = rm.get_review_queue('nonexistent_session', sort_by='vol_desc', intent='transactional')
print('OK — intent filter works:', result2)
"
```
Expected: `OK — returns: []` (no rows, but no crash)

- [ ] **Step 3.3: Commit**

```bash
cd /root/ANNASEOv1
git add engines/annaseo_keyword_input.py
git commit -m "feat(review-manager): add sort_by, intent filter, optional status to get_review_queue"
```

---

## Task 4: Add backend endpoints — score POST/GET, bulk delete, enhance review queue + by-pillar

**Files:**
- Modify: `main.py` — multiple locations

### 4a — Add `_score_jobs` dict and score endpoints

- [ ] **Step 4.1: Add `_score_jobs` dict near `_research_jobs`**

Find line ~1259 in `main.py` where `_research_jobs` is declared:
```python
_research_jobs: dict = {}   # in-memory job tracker (job_id → status dict)
```

Add below it:
```python
_score_jobs: dict = {}      # in-memory scorer job tracker (job_id → status dict)
```

- [ ] **Step 4.2: Import `KeywordScoringEngine` near other engine imports**

Find the `try` block that imports `WiredRufloOrchestrator` or `KeywordInputEngine`. Add after the KI engine import block (around line 1021):

```python
try:
    from engines.annaseo_keyword_scorer import KeywordScoringEngine as _KSE
    _kse = _KSE()
    log.info("[main] KeywordScoringEngine loaded")
except Exception as _kse_err:
    _kse = None
    log.warning(f"[main] KeywordScoringEngine not loaded: {_kse_err}")
```

- [ ] **Step 4.3: Add score background task function**

Add before the `# ── Routes ──` comment near line 1435:

```python
def _run_score_job(job_id: str, project_id: str, session_id: str):
    """Background task: score all keyword_universe_items for a session."""
    try:
        from engines.annaseo_keyword_input import _db as _ki_db_fn
        ki_db = _ki_db_fn()
        rows = ki_db.execute(
            "SELECT item_id, keyword, relevance_score FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchall()
        keywords = [dict(r) for r in rows]
        _score_jobs[job_id]["total"] = len(keywords)

        scorer = _kse or _KSE()

        def _progress(scored, total):
            _score_jobs[job_id]["scored"] = scored

        scored_kws = scorer.score_batch(keywords, on_progress=_progress)

        for kw in scored_kws:
            ki_db.execute(
                """UPDATE keyword_universe_items
                   SET difficulty=?, volume_estimate=?, opportunity_score=?, score_signals=?
                   WHERE item_id=?""",
                (kw["difficulty"], kw["volume_estimate"],
                 kw["opportunity_score"], kw.get("score_signals", "{}"),
                 kw["item_id"])
            )
        ki_db.commit()
        ki_db.close()
        _score_jobs[job_id]["status"] = "completed"
        _score_jobs[job_id]["scored"] = len(scored_kws)
    except Exception as e:
        log.error(f"[Score job {job_id}] Failed: {e}")
        _score_jobs[job_id]["status"] = "failed"
        _score_jobs[job_id]["error"] = str(e)
```

- [ ] **Step 4.4: Add score POST and GET endpoints**

Add after the `ki_research_status` endpoint (around line 1487):

```python
@app.post("/api/ki/{project_id}/score/{session_id}")
async def ki_score_start(project_id: str, session_id: str,
                          bg: BackgroundTasks, user=Depends(current_user)):
    """Start keyword scoring job for a session."""
    from engines.annaseo_keyword_input import _db as _ki_db_fn
    ki_db = _ki_db_fn()
    total = ki_db.execute(
        "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=?", (session_id,)
    ).fetchone()[0]
    ki_db.close()
    if total == 0:
        raise HTTPException(404, "No keywords found for this session")
    job_id = f"score_{uuid.uuid4().hex[:12]}"
    _score_jobs[job_id] = {"status": "running", "scored": 0, "total": total, "error": ""}
    bg.add_task(_run_score_job, job_id, project_id, session_id)
    return {"job_id": job_id, "total": total}


@app.get("/api/ki/{project_id}/score/{session_id}/{job_id}")
async def ki_score_status(project_id: str, session_id: str, job_id: str,
                           user=Depends(current_user)):
    """Poll keyword scoring job status."""
    if job_id not in _score_jobs:
        raise HTTPException(404, "Score job not found")
    return _score_jobs[job_id]
```

### 4b — Add bulk delete endpoint

- [ ] **Step 4.5: Add DELETE endpoint for bulk keyword removal**

Add after the `ki_score_status` endpoint:

```python
@app.delete("/api/ki/{project_id}/review/{session_id}/items")
async def ki_bulk_delete(project_id: str, session_id: str,
                          body: dict = Body(default={}), user=Depends(current_user)):
    """Permanently delete keywords from the review queue."""
    item_ids = body.get("item_ids", [])
    if not item_ids:
        raise HTTPException(400, "item_ids required")
    from engines.annaseo_keyword_input import _db as _ki_db_fn
    ki_db = _ki_db_fn()
    placeholders = ",".join("?" * len(item_ids))
    result = ki_db.execute(
        f"DELETE FROM keyword_universe_items WHERE session_id=? AND item_id IN ({placeholders})",
        [session_id] + item_ids
    )
    ki_db.commit()
    ki_db.close()
    return {"deleted": result.rowcount}
```

### 4c — Enhance `ki_review_queue` and `ki_by_pillar`

- [ ] **Step 4.6: Replace `ki_review_queue` with enhanced version**

Find `ki_review_queue` (around line 1093 inside the KI try/except block). Replace the entire function body with:

```python
    @app.get("/api/ki/{project_id}/review/{session_id}", tags=["KeywordInput"])
    def ki_review_queue(
        project_id: str, session_id: str,
        pillar: Optional[str] = None,
        intent: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: str = "opp_desc",
        limit: int = 40, offset: int = 0,
        user=Depends(current_user)
    ):
        """Get paginated keyword review queue with optional sort/filter."""
        from engines.annaseo_keyword_input import ReviewManager
        rm = ReviewManager()
        keywords = rm.get_review_queue(
            session_id=session_id,
            pillar=pillar, status=status, intent=intent,
            sort_by=sort_by, limit=limit, offset=offset,
        )
        db = _ki_db()
        stats_rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM keyword_universe_items WHERE session_id=? GROUP BY status",
            (session_id,)
        ).fetchall()
        stats = {r["status"]: r["cnt"] for r in stats_rows}
        total_count = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        quick_wins = db.execute(
            "SELECT COUNT(*) FROM keyword_universe_items WHERE session_id=? AND difficulty<=20 AND volume_estimate>=100",
            (session_id,)
        ).fetchone()[0]
        avg_kd_row = db.execute(
            "SELECT AVG(difficulty) FROM keyword_universe_items WHERE session_id=?",
            (session_id,)
        ).fetchone()[0]
        avg_kd = round(avg_kd_row, 1) if avg_kd_row else 50
        db.close()
        return {
            "keywords": keywords,
            "total": total_count,
            "stats": {
                "total": total_count,
                "pending":  stats.get("pending", 0),
                "accepted": stats.get("accepted", 0),
                "rejected": stats.get("rejected", 0),
                "quick_wins": quick_wins,
                "avg_kd": avg_kd,
            }
        }
```

- [ ] **Step 4.7: Replace `ki_by_pillar` with enhanced version**

Find `ki_by_pillar` (around line 1193). Replace the SQL query:

```python
    @app.get("/api/ki/{project_id}/universe/{session_id}/by-pillar", tags=["KeywordInput"])
    def ki_by_pillar(project_id: str, session_id: str, user=Depends(current_user)):
        """Get universe grouped by pillar_keyword with counts and score averages."""
        db = _ki_db()
        rows = db.execute(
            """
            SELECT pillar_keyword as pillar,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
                   SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END) as pending,
                   ROUND(AVG(opportunity_score), 1) as avg_opp_score,
                   ROUND(AVG(difficulty), 1) as avg_kd
            FROM keyword_universe_items
            WHERE session_id=?
            GROUP BY pillar_keyword ORDER BY pillar_keyword
            """,
            (session_id,)
        ).fetchall()
        db.close()
        return {"pillars": [dict(r) for r in rows]}
```

- [ ] **Step 4.8: Verify import and restart service**

```bash
cd /root/ANNASEOv1
./venv/bin/python3 -c "import main; print('OK')" 2>&1
systemctl restart annaseo && sleep 2 && systemctl is-active annaseo
```
Expected: `OK` then `active`

- [ ] **Step 4.9: Smoke-test new endpoints**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=apitest%40test.com&password=testpass" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Test score start
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/ki/proj_e2e8f52959/score/kis_proj_e2e8f52959_1774412167 \
  | python3 -m json.tool

# Test bulk delete (with fake ids — expect deleted:0 not an error)
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"item_ids":["fake_id"]}' \
  http://localhost:8000/api/ki/proj_e2e8f52959/review/kis_proj_e2e8f52959_1774412167/items \
  | python3 -m json.tool

# Test review queue with sort + intent filter
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/ki/proj_e2e8f52959/review/kis_proj_e2e8f52959_1774412167?sort_by=kd_asc&limit=5" \
  | python3 -m json.tool | head -30
```
Expected: score start → `{"job_id":"score_...","total":76}`, delete → `{"deleted":0}`, review → keywords array + stats with `quick_wins` and `avg_kd`

- [ ] **Step 4.10: Commit**

```bash
cd /root/ANNASEOv1
git add main.py
git commit -m "feat(api): add score endpoints + bulk delete + enhanced review queue + by-pillar averages"
```

---

## Task 5: Replace `StepReview` in `KeywordWorkflow.jsx`

**Files:**
- Modify: `frontend/src/KeywordWorkflow.jsx` — replace `StepReview` function (lines ~437–610)

The new component has 4 sub-sections: stat cards, sidebar, toolbar, table. Build them in order.

- [ ] **Step 5.1: Replace `StepReview` with the new implementation**

Find and replace the entire `StepReview` function in `KeywordWorkflow.jsx`. The function starts at the comment `// STEP 3 — UNIFIED REVIEW` and ends just before `// STEP 4`. Replace with:

```jsx
// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 — UNIFIED REVIEW (Score Dashboard + Pillar Sidebar + Table)
// ─────────────────────────────────────────────────────────────────────────────

function StepReview({ projectId, sessionId, onComplete, onBack }) {
  const [filterPillar, setFilterPillar] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterIntent, setFilterIntent] = useState("all")
  const [sortBy, setSortBy]             = useState("opp_desc")
  const [page, setPage]                 = useState(0)
  const [selected, setSelected]         = useState(new Set())
  const [scoreJobId, setScoreJobId]     = useState(null)
  const [scoreProgress, setScoreProgress] = useState(null)  // {scored, total}
  const [showScorePanel, setShowScorePanel] = useState(false)
  const [editModal, setEditModal]       = useState(null)  // {items: [{id,keyword},...]}
  const [movePillarModal, setMovePillarModal] = useState(null) // {pillarChoices:[...]}
  const PAGE_SIZE = 40
  const queryClient = useQueryClient()

  // ── Data fetching ──────────────────────────────────────────────────────────

  const { data, refetch } = useQuery({
    queryKey: ["ki-review", projectId, sessionId, filterPillar, filterStatus,
                filterIntent, sortBy, page],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: PAGE_SIZE, offset: page * PAGE_SIZE, sort_by: sortBy,
        ...(filterPillar !== "all" ? { pillar: filterPillar } : {}),
        ...(filterStatus !== "all" ? { status: filterStatus } : {}),
        ...(filterIntent !== "all" ? { intent: filterIntent } : {}),
      })
      return apiCall(`/api/ki/${projectId}/review/${sessionId}?${params}`)
    },
    enabled: !!sessionId,
    refetchInterval: false,
  })

  const { data: pillarData, refetch: refetchPillars } = useQuery({
    queryKey: ["ki-pillars", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/universe/${sessionId}/by-pillar`),
    enabled: !!sessionId,
  })

  // Poll score job
  useEffect(() => {
    if (!scoreJobId) return
    const iv = setInterval(async () => {
      try {
        const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}/${scoreJobId}`)
        setScoreProgress({ scored: r.scored, total: r.total, status: r.status })
        if (r.status === "completed" || r.status === "failed") {
          clearInterval(iv)
          setScoreJobId(null)
          if (r.status === "completed") {
            refetch()
            refetchPillars()
            queryClient.invalidateQueries(["ki-review"])
          }
        }
      } catch { clearInterval(iv) }
    }, 2000)
    return () => clearInterval(iv)
  }, [scoreJobId])

  // ── Actions ────────────────────────────────────────────────────────────────

  const doAction = async (keyword_id, action, extra = {}) => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/action`, "POST",
      { keyword_id, action, ...extra })
    refetch()
    refetchPillars()
  }

  const acceptAll = async () => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/accept-all`, "POST",
      filterPillar !== "all" ? { pillar: filterPillar } : {})
    setSelected(new Set())
    refetch()
    refetchPillars()
  }

  const bulkAcceptReject = async (action) => {
    if (!selected.size) return
    await Promise.all([...selected].map(id => doAction(id, action)))
    setSelected(new Set())
  }

  const bulkDelete = async () => {
    if (!selected.size) return
    if (!window.confirm(`Delete ${selected.size} keyword(s) permanently?`)) return
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/items`, "DELETE",
      { item_ids: [...selected] })
    setSelected(new Set())
    refetch()
    refetchPillars()
  }

  const startScoring = async () => {
    setShowScorePanel(true)
    try {
      const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}`, "POST", {})
      setScoreJobId(r.job_id)
      setScoreProgress({ scored: 0, total: r.total, status: "running" })
    } catch (e) {
      alert("Scoring failed to start: " + e)
    }
  }

  const toggleRow = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = (checked) => {
    setSelected(checked ? new Set(keywords.map(k => k.item_id)) : new Set())
  }

  // ── Derived data ───────────────────────────────────────────────────────────

  const keywords  = data?.keywords || []
  const total     = data?.total || 0
  const stats     = data?.stats || {}
  const pillars   = pillarData?.pillars || []
  const allAccepted = stats.accepted || 0

  const kdColor = (kd) => kd <= 20 ? T.green : kd <= 50 ? T.amber : T.red
  const oppColor = (s) => s >= 75 ? T.green : s >= 50 ? T.amber : T.red
  const volColor = (v) => v >= 500 ? T.purple : v >= 200 ? T.teal : T.textSoft
  const fmtVol = (v) => v >= 1000 ? (v/1000).toFixed(1)+"K" : String(v || 0)

  const inStyle = {
    padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`,
    fontSize: 12, background: T.bgLight, color: T.text,
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
        <div>
          <div style={{ fontSize:15, fontWeight:700 }}>Step 3 — Unified Review</div>
          <div style={{ fontSize:11, color:T.textSoft }}>
            Session: {sessionId?.slice(-16)}… · Method 1 + 2 merged
          </div>
        </div>
        <Btn variant="primary" onClick={startScoring}
          disabled={!!scoreJobId}>
          {scoreJobId ? `⚡ Scoring… ${scoreProgress?.scored||0}/${scoreProgress?.total||0}` : "⚡ Score Keywords"}
        </Btn>
      </div>

      {/* Stat cards */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:8, marginBottom:12 }}>
        {[
          { label:"Total",       val: stats.total || 0,     color: T.text },
          { label:"Pending",     val: stats.pending || 0,   color: T.amber },
          { label:"Accepted",    val: stats.accepted || 0,  color: T.green },
          { label:"Rejected",    val: stats.rejected || 0,  color: T.red },
          { label:"Quick Wins",  val: stats.quick_wins != null ? stats.quick_wins : "—",
            color: T.teal, sub: "KD≤20 · Vol≥100" },
          { label:"Avg KD",
            val: (stats.avg_kd && stats.avg_kd !== 50) ? stats.avg_kd : "—",
            color: stats.avg_kd <= 20 ? T.green : stats.avg_kd <= 50 ? T.amber : T.red },
        ].map(s => (
          <Card key={s.label} style={{ padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:20, fontWeight:800, color:s.color }}>{s.val}</div>
            <div style={{ fontSize:10, color:T.textSoft }}>{s.label}</div>
            {s.sub && <div style={{ fontSize:9, color:s.color }}>{s.sub}</div>}
          </Card>
        ))}
      </div>

      {/* Score progress bar */}
      {scoreProgress && scoreProgress.status === "running" && (
        <div style={{ marginBottom:10, padding:"8px 12px", background:"#fffbeb",
                      border:`1px solid ${T.amber}`, borderRadius:8, fontSize:12 }}>
          <div style={{ marginBottom:5, color:"#92400e" }}>
            <b>⚡ Scoring in progress…</b> {scoreProgress.scored} / {scoreProgress.total} keywords
          </div>
          <div style={{ height:4, background:"#fef3c7", borderRadius:2, overflow:"hidden" }}>
            <div style={{
              height:"100%", background:T.amber, borderRadius:2,
              width: `${scoreProgress.total ? (scoreProgress.scored/scoreProgress.total*100) : 0}%`,
              transition:"width .3s"
            }}/>
          </div>
        </div>
      )}

      {/* Main layout */}
      <div style={{ display:"flex", gap:10, alignItems:"flex-start" }}>

        {/* Pillar sidebar */}
        <Card style={{ width:160, flexShrink:0 }}>
          <div style={{ padding:"7px 10px", borderBottom:`1px solid ${T.border}`,
                        fontSize:10, fontWeight:700, color:T.textSoft,
                        textTransform:"uppercase", letterSpacing:".05em" }}>Pillars</div>
          {[{ pillar:"all", total: stats.total||0, avg_opp_score:null, avg_kd:null },
            ...pillars].map(p => {
            const active = filterPillar === p.pillar
            return (
              <div key={p.pillar}
                onClick={() => { setFilterPillar(p.pillar); setPage(0); setSelected(new Set()) }}
                style={{
                  padding:"7px 10px", cursor:"pointer",
                  background: active ? "#f0faf7" : "transparent",
                  borderLeft: `3px solid ${active ? T.teal : "transparent"}`,
                }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <span style={{ fontSize:12, fontWeight: active?700:400,
                                 color: active ? T.teal : T.text }}>
                    {p.pillar === "all" ? "All pillars" : p.pillar}
                  </span>
                  <span style={{ fontSize:10, color:T.textSoft }}>{p.total}</span>
                </div>
                {p.avg_opp_score != null && (
                  <div style={{ fontSize:9, color: oppColor(p.avg_opp_score), marginTop:1 }}>
                    Opp:{p.avg_opp_score} · KD:{p.avg_kd}
                  </div>
                )}
              </div>
            )
          })}
          {/* KD legend */}
          <div style={{ padding:"8px 10px", borderTop:`1px solid ${T.border}` }}>
            <div style={{ fontSize:9, fontWeight:700, color:T.textSoft,
                          textTransform:"uppercase", marginBottom:5 }}>KD Legend</div>
            {[["#16a34a","0–20 Easy"],["#d97706","21–50 Med"],["#dc2626","51+ Hard"]].map(([c,l]) => (
              <div key={l} style={{ display:"flex", alignItems:"center", gap:5, marginBottom:3 }}>
                <div style={{ width:8, height:8, borderRadius:2, background:c, flexShrink:0 }}/>
                <span style={{ fontSize:10, color:T.textSoft }}>{l}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Table area */}
        <div style={{ flex:1, minWidth:0 }}>

          {/* Bulk toolbar */}
          <Card style={{ padding:"7px 10px", marginBottom:8,
                         display:"flex", gap:6, alignItems:"center", flexWrap:"wrap" }}>
            <input type="checkbox"
              checked={selected.size > 0 && selected.size === keywords.length}
              onChange={e => toggleAll(e.target.checked)}
              style={{ width:13, height:13, cursor:"pointer" }}/>
            <span style={{ fontSize:11, color:T.textSoft, marginRight:4 }}>
              {selected.size > 0 ? `${selected.size} selected` : "0 selected"}
            </span>
            <div style={{ height:14, width:1, background:T.border, margin:"0 2px" }}/>
            <Btn small variant="teal"
              disabled={!selected.size} onClick={() => bulkAcceptReject("accept")}>✓ Accept</Btn>
            <Btn small style={{ background:"#fef2f2", borderColor:"#fca5a5", color:"#dc2626" }}
              disabled={!selected.size} onClick={() => bulkAcceptReject("reject")}>✕ Reject</Btn>
            <Btn small style={{ color:T.purple, borderColor:"#c4b5fd" }}
              disabled={!selected.size}
              onClick={() => {
                const items = keywords.filter(k => selected.has(k.item_id))
                  .map(k => ({ id: k.item_id, keyword: k.keyword }))
                setEditModal({ items })
              }}>✎ Edit</Btn>
            <Btn small style={{ color:T.amber, borderColor:"#fcd34d" }}
              disabled={!selected.size}
              onClick={() => setMovePillarModal({ choices: pillars.map(p => p.pillar) })}>
              ⇄ Move Pillar</Btn>
            <Btn small style={{ color:"#dc2626", borderColor:"#fca5a5" }}
              disabled={!selected.size} onClick={bulkDelete}>🗑 Delete</Btn>
            <div style={{ height:14, width:1, background:T.border, margin:"0 2px 0 auto" }}/>
            <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(0) }} style={inStyle}>
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
            <select value={filterIntent} onChange={e => { setFilterIntent(e.target.value); setPage(0) }} style={inStyle}>
              <option value="all">All Intent</option>
              <option value="transactional">Transactional</option>
              <option value="commercial">Commercial</option>
              <option value="informational">Informational</option>
            </select>
            <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={inStyle}>
              <option value="opp_desc">Sort: Opp Score ↓</option>
              <option value="kd_asc">Sort: KD ↑ (easiest)</option>
              <option value="vol_desc">Sort: Volume ↓</option>
              <option value="kw_asc">Sort: A→Z</option>
            </select>
            <Btn small variant="teal" onClick={acceptAll}>✓ Accept All Visible</Btn>
          </Card>

          {/* Table */}
          <Card style={{ padding:0, overflow:"hidden" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
              <thead>
                <tr style={{ background:T.grayLight, borderBottom:`1px solid ${T.border}` }}>
                  <th style={{ padding:"7px 10px", width:28 }}>
                    <input type="checkbox"
                      checked={selected.size > 0 && selected.size === keywords.length}
                      onChange={e => toggleAll(e.target.checked)}
                      style={{ width:13, height:13 }}/>
                  </th>
                  {[["Keyword",""], ["Pillar",""], ["Source",""], ["Intent",""],
                    ["KD","kd_asc"], ["Vol","vol_desc"], ["Opp Score","opp_desc"],
                    ["Status",""], ["",""]
                  ].map(([h, s]) => (
                    <th key={h} style={{ padding:"7px 10px", textAlign:"left",
                                        fontWeight:600, color:T.textSoft,
                                        cursor: s ? "pointer" : "default" }}
                      onClick={() => s && setSortBy(s)}>
                      {h}{s && sortBy===s ? " ↓" : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keywords.map((kw, i) => {
                  const isSel = selected.has(kw.item_id)
                  const statusColor = kw.status==="accepted"?"#16a34a":kw.status==="rejected"?"#dc2626":T.amber
                  const statusBg = kw.status==="accepted"?"#f0faf7":kw.status==="rejected"?"#fef2f2":"#fffbeb"
                  return (
                    <tr key={kw.item_id || i}
                      style={{ borderBottom:`1px solid ${T.border}`,
                               background: isSel ? "#f0faf7" : "transparent" }}>
                      <td style={{ padding:"6px 10px" }}>
                        <input type="checkbox" checked={isSel}
                          onChange={() => toggleRow(kw.item_id)}
                          style={{ width:13, height:13 }}/>
                      </td>
                      <td style={{ padding:"6px 10px", fontWeight:500 }}>{kw.keyword}</td>
                      <td style={{ padding:"6px 10px", color:T.teal, fontSize:11 }}>
                        {kw.pillar_keyword || "—"}
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <Badge color={SOURCE_COLORS[kw.source] || T.gray}>
                          {sourceLabel(kw.source)}
                        </Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <Badge color={intentColor(kw.intent)}>{kw.intent?.slice(0,6)}.</Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <span style={{ fontWeight:700, color: kdColor(kw.difficulty) }}>
                          {kw.difficulty ?? "—"}
                        </span>
                      </td>
                      <td style={{ padding:"6px 10px", fontWeight:600,
                                   color: volColor(kw.volume_estimate) }}>
                        {fmtVol(kw.volume_estimate)}
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:5 }}>
                          <div style={{ width:50, height:6, borderRadius:3,
                                        background:"#e5e7eb", overflow:"hidden" }}>
                            <div style={{ height:"100%", borderRadius:3,
                                          background: oppColor(kw.opportunity_score),
                                          width: `${kw.opportunity_score || 0}%` }}/>
                          </div>
                          <span style={{ fontSize:11, fontWeight:700,
                                         color: oppColor(kw.opportunity_score),
                                         minWidth:24 }}>
                            {kw.opportunity_score ?? "—"}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <Badge color={statusColor} style={{ background:statusBg }}>
                          {kw.status}
                        </Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <div style={{ display:"flex", gap:3 }}>
                          {kw.status !== "accepted" && (
                            <Btn small variant="teal" onClick={() => doAction(kw.item_id, "accept")}>✓</Btn>
                          )}
                          {kw.status !== "rejected" && (
                            <Btn small style={{ background:"#fef2f2", borderColor:"#fca5a5", color:"#dc2626" }}
                              onClick={() => doAction(kw.item_id, "reject")}>✕</Btn>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {keywords.length === 0 && (
                  <tr><td colSpan={10} style={{ padding:32, textAlign:"center", color:T.textSoft }}>
                    No keywords found. Complete Step 1 to add keywords.
                  </td></tr>
                )}
              </tbody>
            </table>
            {total > PAGE_SIZE && (
              <div style={{ padding:"7px 12px", display:"flex", gap:8, alignItems:"center",
                             borderTop:`1px solid ${T.border}`, background:T.grayLight }}>
                <Btn small disabled={page===0} onClick={() => setPage(p => p-1)}>← Prev</Btn>
                <span style={{ fontSize:11, color:T.textSoft }}>
                  Page {page+1} of {Math.ceil(total/PAGE_SIZE)} · {total} keywords
                </span>
                <Btn small disabled={(page+1)*PAGE_SIZE >= total}
                  onClick={() => setPage(p => p+1)}>Next →</Btn>
              </div>
            )}
          </Card>

        </div>
      </div>

      {/* Edit modal */}
      {editModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)",
                      display:"flex", alignItems:"center", justifyContent:"center", zIndex:200 }}>
          <Card style={{ width:400, padding:16 }}>
            <div style={{ fontWeight:700, marginBottom:8 }}>
              Edit {editModal.items.length} keyword(s)
            </div>
            <div style={{ fontSize:11, color:T.textSoft, marginBottom:8 }}>
              One keyword per line. Line count must match selection ({editModal.items.length}).
            </div>
            <textarea
              id="editTextarea"
              defaultValue={editModal.items.map(k => k.keyword).join("\n")}
              style={{ width:"100%", height:160, fontSize:12, fontFamily:"monospace",
                       padding:8, borderRadius:6, border:`1px solid ${T.border}`,
                       resize:"vertical", boxSizing:"border-box" }}
            />
            <div style={{ display:"flex", gap:8, marginTop:10 }}>
              <Btn onClick={() => setEditModal(null)}>Cancel</Btn>
              <Btn variant="primary" onClick={async () => {
                const lines = document.getElementById("editTextarea").value
                  .split("\n").map(l => l.trim()).filter(Boolean)
                if (lines.length !== editModal.items.length) {
                  alert(`Line count mismatch: expected ${editModal.items.length}, got ${lines.length}`)
                  return
                }
                await Promise.all(editModal.items.map((item, i) =>
                  doAction(item.id, "edit", { new_keyword: lines[i] })
                ))
                setEditModal(null)
                setSelected(new Set())
              }}>Save Changes</Btn>
            </div>
          </Card>
        </div>
      )}

      {/* Move pillar modal */}
      {movePillarModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)",
                      display:"flex", alignItems:"center", justifyContent:"center", zIndex:200 }}>
          <Card style={{ width:320, padding:16 }}>
            <div style={{ fontWeight:700, marginBottom:8 }}>
              Move {selected.size} keyword(s) to pillar:
            </div>
            {movePillarModal.choices.map(p => (
              <div key={p}
                onClick={async () => {
                  await Promise.all([...selected].map(id =>
                    doAction(id, "move_pillar", { new_pillar: p })
                  ))
                  setMovePillarModal(null)
                  setSelected(new Set())
                  refetch(); refetchPillars()
                }}
                style={{ padding:"8px 12px", cursor:"pointer", borderRadius:6,
                         border:`1px solid ${T.border}`, marginBottom:6,
                         color:T.teal, fontWeight:600 }}>
                {p}
              </div>
            ))}
            <Btn onClick={() => setMovePillarModal(null)} style={{ marginTop:4 }}>Cancel</Btn>
          </Card>
        </div>
      )}

      {/* Navigation */}
      <div style={{ display:"flex", justifyContent:"space-between", marginTop:12 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="primary"
          disabled={allAccepted === 0}
          onClick={() => onComplete({ acceptedCount: allAccepted })}
          style={{ padding:"8px 20px", fontSize:13, fontWeight:600 }}>
          Continue to AI Check → ({allAccepted} accepted)
        </Btn>
      </div>
    </div>
  )
}
```

Also add `useQueryClient` to the react-query import at the top of the file. Find the existing import line:
```js
import { useQuery, useMutation, QueryClient, QueryClientProvider } from "@tanstack/react-query"
```
and change to:
```js
import { useQuery, useMutation, useQueryClient, QueryClient, QueryClientProvider } from "@tanstack/react-query"
```

Also add the `sourceLabel` helper function near the existing `intentColor` helper if it doesn't exist (it was in the old StepReview but should be module-level):
```js
const sourceLabel = (src) => {
  const map = {
    cross_multiply: "User×", site_crawl: "Site", template: "Template",
    competitor_crawl: "Competitor", research_autosuggest: "Suggest",
    research_competitor_gap: "Gap", research_site_crawl: "Site2", strategy: "Strategy",
  }
  return map[src] || src
}
```

- [ ] **Step 5.2: Run frontend build**

```bash
cd /root/ANNASEOv1/frontend && npm run build 2>&1 | tail -15
```
Expected: `✓ built in X.XXs` with 0 errors.

If there are errors, fix them before proceeding. Common issues:
- `useQueryClient` not imported → add to the react-query import line
- `sourceLabel` not found → move it outside `StepReview` (module level)
- `T.bgLight` doesn't exist → use `T.grayLight` instead
- `T.purple` doesn't exist → check `T` object in the file for actual purple key

- [ ] **Step 5.3: Commit**

```bash
cd /root/ANNASEOv1
git add frontend/src/KeywordWorkflow.jsx
git commit -m "feat(step3): replace StepReview with Score Dashboard + Pillar Sidebar + bulk actions"
```

---

## Task 6: Verify end-to-end and restart service

- [ ] **Step 6.1: Verify all tests still pass**

```bash
cd /root/ANNASEOv1 && ./venv/bin/python -m pytest tests/test_keyword_scorer.py tests/test_health.py -v 2>&1 | tail -20
```
Expected: All tests PASS.

- [ ] **Step 6.2: Restart service and verify**

```bash
systemctl restart annaseo && sleep 2 && systemctl is-active annaseo
curl -s http://localhost:8000/api/health | python3 -m json.tool | grep all_ok
```
Expected: `"all_ok": true`

- [ ] **Step 6.3: Full browser verification checklist**

Open the app and navigate to Keywords → Workflow → complete Step 1 → proceed to Step 3.

Verify:
- [ ] Stat cards show Total, Pending, Accepted, Rejected (all show numbers)
- [ ] Quick Wins and Avg KD show "—" before scoring
- [ ] Pillar sidebar lists pillars with counts
- [ ] Clicking a pillar filters the table
- [ ] Sort dropdown changes keyword order
- [ ] Intent filter works
- [ ] Checkbox selects a row → bulk action buttons activate
- [ ] ✓ Accept and ✕ Reject buttons work per-row
- [ ] Bulk Accept and Reject work for selected rows
- [ ] ✎ Edit opens modal, saves to DB
- [ ] ⇄ Move Pillar opens modal, reassigns pillar
- [ ] 🗑 Delete removes keywords after confirm
- [ ] ⚡ Score Keywords starts scoring, progress bar shows, table refreshes on complete
- [ ] "Continue to AI Check →" is disabled when 0 accepted, shows count when accepted

- [ ] **Step 6.4: Final commit**

```bash
cd /root/ANNASEOv1
git add .
git commit -m "chore: Step 3 keyword review redesign complete — scorer + UI + bulk ops"
```
