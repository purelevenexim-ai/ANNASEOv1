# GCP — Google Search Console Engine

## Overview

The **GSC Engine** is an AI-powered keyword intelligence engine using Google Search Console
as the primary real-data source. It sits between **PhaseBI (Business Intelligence)** and **Phase 2
(Keyword Universe Generation)** in the kw2 workflow.

```
Phase 1 (Analyze) → Phase BI (Intel) → [GSC Engine] → Phase 2 (Generate) → ...
```

**GSC does NOT generate keywords.** It **filters, validates, and ranks** keywords
from real user demand — the actual queries people typed into Google to find your site.

---

## Corrected Mental Model

```
❌ WRONG: "Use GSC to generate 100 keywords per pillar"
✅ RIGHT: "Use GSC to extract real demand signals, filtered per pillar"
```

Your site already shows up for hundreds of queries in Google. GSC gives you that data.
The engine filters it by your pillars, classifies intent, scores by business priority,
and gives you the top 100 per pillar.

---

## Phase 1 Upgrade — Full System Flow

```
User Input (business desc + goal + seed keywords)
   ↓
🧠 AI Project Understanding  ← NEW in Phase 1 Upgrade
   pillars + intent signals + supporting angles + synonyms
   ↓
ProjectConfig stored in DB   ← Drives everything downstream
   ↓
GSC Full Keyword Pull  ← 1 API call, all queries (last 90 days)
   ↓
Filter per Pillar      ← Locally, using config pillars + synonyms
   ↓
Intent Classification  ← Config's purchase_intent_keywords first
   ↓
Supporting Angle Detection  ← NEW: groups informational content
   ↓
Scoring                ← source + impressions + clicks + intent boost
   ↓
Top 100 per Pillar     ← Business-prioritized, not just impressions
   ↓
Tree Output → Phase 2 (enriched keyword universe)
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| **AI Config first** | AI knows your business — defines WHAT to filter for, not just keyword names |
| **1 API call total** | Fetch all GSC data once → filter locally per pillar. Quota-friendly. |
| **Config-driven synonyms** | AI knows "elaichi" = cardamom. Regional terms dramatically improve match rate. |
| **Impressions = demand proxy** | GSC doesn't give search volume. Impressions ≈ Google showed your page for that query. |
| **Business-prioritized scoring** | "buy cardamom bulk" (500 impressions, purchase intent) scores HIGHER than "cardamom history" (5000 impressions, info) |
| **NOT keyword generation** | GSC validates real demand. Phase 2 still handles new/undiscovered keywords. |

---

## Important Limitation

If your site **doesn't rank** for "cardamom export", GSC won't show it.
This is why Phase 2 (AI-generated keywords) still runs — to discover keywords
beyond your current rankings. GSC validates; Phase 2 discovers.

---

## Build Phases

| Phase | Name | Status |
|---|---|---|
| Phase 1 | Data Foundation + AI Config | ✅ Complete |
| Phase 2 | Intelligence Layer (embeddings, clustering, graph, insights) | ✅ Complete |
| Phase 3 | UI Strategy Dashboard | 🔵 Planned |

See `ARCHITECTURE.md` for complete technical spec.

---

## New in Phase 1 Upgrade

### `engines/gsc/gsc_ai_config.py` (NEW)
- `ProjectConfig` dataclass — the intelligence object that drives the whole pipeline
- `generate_project_config(description, goal, seeds)` — calls `AIRouter` to analyze the business
- JSON parsing with fallback, sanitization, seed merge

### `engines/gsc/gsc_processor.py` (Upgraded)
- `detect_pillar(keyword, pillars, config)` — uses config synonyms + built-in SYNONYMS
- `classify_intent(keyword, config)` — config `purchase_intent_keywords` checked first
- `detect_angle(keyword, config)` — NEW: groups supporting content by topic
- `process_keywords(raw, config)` — accepts `ProjectConfig` OR `list[str]` (backward compat)

### `engines/gsc/gsc_engine.py` (Upgraded)
- `generate_config(project_id, ...)` — AI prompt → store config
- `get_config(project_id)` — read stored config
- `update_config(project_id, updates)` — manual edit
- `process(project_id, pillars=None)` — config-driven, pillars optional

### `engines/gsc/gsc_db.py` (Upgraded)
- `gsc_project_config` table — stores AI-generated config per project
- `get_project_config(project_id)`, `upsert_project_config(project_id, config)`

### `main.py` (3 new endpoints)
```
POST /api/gsc/{project_id}/config/generate  ← AI generation
GET  /api/gsc/{project_id}/config           ← Read config
PUT  /api/gsc/{project_id}/config           ← Manual edit
```

### `frontend/src/gsc/PhaseGSC.jsx` (Upgraded)
- **Tab 0: 🧠 AI Config** — new tab: describe business, AI generates config, editable
- Tabs 1-3 unchanged (Connect, Intelligence, Strategy)

### `frontend/src/gsc/api.js` (Extended)
- `generateConfig(projectId, body)`, `getConfig(projectId)`, `updateConfig(projectId, updates)`

---

## New in Phase 2 — Intelligence Layer

### Pipeline (7 steps, automated)
1. **Embeddings** — `sentence-transformers/all-MiniLM-L6-v2` (384 dims, local, free)
2. **AI Intent Classification** — batch LLM via AIRouter (50 kws/prompt) with obvious-intent pre-filter
3. **HDBSCAN Clustering** — auto-detect cluster count + LLM-generated cluster names
4. **Keyword Graph** — top-K cosine similarity neighbors (min_similarity=0.3)
5. **Advanced Scoring v2** — adds intent confidence + business priority to scoring formula
6. **Insight Generation** — quick_wins, money_keywords, content_gaps, linking, opportunities
7. **Pillar Authority** — per-pillar 0-100 score (coverage + traffic + intent + ranking + clusters)

### New API Endpoints (5)
```
POST /api/gsc/{project_id}/intelligence/run   ← Run full pipeline
GET  /api/gsc/{project_id}/clusters            ← Keyword clusters
GET  /api/gsc/{project_id}/graph               ← Keyword graph (nodes + links)
GET  /api/gsc/{project_id}/insights            ← SEO insights (optional ?type= filter)
GET  /api/gsc/{project_id}/authority           ← Pillar authority scores
```

### Frontend — Tab 4: Phase 2 Intelligence Dashboard
- **Pipeline Runner** — one-click "Run Intelligence" button with step-by-step timing
- **Authority Cards** — per-pillar score with strong/moderate/weak status
- **Cluster View** — expandable cards showing cluster name → keyword tags
- **Graph View** — interactive ForceGraph2D (intent colors, zoom-on-click, node details)
- **Insights Panel** — 5 sections: quick wins, money keywords, content gaps, linking suggestions, opportunities

### Dependencies Added
- Backend: `hdbscan`, `sentence-transformers`, `google-generativeai`
- Frontend: `react-force-graph-2d`

---

## Setup Requirements

1. Google Cloud Project with Search Console API enabled
2. OAuth 2.0 credentials (Web Application type)
3. Callback URL: `https://yourdomain.com/api/gsc/auth/callback`
4. Scopes: `https://www.googleapis.com/auth/webmasters.readonly`

