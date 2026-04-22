# Content Plan Tab — Full Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 concrete breakdowns in the Content Plan / Blog Suggestions tab: 80-card hard cap, 20-item brief limit, missing start_date in rebuild, unreachable Regenerate Strategy button, and session-unscoped Generated count.

**Architecture:** All changes are contained in three files. The backend endpoint gains a `body` parameter to accept `start_date`. The frontend API helper forwards it. The `ContentPlanTab` React component (inside `SessionStrategyPage.jsx`) gains pagination, full brief batching, bulk generation, a sticky header with Regenerate shortcut, and session-scoped article tracking.

**Tech Stack:** React 18 + vitest (frontend), FastAPI + pytest (backend), SQLite

**Spec:** `docs/superpowers/specs/2026-04-17-content-plan-tab-rebuild-design.md`

---

## File Map

| File | Change |
|------|--------|
| `main.py:23855–23875` | `kw2_rebuild_calendar` — add `body: dict = Body(default={})`, pass `start_date` |
| `frontend/src/kw2/api.js:237–238` | `rebuildCalendar` — add `startDate` param, pass as `{ start_date }` body |
| `frontend/src/kw2/SessionStrategyPage.jsx:2372` | `ContentPlanTab` — add `onRegenerate` prop |
| `frontend/src/kw2/SessionStrategyPage.jsx:2384–2400` | `handleRebuildCalendar` — pass `startDate` in API call |
| `frontend/src/kw2/SessionStrategyPage.jsx:2418–2421` | `articleMap` — make session-scoped |
| `frontend/src/kw2/SessionStrategyPage.jsx:2571–2600` | Rebuild banner → sticky header with Regenerate + Rebuild buttons |
| `frontend/src/kw2/SessionStrategyPage.jsx:2594` | BatchBriefPanel call — remove `.slice(0, 20)` |
| `frontend/src/kw2/SessionStrategyPage.jsx:2230–2266` | `BatchBriefPanel.runBatch` — chunk loop replacing single batch |
| `frontend/src/kw2/SessionStrategyPage.jsx:2601–2650` | Controls row — add Bulk Generate All Pending button |
| `frontend/src/kw2/SessionStrategyPage.jsx:2664–2666` | Card grid — replace `filtered.slice(0, 80)` with pagination |
| `frontend/src/kw2/SessionStrategyPage.jsx:2667–2690` | Card — add "✓ Brief" badge |
| `frontend/src/kw2/SessionStrategyPage.jsx:5983` | `ContentPlanTab` call site — add `onRegenerate={handleRunPhase9}` |
| `tests/test_kw2_rebuild_calendar.py` | New: backend test for `start_date` wiring |
| `frontend/src/kw2/contentPlanUtils.test.js` | New: vitest unit tests for pagination + session-filter logic |

---

## Task 1: Backend — Wire `start_date` through rebuild endpoint

**Files:**
- Modify: `main.py:23855–23875`
- Create: `tests/test_kw2_rebuild_calendar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_kw2_rebuild_calendar.py`:

```python
"""
Tests for kw2_rebuild_calendar endpoint — verifies start_date is accepted and forwarded.

Run: pytest tests/test_kw2_rebuild_calendar.py -v
Requires: backend running on port 8000
"""
import os, sys, pytest, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://127.0.0.1:8000"

@pytest.fixture(scope="module")
def auth_header():
    r = requests.post(f"{BASE_URL}/api/auth/register",
        json={"email": "rebuild_cal_test@test.com", "name": "Test", "password": "pass1234"})
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        r = requests.post(f"{BASE_URL}/api/auth/login",
            data={"username": "rebuild_cal_test@test.com", "password": "pass1234"})
        token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="module")
def project_and_session(auth_header):
    """Create a minimal project + kw2 session to test rebuild against."""
    r = requests.post(f"{BASE_URL}/api/projects",
        json={"name": "Rebuild Cal Test Project", "domain": "test.com"},
        headers=auth_header)
    assert r.status_code == 200
    project_id = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/kw2/{project_id}/sessions",
        json={"mode": "brand", "name": "rebuild test"},
        headers=auth_header)
    assert r.status_code == 200
    session_id = r.json()["session_id"]
    return project_id, session_id

def test_rebuild_accepts_start_date_body(auth_header, project_and_session):
    """Endpoint must accept a JSON body with start_date without 422 Unprocessable Entity."""
    project_id, session_id = project_and_session
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild",
        json={"start_date": "2026-05-01"},
        headers=auth_header,
    )
    # 200 OK or 404 "Session not found" are both acceptable — 422 is the failure case
    assert r.status_code != 422, f"Endpoint rejected body: {r.text}"

def test_rebuild_accepts_empty_body(auth_header, project_and_session):
    """Endpoint must still work when called with no body (backwards-compatible)."""
    project_id, session_id = project_and_session
    r = requests.post(
        f"{BASE_URL}/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild",
        headers=auth_header,
    )
    assert r.status_code != 422, f"Endpoint rejected empty body: {r.text}"
```

