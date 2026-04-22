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

**Last Updated:** April 10, 2026  
**Maintained By:** AI Development Team  
**Next Review:** See Strategy v2 milestone tracker below

---

---

# STRATEGY ENGINE V2 — DEVELOPMENT ROADMAP

**Scope:** Full rebuild of Strategy Page as the application's central intelligence layer  
**Reference:** `docs/strategyv2.md` — complete architecture, DB schema, prompts, API specs  
**Vision:** Transform from "AI Strategy Generator" → "Autonomous SEO Intelligence Platform"

## Why This Matters (Root Problems Being Solved)

1. **Split-brain architecture** — UI mixes KI (old) and KW2 (new) data. Breaks trust immediately.
2. **AI sees truncated data** — only top 30 keywords, top 20 clusters. Strategy is generic, not data-driven.
3. **Strategy is a dead end** — Phase 9 generates, displays, stops. No feedback into pipeline.
4. **Strategy is read-only** — user cannot edit pillar priorities, content mix, timelines.
5. **No execution intelligence** — no "what should I do next?" based on strategy decisions.
6. **Multiple disconnected engines** — Phase 9, Apply Strategy, Legacy Strategy all doing the same thing differently.

---

## MILESTONE 1 — Data Integrity (Fix Split-Brain) 🚨 IMMEDIATE

**Goal:** Fix the root cause of ~40% of existing bugs. Make everything read from kw2 session data.  
**Effort:** 2–3 days backend + 1 day frontend

### Backend

- [ ] **M1-B1** Fix Analysis page API → read from `kw2_validated_keywords` (not KI `keyword_strategy_briefs`)
- [ ] **M1-B2** Fix Content Hub API → read from `kw2_calendar` + `kw2_clusters` (not KI clusters)
- [ ] **M1-B3** Fix Overview KPIs API → read from `kw2_sessions` stats (not KI pipeline counts)
- [ ] **M1-B4** Audit all routes in `main.py` — every route that touches strategy/content must require `session_id`
- [ ] **M1-B5** Add `session_id` as required param to any endpoint currently using only `project_id` for content queries
- [ ] **M1-B6** Add DB migrations for `kw2_sessions`: `geo_targets TEXT`, `audience_targets TEXT`, `intent_target TEXT` columns

### Frontend

- [ ] **M1-F1** Update Analysis page component to call kw2 endpoints (not KI)
- [ ] **M1-F2** Update ContentHub component — replace KI cluster source with `kw2_clusters` + `kw2_calendar`
- [ ] **M1-F3** Update Overview KPI cards to read session-scoped keyword/cluster counts

### Verification

- [ ] **M1-V1** Keyword count in UI matches `kw2_sessions.validated_count` (not KI keyword_strategy_briefs count)
- [ ] **M1-V2** Content Hub articles are linked to a session_id
- [ ] **M1-V3** Overview KPIs show same numbers as Strategy Page Overview tab

---

## MILESTONE 2 — Strategy Intelligence Engine v2 (Upgrade Phase 9)

**Goal:** Upgrade existing Phase 9 to use richer data, 4 sub-modules, versioning, and editable output.  
**Effort:** 3–4 days backend + 2 days frontend  
**Reference:** `docs/strategyv2.md` § Phase 2

### DB Migrations

- [ ] **M2-DB1** Create `kw2_strategy_versions` table (versioned strategy output per session)
- [ ] **M2-DB2** Create `kw2_strategy_edits` table (track user edits to strategy fields)

### Backend — Engine Upgrade (`engines/kw2/strategy_engine.py`)

- [ ] **M2-B1** Remove top-30/top-20 truncation — pass ALL validated keywords using weighted cluster summaries
- [ ] **M2-B2** Implement Sub-Module 2A — Business Analysis (positioning, strengths, differentiation)
  - Input: `kw2_business_profile` + `kw2_biz_intel` + `kw2_biz_pages`
  - Output: `{positioning, strengths, opportunity, differentiation, icp_summary}`
- [ ] **M2-B3** Implement Sub-Module 2B — Keyword Intelligence (full dataset, funnel mapping, cannibalization)
  - Input: ALL `kw2_validated_keywords` + cluster distributions
  - Output: `{priority_clusters, funnel_map, cannibalization_risks, quick_wins}`
