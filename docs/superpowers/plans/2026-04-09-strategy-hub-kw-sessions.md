# Strategy Hub — Keyword Research Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Strategy Hub Overview with a grid of kw2 keyword research session cards (each expandable to show its strategy inline), and fix the bug where strategies generated in PhaseApply never appear in the hub.

**Architecture:** Frontend-only change across 3 files. `StrategyTab` moves from `PhaseApply.jsx` to `kw2/shared.jsx` so both PhaseApply and the new hub component can use it. The hub Overview reads sessions from `/api/kw2/{projectId}/sessions/list` and lazily fetches strategy per card. PhaseApply invalidates the session cache when the apply stream completes so the hub reflects new strategies immediately.

**Tech Stack:** React 18, `@tanstack/react-query` v5, Vite, inline styles (no CSS modules), existing `apiFetch` + auth helpers already defined in each file.

**Spec:** `docs/superpowers/specs/2026-04-09-strategy-hub-kw-sessions-design.md`

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/kw2/shared.jsx` | Add exported `StrategyTab` component |
| `frontend/src/kw2/PhaseApply.jsx` | Remove local `StrategyTab`; add import; add `useQueryClient` + invalidation on `evt.done` |
| `frontend/src/StrategyIntelligenceHub.jsx` | Add `KwSessionCard` + `KwSessionsOverview`; wire `overview` phase to `KwSessionsOverview` |

---

## Task 1: Export `StrategyTab` from `kw2/shared.jsx`

**Files:**
- Modify: `frontend/src/kw2/shared.jsx` (append near end of file, before the closing)
- Modify: `frontend/src/kw2/PhaseApply.jsx` (remove local definition, update import)

### Step 1.1 — Add `StrategyTab` export to `kw2/shared.jsx`

Open `frontend/src/kw2/shared.jsx`. The file currently ends around the `usePhaseRunner` hook and various shared components. Append the following exported function **before the last line** of the file (or at the very end):

```jsx
// ── StrategyTab — renders a kw2 apply strategy document ───────────────────
export function StrategyTab({ strategy }) {
  if (!strategy) {
    return (
      <p style={{ fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 16 }}>
        No strategy generated yet.
      </p>
    )
  }

  if (typeof strategy === "string") {
    return (
      <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.7, color: "#374151", padding: 8 }}>
        {strategy}
      </div>
    )
  }

  const sections = strategy.sections ||
    Object.entries(strategy).filter(([k]) => k !== "id" && k !== "session_id")

  return (
    <div style={{ padding: 8 }}>
      {strategy.title && (
        <h3 style={{ fontSize: 18, fontWeight: 700, color: "#111827", marginBottom: 16 }}>
          {strategy.title}
        </h3>
      )}
      {strategy.summary && (
        <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16, lineHeight: 1.6 }}>
          {strategy.summary}
        </p>
      )}
      {Array.isArray(sections) ? (
        sections.map((section, i) => {
          const title = section.title || section.heading || section[0]
          const content = section.content || section.body || section[1]
          return (
            <div key={i} style={{ marginBottom: 20 }}>
              <h4 style={{ fontSize: 15, fontWeight: 600, color: "#1f2937", marginBottom: 6,
                borderBottom: "1px solid #e5e7eb", paddingBottom: 4 }}>
                {typeof title === "string" ? title : JSON.stringify(title)}
              </h4>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: "#374151", whiteSpace: "pre-wrap" }}>
                {typeof content === "string" ? content : JSON.stringify(content, null, 2)}
              </div>
            </div>
          )
        })
      ) : (
        <div style={{ fontSize: 13, lineHeight: 1.7, color: "#374151", whiteSpace: "pre-wrap" }}>
          {JSON.stringify(strategy, null, 2)}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 1.2 — Update PhaseApply import to include `StrategyTab`**

In `frontend/src/kw2/PhaseApply.jsx`, line 10, change:
```js
import { Card, RunButton, StatsRow, usePhaseRunner, ProgressBar, Badge, Spinner, NotificationList } from "./shared"
```
to:
```js
import { Card, RunButton, StatsRow, usePhaseRunner, ProgressBar, Badge, Spinner, NotificationList, StrategyTab } from "./shared"
```

- [ ] **Step 1.3 — Remove local `StrategyTab` definition from PhaseApply**

In `frontend/src/kw2/PhaseApply.jsx`, delete lines 391–438 (the entire `// ── Strategy Tab` comment and `function StrategyTab` block, from the comment through the closing `}`).

The block to delete is exactly:
```js
// ── Strategy Tab ────────────────────────────────────────────────────────────

function StrategyTab({ strategy }) {
  ...
}
```

After deletion, line 440 (`const tdStyle = ...`) should immediately follow the closing `}` of the `StrategyTab` block. Nothing else sits between `StrategyTab` and `const tdStyle`.

- [ ] **Step 1.4 — Verify PhaseApply still works**

Run the dev server: `cd /root/ANNASEOv1/frontend && npm run dev`

Open the keyword research page, navigate to PhaseApply, click the "Strategy" tab. The strategy document must still render (now reading the imported `StrategyTab`). No visual difference expected.

- [ ] **Step 1.5 — Commit**

```bash
cd /root/ANNASEOv1
git add frontend/src/kw2/shared.jsx frontend/src/kw2/PhaseApply.jsx
git commit -m "refactor(kw2): extract StrategyTab to shared.jsx for reuse in strategy hub"
```

---

## Task 2: Cache invalidation in PhaseApply

**Files:**
- Modify: `frontend/src/kw2/PhaseApply.jsx`

When PhaseApply finishes generating a strategy, it must invalidate the session list cache so the Strategy Hub Overview auto-refreshes.

- [ ] **Step 2.1 — Add `useQueryClient` import to PhaseApply**

In `frontend/src/kw2/PhaseApply.jsx`, line 7, change:
```js
import React, { useState, useCallback, useEffect, useRef, useMemo } from "react"
```
to:
```js
import React, { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
```

- [ ] **Step 2.2 — Wire `useQueryClient` inside the component**

In `frontend/src/kw2/PhaseApply.jsx`, inside `export default function PhaseApply({ projectId, sessionId, onComplete })`, the first line of the component body is:
```js
const { aiProvider, setActivePhase } = useKw2Store()
```

Add `const queryClient = useQueryClient()` immediately after it:
```js
const { aiProvider, setActivePhase } = useKw2Store()
const queryClient = useQueryClient()
```

- [ ] **Step 2.3 — Invalidate cache on `evt.done`**

Locate the `evt.done` handler in the `runStream` callback (around line 504). It currently reads:
```js
if (evt.done) {
  setStreamLoading(false)
  setDone(true)
  setProgress((prev) => ({ ...prev, current: prev.total }))
  log("Apply complete!", "success")
  toast("Apply finished", "success")
  loadResults()
}
```

Add the invalidation call after `loadResults()`:
```js
if (evt.done) {
  setStreamLoading(false)
  setDone(true)
  setProgress((prev) => ({ ...prev, current: prev.total }))
  log("Apply complete!", "success")
  toast("Apply finished", "success")
  loadResults()
  queryClient.invalidateQueries({ queryKey: ["kw2-sessions", projectId] })
}
```

> **Note on syntax:** The codebase has legacy `qc.invalidateQueries(["key"])` calls (React Query v4 array form), but this project runs `@tanstack/react-query` v5. The v5 API requires the object form `{ queryKey: [...] }`. Use the object form here; do NOT change the existing legacy calls elsewhere (leave that for a separate cleanup).

- [ ] **Step 2.4 — Verify no console errors**

Run `npm run dev`, navigate to PhaseApply, and run Apply stream. Check the browser console — no `useQueryClient` errors. (The invalidation will fire but have no visible effect until Task 3 is done.)

- [ ] **Step 2.5 — Commit**

```bash
cd /root/ANNASEOv1
git add frontend/src/kw2/PhaseApply.jsx
git commit -m "fix(kw2): invalidate strategy hub session cache after apply stream completes"
```

---

## Task 3: `KwSessionsOverview` in StrategyIntelligenceHub

**Files:**
- Modify: `frontend/src/StrategyIntelligenceHub.jsx`

This task adds the two new components (`KwSessionCard` and `KwSessionsOverview`) and wires the Overview phase to use them.

### Step 3.1 — Add `StrategyTab` import

At the top of `frontend/src/StrategyIntelligenceHub.jsx`, the imports are:
```js
import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
```

Add the `StrategyTab` import on a new line:
```js
import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { StrategyTab } from "./kw2/shared"
```

- [ ] **Step 3.2 — Add `KwSessionCard` component**

Locate line 1629 in `StrategyIntelligenceHub.jsx` (the `// ── Overview ──` comment). Insert the following two components **immediately before** that comment:

```jsx
// ── Kw Session Card (used by KwSessionsOverview) ─────────────────────────────

const KW_SESSION_MODE_STYLE = {
  brand:  { bg: "#eff6ff", border: "#bfdbfe", badge: "#1e40af", badgeBg: "#dbeafe", icon: "🏢", label: "Brand Analysis" },
  expand: { bg: "#f0fdf4", border: "#bbf7d0", badge: "#166534", badgeBg: "#dcfce7", icon: "🌱", label: "Expand" },
  review: { bg: "#faf5ff", border: "#e9d5ff", badge: "#5b21b6", badgeBg: "#ede9fe", icon: "🔍", label: "Review" },
  v2:     { bg: "#f0fdfa", border: "#99f6e4", badge: "#0f766e", badgeBg: "#ccfbf1", icon: "⚡", label: "Smart Workflow" },
}

const KW_PHASE_KEYS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

function KwSessionCard({ session, projectId, setPage }) {
  const [expanded, setExpanded] = useState(false)
  const [strategy, setStrategy] = useState(null)
  const [stratLoading, setStratLoading] = useState(false)
  const [stratError, setStratError] = useState(null)

  const hasStrategy = !!session.phase9_done
  const st = KW_SESSION_MODE_STYLE[session.mode] || KW_SESSION_MODE_STYLE.brand

  const label = session.name ||
    (Array.isArray(session.seed_keywords) && session.seed_keywords.length
      ? session.seed_keywords.slice(0, 3).join(" · ")
      : `Session ${(session.id || "").slice(-6)}`)

  const donePhasesCount = KW_PHASE_KEYS.filter(i => session[`phase${i}_done`]).length

  const toggle = async () => {
    if (!hasStrategy) return
    if (!expanded && !strategy && !stratError) {
      setStratLoading(true)
      setStratError(null)
      try {
        const data = await apiFetch(`/api/kw2/${projectId}/sessions/${session.id}/apply/strategy`)
        setStrategy(data)
      } catch (e) {
        setStratError(e.message || "Strategy not available")
      }
      setStratLoading(false)
    }
    setExpanded(e => !e)
  }

  return (
    <div style={{
      borderRadius: 12,
      border: expanded ? `2px solid ${st.badge}` : `1px solid ${st.border}`,
      background: st.bg,
      overflow: "hidden",
      boxShadow: T.cardShadow,
      transition: "border .15s",
    }}>
      {/* Card header */}
      <div style={{ padding: 18 }}>
        {/* Mode badge */}
        <div style={{ marginBottom: 10 }}>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "2px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700,
            background: st.badgeBg, color: st.badge,
          }}>
            {st.icon} {st.label}
          </span>
        </div>

        {/* Session name */}
        <div style={{ fontSize: 16, fontWeight: 700, color: "#111827", lineHeight: 1.3,
          marginBottom: 8, wordBreak: "break-word" }}>
          {label}
        </div>

        {/* Keyword counts */}
        <div style={{ display: "flex", gap: 16, marginBottom: 10 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: st.badge }}>
              {(session.universe_total || 0).toLocaleString()}
            </div>
            <div style={{ fontSize: 10, color: T.textSoft }}>universe</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 18, fontWeight: 800,
              color: (session.validated_total || 0) > 0 ? T.teal : "#9ca3af" }}>
              {(session.validated_total || 0).toLocaleString()}
            </div>
            <div style={{ fontSize: 10, color: T.textSoft }}>validated</div>
          </div>
        </div>

        {/* Phase dots */}
        <div style={{ display: "flex", gap: 3, alignItems: "center", marginBottom: 14 }}>
          {KW_PHASE_KEYS.map(i => (
            <div key={i} style={{
              width: 8, height: 8, borderRadius: "50%",
              background: session[`phase${i}_done`] ? T.teal : "#e5e7eb",
            }} title={`Phase ${i}`} />
          ))}
          <span style={{ fontSize: 10, color: T.gray, marginLeft: 4 }}>
            {donePhasesCount}/9
          </span>
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {hasStrategy && (
            <button
              onClick={toggle}
              style={{
                width: "100%", padding: "7px 0", borderRadius: 7, border: "none",
                background: expanded ? st.badge : st.badgeBg,
                color: expanded ? "#fff" : st.badge,
                fontWeight: 700, fontSize: 12, cursor: "pointer", transition: "all .12s",
              }}
            >
              {expanded ? "Collapse ▲" : "View Strategy ▼"}
            </button>
          )}
          {!hasStrategy && (
            <div style={{ fontSize: 11, color: T.gray, fontStyle: "italic", marginBottom: 4 }}>
              Complete Phase 9 to generate strategy
            </div>
          )}
          {setPage && (
            <button
              onClick={() => setPage("keywords")}
              style={{
                width: "100%", padding: "6px 0", borderRadius: 7,
                border: `1px solid ${st.border}`,
                background: "transparent", color: st.badge,
                fontWeight: 600, fontSize: 11, cursor: "pointer",
              }}
            >
              Go to Research →
            </button>
          )}
        </div>
      </div>

      {/* Expanded strategy panel */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${st.border}`, padding: 18, background: "#fff" }}>
          {stratLoading ? (
            <div style={{ textAlign: "center", padding: 20, color: T.textSoft, fontSize: 13 }}>
              Loading strategy…
            </div>
          ) : stratError ? (
            <div style={{ color: T.red, fontSize: 13, padding: "8px 0" }}>
              Strategy not generated yet — complete Phase 9 or run Apply
            </div>
          ) : (
            <StrategyTab strategy={strategy} />
          )}
        </div>
      )}
    </div>
  )
}

