# AnnaSEO — Keyword Workflow (7-Step Wizard)

Unified keyword discovery, review, AI validation, pipeline execution, cluster generation, and calendar handoff in one linear wizard.

---

## Overview

The Keyword Workflow replaces the disconnected "Universe Input" and "Run Pipeline" tabs with a single 7-step wizard located at the **Workflow** tab on the Keywords page.

```
Step 1: Input       → Manual pillar + supporting keyword entry (Method 1)
Step 2: Research    → Auto engine-driven keyword discovery (Method 2)
Step 3: Review      → Unified keyword table — accept / reject / edit
Step 4: AI Check    → 3-stage AI validation: DeepSeek → Groq → Claude
Step 5: Pipeline    → 20-phase keyword universe engine per pillar
Step 6: Clusters    → Review clusters, rename/merge, capacity planning
Step 7: Calendar    → Handoff to BlogCalendarPage
```

---

## Step 1 — Input (Method 1)

**What:** User manually enters pillar keywords, supporting keywords, intent focus, and optional URLs.

**UI:** Form fields:
- Pillar keywords (one per line)
- Supporting / modifier keywords (one per line)
- Intent focus (informational / commercial / mixed)
- Customer website URL
- Competitor URLs (one per line)

**On "Save & Continue":**
- `POST /api/ki/{project_id}/input`
- Saves to `pillar_keywords` + `supporting_keywords` + `keyword_sessions` tables
- Cross-multiplies pillars × supporting → `keyword_universe_items` (source="cross_multiply")
- Advances to Step 2

---

## Step 2 — Research (Method 2)

**What:** Engine-driven keyword discovery across 3 sources using the customer URL and competitor URLs from Step 1.

**Engines used:**

| Source | Engine | Output |
|--------|--------|--------|
| Google Autosuggest | P2_Enhanced (`annaseo_p2_enhanced.py`) | Pillar × supporting → autosuggest phrases |
| Competitor gap | CompetitorGapEngine (`annaseo_competitor_gap.py`) | Keywords competitors rank for |
| Site crawl | WebsiteKeywordExtractor (`annaseo_keyword_input.py`) | H1/H2/meta/product text from customer site |

All keywords are deduplicated via AnnaBrain intent classification and saved to `keyword_universe_items` with source prefixes: `research_autosuggest`, `research_competitor_gap`, `research_site_crawl`.

**On "Fetch Keywords Now":**
- `POST /api/ki/{project_id}/research` → returns `{"job_id": "..."}`
- Poll `GET /api/ki/{project_id}/research/{job_id}` every 2s
- Shows per-source checkmarks and keyword counts as each source completes
- "Skip" button available to proceed without research keywords

---

## Step 3 — Unified Review

**What:** Merge Method 1 + Method 2 keywords into one review table.

**Data sources merged:**
- Method 1: `keyword_universe_items` where source in (cross_multiply, manual)
- Method 2: `keyword_universe_items` where source like research_*
- Strategy: priority_queue keywords from latest strategy session (source="strategy", pre-accepted)

**Table columns:** keyword | source badge | pillar | intent | volume | KD | score | status

**Actions per row:** Accept (✓) | Reject (✗) — sets `status` field in `keyword_universe_items`

**Bulk actions:** Accept All Visible | filter by pillar/source/status

**On "Continue to AI Check →":** at least 1 accepted keyword required

---

## Step 4 — AI Check (3-Stage Sequential)

**What:** Three AI models review accepted keywords in sequence, each flagging irrelevant/problematic keywords with reasons. The user can override each flag.

### Stage 1 — DeepSeek (local, free)

- Model: DeepSeek via Ollama at `http://localhost:11434/api/generate`
- Focus: Business fit — flags keywords that don't match the business type/industry
- Default prompt:
  ```
  You are an SEO expert for a {{business_type}} business in the {{industry}} industry.
  Review the following keywords and flag any that do NOT fit this business.
  A keyword should be flagged if it: (1) targets an unrelated industry, (2) has no search intent
  relevant to {{industry}}, or (3) would bring wrong-audience traffic.
  For each flagged keyword, give a short reason (max 15 words).
  Business USP: {{usp}}
  Keywords: {{keywords}}
  Respond as JSON: [{"keyword": "...", "flagged": true/false, "reason": "..."}]
  ```

### Stage 2 — Groq Llama (free API)

