# Design Spec: Content Plan Tab — Full Rebuild
**Date:** 2026-04-17  
**Status:** Approved by user  
**Scope:** `frontend/src/kw2/SessionStrategyPage.jsx` (ContentPlanTab) + `main.py` (2 endpoint fixes)

---

## Problem Statement

The Content Plan / Blog Suggestions tab has four concrete breakdowns:

| # | Issue | Symptom |
|---|-------|---------|
| 1 | Hard cap at 80 visible cards | `filtered.slice(0, 80)` — 427 of 507 articles are hidden with no UI affordance |
| 2 | "Run All Briefs" only processes 20 | `BatchBriefPanel` receives `primaryItems.slice(0, 20)`; 487 articles never get a brief |
| 3 | Rebuild Calendar ignores start date | `kw2_rebuild_calendar` endpoint never passes `start_date` to `build_from_strategy`; article dates are wrong after rebuild |
| 4 | "Regenerate Strategy" not reachable from ContentPlanTab | Once viewing the card grid, there is no way to re-trigger strategy generation without scrolling to a different section |
| 5 | "Generated" count includes articles from other sessions | `articleMap` uses the full project article list; session-scoped calendar keywords not filtered |

---

## Chosen Approach: Full ContentPlanTab Rebuild (Option C)

Rebuild the `ContentPlanTab` component (inside `SessionStrategyPage.jsx`) to fix all five issues. No new files. Two small backend fixes in `main.py`.

---

## Architecture

```
ContentPlanTab (rebuilt)
├── Sticky header
│   ├── "{N} blog ideas (strategy + intelligence + keywords)"
│   ├── [Regenerate Strategy]   ← NEW shortcut button
│   └── [Rebuild Content Plan]  ← existing, stays
│
├── BatchBriefPanel (full batching)
│   └── Processes ALL primaryItems in sequential chunks of 20
│       Shows: "Generating briefs 40/507… chunk 3/26"
│
├── Controls row
│   ├── Filter tabs: All (N) | Pending (N) | Generated (N)
│   ├── Search input
│   ├── All Pillars dropdown
│   └── AI provider dropdown
│
├── Progress bar ("X of N articles generated")
├── Source label
│
├── Bulk actions bar  ← NEW
│   └── [Generate All Pending (N)] — queues all pending with 400ms gap
│
└── Article card grid — PAGINATED (50/page)
    ├── Page nav: ← Prev | Page 3 of 11 | Next →
    └── Cards: same design + "✓ Brief" badge when brief is loaded
```

---

## Component Design

### 1. Sticky Header

Replace the existing rebuild banner with a two-row sticky header:

```jsx
// Row 1: count + action buttons
<div style={{ display: "flex", alignItems: "center", gap: 10, ... }}>
  <strong>{primaryItems.length} blog ideas</strong>
  <span style={{ color: T.textSoft }}>(strategy + intelligence questions + keywords)</span>
  {rebuildResult && !rebuildResult.error && (
    <span style={{ color: T.teal }}>
      ✓ {rebuildResult.from_strategy} strategy ·
      {rebuildResult.from_intelligence} intel ·
      {rebuildResult.from_keywords} keywords
    </span>
  )}
  <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
    <button onClick={handleRegenerateStrategy}>🔄 Regenerate Strategy</button>
    <button onClick={handleRebuildCalendar}>↺ Rebuild Content Plan</button>
  </div>
</div>
```

`handleRegenerateStrategy` calls the `onRegenerate` prop. This prop is **new** — it must be added to the `ContentPlanTab` call site at `SessionStrategyPage.jsx:5983`:

```jsx
<ContentPlanTab
  strat={strat}
  calendarData={calendarData}
  projectId={projectId}
  sessionId={sessionId}
  startDate={contentParams.start_date}
  refetchCalendar={refetchCalendar}
  chooseAI={chooseAI}
  onRegenerate={onGenerate}   {/* ← ADD THIS */}
/>
```

where `onGenerate` is the existing strategy generation handler already defined in the session page.

### 2. Pagination

```javascript
const PAGE_SIZE = 50
const [page, setPage] = useState(0)

// Reset page on filter/search/pillar change OR when the calendar reloads
// Include primaryItems.length so a calendar rebuild that changes the item count
// also resets to page 0 (prevents landing on a now-empty page).
useEffect(() => setPage(0), [filter, search, pillarFilter, primaryItems.length])

// Slice for render
const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
```

Pagination controls:
```jsx
{totalPages > 1 && (
  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
    <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
    <span>Page {page + 1} of {totalPages}</span>
    <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page === totalPages - 1}>Next →</button>
  </div>
)}
```

### 3. Full Brief Batching in BatchBriefPanel

**Change:** `BatchBriefPanel` receives all `primaryItems` (remove the `.slice(0, 20)` from the call site in ContentPlanTab).