// ── KwSessionsOverview ────────────────────────────────────────────────────────

function KwSessionsOverview({ projectId, setPage }) {
  const { data, isLoading } = useQuery({
    queryKey: ["kw2-sessions", projectId],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/list`),
    staleTime: 0,
    enabled: !!projectId,
  })
  const sessions = data?.sessions || []

  if (isLoading) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: T.textSoft, fontSize: 14 }}>
        Loading keyword research sessions…
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔬</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.text, marginBottom: 8 }}>
          No keyword research sessions yet
        </div>
        <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 20, maxWidth: 380, margin: "0 auto 20px" }}>
          Run keyword research to build your strategy foundation.
          Each session generates a full SEO strategy document.
        </div>
        {setPage && (
          <button
            onClick={() => setPage("keywords")}
            style={{
              padding: "9px 22px", borderRadius: 9, border: "none",
              background: T.purple, color: "#fff", cursor: "pointer",
              fontWeight: 700, fontSize: 13,
            }}
          >
            → Go to Keyword Research
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Keyword Research Sessions</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            {sessions.length} session{sessions.length !== 1 ? "s" : ""} for this project —
            click a card to expand its strategy
          </p>
        </div>
        {setPage && (
          <button
            onClick={() => setPage("keywords")}
            style={{
              padding: "6px 14px", borderRadius: 7, border: `1px solid ${T.border}`,
              background: "#fff", color: T.purpleDark, cursor: "pointer",
              fontWeight: 600, fontSize: 12,
            }}
          >
            + New Session
          </button>
        )}
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 16,
      }}>
        {sessions.map(s => (
          <KwSessionCard key={s.id} session={s} projectId={projectId} setPage={setPage} />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3.3 — Wire `KwSessionsOverview` to the Overview phase**

In `StrategyIntelligenceHub.jsx`, line 4009, change:
```jsx
{activePhase === "overview"  && <OverviewPhase projectId={projectId} strategy={strategy} onNavigate={setActivePhase} />}
```
to:
```jsx
{activePhase === "overview"  && <KwSessionsOverview projectId={projectId} setPage={setPage} />}
```

> Note: `setPage` is the prop passed to `StrategyIntelligenceHub` from `App.jsx` for cross-page navigation. It's already available in the component scope.

- [ ] **Step 3.4 — Verify the Overview renders**

Run `npm run dev`. Navigate to Strategy Hub → Overview tab. You should see:
- If the project has kw2 sessions: a card grid with session names and keyword counts
- If no sessions: the empty state with "→ Go to Keyword Research" button
- Click a session card that has Phase 9 complete: it should expand and show the strategy (or "Loading strategy…" briefly)

- [ ] **Step 3.5 — Test the strategy sync fix**

1. In PhaseApply (keyword research page), run Stream Apply on a session
2. Wait for it to complete (you should see "Apply finished" toast)
3. Navigate to Strategy Hub → Overview
4. The session card should be visible and "View Strategy ▼" button should appear if Phase 9 was done

- [ ] **Step 3.6 — Commit**

```bash
cd /root/ANNASEOv1
git add frontend/src/StrategyIntelligenceHub.jsx
git commit -m "feat(hub): replace Overview with kw2 session cards showing inline strategies"
```

---

## Post-implementation checklist

- [ ] No browser console errors when Strategy Hub loads
- [ ] Session cards appear in the correct grid layout for multiple sessions
- [ ] Empty state shows when no sessions exist
- [ ] "View Strategy ▼" button only appears on cards where `phase9_done` is true
- [ ] Expanding a card with no strategy (404 response) shows the error message, not a crash
- [ ] Collapsing a card and re-expanding reuses the already-fetched strategy (no second API call)
- [ ] `+ New Session` button navigates to the keyword research page

---

## Notes for implementer

- `apiFetch` is already defined at the top of `StrategyIntelligenceHub.jsx` — no need to redefine it
- The `T` color palette object is defined at the top of the hub file — use it for colors
- `OverviewPhase` function is left in the file (not deleted) — it's now unused but harmless; delete it as cleanup if desired
- The `strategy` prop that was passed to `OverviewPhase` from the main component (line 4009) is no longer needed by Overview; `KwSessionsOverview` fetches its own data
- Do NOT change `AnalysisPhase`, `StrategyPhase`, or any other phase component