See `GSC_OAUTH_SETUP.md` for step-by-step setup.

---

## Files

```
GCP/
  README.md               ← This file
  ARCHITECTURE.md         ← Full technical architecture (Phase 1 + Phase 2)
  GSC_OAUTH_SETUP.md      ← Google Cloud + OAuth setup guide

engines/gsc/
  gsc_ai_config.py        ← AI project understanding + ProjectConfig (Phase 1)
  gsc_db.py               ← DB layer (Phase 2: 4 new tables, embeddings/clusters/graph/insights)
  gsc_client.py           ← OAuth + data fetch
  gsc_processor.py        ← Config-driven keyword processing (Phase 1)
  gsc_engine.py           ← Orchestrator (Phase 2: 5 new methods)
  gsc_embeddings.py       ← Local sentence-transformers embeddings (Phase 2 – NEW)
  gsc_intent_ai.py        ← Batch LLM intent classification (Phase 2 – NEW)
  gsc_clustering.py       ← HDBSCAN clustering + LLM naming (Phase 2 – NEW)
  gsc_graph.py            ← Keyword similarity graph (Phase 2 – NEW)
  gsc_scoring_v2.py       ← Advanced scoring + authority (Phase 2 – NEW)
  gsc_insights.py         ← Quick wins, money kws, gaps, linking (Phase 2 – NEW)
  gsc_intelligence.py     ← Pipeline orchestrator (Phase 2 – NEW)

frontend/src/gsc/
  PhaseGSC.jsx            ← UI (Tab 4 added: Phase 2 Intelligence Dashboard)
  KeywordGraph.jsx        ← Interactive keyword graph (Phase 2 – NEW)
  api.js                  ← API helpers (5 Phase 2 functions added)
```


