# Keyword Page — Full Reference

> The Keyword page is the core SEO intelligence module of AnnaSEO. It is a 3-step wizard (`Setup → Discovery → Pipeline`) that transforms a user's business inputs into a structured, scored, clustered keyword universe ready for content strategy.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Frontend Components](#frontend-components)
4. [7-Step Legacy Workflow (Backup Path)](#7-step-legacy-workflow-backup-path)
5. [API Routes Reference](#api-routes-reference)
6. [Backend Engines](#backend-engines)
7. [Database Schema](#database-schema)
8. [AI Providers & API Keys](#ai-providers--api-keys)
9. [Scoring System](#scoring-system)
10. [Data Flow — End to End](#data-flow--end-to-end)
11. [Pipeline Phases (P1–P14)](#pipeline-phases-p1p14)
12. [Environment Variables](#environment-variables)
13. [Key Files Index](#key-files-index)

---

## Overview

The Keyword page (`/keywords` route) is a **unified tab container** exposing three sub-views:

| Tab | Component | Purpose |
|-----|-----------|---------|
| **Workflow** | `KeywordWorkflow` | 3-step wizard: Setup → Discovery → Pipeline |
| **Keyword Tree** | `KeywordTreePage` | D3.js visual explorer of the keyword universe |
| **Rankings** | `RankingsPage` | Track keyword positions over time |

The workflow starts a **session** tied to a project. A session tracks progress through all stages; it is resumable — the user can close and reopen the browser and continue from where they left off.

---

## Architecture

```
Browser (React/Vite)
│
├── KeywordsUnifiedPage        [App.jsx]
│     ├── KeywordWorkflow      [KeywordWorkflow.jsx]
│     │     ├── Step1Setup     [workflow/Step1Setup.jsx]
│     │     ├── Step2Discovery [workflow/Step2Discovery.jsx]
│     │     └── Step3Pipeline  [workflow/Step3Pipeline.jsx]
│     ├── KeywordTreePage      [App.jsx — D3.js tree]
│     └── RankingsPage         [App.jsx]
│
└── State: WorkflowContext (Zustand) + React Query
          └── ctx.step1 (pillars, supports, urls, intent)
          └── ctx.step2 (keyword_count, clusterData)
          └── ctx.step3 (pipeline results)

FastAPI Backend [main.py — port 8000]
│
├── /api/ki/{project_id}/*     KeywordInput routes (79 endpoints)
├── /api/ki/{project_id}/research/stream   SSE stream
├── /api/ki/{project_id}/cluster-keywords  AI clustering
├── /api/ki/{project_id}/strategy/stream   Strategy generation
│
├── engines/annaseo_keyword_input.py    Universe generation
├── engines/annaseo_keyword_scorer.py   KD + volume scoring
├── engines/research_engine.py          Multi-source research
├── engines/intelligent_crawl_engine.py Crawl + competitor
├── engines/ruflo_v3_keyword_system.py  20-phase pipeline
└── engines/ruflo_20phase_engine.py     Phase orchestration

Database: ./annaseo.db (SQLite)
```

---

## Frontend Components

### `KeywordsUnifiedPage` — `App.jsx`
- Container for the three tabs
- Pulls `activeProject` from Zustand store
- Loads latest strategy summary on mount (`GET /api/strategy/{id}/latest`)

### `KeywordWorkflow` — `frontend/src/KeywordWorkflow.jsx`
3-step orchestrator. Manages:
- `step` (1/2/3), `sessionId`, `maxReached`
- Session checkpoint via `ctx.flush()` → DB after each step completes
- `GET /api/ki/{project_id}/workflow-status` on mount to resume correct step

**Step routing:**
```
Backend stage  → Frontend step
input/setup    → 1 (Step1Setup)
research/disco → 2 (Step2Discovery)
review/pipeline
 clusters/cal  → 3 (Step3Pipeline)
```

---

### Step 1 — Setup (`workflow/Step1Setup.jsx`)

**Purpose:** Collect all business inputs needed for keyword discovery.

**Fields collected:**
- Business name, type, industry, description
- Target locations (array of regions/cities)
- Target languages
- Personas / audience segments
- Customer website URL
- Competitor URLs (up to 5)
- Pillar keywords (the core strategy anchors, e.g. "Cinnamon")
- Supporting keywords / qualifiers (e.g. "organic", "buy online", "Kerala")
- Business intent: `transactional | informational | mixed`

**API calls:**
- `PUT /api/ki/{project_id}/profile` — saves business profile
- `POST /api/ki/{project_id}/input` — saves pillars + supporting keywords, creates session

**Output:** `sessionId` passed to Step 2

---

### Step 2 — Discovery (`workflow/Step2Discovery.jsx`)

**Purpose:** Multi-source keyword discovery with live SSE console, 6 discovery stages.

**6 Discovery Stages (cascading, results appear per stage):**

| Stage | What happens |
|-------|-------------|
| **Stage 1** | Crawl customer website → extract ranking keywords, H1/H2, meta descriptions |
| **Stage 2** | Crawl competitor websites → extract their pillars |
| **Stage 3** | SSE research stream — 6-source keyword discovery |
| **Stage 4** | Keyword universe build → `keyword_universe_items` |
| **Stage 5** | AI scoring + cluster grouping |
| **Stage 6** | (Reserved) Strategy run |

**Stage 3 sources (inside SSE stream `POST /api/ki/{id}/research/stream`):**
1. User-provided supporting keywords (score +10)
2. Cross-multiplication: Pillar × Supporting → combinations
3. Customer site crawl keywords
4. Competitor site crawl keywords  
5. Google Autosuggest per combination
6. Wikipedia / encyclopedic context scraping

**AI Provider Selector:**
Users can choose which AI scores and clusters the keywords:

| Option | Model | Notes |
|--------|-------|-------|
| Groq | `llama-3.3-70b-versatile` | Default: fastest |
| Gemini Free | `gemini-2.0-flash` | Free tier |
| Gemini Paid | `gemini-pro` | Paid tier |
| Ollama | `mistral:7b-instruct-q4_K_M` | Local/remote |
| Claude | `claude-sonnet` | Anthropic |
| ChatGPT | `gpt-4o` | OpenAI |

The selected provider is sent as `preferred_provider` in both:
- `POST /api/ki/{id}/research/stream`
- `POST /api/ki/{id}/cluster-keywords`

**Key state in Step2Discovery:**
```js
discoveryAiProvider  // which AI to use (default: "groq")
streamEvents         // live log lines from SSE
mergedCrawlCards     // combined Stage1+2 pillar cards
universeData         // Stage 4: keyword universe
clusterData          // Stage 5: AI-scored clusters
```

**Inline results table features:**
- Filter by source badge (cross-multiply / user / site-crawl / competitor / google / wikipedia)
- Filter by intent (transactional / informational / commercial / comparison / local)
- Pagination (50 per page)
- Accept / Reject / Edit individual keywords
- Bulk accept/reject/mark-bad
- Rename pillar, delete pillar, move keywords between pillars

---

### Step 3 — Pipeline (`workflow/Step3Pipeline.jsx`)

**Purpose:** Run 14 structured phases (P1–P14) to process the accepted keyword universe into a production-ready structure.

**Layout:** Split-view
- Left 40%: Live console scrolling through phase logs
- Right 60%: 14 result cards filling in as phases complete

**Execution modes:**
- Auto (run all 14 phases end-to-end)
- Manual (pause between phases for review)

**Per-pillar tabs:** Results can be browsed by each confirmed pillar keyword

See [Pipeline Phases (P1–P14)](#pipeline-phases-p1p14) for detail.

---

### Legacy 7-Step Workflow (inside `KeywordWorkflow.jsx` — backup)

There is also an older 7-step linear flow still present in the same file, used as fallback:

| Step | Component | Purpose |
|------|-----------|---------|
| 1 | `StepInput` | Enter pillar + supporting keywords |
| 2 | `StepResearch` | SSE discovery stream |
| 3 | `StepReview` | Review/edit keyword universe table |
| 4 | `StepAIReview` | AI auto-classify remaining keywords |
| 5 | `StepPipeline` | Select pillars for pipeline |
| 6 | `StepClusters` | View cluster structure |
| 7 | `StepCalendar` | Handoff to content calendar |

---

### `KeywordDashboard`
Shown when a project already has keywords (skip Step 1+2). Displays:
- Session summary (pillars, keyword counts, status breakdown)
- Recent keywords table with accept/reject status
- Quick-action cards: Continue pipeline, Go to Strategy, Go to Calendar

### `KeywordTreePage` — D3.js (inside `App.jsx`)
- Text filter input
- Intent filter buttons: all / informational / transactional / question / comparison
- Radial D3.js tree rendering the full keyword universe
- Data source: `GET /api/projects/{project_id}/keyword-tree`

---

## API Routes Reference

All routes are under `/api/ki/{project_id}/`. Auth: `Bearer` JWT required.

### Session & Input

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/input` | Save pillar + supporting keywords, create session |
| `GET` | `/api/ki/{pid}/session/{session_id}` | Get session state |
| `GET` | `/api/ki/{pid}/latest-session` | Get most recent session |
| `GET` | `/api/ki/{pid}/sessions` | List all sessions |
| `PATCH` | `/api/ki/{pid}/session/{session_id}/ctx` | Update session workflow context |
| `GET` | `/api/ki/{pid}/session/{session_id}/ctx` | Get session workflow context |

### Pillars

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/pillars` | List confirmed pillar keywords |
| `DELETE` | `/api/ki/{pid}/pillars/{pillar}` | Delete a pillar (nulls child keywords) |
| `GET` | `/api/ki/{pid}/pillar-status` | Pillar processing status |

### Keyword Universe

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/final-keywords` | Get all accepted/confirmed keywords |
| `POST` | `/api/ki/{pid}/keyword-delete` | Delete a keyword item |
| `POST` | `/api/ki/{pid}/keyword-update` | Update keyword text/intent/pillar |
| `GET` | `/api/ki/{pid}/universe/{session_id}/by-pillar` | Keywords grouped by pillar |
| `GET` | `/api/ki/{pid}/universe/{session_id}/pillar-cards` | Summary cards per pillar |
| `POST` | `/api/ki/{pid}/keyword-universe` | Trigger keyword universe build |

### Review Flow

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/review/{session_id}` | Get review queue (paginated) |
| `POST` | `/api/ki/{pid}/review/{session_id}/action` | Accept / reject / edit single keyword |
| `POST` | `/api/ki/{pid}/review/{session_id}/accept-all` | Accept all pending |
| `POST` | `/api/ki/{pid}/review/{session_id}/bulk-action` | Bulk accept/reject/move |
| `POST` | `/api/ki/{pid}/review/{session_id}/rename-pillar` | Rename a pillar |
| `POST` | `/api/ki/{pid}/review/{session_id}/delete-pillar` | Delete entire pillar |
| `POST` | `/api/ki/{pid}/review/{session_id}/move-keywords` | Move keywords to another pillar |
| `DELETE` | `/api/ki/{pid}/review/{session_id}/items` | Delete multiple items |
| `POST` | `/api/ki/{pid}/confirm/{session_id}` | Confirm final universe |
| `GET` | `/api/ki/{pid}/session/{session_id}/accepted-pillars` | Accepted pillars for session |

### AI Review

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/ai-review` | Trigger AI auto-classification of keywords |
| `POST` | `/api/ki/{pid}/ai-review/session/{session_id}` | AI review for specific session |
| `POST` | `/api/ki/{pid}/ai-review/override` | Override AI classification decision |
| `GET` | `/api/ki/{pid}/ai-review/results` | Get AI review results |

### Research & Discovery (SSE)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/research` | Non-streaming research (batch) |
| `POST` | `/api/ki/{pid}/research/stream` | **SSE stream** — 6-source discovery with live events |
| `POST` | `/api/ki/{pid}/run` | Start research job (async) |
| `GET` | `/api/ki/{pid}/research/{job_id}` | Poll research job status |

**`/research/stream` body:**
```json
{
  "session_id": "sess_xxx",
  "pillars": ["cinnamon", "turmeric"],
  "supports": ["organic", "buy online"],
  "customer_url": "https://yoursite.com",
  "competitor_urls": ["https://comp1.com"],
  "business_intent": "transactional",
  "preferred_provider": "groq"
}
```

### Scoring & Clustering

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/score/{session_id}` | Score keyword batch (KD + volume) |
| `GET` | `/api/ki/{pid}/score/{session_id}/{job_id}` | Poll scoring job |
| `POST` | `/api/ki/{pid}/cluster-keywords` | AI-powered keyword clustering |
| `GET` | `/api/ki/{pid}/clusters` | Get cluster structure |
| `POST` | `/api/ki/{pid}/clusters/generate` | Regenerate clusters |

**`/cluster-keywords` body:**
```json
{
  "session_id": "sess_xxx",
  "keywords": [...],
  "preferred_provider": "groq"
}
```

### Crawl & Intelligence

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/intelligent-crawl` | Crawl customer site, extract keywords |
| `POST` | `/api/ki/{pid}/intelligent-competitor` | Crawl competitor sites |
| `POST` | `/api/ki/{pid}/intelligent-score` | AI score a keyword set |
| `POST` | `/api/ki/{pid}/crawl-context` | Store crawl context |
| `POST` | `/api/ki/{pid}/crawl-review/action` | Accept/reject crawled keyword |
| `POST` | `/api/ki/{pid}/crawl-save-state` | Save crawl review state |
| `POST` | `/api/ki/{pid}/{session_id}/merge-crawl` | Merge crawled keywords into session |
| `GET` | `/api/ki/{pid}/crawl-saved-state` | Get saved crawl state |

### Top-100 Tracking

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/top100/{session_id}` | Get top 100 keywords |
| `POST` | `/api/ki/{pid}/top100/{session_id}/refresh` | Re-score top 100 |
| `GET` | `/api/ki/{pid}/top100/{session_id}/diff` | Diff vs previous snapshot |
| `GET` | `/api/ki/{pid}/top100/{session_id}/summary` | Summary stats |
| `POST` | `/api/ki/{pid}/top100/{session_id}/serp-check` | Live SERP check for keywords |
| `GET` | `/api/ki/{pid}/top100/{session_id}/status` | Snapshot status |

### Pipeline (P1–P14)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/run-pipeline` | Run full P1–P14 pipeline |
| `POST` | `/api/ki/{pid}/pipeline/generate` | Generate pipeline content |
| `POST` | `/api/ki/{pid}/pipeline/refresh` | Refresh pipeline output |
| `GET` | `/api/ki/{pid}/pipeline/metrics` | Pipeline performance metrics |
| `GET` | `/api/ki/{pid}/pipeline/report` | Full pipeline report |
| `GET` | `/api/ki/{pid}/pipeline/report/v2` | V2 pipeline report |
| `GET` | `/api/ki/{pid}/pipeline/health` | Pipeline health check |
| `GET` | `/api/ki/{pid}/pipeline-runs` | List past pipeline runs |
| `POST` | `/api/ki/{pid}/post-pipeline-strategy` | Generate strategy after pipeline |

### Strategy (via Keyword Input)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/strategy-input` | Submit input for strategy generation |
| `POST` | `/api/ki/{pid}/strategy/stream` | **SSE stream** — full strategy generation (Groq → Ollama → rule-based) |
| `POST` | `/api/ki/{pid}/generate-strategy` | Non-streaming strategy generation |
| `GET` | `/api/ki/{pid}/saved-strategy` | Get saved strategy JSON |
| `PUT` | `/api/ki/{pid}/strategy` | Update strategy JSON |
| `POST` | `/api/ki/{pid}/send-to-strategy` | Generate keyword brief + send to Strategy Hub |
| `GET` | `/api/ki/{pid}/keyword-strategy-brief` | Get latest strategy brief |

### Cluster Topics

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ki/{pid}/cluster/{cluster_index}/add-topic` | Add topic to a cluster |
| `POST` | `/api/ki/{pid}/cluster/{cluster_index}/regenerate-topics` | AI regenerate cluster topics |

### Profile & Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/profile` | Get keyword/business profile |
| `PUT` | `/api/ki/{pid}/profile` | Update profile |
| `GET` | `/api/ki/{pid}/dashboard` | Dashboard summary (sessions, pillar counts, status) |
| `GET` | `/api/ki/{pid}/workflow-status` | Current workflow stage |
| `POST` | `/api/ki/{pid}/workflow/advance` | Advance to next stage |

### Prompts (Custom Prompt Management)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/prompts` | Get all custom prompts for this project |
| `PUT` | `/api/ki/{pid}/prompts/{prompt_type}` | Update a specific prompt |
| `POST` | `/api/ki/{pid}/prompts/{prompt_type}/improve` | AI-improve a prompt |

### Misc

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ki/{pid}/generate/{session_id}` | Trigger universe generation for session |
| `GET` | `/api/projects/{pid}/keyword-stats` | Summary keyword stats for project |

---

## Backend Engines

### `engines/annaseo_keyword_input.py`
- **Core engine** for the entire keyword module
- Contains: `CustomerInputCollector`, `CrossMultiplier`, `WebsiteKeywordExtractor`, `GoogleKeywordEnricher`, `UniverseAssembler`
- Manages all 6 DB tables (see schema below)
- Cross-multiplication: Pillar × Supporting → combinations (scores +intent signals)
- Google Autosuggest fetcher: `https://suggestqueries.google.com/complete/search`
- DataForSEO integration: `https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live` (only used if `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` are set)

### `engines/annaseo_keyword_scorer.py` — `KeywordScoringEngine`
Two scoring paths:
1. **Free path** (default): DuckDuckGo SERP scrape + Google Autosuggest volume
2. **DataForSEO path** (if credentials set): Real KD + volume via DataForSEO API

Scoring signals:
- `serp_score`: result count from DDG → 0-100 
- `brand_score`: big-brand domains in top results → 0-100
- `title_score`: exact keyword in page titles → 0-100
- `autosuggest_vol`: Google autosuggest frequency → volume estimate
- `kd` (final): `serp × 0.35 + brand × 0.35 + title × 0.30`
- `opportunity_score`: `volume_normalized × (1 - kd_normalized) × relevance`

### `engines/research_engine.py` — `ResearchEngine`
Multi-source orchestrator:
- Source 1: User supporting keywords (+10)
- Source 2: Google Autosuggest (+5)
- Source 3: AI classification/scoring (variable)
- Lazy-loads `AIScorer` from `research_ai_scorer.py`

### `engines/research_ai_scorer.py` — `AIScorer`
AI-powered keyword scorer (intent, relevance, opportunity)

### `engines/intelligent_crawl_engine.py`
- Crawls customer + competitor URLs
- Extracts: ranking keywords, H1/H2 headings, meta descriptions, product names
- Deduplicates and scores extracted keywords
- Handles JS-blocked sites with multiple user-agent fallbacks

### `engines/ruflo_v3_keyword_system.py` — `AI` class
- `AI.deepseek()` — Ollama `/api/generate` (mistral-7b)
- `AI.gemini()` — Gemini free tier
- Used for: keyword classification, scoring, pillar naming

### `engines/ruflo_20phase_engine.py`
20-phase pipeline orchestrator (superset of P1–P14):
- `AI.deepseek()` — Ollama `/api/generate`
- `AI.gemini()` — Gemini
- Phases: seed validation → expansion → normalization → entity detection → intent → SERP → opportunity → topics → clusters → pillars → knowledge graph → internal links → calendar → dedup

### `engines/ruflo_confirmation_pipeline.py`
Confirmation and validation pipeline for keyword sets

### `engines/prompt_manager.py`
Manages per-project custom prompts for AI operations in the keyword workflow

---

## Database Schema

Database file: `./annaseo.db` (SQLite)  
Path set by: `ANNASEO_DB` env var

### `pillar_keywords`
Core content strategy anchors confirmed by the customer.

```sql
pillar_id    TEXT PRIMARY KEY   -- uuid
project_id   TEXT NOT NULL
keyword      TEXT NOT NULL      -- e.g. "Cinnamon"
intent       TEXT               -- informational | transactional | ...
priority     INTEGER DEFAULT 1
confirmed    INTEGER DEFAULT 1
notes        TEXT
created_at   TEXT
```
Index: `ix_pillar_project ON (project_id)`

### `supporting_keywords`
Qualifiers that combine with pillars to form the cross-multiplied universe.

```sql
support_id   TEXT PRIMARY KEY
project_id   TEXT NOT NULL
keyword      TEXT NOT NULL      -- e.g. "organic", "buy online", "Kerala"
intent_type  TEXT               -- transactional | informational
confirmed    INTEGER DEFAULT 1
created_at   TEXT
```

### `keyword_universe_items`
Every keyword generated/discovered, with full scoring data.

```sql
item_id           TEXT PRIMARY KEY
project_id        TEXT NOT NULL
session_id        TEXT NOT NULL
keyword           TEXT NOT NULL
pillar_keyword    TEXT          -- which pillar this belongs to
source            TEXT          -- cross_multiply | user | site_crawl | competitor | google | ai_generated
intent            TEXT          -- transactional | informational | commercial | comparison | local
volume_estimate   INTEGER       -- estimated search volume
difficulty        INTEGER       -- 0-100 KD score
relevance_score   REAL          -- 0-100 relevance to pillar
opportunity_score REAL          -- volume × (1-kd) × relevance
quick_win         INTEGER       -- 1 if ranking 11-20 (just needs a push)
status            TEXT          -- pending | accepted | rejected | edited
edited_keyword    TEXT          -- user-edited version
customer_notes    TEXT
created_at        TEXT
reviewed_at       TEXT
```
Indexes: `(project_id)`, `(session_id)`, `(pillar_keyword)`, `(status)`

### `keyword_input_sessions`
One row per research run. Tracks all stage transitions and is the resumption point.

```sql
session_id         TEXT PRIMARY KEY
project_id         TEXT NOT NULL
seed_keyword       TEXT
stage              TEXT    -- input | research | review | ai_review | pipeline | clusters | calendar
stage_status       TEXT    -- pending | running | complete | error
pillar_support_map TEXT    -- JSON: {pillar: [supports...]}
intent_focus       TEXT    -- transactional | informational | both
total_generated    INTEGER
total_accepted     INTEGER
total_rejected     INTEGER
sources_done       TEXT    -- JSON array of completed source names
customer_url       TEXT
competitor_urls    TEXT    -- JSON array
business_intent    TEXT    -- transactional | informational | mixed
target_audience    TEXT
geographic_focus   TEXT    -- default: "India"
workflow_ctx       TEXT    -- JSON: full WorkflowContext state snapshot
strategy_json      TEXT    -- JSON: generated strategy
created_at         TEXT
updated_at         TEXT
```

### `keyword_review_actions`
Audit log of every user action in the review UI.

```sql
id         INTEGER PRIMARY KEY AUTOINCREMENT
session_id TEXT NOT NULL
item_id    TEXT NOT NULL
action     TEXT    -- accept | reject | edit | move | delete
old_value  TEXT
new_value  TEXT
reason     TEXT
created_at TEXT
```

### `top100_snapshots`
Point-in-time snapshots of the top 100 keywords (for diff tracking).

```sql
snapshot_id TEXT PRIMARY KEY
project_id  TEXT NOT NULL
session_id  TEXT NOT NULL
keywords    TEXT    -- JSON
created_at  TEXT
```

### `keyword_strategy_briefs`
AI-generated strategy briefs ready to be sent to the Strategy Hub.

```sql
brief_id       TEXT PRIMARY KEY
project_id     TEXT NOT NULL
session_id     TEXT NOT NULL
pillar_count   INTEGER
total_keywords INTEGER
pillars_json   TEXT    -- JSON array of pillar names
keywords_json  TEXT    -- JSON: {pillar: [keywords]}
context_json   TEXT    -- JSON: business context
brief_text     TEXT    -- AI-written brief (Groq → Ollama fallback)
sent_at        TEXT
updated_at     TEXT
```
Index: `ix_ksb_project ON (project_id)`

---

## AI Providers & API Keys

### Keys (set in `.env`)

| Key | Provider | Used for |
|-----|----------|---------|
| `GROQ_API_KEY` | Groq | Keyword scoring, clustering, strategy generation, briefs |
| `GEMINI_API_KEY` | Google Gemini Free | Keyword expansion, pillar generation |
| `GEMINI_PAID_API_KEY` | Google Gemini Pro | Higher-quality generation |
| `ANTHROPIC_API_KEY` | Anthropic Claude | Quality verification, AI brain |
| `OPENAI_API_KEY` | OpenAI GPT-4o | Optional: content tasks |
| `OPENROUTER_API_KEY` | OpenRouter | Multi-model gateway |
| `OLLAMA_URL` | Remote Ollama | `http://172.235.16.165:8080` |
| `OLLAMA_MODEL` | Ollama model | `mistral:7b-instruct-q4_K_M` |
| `DATAFORSEO_LOGIN` | DataForSEO | Optional: real KD + volume data |
| `DATAFORSEO_PASSWORD` | DataForSEO | Optional: real KD + volume data |

### Ollama Server
- **Host:** `172.235.16.165`
- **Proxy port:** `8080` (reverse proxy — only these endpoints exposed)
  - `POST /api/generate` ✅ (used)
  - `GET /api/tags` ✅
  - `GET /api/version` ✅
  - `GET /api/ps` ✅
  - `POST /api/chat` ❌ 404 — blocked by proxy
- **Model loaded:** `mistral:7b-instruct-q4_K_M`
- **Ollama version:** 0.20.2

> **Important:** All Ollama calls must use `/api/generate` with a `prompt` string (not `/api/chat` with `messages[]`).

### Provider Cascade (keyword scoring / strategy)

The backend attempts providers in this order and falls back on error:

```
Groq (llama-3.3-70b)  →  Gemini Paid  →  Ollama /api/generate  →  rule-based
```

AI scoring for discovery stream (Step 2 Stage 3+5):
```
preferred_provider (user choice)  →  Groq  →  Gemini Free  →  Ollama
```

---

## Scoring System

### Keyword Difficulty (KD) — 0 to 100

Computed from 3 free SERP signals (DuckDuckGo):

```
kd = serp_score × 0.35 + brand_score × 0.35 + title_score × 0.30
```

| Signal | Calculation |
|--------|------------|
| `serp_score` | DDG result count: <100K→20, <1M→45, <10M→65, >10M→85 |
| `brand_score` | Count of big-brand domains (Amazon, Wikipedia, etc.) in top results |
| `title_score` | How many top titles contain the exact keyword |

### Volume Estimate

From Google Autosuggest frequency:
- Number of autosuggest matches → proxy for search volume
- Range: 0–1,000+

### Opportunity Score — 0 to 100

```
opportunity = (volume / 1000) × (1 - kd/100) × (relevance/100) × 100
```

Low KD + high volume + high relevance = highest opportunity.

### Relevance Score
AI-assigned (0–100): how closely the keyword matches the pillar's intent and business context.

### Quick Win Flag
Set to `1` if GSC data shows the keyword already ranks 11–20 (just needs a content push).

---

## Data Flow — End to End

```
Step 1: Setup
  User input → PUT /api/ki/{pid}/profile
             → POST /api/ki/{pid}/input
             → Creates session_id, stores pillars + supports
             → Stage: "input"

Step 2: Discovery
  Stage 1+2: POST /api/ki/{pid}/intelligent-crawl
             POST /api/ki/{pid}/intelligent-competitor
             → Extracts keywords from customer + competitor sites
             → Creates pillar cards

  Stage 3:   POST /api/ki/{pid}/research/stream  (SSE)
             → 6 sources emit events
             → Cross-multiply: pillars × supports = combinations
             → Google Autosuggest per combination
             → All inserted into keyword_universe_items (status=pending)

  Stage 4:   POST /api/ki/{pid}/keyword-universe
             → Assembles, deduplicates, normalises all items
             → Assigns preliminary opportunity scores

  Stage 5:   POST /api/ki/{pid}/cluster-keywords  (preferred_provider)
             → AI groups keywords into clusters
             → Scores intent, difficulty, relevance
             → Returns cluster map

  User review: Accept / reject / edit individual keywords
             POST /api/ki/{pid}/review/{session_id}/action
             → Logs to keyword_review_actions
             → Updates status in keyword_universe_items

  Confirm:   POST /api/ki/{pid}/confirm/{session_id}
             → Stage advances to "pipeline"

Step 3: Pipeline (P1–P14)
  POST /api/ki/{pid}/run-pipeline
  → P1 Seed Validation → P2 Expansion → P3 Normalization
  → P4 Entity Detection → P5 Intent Classification → P6 SERP Analysis
  → P7 Opportunity Scoring → P8 Topic Detection → P9 Cluster Formation
  → P10 Pillar Identification → P11 Knowledge Graph → P12 Internal Links
  → P13 Content Calendar → P14 Deduplication
  → Final structure stored → stage="calendar"

Send to Strategy:
  POST /api/ki/{pid}/send-to-strategy
  → AI generates strategy brief (Groq → Ollama)
  → Stored in keyword_strategy_briefs
  → Strategy Hub can pull it via GET /api/ki/{pid}/keyword-strategy-brief
```

---

## Pipeline Phases (P1–P14)

Defined in `frontend/src/workflow/Step3Pipeline.jsx`:

| Phase | Name | Group | Description |
|-------|------|-------|-------------|
| P1 | Seed Validation | Collection | Validate pillar keywords are real, rankable seeds |
| P2 | Keyword Expansion | Collection | Expand each seed with variations + related terms |
| P3 | Normalization | Collection | Deduplicate, lowercase, remove garbage |
| P4 | Entity Detection | Analysis | NER — identify product/place/brand entities |
| P5 | Intent Classification | Analysis | Label each keyword with search intent |
| P6 | SERP Analysis | Analysis | Check SERP features (featured snippet, PAA box) |
| P7 | Opportunity Scoring | Scoring | Assign final opportunity score using KD + volume + relevance |
| P8 | Topic Detection | Scoring | Group into broad topics / themes |
| P9 | Cluster Formation | Scoring | Build pillar → cluster → supporting hierarchy |
| P10 | Pillar Identification | Scoring | Confirm/rerank pillar keywords |
| P11 | Knowledge Graph | Structure | Link entities across clusters |
| P12 | Internal Links | Structure | Build internal link map between planned articles |
| P13 | Content Calendar | Planning | Assign keywords to publishing months |
| P14 | Deduplication | Planning | Final deduplicate + prune low-value keywords |

---

## Environment Variables

Full set relevant to the keyword module:

```bash
# Database
ANNASEO_DB=./annaseo.db          # SQLite path

# AI APIs
GROQ_API_KEY=gsk_...             # Groq — primary for keyword AI
GEMINI_API_KEY=AIza...           # Gemini free
GEMINI_PAID_API_KEY=AIza...      # Gemini paid
ANTHROPIC_API_KEY=sk-ant-...     # Claude
OPENAI_API_KEY=sk-proj-...       # GPT-4o
OPENROUTER_API_KEY=sk-or-...     # OpenRouter gateway
CLAUDE_MODEL=claude-sonnet-4-6

# Ollama (remote)
OLLAMA_URL=http://172.235.16.165:8080
OLLAMA_MODEL=mistral:7b-instruct-q4_K_M

# Optional: DataForSEO (real KD + volume data)
DATAFORSEO_LOGIN=your@email.com
DATAFORSEO_PASSWORD=your_password

# Auth
JWT_SECRET=...
FERNET_KEY=...

# Rate limits
GEMINI_RATE_LIMIT_SECONDS=4.0
```

---

## Key Files Index

| File | Role |
|------|------|
| `frontend/src/App.jsx` | `KeywordsUnifiedPage`, `KeywordTreePage` container |
| `frontend/src/KeywordWorkflow.jsx` | 3-step (new) + 7-step (legacy) orchestrator |
| `frontend/src/KeywordInput.jsx` | Alternative 4-step input wizard |
| `frontend/src/workflow/Step1Setup.jsx` | Business profile + pillars form |
| `frontend/src/workflow/Step2Discovery.jsx` | SSE discovery + AI provider selector |
| `frontend/src/workflow/Step3Pipeline.jsx` | P1–P14 split-view pipeline |
| `frontend/src/workflow/shared.jsx` | Design tokens, shared components |
| `frontend/src/store/workflowContext.js` | Zustand workflow context |
| `frontend/src/components/KeywordTreeConfirmation.jsx` | Tree confirmation component |
| `main.py` | All 79+ `/api/ki/*` FastAPI routes |
| `engines/annaseo_keyword_input.py` | Core universe engine + DB schema |
| `engines/annaseo_keyword_scorer.py` | KD + volume scoring (free + DataForSEO) |
| `engines/research_engine.py` | Multi-source research orchestrator |
| `engines/research_ai_scorer.py` | AI keyword scorer |
| `engines/intelligent_crawl_engine.py` | Site + competitor crawl engine |
| `engines/ruflo_v3_keyword_system.py` | AI class (Ollama + Gemini) |
| `engines/ruflo_20phase_engine.py` | 20-phase pipeline orchestrator |
| `engines/ruflo_confirmation_pipeline.py` | Keyword confirmation pipeline |
| `engines/prompt_manager.py` | Per-project custom prompt storage |
| `.env` | All API keys and configuration |
| `annaseo.db` | SQLite database (all keyword tables) |