- [ ] **Step 2: Run tests to confirm they fail (422 currently)**

```bash
cd /root/ANNASEOv1 && pytest tests/test_kw2_rebuild_calendar.py -v
```

Expected output: `FAILED — AssertionError: Endpoint rejected body` (because the endpoint doesn't accept a body yet)

- [ ] **Step 3: Apply the backend fix**

In `main.py`, replace lines 23855–23875 (the `@app.post` decorator + full function body):

**Before (lines 23855–23875):**
```python
@app.post("/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild", tags=["KW2"])
async def kw2_rebuild_calendar(
    project_id: str, session_id: str,
    user=Depends(current_user),
):
    """Rebuild content calendar from existing strategy + intelligence questions + keywords.
    No need to re-run Phase 9 — uses cached strategy output."""
    _validate_project_exists(project_id, user)
    session = kw2_db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Load existing strategy
    strat_engine = StrategyEngine()
    strategy = strat_engine.get_strategy(session_id) or {}

    cal = ContentCalendar()
    result = await asyncio.to_thread(
        cal.build_from_strategy, project_id, session_id, strategy,
    )
    return {"calendar": result}
```

**After:**
```python
@app.post("/api/kw2/{project_id}/sessions/{session_id}/calendar/rebuild", tags=["KW2"])
async def kw2_rebuild_calendar(
    project_id: str, session_id: str,
    body: dict = Body(default={}),
    user=Depends(current_user),
):
    """Rebuild content calendar from existing strategy + intelligence questions + keywords.
    No need to re-run Phase 9 — uses cached strategy output.
    Accepts optional start_date (ISO string) to anchor article publish dates."""
    _validate_project_exists(project_id, user)
    session = kw2_db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    start_date = body.get("start_date") or None

    # Load existing strategy
    strat_engine = StrategyEngine()
    strategy = strat_engine.get_strategy(session_id) or {}

    cal = ContentCalendar()
    result = await asyncio.to_thread(
        cal.build_from_strategy, project_id, session_id, strategy, start_date,
    )
    return {"calendar": result}
```

Note: `Body` is already imported at the top of `main.py` — no new import needed.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /root/ANNASEOv1 && pytest tests/test_kw2_rebuild_calendar.py -v
```

Expected: `PASSED` for both tests

- [ ] **Step 5: Commit**

```bash
cd /root/ANNASEOv1 && git add main.py tests/test_kw2_rebuild_calendar.py
git commit -m "$(cat <<'EOF'
fix(kw2): wire start_date through calendar rebuild endpoint

kw2_rebuild_calendar now accepts an optional start_date in the request
body and forwards it to build_from_strategy, fixing wrong article
publish dates after a manual rebuild.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Frontend API — Pass `start_date` in `rebuildCalendar`

**Files:**
- Modify: `frontend/src/kw2/api.js:237–238`

- [ ] **Step 1: Update the `rebuildCalendar` export**

In `frontend/src/kw2/api.js`, replace line 237–238:

**Before:**
```javascript
export const rebuildCalendar = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar/rebuild`, "POST")
```

**After:**
```javascript
export const rebuildCalendar = (projectId, sessionId, startDate) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar/rebuild`, "POST", { start_date: startDate || null })
```

- [ ] **Step 2: (Confirmed) `apiCall` supports a third body argument**

`apiCall` is defined in `frontend/src/lib/apiCall.js` with signature:
```javascript
export default async function apiCall(path, method = "GET", body = null, signal = null)
```
The third argument is the POST body — confirmed. No change needed to `apiCall` itself.

- [ ] **Step 3: Commit**

