# ANNASEOv1 — Complete Development Roadmap

**Status:** Phase 1 (Critical Fixes) — Week 1 **STARTED ✅**  
**Current Date:** March 25, 2026  
**Implementation Focus:** Step 5 Pillar Keyword Crisis + API Wiring  

---

## Executive Summary

This document outlines **100+ development items** organized into 5 phases. The phased approach ensures:

1. **Week 1 (Phase 1):** Fix critical Step 5/Gate 2 pillar issue + API wiring (CURRENTLY IMPLEMENTING)
2. **Week 2 (Phase 2):** Build core confirmation pipeline UI  
3. **Week 3 (Phase 3):** UI/UX enhancements (D3 tree, console output)  
4. **Week 4+ (Phase 4):** Quality systems (intent learning, GEO tuning, rollback testing)  
5. **Post-MVP (Phase 5):** Advanced features (programmatic SEO, backlinks, local SEO)

**Total MVP Timeline:** ~4 weeks (150 hours, full-time)  
**Critical Path:** Phase 1 → Phase 2 → Phase 3 (Phase 4 can run in parallel)

---

## PHASE 1: CRITICAL FIXES (WEEK 1)

### ✅ COMPLETED (Items 1.1-1.15)

#### Database Infrastructure  
- ✅ **1.1-1.2** Gate 2 database tables (gate_states, content_strategy, keyword_feedback_intent)
- ✅ **1.3-1.7** Runs table migrations (gate_1_confirmed through gate_5_confirmed columns)
- ✅ **1.8** New migration columns for pillars_json, keywords_json, etc.

#### Backend API Endpoints  
- ✅ **1.9-1.10** Pydantic models: `PillarData`, `Gate2ConfirmationRequest`, `Gate2ConfirmationResponse`
- ✅ **1.11** POST `/api/runs/{run_id}/gate-2` — Save customer-confirmed pillars
- ✅ **1.12** GET `/api/runs/{run_id}/gate-2` — Retrieve Gate 2 state + pillars
- ✅ **1.13-1.14** GET `/api/system-status` — Ollama/Gemini/Claude/GSC health check
- ✅ **1.15** GET `/api/projects/{id}/d3-graph` — D3-ready graph JSON with caching
- ✅ **1.16** POST `/api/projects/{id}/impact-assessment` — Estimate impact of config changes