- [ ] **M2-B4** Implement Sub-Module 2C — Strategy Builder (uses 2A + 2B + competitors, generates full strategy JSON)
- [ ] **M2-B5** Implement Sub-Module 2D — Action Mapping (keyword boosts, cluster reorder, calendar priority)
  - Output: `{keyword_boosts, cluster_reorder, calendar_priority}` — feeds back into pipeline
- [ ] **M2-B6** Save each generation to `kw2_strategy_versions` (not overwriting `strategy_json`)
- [ ] **M2-B7** `GET /api/kw2/{pid}/sessions/{sid}/strategy/versions` — list all versions
- [ ] **M2-B8** `POST /api/kw2/{pid}/sessions/{sid}/strategy/activate/{version_id}` — set active version
- [ ] **M2-B9** `PATCH /api/kw2/{pid}/sessions/{sid}/strategy/edit` — save user edits to `kw2_strategy_edits`
- [ ] **M2-B10** `GET /api/kw2/{pid}/sessions/{sid}/strategy/diff/{v1}/{v2}` — compare two versions

### Backend — Action Mapping Feedback (close the loop)

- [ ] **M2-B11** After Phase 9 completes: apply `keyword_boosts` from 2D to `kw2_validated_keywords.final_score`
- [ ] **M2-B12** After Phase 9 completes: apply `cluster_reorder` to `kw2_clusters` sort order
- [ ] **M2-B13** After Phase 9 completes: apply `calendar_priority` to `kw2_calendar` schedule ordering

### Frontend — `SessionStrategyPage.jsx` StrategyTab Upgrades

- [ ] **M2-F1** Version badge in metadata bar: "v3 · Generated 2h ago · Active"
- [ ] **M2-F2** Version history drawer (list versions, Activate / Compare buttons)
- [ ] **M2-F3** Edit mode toggle per strategy section (pillar priorities, content mix sliders, quick wins)
- [ ] **M2-F4** "Regenerate section" button per strategy card (calls sub-module endpoint)
- [ ] **M2-F5** Side-by-side diff view for two strategy versions

---

## MILESTONE 3 — Question Intelligence Engine (NEW)

**Goal:** Build the 7-module question intelligence system that generates structured business questions from all data.  
**Effort:** 3 days backend + 2 days frontend  
**Reference:** `docs/strategyv2.md` § Phase 3  
**New file:** `engines/kw2/question_engine.py`

### DB Migrations

- [ ] **M3-DB1** Create `kw2_intelligence_questions` table
  - Columns: `id, session_id, project_id, source_module, question, category, why_it_matters, data_source, priority, answer, answer_confidence, expansion_depth, parent_question_id, status`
  - Add enrichment columns: `intent, funnel_stage, audience_segment, geo_relevance, business_relevance, content_type, effort`
  - Add scoring columns: `final_score, score_breakdown`
  - Add clustering columns: `content_cluster_id, is_duplicate, duplicate_of`

### Backend — `engines/kw2/question_engine.py`

- [ ] **M3-B1** Module Q1: Business Core Questions (from `kw2_business_profile` + `kw2_biz_intel`)
- [ ] **M3-B2** Module Q2: Audience Intelligence Questions (from `kw2_biz_intel.audience_segments` + keyword intent)
- [ ] **M3-B3** Module Q3: Intent Mapping Questions (from ALL `kw2_validated_keywords`)
- [ ] **M3-B4** Module Q4: Customer Journey Questions (from `buyer_readiness` + intent distribution → TOFU/MOFU/BOFU)
- [ ] **M3-B5** Module Q5: Product/Service Deep Questions (from `kw2_biz_pages` + `products_services`)
- [ ] **M3-B6** Module Q6: Content Opportunity Questions (educational, problem-based, comparison, authority)
- [ ] **M3-B7** Module Q7: Competitive Intelligence Questions (from `kw2_biz_competitors` + `kw2_biz_competitor_keywords`)
- [ ] **M3-B8** Prompt templates for each module — no hardcoding, all variables from session data
- [ ] **M3-B9** `POST /api/kw2/{pid}/sessions/{sid}/question-engine/run` — trigger all 7 modules
- [ ] **M3-B10** `GET /api/kw2/{pid}/sessions/{sid}/question-engine/questions` — list with filters
- [ ] **M3-B11** `GET /api/kw2/{pid}/sessions/{sid}/question-engine/summary` — count per module + status
- [ ] **M3-B12** `PATCH /api/kw2/{pid}/sessions/{sid}/question-engine/{qid}` — edit/annotate  
- [ ] **M3-B13** `DELETE /api/kw2/{pid}/sessions/{sid}/question-engine/{qid}` — remove