```bash
cd /root/ANNASEOv1 && git add frontend/src/kw2/api.js
git commit -m "$(cat <<'EOF'
fix(kw2): forward startDate from rebuildCalendar API call

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: ContentPlanTab — `onRegenerate` prop + sticky header + `handleRebuildCalendar` fix

**Files:**
- Modify: `frontend/src/kw2/SessionStrategyPage.jsx` (multiple hunks)

This task wires up the Regenerate Strategy shortcut and fixes `handleRebuildCalendar` to pass the start date.

- [ ] **Step 1: Add `onRegenerate` to ContentPlanTab function signature**

At line 2372, replace:
```javascript
function ContentPlanTab({ strat, calendarData, projectId, sessionId, startDate, refetchCalendar, chooseAI }) {
```
With:
```javascript
function ContentPlanTab({ strat, calendarData, projectId, sessionId, startDate, refetchCalendar, chooseAI, onRegenerate }) {
```

- [ ] **Step 2: Update `handleRebuildCalendar` to pass `startDate`**

Find the `handleRebuildCalendar` function (starts around line 2384). Replace:
```javascript
      const res = await api.rebuildCalendar(projectId, sessionId)
```
With:
```javascript
      const res = await api.rebuildCalendar(projectId, sessionId, startDate)
```

- [ ] **Step 3: Replace the rebuild banner with a sticky header**

Find the "Rebuild banner" comment block (around line 2571–2589):

**Before:**
```jsx
      {/* Rebuild banner */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: T.grayLight, borderRadius: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1, fontSize: 12, color: T.textSoft }}>
          <strong style={{ color: T.text }}>{primaryItems.length} blog ideas</strong>
          {" "}(strategy + intelligence questions + keywords)
          {rebuildResult && !rebuildResult.error && (
            <span style={{ color: T.teal, marginLeft: 8 }}>
              ✓ Rebuilt — {rebuildResult.from_strategy || 0} strategy · {rebuildResult.from_intelligence || 0} intelligence · {rebuildResult.from_keywords || 0} keywords
            </span>
          )}
        </div>
        <button onClick={handleRebuildCalendar} disabled={rebuilding}
          style={{ padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.border}`, background: "#fff", fontSize: 12, fontWeight: 600, cursor: rebuilding ? "not-allowed" : "pointer", color: T.purple }}>
          {rebuilding ? "⏳ Rebuilding…" : "🔄 Rebuild Content Plan"}
        </button>
      </div>
```

**After:**
```jsx
      {/* Sticky header — count + Regenerate + Rebuild */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: T.grayLight, borderRadius: 10, flexWrap: "wrap", position: "sticky", top: 0, zIndex: 2 }}>
        <div style={{ flex: 1, fontSize: 12, color: T.textSoft }}>
          <strong style={{ color: T.text }}>{primaryItems.length} blog ideas</strong>
          {" "}(strategy + intelligence questions + keywords)
          {rebuildResult && !rebuildResult.error && (
            <span style={{ color: T.teal, marginLeft: 8 }}>
              ✓ {rebuildResult.from_strategy || 0} strategy · {rebuildResult.from_intelligence || 0} intel · {rebuildResult.from_keywords || 0} keywords
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {onRegenerate && (
            <button onClick={() => {
              if (window.confirm("Re-run strategy generation? This will overwrite the current strategy.")) {
                onRegenerate()
              }
            }}
              style={{ padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.purple}`, background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", color: T.purple }}>
              🔄 Regenerate Strategy
            </button>
          )}
          <button onClick={handleRebuildCalendar} disabled={rebuilding}
            style={{ padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.border}`, background: "#fff", fontSize: 12, fontWeight: 600, cursor: rebuilding ? "not-allowed" : "pointer", color: T.textSoft }}>
            {rebuilding ? "⏳ Rebuilding…" : "↺ Rebuild Content Plan"}
          </button>
        </div>
      </div>
```

- [ ] **Step 4: Add `onRegenerate={handleRunPhase9}` to the ContentPlanTab call site**

Find line 5983 (the `<ContentPlanTab` JSX).

> **Note:** `handleRunPhase9` is defined at line 5625 in the outer `SessionStrategyPage` scope. It is the same function that `ContentParametersTab` receives as `onGenerate={handleRunPhase9}` at line 5957. The spec uses the alias `onGenerate` but the actual variable name in scope here is `handleRunPhase9` — use `handleRunPhase9` directly.

Replace:
```jsx
            <ContentPlanTab strat={strat} calendarData={calendarData} projectId={projectId} sessionId={sessionId} startDate={contentParams.start_date} refetchCalendar={refetchCalendar} chooseAI={chooseAI} />
```
With:
```jsx
            <ContentPlanTab strat={strat} calendarData={calendarData} projectId={projectId} sessionId={sessionId} startDate={contentParams.start_date} refetchCalendar={refetchCalendar} chooseAI={chooseAI} onRegenerate={handleRunPhase9} />
```

- [ ] **Step 5: Verify in browser**

Start the dev server if not running:
```bash
cd /root/ANNASEOv1/frontend && npm run dev
```

Navigate to a session with a strategy → Content Plan tab.
- Confirm the sticky header shows both "Regenerate Strategy" and "Rebuild Content Plan" buttons
- Click "Rebuild Content Plan" — confirm the calendar rebuilds (network tab shows `start_date` in the POST body)
- Click "Regenerate Strategy" — confirm the confirm dialog appears

- [ ] **Step 6: Commit**

```bash
cd /root/ANNASEOv1 && git add frontend/src/kw2/SessionStrategyPage.jsx
git commit -m "$(cat <<'EOF'
feat(content-plan): add Regenerate Strategy shortcut + fix rebuild start_date

- Sticky header with Regenerate Strategy button wired to handleRunPhase9
- handleRebuildCalendar now passes startDate so article dates are correct
- onRegenerate prop added to ContentPlanTab

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: ContentPlanTab — Pagination + session-scoped `articleMap`

**Files:**
- Modify: `frontend/src/kw2/SessionStrategyPage.jsx` (two hunks)
- Create: `frontend/src/kw2/contentPlanUtils.test.js`

- [ ] **Step 1: Write vitest unit tests for the pure logic**

Create `frontend/src/kw2/contentPlanUtils.test.js`:

```javascript
import { test, expect } from 'vitest'

// ── Pagination helpers ────────────────────────────────────────────────────────

function paginate(items, page, pageSize) {
  return items.slice(page * pageSize, (page + 1) * pageSize)
}

function totalPages(items, pageSize) {
  return Math.ceil(items.length / pageSize)
}

test('paginate returns correct slice for page 0', () => {
  const items = Array.from({ length: 507 }, (_, i) => i)
  expect(paginate(items, 0, 50)).toEqual(items.slice(0, 50))
})

test('paginate returns correct slice for last page', () => {
  const items = Array.from({ length: 507 }, (_, i) => i)
  const lastPage = totalPages(items, 50) - 1  // page 10 (0-indexed)
  const result = paginate(items, lastPage, 50)
  expect(result).toEqual(items.slice(500, 507))
  expect(result.length).toBe(7)
})

test('totalPages for 507 items at 50/page is 11', () => {
  const items = Array.from({ length: 507 })
  expect(totalPages(items, 50)).toBe(11)
})

test('totalPages for exactly 50 items is 1', () => {
  expect(totalPages(Array.from({ length: 50 }), 50)).toBe(1)
})

// ── Session-scoped articleMap ─────────────────────────────────────────────────

function buildSessionArticleMap(articleList, calendarKeywords) {
  const map = {}
  articleList
    .filter(a => calendarKeywords.has((a.keyword || '').toLowerCase()))
    .forEach(a => { map[(a.keyword || '').toLowerCase()] = a })
  return map
}

test('buildSessionArticleMap excludes articles not in calendar', () => {
  const articles = [
    { keyword: 'spices online', status: 'published' },
    { keyword: 'other project topic', status: 'published' },
  ]
  const calendarKeywords = new Set(['spices online'])
  const map = buildSessionArticleMap(articles, calendarKeywords)
  expect(Object.keys(map)).toEqual(['spices online'])
  expect(map['other project topic']).toBeUndefined()
})

test('buildSessionArticleMap is case-insensitive', () => {
  const articles = [{ keyword: 'Kerala Spices', status: 'draft' }]
  const calendarKeywords = new Set(['kerala spices'])
  const map = buildSessionArticleMap(articles, calendarKeywords)
  expect(map['kerala spices']).toBeDefined()
})

test('buildSessionArticleMap returns empty map when no overlap', () => {
  const articles = [{ keyword: 'foo', status: 'draft' }]
  const calendarKeywords = new Set(['bar'])
  expect(buildSessionArticleMap(articles, calendarKeywords)).toEqual({})
})
```

- [ ] **Step 2: Run tests to confirm they pass (pure logic, no component)**

```bash
cd /root/ANNASEOv1/frontend && npx vitest run src/kw2/contentPlanUtils.test.js
```

Expected: All 7 tests PASS (these are pure functions, no component mount needed)

> **Note on test design:** These tests validate the pagination and filter logic in isolation by re-implementing the formulas inline. They don't import from the component, so they won't catch a `PAGE_SIZE` constant drift if someone changes it in `SessionStrategyPage.jsx`. They're smoke tests to verify the algorithm is correct — the browser verification steps in each task are the integration check.

- [ ] **Step 3: Add pagination state to ContentPlanTab**

In `ContentPlanTab`, after the existing state declarations (around line 2380), add:

```javascript
  const PAGE_SIZE = 50
  const [page, setPage] = useState(0)
```

- [ ] **Step 4: Add page-reset useEffect**

After the existing state declarations, add:

```javascript
  // Reset to page 0 when filter/search/pillar changes, or when calendar reloads
  useEffect(() => setPage(0), [filter, search, pillarFilter, primaryItems.length])
```

- [ ] **Step 5: Make articleMap session-scoped**

Find lines 2418–2421 (the `articleMap` construction):

**Before:**
```javascript
  const articleMap = {}
  articleList.forEach(a => { articleMap[(a.keyword || "").toLowerCase()] = a })
```

**After:**
```javascript
  const calendarKeywords = new Set(primaryItems.map(i => (i.keyword || i.title || "").toLowerCase()))
  const articleMap = {}
  articleList
    .filter(a => calendarKeywords.has((a.keyword || "").toLowerCase()))
    .forEach(a => { articleMap[(a.keyword || "").toLowerCase()] = a })
```

- [ ] **Step 6: Replace `filtered.slice(0, 80)` with paginated slice**

Find the article grid (around line 2663):

**Before:**
```jsx
      {/* Article grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 10 }}>
        {filtered.slice(0, 80).map((item, i) => {
```

**After:**
```jsx
      {/* Pagination controls */}
      {Math.ceil(filtered.length / PAGE_SIZE) > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.border}`, background: page === 0 ? T.grayLight : "#fff", cursor: page === 0 ? "not-allowed" : "pointer", fontSize: 12, color: page === 0 ? T.textSoft : T.text }}
          >← Prev</button>
          <span style={{ color: T.textSoft }}>
            Page {page + 1} of {Math.ceil(filtered.length / PAGE_SIZE)}
          </span>
          <button
            onClick={() => setPage(p => Math.min(Math.ceil(filtered.length / PAGE_SIZE) - 1, p + 1))}
            disabled={page >= Math.ceil(filtered.length / PAGE_SIZE) - 1}
            style={{ padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.border}`, background: page >= Math.ceil(filtered.length / PAGE_SIZE) - 1 ? T.grayLight : "#fff", cursor: page >= Math.ceil(filtered.length / PAGE_SIZE) - 1 ? "not-allowed" : "pointer", fontSize: 12, color: page >= Math.ceil(filtered.length / PAGE_SIZE) - 1 ? T.textSoft : T.text }}
          >Next →</button>
        </div>
      )}

      {/* Article grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 10 }}>
        {filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((item, i) => {
```

- [ ] **Step 7: Verify in browser**

- Navigate to a session with 80+ calendar items
- Confirm the card grid shows exactly 50 cards with Prev/Next pagination
- Confirm page resets to 1 when you change the filter tab or search

- [ ] **Step 8: Commit**

```bash
cd /root/ANNASEOv1 && git add frontend/src/kw2/SessionStrategyPage.jsx frontend/src/kw2/contentPlanUtils.test.js
git commit -m "$(cat <<'EOF'
fix(content-plan): paginate card grid (50/page) + session-scope articleMap

Replaces the 80-card hard cap with 50-per-page pagination.
articleMap now only counts articles whose keywords appear in the
current calendar, preventing cross-session false positives in the
Generated count.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: BatchBriefPanel — Full chunked batching

**Files:**
- Modify: `frontend/src/kw2/SessionStrategyPage.jsx` (two hunks)

- [ ] **Step 1: Remove the `.slice(0, 20)` at the BatchBriefPanel call site**

Find the `<BatchBriefPanel` JSX around line 2590:

**Before:**
```jsx
        items={primaryItems.slice(0, 20)}
```

**After:**
```jsx
        items={primaryItems}
```

- [ ] **Step 2: Replace the single-batch `runBatch` with a chunk loop**

Find `BatchBriefPanel.runBatch` (line 2230). Replace the entire `runBatch` function (lines 2230–2266):

**Before:**
```javascript
  const runBatch = async () => {
    if (!items.length) return
    setRunning(true); setError(""); setPhase("Preparing briefs…"); setOpen(true)
    try {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")

      // Take up to 20 items for batch
      const keywords = items.slice(0, 20).map(i => ({
        keyword: i.keyword || i.title || "",
        title:   i.title || i.keyword || "",
        pillar:  i.pillar || "",
      }))

      setPhase(`Generating briefs for ${keywords.length} articles…`)
      const r = await fetch(`${API}/api/ki/${projectId}/blog-briefs-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({
          keywords,
          session_id: sessionId || "",
          ai_provider: aiConfig.ai_provider,
          custom_prompt: aiConfig.custom_prompt,
        }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setBriefs(data.briefs || [])
      setPhase(`${data.count || 0} briefs ready`)
      if (onBriefsLoaded) onBriefsLoaded(data.briefs || [])
    } catch (e) {
      setError(String(e))
      setPhase("")
    } finally {
      setRunning(false)
    }
  }
```

**After:**
```javascript
  const BRIEF_CHUNK = 20

  const runBatch = async () => {
    if (!items.length) return
    setRunning(true); setError(""); setPhase("Preparing briefs…"); setOpen(true)
    const API = import.meta.env.VITE_API_URL || ""
    const t = localStorage.getItem("annaseo_token")
    const allBriefs = []

    try {
      for (let i = 0; i < items.length; i += BRIEF_CHUNK) {
        const chunk = items.slice(i, i + BRIEF_CHUNK)
        const end = Math.min(i + BRIEF_CHUNK, items.length)
        setPhase(`Generating briefs ${i + 1}–${end} of ${items.length}…`)

        const keywords = chunk.map(item => ({
          keyword: item.keyword || item.title || "",
          title:   item.title || item.keyword || "",
          pillar:  item.pillar || "",
        }))

        try {
          const r = await fetch(`${API}/api/ki/${projectId}/blog-briefs-batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
            body: JSON.stringify({
              keywords,
              session_id: sessionId || "",
              ai_provider: aiConfig.ai_provider,
              custom_prompt: aiConfig.custom_prompt,
            }),
          })
          if (!r.ok) {
            console.warn(`[BatchBriefs] chunk ${i}–${end} failed: HTTP ${r.status}`)
            continue  // skip failed chunk, don't abort remaining chunks
          }
          const data = await r.json()
          allBriefs.push(...(data.briefs || []))
        } catch (chunkErr) {
          console.warn(`[BatchBriefs] chunk ${i}–${end} error:`, chunkErr)
          // continue with next chunk
        }
      }

      setBriefs(allBriefs)
      setPhase(`${allBriefs.length} of ${items.length} briefs ready`)
      if (onBriefsLoaded) onBriefsLoaded(allBriefs)
    } catch (e) {
      setError(String(e))
      setPhase("")
    } finally {
      setRunning(false)
    }
  }
```

- [ ] **Step 3: Verify in browser**

- Click "Run All Briefs" on a session with 100+ items
- Confirm the phase text cycles through "Generating briefs 1–20 of 507…", "Generating briefs 21–40 of 507…" etc.
- Confirm the final "N of 507 briefs ready" count is larger than 20

- [ ] **Step 4: Commit**

```bash
cd /root/ANNASEOv1 && git add frontend/src/kw2/SessionStrategyPage.jsx
git commit -m "$(cat <<'EOF'
fix(content-plan): batch all briefs in chunks of 20, not just first 20

Run All Briefs now processes all calendar items sequentially in 20-item
chunks instead of capping at the first 20. Chunk errors are skipped
gracefully so a single failed chunk doesn't abort the whole run.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: ContentPlanTab — Bulk Generate All Pending + Brief badge

**Files:**
- Modify: `frontend/src/kw2/SessionStrategyPage.jsx` (two hunks)

- [ ] **Step 1: Add bulk generate state variables**

In `ContentPlanTab`, add after the existing state declarations (around line 2388):

```javascript
  const [bulkRunning, setBulkRunning] = useState(false)
  const [bulkDone, setBulkDone]       = useState(0)
```

- [ ] **Step 2: Add `handleGenerateAll` function**

Add this function after the existing `handleGenerate` function (around line 2536):

```javascript
  const handleGenerateAll = async () => {
    setBulkRunning(true)
    setBulkDone(0)
    const pending = primaryItems.filter(item => {
      const kw = (item.keyword || item.title || "").toLowerCase()
      return !articleMap[kw] && genStatus[kw] !== "pending" && genStatus[kw] !== "done"
    })
    for (let i = 0; i < pending.length; i++) {
      await handleGenerate(pending[i])
      setBulkDone(i + 1)
      await new Promise(r => setTimeout(r, 400))
    }
    setBulkRunning(false)
    setBulkDone(0)
  }
```

- [ ] **Step 3: Add Bulk Generate button to the controls row**

Find the controls row (the `<div>` containing filter pills, search, and selects, around line 2601). Add the bulk generate button at the end of that row, after the AI Engine select:

```jsx
        {/* Bulk Generate All Pending */}
        {pendingCount > 0 && (
          <button
            onClick={handleGenerateAll}
            disabled={bulkRunning}
            style={{
              padding: "5px 14px", borderRadius: 7, border: "none", fontSize: 11, fontWeight: 700,
              background: bulkRunning ? T.grayLight : T.purple,
              color: bulkRunning ? T.textSoft : "#fff",
              cursor: bulkRunning ? "not-allowed" : "pointer",
            }}
          >
            {bulkRunning
              ? `⏳ Queueing ${bulkDone}/${primaryItems.filter(i => !articleMap[(i.keyword || i.title || "").toLowerCase()]).length}…`
              : `⚡ Generate All Pending (${pendingCount})`}
          </button>
        )}