#### What This Fixes
✅ Gate 2 pillar confirmation now has:
- Full database persistence
- API endpoint to save/load pillar state
- SSE event emission for real-time feedback
- Resumption capability (don't re-run P9-P10 if confirmed)

---

### 🟡 IN PROGRESS (Items 1.17-1.20)

#### Resume-from-Gate-2 Logic  
- [ ] **1.17** Implement `RufloEngine.resume_from_gate_2()` in `engines/ruflo_20phase_wired.py`
  - **What:** Skip P9-P10 if Gate 2 already confirmed
  - **How:** Check `run.gate_2_confirmed` before executing phases
  - **Time:** 3h
  
- [ ] **1.18** Update `RufloEngine.run_seed()` to use confirmed pillars
  - **What:** Load pillars from `gate_states` instead of P10 output
  - **How:** Before P11, load confirmed pillars from DB
  - **Time:** 2h

#### Console Output Enhancements  
- [ ] **1.19** Emit enhanced console events with color + timing + data counts
  - **Schema:** `{phase, status, progress%, color, elapsed_ms, est_remaining_ms, data: {input_count, output_count, examples}}`
  - **Time:** 3h
  
- [ ] **1.20** Show memory usage per phase + data flow handoffs
  - **What:** "P9: 8 clusters → P10 receives (8 cluster items) → generates 8 pillars → P11 receives"
  - **Time:** 2h

**Subtotal:** 4 items to complete (10h work)

---

### 📋 Next Steps (Dependency Chain)

```
1.17-1.18 (Resume logic)
    ↓
1.19-1.20 (Console enhancements)
    ↓
CREATE PillarConfirmation.jsx (Phase 2, Item 2.1)
    ↓
Test end-to-end: Pillar confirmation → P11+ execution
```

---

## PHASE 1 COMPLETION CHECKLIST

Before marking Phase 1 complete, verify:

- [ ] Gate 2 API endpoints return 200 OK
- [ ] Pillar confirmation saves to `gate_states` table
- [ ] GET `/api/runs/{id}/gate-2` returns confirmed pillars
- [ ] `/api/system-status` shows all 4 service statuses
- [ ] `/api/projects/{id}/d3-graph` returns D3 JSON structure
- [ ] `/api/projects/{id}/impact-assessment` calculates impact correctly
- [ ] Console events include phase, progress, timing info
- [ ] No syntax errors in main.py (✅ validated)

**Estimated Time to Complete Phase 1:** 8-10 hours  
**Current Progress:** ~40% (6/15 items complete)

---

## PHASE 2: CORE GATEWAY COMPLETION (WEEK 2)

Build remaining 4 gates + Content Strategy module.

| Gate | UI Component | Backend Endpoint | Items | Time |
|------|--------------|------------------|-------|------|
| **Gate 1** | UniverseConfirmation.jsx | POST /api/runs/{id}/gate-1 | 2.1-2.3 | 6h |
| **Gate 3** | KeywordTreeConfirmation.jsx | POST /api/runs/{id}/gate-3 | 2.4-2.6 | 8h |
| **Gate 4** | BlogSuggestionsConfirmation.jsx | POST /api/runs/{id}/gate-4 | 2.7-2.9 | 6h |
| **Gate 5** | FinalStrategyConfirmation.jsx | POST /api/runs/{id}/gate-5 | 2.10-2.12 | 6h |
| **P4 Module** | ContentStrategyPage.jsx | POST /api/runs/{id}/run-content-strategy | 2.13-2.18 | 12h |

**Subtotal:** 25 items (38h work)

---

## PHASE 3: UI/UX POLISH (WEEK 3)

### 3A: Keyword Universe Browser (D3 Tree)

| Item | What | Time |
|------|------|------|
| 3.1 | Backend: Generate D3 graph JSON from hierarchy | 2h |
| 3.2 | Store graph in system_graph_cache | 1h |
| 3.3 | KeywordTree.jsx — D3 force graph component | 6h |
| 3.4 | Add D3 library to package.json | 0.5h |
| 3.5 | Left panel: Keyword details (click node) | 3h |
| 3.6 | Right sidebar: Cluster actions (edit/delete/move) | 2h |
| 3.7 | Drag-drop for keyword movement between clusters | 3h |
| 3.8 | Test D3 tree interactions | 1.5h |

### 3B: Advanced Keyword Editing

| Item | Feature | Time |
|------|---------|------|
| 3.9 | Edit keyword term | 2h |
| 3.10 | Override keyword score | 1.5h |
| 3.11 | Delete keyword from universe | 1.5h |
| 3.12 | Add new keyword to cluster | 2h |
| 3.13 | Rerun keyword generation for single cluster | 4h |
| 3.14 | Test keyword editing operations | 2h |

### 3C: Console Enhancements

| Item | Feature | Time |
|------|---------|------|
| 3.15 | Phase card component | 2h |
| 3.16 | Data flow visualization arrows | 3h |
| 3.17 | Live progress indicators | 2h |
| 3.18 | Collapse/expand phase logs | 1.5h |
| 3.19 | Export console log button | 1h |
| 3.20 | Warnings/errors panel | 1.5h |

**Subtotal:** 20 items (42h work)

---

## PHASE 4: QUALITY + TESTING (WEEK 4+)

### 4A: P5 (Intent Classification) Learning Loop

**Issue:** P5 is rule-based only; no learning from customer feedback.

| Item | Task | Time |
|------|------|------|
| 4.1 | Add intent feedback button in KeywordPanel | 1.5h |
| 4.2 | Store feedback in keyword_feedback_intent table | 1h |
| 4.3 | QI Engine detects misclassification patterns | 2h |
| 4.4 | Generate tuning suggestions (Claude) | 2h |
| 4.5 | RSD approves tuning | 1.5h |
| 4.6 | Test: Manual corrections → tuning → reapplied | 1.5h |

**Result:** Intent classifier improves with each project run

### 4B: GEO Scorer Calibration

**Issue:** GEO scorer marks valid geo-content as 68-71 (below 75% threshold).

| Item | Task | Time |
|------|------|------|
| 4.7 | Collect 10 real geo-targeted articles + manual scores | 2h |
| 4.8 | Analyze GEO scorer weights | 1h |
| 4.9 | Retrain threshold weights | 2h |
| 4.10 | Test on 10 samples (target: < 10pt difference) | 1h |

**Result:** GEO score accuracy ≥ 90%

### 4C: AI Watermark Detector Tuning

**Issue:** 82% accuracy (18% false positive/negative).

| Item | Task | Time |
|------|------|------|
| 4.11 | Collect 200 training samples | 3h |
| 4.12 | Retrain detection model | 3h |
| 4.13 | Test on holdout set | 1.5h |

**Result:** 90%+ precision & recall

### 4D: Rate Limiting + Exponential Backoff

**Issue:** Basic Gemini rate limiting; needs exponential backoff.

| Item | Task | Time |
|------|------|------|
| 4.14 | Add exponential backoff for Gemini | 2h |
| 4.15 | Implement request queue | 2h |
| 4.16 | Test: 20 concurrent requests | 1.5h |

### 4E-F: Checkpoint & Rollback Testing

| Item | Task | Time |
|------|------|------|
| 4.17-4.19 | Test checkpoint resume under failures | 5h |
| 4.20-4.22 | Test rollback mechanism end-to-end | 3.5h |

**Subtotal:** 22 items (40h work)

---

## PHASE 5: POST-MVP FEATURES (Week 5+, Lower Priority)

| Feature | Est. Time | Priority |
|---------|-----------|----------|
| Programmatic SEO builder | 10h | Low |
| Backlink analysis engine | 12h | Low |
| Local SEO builder (NAP schema) | 6h | Low |
| Entity knowledge panel strength| 8h | Low |
| Content refresh weekly monitor | 6h | Medium |
| Multi-language keyword UI | 4h | Medium |
| Competitor keyword comparison | 4h | Medium |

**Subtotal:** 8 features (50h+ work)

---

## IMPLEMENTATION WORKFLOW

### How to Execute Phase 1 (NEXT 10 HOURS)

1. **Now (0.5h):** Confirm Phase 1.17-1.20 tasks with team
2. **Hours 1-3 (3h):** Implement resume-from-gate-2 logic in RufloEngine
3. **Hours 4-6.5 (2.5h):** Enhance console output with color/timing/data flow
4. **Hours 6.5-10 (3.5h):** Create PillarConfirmation.jsx (Phase 2) to test backend

### Parallelization Strategy

- **Frontend devs:** Build PillarConfirmation.jsx in hours 6.5-10 while backend work completes
- **Backend devs:** Continue with console enhancements in hours 4-6.5
- **QA:** Start integration tests with mock pillar data in hours 8-10

### Testing Checklist

After each 2-hour block:
1. Syntax check: `python3 -m py_compile main.py`
2. API endpoint test: `curl http://localhost:8000/api/system-status`
3. Git commit: `git add -A && git commit -m "Phase 1.X: [description]"`

---

## DATABASE SCHEMA REFERENCE

### New Tables (Added)

```sql
-- Gate state tracking
CREATE TABLE gate_states(
  gate_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  gate_number INTEGER NOT NULL,
  gate_name TEXT,
  input_json TEXT DEFAULT '{}',           -- what system showed
  customer_input_json TEXT DEFAULT '{}',  -- what customer confirmed/edited
  confirmed_at TEXT,
  confirmed_by TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(run_id, gate_number)
);

-- Content strategy for pillars
CREATE TABLE content_strategy(
  session_id TEXT PRIMARY KEY,
  run_id TEXT,
  pillar_id TEXT,
  angle TEXT,                    -- e.g., "Cost optimization focus"
  target_entities TEXT DEFAULT '[]',      -- JSON array of entities to emphasize
  schema_types TEXT DEFAULT '[]',        -- e.g., ["Article", "HowTo", "FAQ"]
  format_hints TEXT,             -- e.g., "Use comparison tables"
  internal_link_map TEXT DEFAULT '{}',   -- {source_keyword: [target_keywords]}
  confidence REAL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Keyword intent feedback (for QI learning)
CREATE TABLE keyword_feedback_intent(
  feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  keyword TEXT,
  predicted_intent TEXT,         -- what P5 said
  user_corrected_intent TEXT,    -- what user corrected to
  confidence REAL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Modified Tables (Columns Added)

**runs table:**
- `current_gate INTEGER` — Track which gate user is on
- `gate_1_confirmed INTEGER` — Flags for each gate
- `gate_2_confirmed INTEGER` through `gate_5_confirmed`
- `pillars_json TEXT` — Confirmed pillars from Gate 2
- `keywords_json TEXT` — Confirmed keywords from Gate 3
- `blog_suggestions_json TEXT` — Confirmed blogs from Gate 4
- `strategy_json TEXT` — Final strategy from Gate 5

**system_graph_cache table:**
- `node_types TEXT` — Summary of node counts by type
- `last_keyword_update TEXT` — When keywords last changed

---

## KEY ENDPOINTS IMPLEMENTED (Phase 1)

### Gate 2 Pillar Confirmation

```python
POST /api/runs/{run_id}/gate-2
{
  "pillars": [
    {
      "cluster_name": "Cinnamon Health",
      "pillar_title": "Benefits of Cinnamon for Health",
      "pillar_keyword": "cinnamon health benefits",
      "topics": ["blood sugar", "cholesterol", "diabetes"],
      "article_count": 12
    }
  ],
  "confirmed_by": "user@example.com",
  "notes": "Looks good, approved"
}

Response:
{
  "success": true,
  "gate_id": 2,
  "message": "Saved 5 pillars. Ready to proceed to keyword confirmation.",
  "next_gate": 3
}
```

### System Status

```python
GET /api/system-status

Response:
{
  "timestamp": "2026-03-25T14:30:00",
  "ollama": {
    "status": "ok|warning|error",
    "model": "deepseek-r1:7b",
    "message": "Loaded: deepseek-r1:7b"
  },
  "gemini": {
    "status": "ok",
    "configured": true,
    "message": "API key configured"
  },
  "claude": {
    "status": "ok",
    "configured": true,
    "message": "API key configured"
  },
  "gsc": {
    "status": "ok",
    "connected_projects": 3,
    "message": "3 projects syncing"
  }
}
```

### D3 Graph (Cached)

```python
GET /api/projects/{id}/d3-graph

Response:
{
  "name": "Black Pepper",
  "type": "root",
  "children": [
    {
      "name": "Cinnamon Health",
      "type": "pillar",
      "children": [
        {
          "name": "Blood Sugar Management",
          "type": "cluster",
          "children": [
            {
              "name": "cinnamon blood sugar",
              "type": "keyword",
              "intent": "informational",
              "keywords": ["cinnamon for blood sugar", "cinnamon diabetes"]
            }
          ]
        }
      ]
    }
  ],
  "total_keywords": 284,
  "total_pillars": 8
}
```

---

## SUMMARY TABLE (At a Glance)

| Phase | Items | Time | Status | Start Date |(End Date |
|-------|-------|------|--------|-----------|----------|
| **1: Fixes** | 20 | 30h | 🔴 IN PROGRESS | Mar 25 | Mar 27 |
| **2: Gates** | 25 | 44h | ⏳ WAITING | Mar 27 | Apr 3 |
| **3: UI/UX** | 20 | 42h | ⏳ WAITING | Mar 31 | Apr 7 |
| **4: Quality** | 22 | 40h | ⏳ WAITING | Apr 7 | Apr 14 |
| **5: Post-MVP** | 8 | 50h | ⏳ FUTURE | Apr 14+ | TBD |

**Total:** 95 items, **~150 hours**, **4 weeks** (full-time)

---

## HOW TO USE THIS DOCUMENT

1. **For Backend Devs:**
   - Read Phase 1 items 1.17-1.20
   - Implement resume-from-gate-2 + console enhancements
   - Reference database schema for gate_states table

2. **For Frontend Devs:**
   - Read Phase 2 items 2.1-2.12 (Gates 1-5)
   - Build PillarConfirmation.jsx once backend ready
   - Reference API endpoint examples

3. **For QA/Testing:**
   - Use completion checklists at end of each phase
   - Run API endpoint tests after each 2h block
   - Report issues to tech leads

4. **For Project Managers:**
   - Track progress against 4-week sprint
   - Green items = complete ✅
   - Yellow items = in progress 🟡
   - Red items = blocked 🔴

---

## CRITICAL SUCCESS FACTORS

✅ **Must Fix (Week 1):**
- Gate 2 pillar confirmation working end-to-end
- Resume-from-gate-2 logic preventing re-runs
- Console showing data flow + timing

✅ **Must Complete (Week 2):**
- All 5 gates have UI components
- Content duration picker after Gate 5
- Content Strategy module (P4) wired

✅ **Must Test (Week 4):**
- Rollback mechanism works (no data loss)
- Checkpoint resume under failures
- P5 intent feedback loop active

---

## Questions? Issues?

- **Blocked on backend API?** → Check main.py line numbers in this doc
- **Need clarification on gate flow?** → See RUFLO_ARCHITECTURE_V2.md in /root/ANNASEOv1/docs/
- **Database schema questions?** → See DATA_MODELS.md

---

**Last Updated:** March 25, 2026, 14:30 UTC  
**Maintained By:** AI Development Team  
**Next Review:** March 27, 2026 (End of Phase 1)