### Frontend — New "Intelligence" Tab in `SessionStrategyPage.jsx`

- [ ] **M3-F1** Add `🧠 Intelligence` tab between `Keywords` and `Strategy`
- [ ] **M3-F2** Module cards (Q1–Q7) with question counts, status badges (pending/answered/expanded)
- [ ] **M3-F3** Question list per module: question text, category, priority badge, expandable answer panel
- [ ] **M3-F4** Filter bar: by module, priority, answered/unanswered, category
- [ ] **M3-F5** "Generate Questions" button → runs Phase 3 engine
- [ ] **M3-F6** "Answer All" button → runs Phase 5 enrichment for all questions
- [ ] **M3-F7** Add `api.runQuestionEngine()`, `api.getQuestions()`, `api.getQuestionSummary()` to `api.js`

---

## MILESTONE 4 — Expansion Engine + Dedup + Scoring

**Goal:** Recursively expand questions across business-specific dimensions; deduplicate; score all questions.  
**Effort:** 4 days backend + 1 day frontend  
**Reference:** `docs/strategyv2.md` § Phases 4, 6, 7  
**New files:** `engines/kw2/expansion_engine.py`, `engines/kw2/dedup_engine.py`, `engines/kw2/scoring_engine.py`

### DB Migrations

- [ ] **M4-DB1** Create `kw2_expansion_config` table (max_depth, max_per_node, dedup_threshold, max_total, discovered_dimensions)
- [ ] **M4-DB2** Create `kw2_content_clusters` table (cluster_name, description, pillar, intent_mix, question_count, avg_score)
- [ ] **M4-DB3** Create `kw2_scoring_config` table (per-session weights JSON)

### Backend — Expansion Engine (`engines/kw2/expansion_engine.py`)

- [ ] **M4-B1** Dimension discovery prompt — AI identifies geo/use-case/audience/product dimensions from session data (no hardcoding)
- [ ] **M4-B2** Expansion prompt template — expands any question across any dimension (generic, business-agnostic)
- [ ] **M4-B3** Recursive expansion loop: L0 (seed) → L1 → L2, controlled by config
- [ ] **M4-B4** Config controls: `max_depth`, `max_per_node`, `max_total` (all user-configurable)
- [ ] **M4-B5** `POST /api/kw2/{pid}/sessions/{sid}/expansion/discover-dimensions`
- [ ] **M4-B6** `POST /api/kw2/{pid}/sessions/{sid}/expansion/run`
- [ ] **M4-B7** `GET /api/kw2/{pid}/sessions/{sid}/expansion/status`
- [ ] **M4-B8** `PATCH /api/kw2/{pid}/sessions/{sid}/expansion/config`

### Backend — Dedup Engine (`engines/kw2/dedup_engine.py`)

- [ ] **M4-B9** Pass 1: Levenshtein exact/near-exact dedup (threshold < 0.1)
- [ ] **M4-B10** Pass 2: Semantic embedding similarity dedup (cosine > 0.85 = duplicate)
- [ ] **M4-B11** Mark duplicates in `kw2_intelligence_questions` (`is_duplicate=1, duplicate_of=parent_id`)
- [ ] **M4-B12** Clustering prompt: group deduplicated questions into coherent content topic clusters
- [ ] **M4-B13** Save clusters to `kw2_content_clusters`; update `content_cluster_id` on each question

### Backend — Scoring Engine (`engines/kw2/scoring_engine.py`)