```

- [ ] **Step 4: Add "✓ Brief" badge to cards**

Inside the card render (in the `{/* Meta badges */}` area, after the existing pillar/type/date badges, around line 2690), add:

```jsx
                {brief && !brief.error && (
                  <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 99, background: T.teal + "18", color: T.teal, fontWeight: 600 }}>✓ Brief</span>
                )}
```

Add this right after the `{item.word_count && ...}` badge block. The `brief` variable is already declared in the card render: `const brief = briefData[kw]`.

- [ ] **Step 5: Verify in browser**

- With pending articles visible, confirm "⚡ Generate All Pending (N)" button appears
- Click it — confirm the button shows "⏳ Queueing 1/N…" and increments
- After running briefs, confirm cards show the "✓ Brief" green badge
- Confirm the bulk button disappears once all articles are generated (pendingCount === 0)

- [ ] **Step 6: Commit**

```bash
cd /root/ANNASEOv1 && git add frontend/src/kw2/SessionStrategyPage.jsx
git commit -m "$(cat <<'EOF'
feat(content-plan): add bulk Generate All Pending + Brief ready badge

- Generate All Pending button queues all ungenerated articles with a
  400ms gap between requests to avoid hammering the backend
- Cards display a green '✓ Brief' badge when a brief has been loaded
  via the brief panel or Run All Briefs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Checklist

After all 6 tasks, do a full end-to-end smoke test:

- [ ] Open a session with 100+ calendar items
- [ ] Sticky header shows both "Regenerate Strategy" and "Rebuild Content Plan"
- [ ] **Session-scoping regression check:** If articles were generated in a previous session with the same keywords, confirm they are NOT counted as "Generated" in this session's calendar. If they are, open browser devtools → Application → confirm `ssp-articles` query is returning articles for the correct project, then verify `calendarKeywords` Set contains the expected keywords.
- [ ] Clicking "Rebuild Content Plan" triggers a POST with `start_date` in the body (check browser network tab)
- [ ] Article dates in cards match the campaign start date after rebuild
- [ ] Card grid shows 50 cards, pagination shows "Page 1 of N"
- [ ] Changing filter tab resets to Page 1
- [ ] "Run All Briefs" cycles through all items in chunks (not just 20)
- [ ] Generated count (e.g. "Generated (12)") only counts articles from this calendar
- [ ] "⚡ Generate All Pending" button queues articles with visible counter
- [ ] Cards with briefs show "✓ Brief" badge
- [ ] All existing features still work: individual Brief/Generate per card, AI provider select, pillar filter, search
