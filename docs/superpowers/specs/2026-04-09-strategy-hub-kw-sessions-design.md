# Strategy Hub — Keyword Research Sessions Design

**Date:** 2026-04-09  
**Status:** Approved  
**Scope:** Frontend only (no backend changes)

---

## Problem

Two related issues:

1. **Strategy not syncing:** When a user generates a strategy from PhaseApply (kw2), it is stored in `keyword_input_sessions.strategy_json` via the kw2 backend. The Strategy Hub's Overview tab reads from a completely separate system (`strategy_sessions` table via `/api/strategy/{projectId}/latest`). The two systems never connect, so generated strategies never appear in the hub.

2. **No session grouping:** The Strategy Hub Overview currently shows generic SEO metrics and analytics. It has no awareness of kw2 sessions. Users need to see all keyword research sessions for a project grouped together, with individual cards per session.

---

## Goals

- Group all kw2 keyword research sessions for a project in the Strategy Hub Overview
- Show individual card per session (name + keyword count)
- Expand inline to show that session's full strategy
- Fix the "strategy generated but not reflected" sync bug

---

## Architecture

### No backend changes

The kw2 system already exposes all the data needed:
- `GET /api/kw2/{projectId}/sessions/list` — list all sessions for a project
- `GET /api/kw2/{projectId}/sessions/{sessionId}/apply/strategy` — get strategy for a session

The Strategy Hub will read directly from these endpoints.

### Auto-push fix

Pure cache invalidation: when PhaseApply's SSE stream fires `evt.done === true` (the top-level boolean flag that signals the entire apply stream is complete), call:
```js
queryClient.invalidateQueries(["kw2-sessions", projectId])
```

`PhaseApply.jsx` must add:
```js
import { useQueryClient } from "@tanstack/react-query"
// inside the component:
const queryClient = useQueryClient()
// in the SSE done handler:
if (evt.done) {
  queryClient.invalidateQueries(["kw2-sessions", projectId])
}
```

This triggers an immediate background refetch of the session list in any mounted Strategy Hub instance, and ensures the next mount also gets fresh data.

---

## Components

### `KwSessionsOverview` (new, in `StrategyIntelligenceHub.jsx`)

Replaces the existing `OverviewPhase` component as the `overview` phase handler.

**Data:**
```js
useQuery({
  queryKey: ["kw2-sessions", projectId],
  queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/list`),
  staleTime: 0,  // always fresh on mount
  enabled: !!projectId,
})
```

**Render:**
- Header: "Keyword Research Sessions" + subtitle
- Grid: `auto-fill minmax(280px, 1fr)` card grid
- Empty state: message + "Go to Keyword Research" button (calls `setPage("keywords")`)

### Session Card (within `KwSessionsOverview`)

**Collapsed state shows:**
- Mode badge (color-coded by session mode)
- Session name (or seed keywords joined by "·" as fallback)
- Keyword counts: `universe` + `validated`
- Phase progress dots (phases 1–9, filled = done)
- "View Strategy ▼" button — only shown if `phase9_done` is true or strategy exists
- "Go to Research →" button — always shown as secondary action

**Expanded state (inline, below the card summary):**
- "Collapse ▲" button at top
- Renders `StrategyTab` component (reused from `PhaseApply.jsx`) fed with lazily-fetched strategy
- Fetches strategy from `/api/kw2/{projectId}/sessions/{sessionId}/apply/strategy` only when expanded
- Loading spinner while fetching
- Error state: "Strategy not generated yet — complete Phase 9 or run Apply"
- "→ Create Content from this" button (navigates to Content Hub)

### Strategy lazy fetch (per-card)

Each card manages its own strategy state:
```js
const [expanded, setExpanded] = useState(false)
const [strategy, setStrategy] = useState(null)
const [stratLoading, setStratLoading] = useState(false)

const expand = async () => {
  if (!expanded && !strategy) {
    setStratLoading(true)
    const data = await apiFetch(`/api/kw2/${projectId}/sessions/${sessionId}/apply/strategy`).catch(() => null)
    setStrategy(data)
    setStratLoading(false)
  }
  setExpanded(e => !e)
}
```

### `StrategyTab` reuse

The `StrategyTab` function in `PhaseApply.jsx` is moved to `kw2/shared.jsx` and exported from there. Both `PhaseApply.jsx` and `KwSessionsOverview` import it from that shared location. `PhaseApply.jsx` removes its local definition and adds the import.

---

## Data flow

```
User opens Strategy Hub
  → KwSessionsOverview mounts
  → GET /api/kw2/{projectId}/sessions/list
  → Renders session cards (collapsed)

User clicks "View Strategy" on a card
  → Card expands
  → GET /api/kw2/{projectId}/sessions/{sessionId}/apply/strategy
  → StrategyTab renders strategy document

User generates strategy in PhaseApply
  → SSE stream completes (evt.done === true)
  → queryClient.invalidateQueries(["kw2-sessions", projectId])
  → Next time Strategy Hub opens, refetches session list
```

---

## Files changed

| File | Change |
|------|--------|
| `frontend/src/StrategyIntelligenceHub.jsx` | Replace `OverviewPhase` with `KwSessionsOverview` component; import `StrategyTab` from `kw2/shared.jsx` |
| `frontend/src/kw2/shared.jsx` | Add exported `StrategyTab` component (moved from PhaseApply) |
| `frontend/src/kw2/PhaseApply.jsx` | Remove local `StrategyTab` definition; import from `kw2/shared.jsx`; add `useQueryClient` import + hook; call `queryClient.invalidateQueries(["kw2-sessions", projectId])` on `evt.done === true` |

### What is NOT changed

- Backend: no changes
- `strategy_sessions` table: untouched (old pipeline still works)
- `RoadmapPhase` (Strategy tab): stays as-is
- All other Strategy Hub phases: untouched

---

## Edge cases

- **Session with no strategy yet:** Card shows "Go to Research →" and expand is disabled (no "View Strategy" button)
- **Strategy fetch fails (404):** Show message "Strategy not generated yet — run Phase 9 or Apply"
- **Empty session list:** Show empty state with prompt to create first keyword research session
- **Very long session lists:** Grid uses `auto-fill` so it wraps naturally; no pagination needed for typical use (< 20 sessions per project)

---

## Out of scope

- Bulk strategy comparison across sessions
- Editing strategies from the hub
- Moving the existing Overview analytics/metrics anywhere (they are removed; they were mostly empty)