- [ ] **M4-B14** Generic 5-component weighted scoring formula (no hardcoding):
  - `business_fit × w1` — AI score from enrichment × pillar match bonus
  - `intent_value × w2` — transactional=1.0, commercial=0.8, informational=0.6, navigational=0.4
  - `demand_potential × w3` — keyword volume signal or AI estimate
  - `competition_ease × w4` — inverse keyword difficulty
  - `uniqueness × w5` — penalise well-covered competitor topics; reward gap topics
- [ ] **M4-B15** Weights stored per session in `kw2_scoring_config` (default: 0.30/0.20/0.20/0.15/0.15)
- [ ] **M4-B16** `POST /api/kw2/{pid}/sessions/{sid}/scoring/run`
- [ ] **M4-B17** `GET /api/kw2/{pid}/sessions/{sid}/scoring/config`
- [ ] **M4-B18** `PATCH /api/kw2/{pid}/sessions/{sid}/scoring/config` — update weights
- [ ] **M4-B19** `GET /api/kw2/{pid}/sessions/{sid}/scoring/ranked` — sorted by `final_score`

### Frontend — Intelligence Tab Additions

- [ ] **M4-F1** Expansion progress bar + status (total generated, after dedup, by cluster)
- [ ] **M4-F2** Scoring config panel: 5 weight sliders (must sum to 1.0)
- [ ] **M4-F3** Ranked question list with score breakdown tooltip
- [ ] **M4-F4** Cluster view: group questions by `content_cluster_id`

---

## MILESTONE 5 — Content Title Engine + Selection (Phases 8 & 9)

**Goal:** Select balanced top-N questions and convert them into SEO-optimised content titles.  
**Effort:** 3 days backend + 3 days frontend  
**Reference:** `docs/strategyv2.md` § Phases 8, 9  
**New files:** `engines/kw2/selection_engine.py`, `engines/kw2/content_title_engine.py`

### DB Migrations

- [ ] **M5-DB1** Create `kw2_selected_questions` table (selection_rank, selection_reason, cluster_id, content_title_id, status)
- [ ] **M5-DB2** Create `kw2_content_titles` table
  - Columns: `id, session_id, project_id, question_id, title, slug, primary_keyword, meta_title, content_type, word_count_target, pillar, cluster_name, intent, funnel_stage, brief_json, article_id, status, scheduled_date`

### Backend — Selection Engine (`engines/kw2/selection_engine.py`)

- [ ] **M5-B1** Selection config: `target_count`, `min_per_cluster`, `max_per_cluster`, intent distribution targets
- [ ] **M5-B2** Diversity-balanced selection algorithm (ensures geo/intent/funnel/cluster coverage)
- [ ] **M5-B3** `POST /api/kw2/{pid}/sessions/{sid}/selection/run`
- [ ] **M5-B4** `GET /api/kw2/{pid}/sessions/{sid}/selection/list`
- [ ] **M5-B5** `POST /api/kw2/{pid}/sessions/{sid}/selection/include/{qid}` — manual add
- [ ] **M5-B6** `DELETE /api/kw2/{pid}/sessions/{sid}/selection/{qid}` — manual remove

### Backend — Content Title Engine (`engines/kw2/content_title_engine.py`)

- [ ] **M5-B7** Title generation prompt: question → SEO title + slug + primary_keyword + meta_title (generic, no hardcoding)
- [ ] **M5-B8** Batch processing (50 questions per AI call)
- [ ] **M5-B9** Save to `kw2_content_titles`; link to `kw2_selected_questions`
- [ ] **M5-B10** `POST /api/kw2/{pid}/sessions/{sid}/content-titles/generate` — batch title generation
- [ ] **M5-B11** `GET /api/kw2/{pid}/sessions/{sid}/content-titles` — list with pillar/intent/status filters
- [ ] **M5-B12** `POST /api/kw2/{pid}/sessions/{sid}/content-titles/{id}/brief` — generate brief (uses existing brief infrastructure)
- [ ] **M5-B13** `POST /api/kw2/{pid}/sessions/{sid}/content-titles/{id}/article` — generate article
- [ ] **M5-B14** `PATCH /api/kw2/{pid}/sessions/{sid}/content-titles/{id}` — edit title/slug/meta