- Model: Groq `llama-3.1-8b-instant`
- Focus: Search intent + audience fit
- Default prompt:
  ```
  You are a search intent analyst. For each keyword below, check if it matches the
  target audience: {{business_type}} customers in {{industry}}, located in {{locations}}.
  Flag keywords where the searcher's intent does NOT match what this business sells.
  Keywords: {{keywords}}
  Respond as JSON: [{"keyword": "...", "flagged": true/false, "reason": "..."}]
  ```

### Stage 3 — Claude Sonnet

- Model: `claude-sonnet-4-6` via Anthropic API
- Focus: Cannibalization risks, E-E-A-T issues, thin intent, opportunity scoring
- Default prompt:
  ```
  You are an advanced SEO strategist. Review these keywords for a {{industry}} {{business_type}}
  business. Flag any that have: (1) cannibalization risk with another keyword in the list,
  (2) E-E-A-T issues (medical/legal claims without expertise signals), (3) zero commercial value.
  Also assign an SEO opportunity score 0-100 based on specificity and buyer intent.
  Keywords: {{keywords}}
  Respond as JSON: [{"keyword": "...", "flagged": true/false, "reason": "...", "score": 0-100}]
  ```

### Prompt editing

Each stage shows a collapsible prompt textarea (`▼ Edit prompt`). Edits auto-save to the `project_prompts` table on "Save prompt". "Reset to default" restores the hardcoded default above.

Saved prompts are loaded on mount via `GET /api/ki/{project_id}/prompts`.

### User override

Each flagged keyword shows:
- The flag reason from the AI
- [Keep] — sets `user_decision="keep"` in `ai_review_results`
- [Remove] — sets `user_decision="remove"`, marks keyword `status="rejected"` in `keyword_universe_items`

Bulk: "Keep all" / "Remove all" buttons apply to all flags in the current stage.

### AI Score

After all 3 stages, each keyword gets a composite AI score (0–100) stored in `keyword_universe_items.ai_score`. Claude's per-keyword score is used when available; otherwise defaults to 100 for non-flagged, 0 for flagged-and-removed keywords.

**On "Send to Pipeline →":** proceeds to Step 5 with all non-rejected keywords

---

## Step 5 — Pipeline

**What:** Run the 20-phase keyword universe engine using confirmed pillar keywords.

**Trigger:** `POST /api/ki/{project_id}/run-pipeline`

**Backend behavior:**
1. Reads confirmed `pillar_keywords` from DB for the current session
2. Creates one run record per pillar in the `runs` table
3. Runs `WiredRufloOrchestrator.run_seed(seed_keyword, project_id, run_id)` per pillar (sequential, background)
4. Supporting keywords from the session are passed as expansion hints

**Progress UI:**
- Per-pillar status rows: "Running..." spinner → "Done" checkmark
- Each pillar links to its run via `GET /api/runs/{run_id}` (same polling as existing pipeline)
- Status: waiting → running → done | error

**On completion:** all pillar runs done → auto-advances to Step 6

---

## Step 6 — Clusters

**What:** Review and organize clusters generated by the 20-phase pipeline.

**Data:** `GET /api/ki/{project_id}/clusters` — reads completed run result JSON for `pillars.{pillar}.clusters` structure.

**UI:**
- Expandable accordion per pillar
- Per cluster: cluster name | keyword count | first 5 keywords preview
- Capacity indicator: `~N months of content at 1 blog/day`
- "Generate more clusters" button (for pillars with < 24 clusters) → `POST /api/ki/{project_id}/clusters/generate`

**Cluster naming AI prompt** (editable, same collapsible pattern as Step 4):
```
You are a content strategist. Given these keywords clustered together, suggest a concise
cluster name (3-5 words) that captures the main topic, and a content type (blog/guide/comparison/faq).
Keywords: {{keywords}}
Respond as JSON: {"name": "...", "content_type": "..."}
```

**On "Send to Calendar →":** calls `onGoToCalendar` prop → navigates to BlogCalendarPage

---

## Step 7 — Calendar Handoff

**What:** Success screen showing summary + link to content calendar.

**Displays:**
- Total clusters generated
- Total pillars
- Estimated months of content
- "Open Content Calendar" button → navigates to BlogCalendarPage (`/blogs`)