**Inside `BatchBriefPanel.runBatch`:** Process items in sequential chunks of 20:

```javascript
const CHUNK = 20
const runBatch = async () => {
  setRunning(true)
  const allBriefs = []
  for (let i = 0; i < items.length; i += CHUNK) {
    const chunk = items.slice(i, i + CHUNK)
    setPhase(`Generating briefs ${i + 1}–${Math.min(i + CHUNK, items.length)} of ${items.length}…`)
    const r = await fetch(`${API}/api/ki/${projectId}/blog-briefs-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ... },
      body: JSON.stringify({ keywords: chunk.map(...), session_id, ai_provider, custom_prompt }),
    })
    const data = await r.json()
    allBriefs.push(...(data.briefs || []))
  }
  setBriefs(allBriefs)
  setPhase(`${allBriefs.length} briefs ready`)
  onBriefsLoaded?.(allBriefs)
}
```

### 4. Bulk Generate All Pending

New button in the controls row (shown only when `pendingCount > 0`):

```jsx
<button onClick={handleGenerateAll} disabled={bulkRunning}>
  {bulkRunning ? `Queueing ${bulkDone}/${pendingItems.length}…` : `⚡ Generate All Pending (${pendingCount})`}
</button>
```

Implementation:
```javascript
const handleGenerateAll = async () => {
  setBulkRunning(true)
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
}
```

### 5. Brief-Ready Card Badge

Cards now show a "✓ Brief" badge when a brief has been loaded:

```jsx
{brief && !brief.error && !art && (
  <span style={{ fontSize: 10, color: T.teal, fontWeight: 600 }}>✓ Brief</span>
)}
```

### 6. Session-Scoped Generated Count

Build `articleMap` against only keywords in the calendar:

```javascript
const calendarKeywords = new Set(primaryItems.map(i => (i.keyword || i.title || "").toLowerCase()))
const articleMap = {}
articleList
  .filter(a => calendarKeywords.has((a.keyword || "").toLowerCase()))
  .forEach(a => { articleMap[(a.keyword || "").toLowerCase()] = a })
```

---

## Backend Fixes

### Fix 1 — `kw2_rebuild_calendar` endpoint passes `start_date`

**File:** `main.py` — `kw2_rebuild_calendar` function (~line 23580)

**Current:**
```python
async def kw2_rebuild_calendar(project_id: str, session_id: str, user=Depends(current_user)):
    ...
    result = await asyncio.to_thread(
        cal.build_from_strategy, project_id, session_id, strategy,
    )
```

**Fix:**
```python
async def kw2_rebuild_calendar(
    project_id: str, session_id: str,
    body: dict = Body(default={}),
    user=Depends(current_user),
):
    ...
    start_date = body.get("start_date") or None
    result = await asyncio.to_thread(
        cal.build_from_strategy, project_id, session_id, strategy, start_date,
    )
```

### Fix 2 — Frontend `handleRebuildCalendar` passes `start_date`

**File:** `frontend/src/kw2/SessionStrategyPage.jsx` — `ContentPlanTab`

`ContentPlanTab` already receives `startDate` as a prop. Update `handleRebuildCalendar`:

```javascript
// ContentPlanTab receives: startDate prop
const handleRebuildCalendar = async () => {
  setRebuilding(true)
  try {
    const res = await api.rebuildCalendar(projectId, sessionId, startDate)  // pass startDate
    ...
  }
}
```

Update `api.rebuildCalendar` in `api.js` (use `apiCall`, the helper already used throughout this file — NOT `apiFetch`):
```javascript
export const rebuildCalendar = (projectId, sessionId, startDate) =>
  apiCall(
    `${KW2}/${projectId}/sessions/${sessionId}/calendar/rebuild`,
    "POST",
    { start_date: startDate || null }
  )
```

---

## Error Handling

- Brief batch errors per chunk: log the error, skip that chunk, continue with remaining
- Bulk generate errors per article: mark card as "error" state (existing behavior), don't stop the queue
- Rebuild calendar errors: existing error handling unchanged

---

## What Does NOT Change

- Card visual design and content (title, pillar badge, type badge, date, keyword snippet)
- Brief expand/collapse within cards
- Individual Brief and Generate buttons per card
- AI provider selector behavior
- Filter/search/pillar filter logic
- Article editor (EditorPanel) — untouched
- All other tabs (Pipeline, AI Hub, AI Cost)
- Writing Profile Context Banner
- Content generation quality pipeline

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/kw2/SessionStrategyPage.jsx` | ContentPlanTab: pagination, bulk generate, full brief batching, sticky header, session-scoped counts |
| `frontend/src/kw2/api.js` | `rebuildCalendar` — add `start_date` param |
| `main.py` | `kw2_rebuild_calendar` — accept `start_date` in body, pass to `build_from_strategy` |