### Frontend — New "Titles" Tab in `SessionStrategyPage.jsx`

- [ ] **M5-F1** Add `📝 Titles` tab between `Strategy` and `Content Plan`
- [ ] **M5-F2** Title list: title, keyword, intent badge, funnel badge, score, status chip
- [ ] **M5-F3** Filter bar: pillar, cluster, intent, funnel_stage, status
- [ ] **M5-F4** Bulk action: select multiple → "Generate All Briefs"
- [ ] **M5-F5** Article grid actions per title: Generate Brief | Edit | Schedule | Mark Published

### Frontend — Content Hub Upgrade (Session-Aware)

- [ ] **M5-F6** Content Hub article list reads from `kw2_content_titles` (not ad-hoc)
- [ ] **M5-F7** Articles ordered by `selection_rank`
- [ ] **M5-F8** "What to do next" widget: 3 actionable cards (Money priority, Quick Win, Cluster momentum)
- [ ] **M5-F9** Pillar-based browsing: pillar → cluster → titles hierarchy

---

## MILESTONE 6 — Prompt Studio (Phase 12)

**Goal:** Every AI prompt in the system is visible, editable, versioned, and testable by the user.  
**Effort:** 3 days backend + 2 days frontend  
**Reference:** `docs/strategyv2.md` § Phase 12  
**New file:** `engines/kw2/prompt_manager.py`

### DB Migrations

- [ ] **M6-DB1** Create `kw2_prompts` table (prompt_key, phase, display_name, template, variables, is_system, version)
- [ ] **M6-DB2** Create `kw2_prompt_versions` table (prompt_id, template, version, changed_by, change_note)

### Backend

- [ ] **M6-B1** Seed all existing prompts from `engines/kw2/prompts.py` into `kw2_prompts` table on startup
- [ ] **M6-B2** `engines/kw2/prompt_manager.py` — CRUD helper; all AI calls read from DB instead of hardcoded strings
- [ ] **M6-B3** Update all engines to use `prompt_manager.get_prompt(key, variables)` instead of inline templates
- [ ] **M6-B4** `GET /api/kw2/prompts` — list all prompts
- [ ] **M6-B5** `GET /api/kw2/prompts/{key}` — get prompt + variable documentation
- [ ] **M6-B6** `PATCH /api/kw2/prompts/{key}` — update template (saves old version automatically)
- [ ] **M6-B7** `POST /api/kw2/prompts/{key}/test` — test prompt with sample session data → returns AI output
- [ ] **M6-B8** `GET /api/kw2/prompts/{key}/versions` — version history
- [ ] **M6-B9** `POST /api/kw2/prompts/{key}/restore/{version}` — rollback

### Frontend — New "Prompts" Tab in `SessionStrategyPage.jsx`

- [ ] **M6-F1** Add `🔧 Prompts` tab at end of tab bar
- [ ] **M6-F2** Prompt list grouped by phase (Phase 2 / Phase 3 / Phase 4 / etc.)
- [ ] **M6-F3** Prompt editor: textarea + variable reference panel showing what each `{variable}` contains
- [ ] **M6-F4** "Test Prompt" button → sends sample context → shows AI output preview
- [ ] **M6-F5** Version history with diff view + Restore button
- [ ] **M6-F6** Phase badge per prompt (e.g. "Phase 3 · Q2 Audience")

---

## MILESTONE 7 — Feedback & Learning Engine (Phase 11)

**Goal:** Track published content performance and feed results back into scoring weights automatically.  
**Effort:** 3 days backend + 2 days frontend  
**Reference:** `docs/strategyv2.md` § Phase 11  
**New file:** `engines/kw2/feedback_engine.py`

### DB Migrations

- [ ] **M7-DB1** Create `kw2_content_performance` table
  - Columns: `id, session_id, content_title_id, article_id, tracked_date, google_position, organic_clicks, impressions, ctr, conversions, data_source`

### Backend

