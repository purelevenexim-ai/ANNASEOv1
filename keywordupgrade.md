# KW2 Upgrade — DAG Phase Engine & Intelligence Features

> Living spec — updated as features ship.  
> Previous version covered mode-based flow + Search rename (implemented).  
> This version adds DAG engine, feedback loops, segmentation, and intelligence features.

---

## Architecture Overview

KW2 v2 replaces the linear phase pipeline with a **DAG (Directed Acyclic Graph) Phase Engine**. Phases declare their dependencies, outputs, and behavior. The engine resolves execution order, detects parallelism, manages feedback loops, and enforces input/output contracts.

### Core Components

| File | Purpose |
|------|---------|
| `services/phase_registry.py` | Phase specs — every phase self-declares deps, outputs, modes, gates |
| `services/dag_resolver.py` | Topological sort (Kahn's algorithm) → parallel level detection |
| `services/session_graph.py` | Typed state container — immutable versioned outputs, feedback, rollback |
| `services/execution_engine.py` | Level-by-level execution, retry, parallel, feedback loops |
| `engines/kw2/db.py` | `session_graph` column for persisted DAG state |
| `frontend/src/kw2/useDAGEngine.js` | React hook — fetches DAG, computes runnable phases, run/approve actions |
| `frontend/src/kw2/api.js` | DAG API helpers (`getDagState`, `runDagPhase`, `approveDagGate`) |

### DAG API Endpoints

```
GET  /api/kw2/{pid}/sessions/{sid}/dag              → full DAG topology + statuses
POST /api/kw2/{pid}/sessions/{sid}/dag/run/{phase}   → execute one phase
POST /api/kw2/{pid}/sessions/{sid}/dag/approve/{gate} → approve human gate
GET  /api/kw2/{pid}/sessions/{sid}/dag/order          → flat execution order
```

---

## Workflow Modes

| Mode | Entry Point | Flow |
|------|-------------|------|
| **Brand** | New business analysis | analyze → intel → business_context → confirm_pillars → search(parallel) → merge → generate ⇄ validate → review → score → strategy |
| **Expand** | Existing project expansion | search(parallel) → merge → generate ⇄ validate → review → score → strategy |
| **Review** | GSC audit only | search_gsc → insights |

---

## 13 Registered Phases

| ID | Label | Dependencies | Mode(s) | Notes |
|----|-------|-------------|---------|-------|
| `analyze` | 🔬 Analyze | — | brand | Extract business profile |
| `intel` | 🕵️ Intel | analyze | brand | Market research + competitor analysis |
| `business_context` | 📋 Business Context | analyze, intel | brand | Structured context object |
| `confirm_pillars` | ✅ Confirm Pillars | business_context | brand | **Human gate** |
| `search_gsc` | 📡 Search (GSC) | — | brand, review | **Parallel-eligible** |
| `search_global` | 🌍 Search (Global) | — | brand, expand | **Parallel-eligible** |
| `merge_keywords` | 🔗 Merge | search_gsc, search_global (ANY) | brand, expand | Deduplicate sources |
| `generate` | ⚙️ Generate | merge_keywords, business_context | brand, expand | **Feedback target** from validate |
| `validate` | 🛡️ Validate | generate | brand, expand | **Feedback source** → generate |
| `review` | 👁️ Review | validate | brand, expand | **Human gate** |
| `score` | 📊 Score | review | brand, expand | Scoring + clustering |
| `strategy` | 🎯 Strategy | score, intel | brand, expand | Quick wins + content plan |
| `insights` | 💡 Insights | search_gsc | review | GSC authority analysis |

---

## Key Features

### 1. DAG-Based Execution
- Phases execute level-by-level from topological sort
- Parallel-eligible phases run concurrently (search_gsc + search_global)
- Resume support — skips already-completed phases
- Human gates pause the pipeline and wait for approval

### 2. Feedback Loops (validate → generate)
- After validation, if rejection rate ≥ 60%, the generate phase re-runs
- Feedback signals carry rejection reasons as constraints
- Max 2 feedback iterations to prevent infinite loops
- Rejection report includes top rejection reasons for targeted improvement

### 3. Session Graph (Immutable State)
- Every phase output is version-tracked with full history
- `rollback(phase_id)` restores to previous version
- Feedback signals stored per-phase
- Token cost tracking per phase
- JSON-serialized to SQLite `session_graph` column

### 4. Structured Business Context
- Replaces raw README text blob
- Synthesized from profile + intel phases
- Provides structured data for downstream phases
- Stored as confirmed_pillars via human gate

### 5. Keyword Segmentation (Phase 4)
- **Money keywords**: High commercial score + high composite → prioritize now
- **Growth keywords**: High volume, mid competition → 3-6 month investment
- **Support keywords**: Informational & long-tail → topical authority building
- **Quick Wins**: Score ≥ 60 + difficulty ≤ 35 → target in month 1
- Auto-generated strategy recommendations based on distribution

### 6. Score Distribution Visualization
- CSS bar chart showing score ranges
- Color-coded by range
- No external charting dependency needed

---

## Intelligence Features (Roadmap)

### Implemented
- [x] Keyword segmentation (Money / Growth / Support)
- [x] Quick Wins detection
- [x] Auto strategy recommendations
- [x] Feedback loop for high-rejection batches

### Planned
- [ ] **Confidence Decay** — score degradation over time if keywords aren't acted on
- [ ] **Intent Funnel Mapping** — map keywords to TOFU/MOFU/BOFU stages
- [ ] **Cannibalization Detection** — identify keyword overlap across existing pages
- [ ] **Difficulty Calibration** — adjust difficulty scores using GSC actual performance
- [ ] **Semantic Gap Finder** — detect missing topic areas in pillar coverage
- [ ] **Auto-Brief Generator** — generate content briefs from scored keyword clusters
- [ ] **Session Comparison** — diff two sessions to track keyword evolution
- [ ] **Live SERP Snapshots** — capture SERP features for top keywords

---

## DB Schema Changes

### kw2_sessions (new column)
```sql
session_graph TEXT DEFAULT '{}'
```

Auto-migrated via `init_kw2_db()` PRAGMA + ALTER TABLE pattern.

---

## Frontend Architecture

### useDAGEngine Hook
```js
const {
  dag,            // full DAG topology from backend
  statuses,       // phase_id → status
  running,        // currently executing phase
  loading,        // initial load state
  runnablePhases, // computed: phases with all deps met
  runPhase,       // (phaseId) → execute
  approveGate,    // (phaseId, data) → approve human gate
  refresh,        // re-fetch DAG state
} = useDAGEngine()
```

### Phase4.jsx Segments
- `classifyKeyword(kw)` → money | growth | support
- `detectQuickWins(keywords)` → top 10 easy high-scorers
- `generateRecommendations(segments, quickWins, stats)` → action items
- `ScoreDistChart` — pure CSS bar chart component
- `SegmentPanel` — expandable keyword table per segment
- `QuickWinsCard` — highlighted easy wins
- `RecommendationsCard` — auto-generated strategy actions

---

## Testing Strategy

1. **Backend syntax**: `python3 -m py_compile services/phase_registry.py services/dag_resolver.py services/session_graph.py services/execution_engine.py`
2. **Frontend build**: `cd frontend && npm run build`
3. **DAG resolution**: Unit test topological sort for each mode
4. **Feedback loop**: Test rejection threshold triggers re-generation
5. **API integration**: Hit DAG endpoints with valid session
6. **E2E**: Full brand mode flow through DAG engine

---

## File Inventory

### New Files
- `services/phase_registry.py` — Phase spec registry
- `services/dag_resolver.py` — DAG topological sort
- `services/session_graph.py` — Session state container
- `services/execution_engine.py` — Pipeline executor
- `frontend/src/kw2/useDAGEngine.js` — DAG React hook

### Modified Files
- `engines/kw2/db.py` — Added `session_graph` column + `save_session_graph()` / `load_session_graph()`
- `main.py` — Added DAG imports + 4 new API endpoints
- `frontend/src/kw2/api.js` — Added DAG API helpers
- `frontend/src/kw2/Phase4.jsx` — Full refactor with segmentation, charts, recommendations
- `frontend/src/kw2/store.js` — Previously added mode/flow support
- `frontend/src/kw2/flow.js` — Previously added mode routing
- `frontend/src/kw2/KwPage.jsx` — Previously added mode awareness

---

## Previous Upgrade (v1 → v2 modes)

The following was completed in the prior session:
- GSC → Search rename across UI
- 3 workflow modes (brand / expand / review)
- flow.js mode routing + ModeSelector.jsx
- business_readme DB column + API endpoints
- Confirmed pillars in Phase 2 generation
- Store.js mode-aware phase navigation