---

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ki/{project_id}/research` | Trigger Method 2 research job |
| GET | `/api/ki/{project_id}/research/{job_id}` | Poll research job status + keyword count |
| GET | `/api/ki/{project_id}/prompts` | Get all saved prompts for this project |
| PUT | `/api/ki/{project_id}/prompts/{prompt_type}` | Save/update a prompt |
| POST | `/api/ki/{project_id}/ai-review` | Run AI review for one stage (deepseek/groq/claude) |
| POST | `/api/ki/{project_id}/ai-review/override` | Save user keep/remove decisions |
| GET | `/api/ki/{project_id}/ai-review/results` | Get review results by session and stage |
| POST | `/api/ki/{project_id}/run-pipeline` | Trigger 20-phase pipeline per confirmed pillar |
| GET | `/api/ki/{project_id}/clusters` | Get clusters from latest completed pipeline runs |
| POST | `/api/ki/{project_id}/clusters/generate` | AI cluster naming with custom prompt |

---

## Database Tables

### ai_review_results

Stores per-keyword flags and user decisions from each AI stage.

```sql
id             INTEGER PRIMARY KEY AUTOINCREMENT
project_id     TEXT NOT NULL
session_id     TEXT NOT NULL
stage          TEXT NOT NULL        -- deepseek | groq | claude
keyword        TEXT NOT NULL
flagged        INTEGER DEFAULT 0    -- 1 = flagged by AI
reason         TEXT DEFAULT ''      -- AI reason
user_decision  TEXT DEFAULT 'pending'  -- pending | keep | remove
ai_score       REAL DEFAULT 0.0
created_at     TEXT DEFAULT CURRENT_TIMESTAMP
```

### project_prompts

Per-project editable prompts for each AI stage.

```sql
id             INTEGER PRIMARY KEY AUTOINCREMENT
project_id     TEXT NOT NULL
prompt_type    TEXT NOT NULL   -- deepseek_kw_review | groq_kw_review | claude_kw_review | cluster_naming
content        TEXT NOT NULL
created_at     TEXT DEFAULT CURRENT_TIMESTAMP
updated_at     TEXT DEFAULT CURRENT_TIMESTAMP
UNIQUE(project_id, prompt_type)
```

### research_jobs

Tracks in-progress Method 2 research jobs.

```sql
job_id         TEXT PRIMARY KEY
project_id     TEXT NOT NULL
status         TEXT DEFAULT 'running'   -- running | completed | failed
sources_done   TEXT DEFAULT '[]'        -- JSON list of completed source names
keyword_count  INTEGER DEFAULT 0
error          TEXT DEFAULT ''
created_at     TEXT DEFAULT CURRENT_TIMESTAMP
```

### keyword_universe_items (new columns)

```sql
ai_score   REAL DEFAULT 0.0   -- composite score from AI review stages
ai_flags   TEXT DEFAULT '[]'  -- JSON array of flag objects
```

---

## Engines

| Engine | File | Role |
|--------|------|------|
| KeywordInputEngine | `engines/annaseo_keyword_input.py` | Step 1 — cross-multiply + site crawl |
| P2_Enhanced | `engines/annaseo_p2_enhanced.py` | Step 2 — Google Autosuggest expansion |
| CompetitorGapEngine | `engines/annaseo_competitor_gap.py` | Step 2 — competitor keyword gap |
| AnnaBrain | `engines/annaseo_ai_brain.py` | Step 2 — deduplication + intent classification |
| DeepSeek (Ollama) | localhost:11434 | Step 4 Stage 1 — business fit review |
| Groq Llama | Groq API | Step 4 Stage 2 — intent validation |
| Claude Sonnet | Anthropic API | Step 4 Stage 3 — SEO audit + scoring |
| WiredRufloOrchestrator | `engines/ruflo_20phase_wired.py` | Step 5 — 20-phase pipeline |

---

## Frontend

**Component:** `frontend/src/KeywordWorkflow.jsx`

**Props:**
- `projectId` — current project ID
- `onGoToCalendar` — callback called from Step 7 to navigate to BlogCalendarPage

**State managed:**
- `step` — current wizard step (1–7)
- `sessionId` — keyword session ID created in Step 1
- `customerUrl` — passed from Step 1 to Step 2
- `competitorUrls` — passed from Step 1 to Step 2

**Sub-components:**
- `ProgressBar` — 7 numbered circles, teal=completed, purple=active, gray=future
- `StepInput` — pillar + supporting form
- `StepResearch` — trigger + polling + source progress
- `StepReview` — unified keyword table with source badges
- `AIStageCard` — reusable per-stage UI (prompt editor + flag list + override buttons)
- `StepAIReview` — 3 × AIStageCard sequential
- `StepPipeline` — per-pillar run trigger + status rows
- `StepClusters` — accordion + capacity meter
- `StepCalendar` — success screen + navigation