- [ ] **M7-B1** `POST /api/kw2/{pid}/sessions/{sid}/performance/record` — manual performance entry
- [ ] **M7-B2** `GET /api/kw2/{pid}/sessions/{sid}/performance/summary`
- [ ] **M7-B3** Feedback analysis: compare predicted score vs actual performance
- [ ] **M7-B4** Bayesian weight adjustment (learning_rate=0.1, min 5 data points before adjusting)
- [ ] **M7-B5** `POST /api/kw2/{pid}/sessions/{sid}/performance/apply-learnings` — update `kw2_scoring_config.weights`

### Frontend

- [ ] **M7-F1** Performance dashboard in Overview tab: CTR, position, clicks per content title
- [ ] **M7-F2** Manual performance input form per article in Titles tab
- [ ] **M7-F3** "Apply Learnings" button → shows how weights will change → confirm → applies

---

## PHASE SUMMARY TABLE

| Milestone | Phases | New Files | Backend Items | Frontend Items | Effort |
|---|---|---|---|---|---|
| **M1: Data Integrity** | — | — | 6 | 3 | 3–4 days |
| **M2: Strategy v2** | Phase 2 | `strategy_engine.py` upgrade | 13 | 5 | 5–6 days |
| **M3: Question Engine** | Phase 3 | `question_engine.py` | 13 | 7 | 5 days |
| **M4: Expansion+Scoring** | Phases 4,6,7 | `expansion_engine.py`, `dedup_engine.py`, `scoring_engine.py` | 19 | 4 | 5 days |
| **M5: Titles+ContentHub** | Phases 8,9,10 | `selection_engine.py`, `content_title_engine.py` | 14 | 9 | 6 days |
| **M6: Prompt Studio** | Phase 12 | `prompt_manager.py` | 9 | 6 | 5 days |
| **M7: Feedback Loop** | Phase 11 | `feedback_engine.py` | 5 | 3 | 5 days |

**Total new items:** ~120 tasks  
**Total new engine files:** 7  
**Total new DB tables:** 11  
**Total estimated effort:** 34–36 days (building sequentially)

---

## NEW DB TABLES REQUIRED

| Table | Milestone | Purpose |
|---|---|---|
| `kw2_strategy_versions` | M2 | Versioned strategy outputs |
| `kw2_strategy_edits` | M2 | User edits to strategy fields |
| `kw2_intelligence_questions` | M3 | All questions: seed + expanded + enriched + scored |
| `kw2_expansion_config` | M4 | Expansion engine config per session |
| `kw2_content_clusters` | M4 | Topic clusters from dedup phase |
| `kw2_scoring_config` | M4 | Per-session scoring weights |
| `kw2_selected_questions` | M5 | Top questions selected for content |
| `kw2_content_titles` | M5 | Generated SEO titles → briefs → articles |
| `kw2_content_performance` | M7 | Published article performance metrics |
| `kw2_prompts` | M6 | Prompt registry with templates |
| `kw2_prompt_versions` | M6 | Prompt version history |

Full schema DDL for each table is in `docs/strategyv2.md`.

---

## DESIGN PRINCIPLES (Non-Negotiable)

1. **No hardcoding** — every value derived from data, config or user input
2. **Session-first** — every query requires `session_id`
3. **Prompt visibility** — user can see and edit every prompt
4. **Modular AI blocks** — each engine is independent; swap or skip any phase
5. **Generic business model** — zero assumptions about business type in engine logic
6. **Controlled expansion** — recursive growth bounded by configurable limits
7. **Strategy drives everything** — content, calendar, briefs derive from strategy decisions
8. **Feedback loop** — system improves based on published content performance

---

## UPDATED TAB STRUCTURE (After v2)

```
Current (7 tabs):
📊 Overview | 🔑 Keywords | 🗺️ Strategy | ✍️ Content Plan | 🔗 Links | 📋 Parameters | 🎯 Goals

v2 Target (10 tabs):
📊 Overview | 🔑 Keywords | 🧠 Intelligence | 🗺️ Strategy | 📝 Titles | ✍️ Content Plan | 🔗 Links | 📋 Parameters | 🎯 Goals | 🔧 Prompts
```

---

**Architecture reference:** `docs/strategyv2.md`  
**Last Updated:** April 10, 2026
