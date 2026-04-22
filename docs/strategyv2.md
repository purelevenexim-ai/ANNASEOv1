# Strategy Engine v2 — Architecture, Phases & Integration Plan

**Status:** Design Blueprint (Supersedes STRATEGY_README.md §14 roadmap)  
**Date:** April 2026  
**Scope:** Full redesign of the Strategy Page as the application's central intelligence layer

---

## Core Vision

> The Strategy Page is the **heart** of the application.
> Every other module — keyword pipeline, content hub, calendar, internal links — feeds into it or receives decisions from it.

**Current state:**
```
KW2 Pipeline (Phases 1–8) → Phase 9 Strategy → Display (read-only) → STOP
```

**Target state:**
```
KW2 Pipeline → Strategy Engine → Question Intelligence → Expansion Engine
     ↑               ↓                                        ↓
Feedback      Execution Engine                         Scoring Engine
     ↑               ↓                                        ↓
Content Hub ← Content Hub ← Selection Engine ← Dedup/Cluster
```

The strategy page stops being a **display layer** and becomes a **decision engine** that:
- Understands the business deeply through structured questions
- Generates and expands thousands of intelligence questions
- Scores and selects the highest-value content opportunities
- Feeds decisions back into keyword ranking, calendar, and content generation
- Learns from performance over time

---

## What Already Exists (Do Not Re-Build)

From the current kw2 system (`STRATEGY_README.md`):

| Component | Status | Location |
|---|---|---|
| Phase 9 strategy generation | ✅ Built | `engines/kw2/strategy_engine.py` |
| 7-tab Strategy UI | ✅ Built | `frontend/src/kw2/SessionStrategyPage.jsx` |
| Business intel (Phase 5) | ✅ Built | `kw2_biz_intel`, `kw2_biz_pages` |
| Competitor intel (Phase 6) | ✅ Built | `kw2_biz_competitors` |
| Keyword segmentation (Money/Growth/Support/QW) | ✅ Built | KeywordsTab in JSX |
| Health score | ✅ Built | `computeHealthScore()` |
| AI provider cascade | ✅ Built | `engines/kw2/ai_caller.py` |
| All DB tables (15 tables) | ✅ Built | `engines/kw2/db.py` |
| Content Parameters config | ✅ Built | ContentParametersTab |
| Goals + BI sidebar | ✅ Built | GoalsTab |

### Critical gaps in what exists

| Gap | Impact | Fix Phase |
|---|---|---|
| AI sees only top 30 keywords, top 20 clusters | Strategy misses long-tail depth | Phase 2 upgrade |
| Strategy is read-only after generation | Kills usability | Phase 3 |
| No feedback loop from strategy to pipeline | Strategy is a dead end | Phase 5 |
| No question intelligence engine | Content is generic | Phase 3 |
| No expansion engine | Content misses geo/audience/use-case depth | Phase 4 |
| No scoring beyond basic kw scoring | Opportunity prioritisation weak | Phase 6 |
| No content title generation system | Gap between strategy and content hub | Phase 8 |
| No strategy versioning | No iteration / experimentation | Phase 3 |
| Multiple disconnected strategy engines | Duplicated logic, confusion | Phase 2 |

---

## 12-Phase v2 Architecture

```
Phase 0  — Input & Context Layer         ← user configures session
Phase 1  — Data Intelligence (KW2)       ← ALREADY BUILT (Phases 1–8)
Phase 2  — Strategy Intelligence Engine  ← UPGRADE existing Phase 9
Phase 3  — Question Intelligence Engine  ← NEW
Phase 4  — Expansion Engine              ← NEW (recursive)
Phase 5  — Enrichment Engine             ← NEW
Phase 6  — Deduplication & Clustering    ← NEW
Phase 7  — Scoring Engine                ← NEW (generic, weighted)
Phase 8  — Selection Engine              ← NEW
Phase 9  — Content Generation Engine     ← NEW (replaces manual brief)
Phase 10 — Execution Layer               ← UPGRADE Content Hub
Phase 11 — Feedback & Learning Engine    ← NEW
Phase 12 — Prompt & Control Layer        ← NEW (Prompt Studio)
```

---

## Phase 0 — Input & Context Layer

**Goal:** Capture and structure everything about the business at session start.  
**Status:** Partially built — `kw2_business_profile`, `kw2_biz_intel` exist.  
**Upgrade needed:** Richer geo targeting, explicit intent declaration, audience depth.

### What it captures

```python
{
  "business_type": str,           # auto-detected + user-confirmed
  "products_services": list,      # what is sold
  "target_intent": str,           # "online_sales" | "lead_gen" | "brand_awareness" | "support"
  "geo_scope": {
    "primary_country": str,
    "target_regions": list,       # states/districts (user selectable)
    "target_cities": list,        # city-level (user selectable or AI-suggested)
    "expand_geo": bool            # allow engine to auto-expand geo
  },
  "audience": {
    "primary": list,              # e.g. ["home cooks", "restaurants"]
    "secondary": list,
    "expand_audience": bool       # allow engine to discover sub-segments
  },
  "content_velocity": {
    "blogs_per_week": int,
    "duration_weeks": int,
    "start_date": str
  },
  "extra_guidance": str           # free text from user
}
```

### DB: `kw2_sessions` (existing, add columns via migration)

```sql
ALTER TABLE kw2_sessions ADD COLUMN geo_targets TEXT DEFAULT '{}';
ALTER TABLE kw2_sessions ADD COLUMN audience_targets TEXT DEFAULT '{}';
ALTER TABLE kw2_sessions ADD COLUMN intent_target TEXT DEFAULT '';
```

### Integration

- Feeds directly into Phase 2 (strategy) and Phase 3 (question engine).
- User edits via `ContentParametersTab` (already exists) — extend that tab.

---

## Phase 1 — Data Intelligence (kw2 Phases 1–8)

**Status:** ✅ FULLY BUILT — do not rebuild.

| Sub-phase | What it produces | DB table |
|---|---|---|
| Phase 1 | Seed keywords + session setup | `kw2_sessions`, `kw2_universe_items` |
| Phase 2 | Expanded keyword universe | `kw2_universe_items` |
| Phase 3 | Validated keywords with intent + scores | `kw2_validated_keywords` |
| Phase 4 | Pillar assignment | `kw2_validated_keywords.pillar` |
| Phase 5 | Business intel: pages, USPs, goals | `kw2_biz_intel`, `kw2_biz_pages` |
| Phase 6 | Competitor intel: gaps, weaknesses | `kw2_biz_competitors`, `kw2_biz_competitor_keywords` |
| Phase 7 | Keyword scoring + internal links | `kw2_internal_links`, scores updated |
| Phase 8 | Content calendar | `kw2_calendar` |

**v2 upgrade for Phase 1:** Pass the **full validated keyword set** (not top 30) into downstream phases. Use weighted summaries per cluster rather than row-limit truncation.

---

## Phase 2 — Strategy Intelligence Engine

**Goal:** Upgrade the existing Phase 9 to use richer data, editable output, and versioning.  
**Status:** Partially built — `engines/kw2/strategy_engine.py`.  
**File:** `engines/kw2/strategy_engine.py` (upgrade in-place)

### v2 Changes vs Current Phase 9

| Current | v2 |
|---|---|
| Top 30 keywords only | All validated keywords, weighted cluster summaries |
| Top 20 clusters only | All clusters with intent distribution |
| Single strategy_json blob | Versioned strategies (`kw2_strategy_versions` table) |
| One-shot AI call | Module-by-module intelligence (4 sub-modules) |
| Read-only output | Editable fields per section |

### 4 Sub-Modules Inside Phase 2

#### Sub-Module 2A — Business Analysis
```python
# Input: kw2_business_profile + kw2_biz_intel + kw2_biz_pages
# Output: positioning, strengths, differentiation

PROMPT_2A = """
ROLE: Senior business analyst and SEO strategist.

CONTEXT:
Business: {universe} ({business_type})
Products/Services: {products_services}
USPs: {usps}
Goals: {goals}
Website pages: {pages_summary}
Brand voice: {brand_voice}

TASK:
Analyze and output:
1. Core positioning statement (why this business wins)
2. Primary strengths (3-5 points)
3. Biggest market opportunity
4. Content differentiation angle

OUTPUT: Strict JSON only.
{
  "positioning": "",
  "strengths": [],
  "opportunity": "",
  "differentiation": "",
  "icp_summary": ""
}
"""
```

#### Sub-Module 2B — Keyword Intelligence
```python
# Input: ALL kw2_validated_keywords + cluster distributions (not truncated)
# Output: weighted priority map, funnel assignment, segment classification

PROMPT_2B = """
ROLE: SEO keyword strategist.

CONTEXT:
All validated keywords ({total_count} total):
{keyword_clusters_with_distributions}
  — format: cluster | intent_mix | avg_score | top_keywords[]

TASK:
1. Identify the top-priority clusters by commercial opportunity
2. Map each cluster to funnel stage (TOFU/MOFU/BOFU)
3. Identify cannibalization risks
4. Flag quick wins (high score, low competition)

OUTPUT: Strict JSON only.
{
  "priority_clusters": [],
  "funnel_map": {},
  "cannibalization_risks": [],
  "quick_wins": []
}
"""
```

#### Sub-Module 2C — Strategy Builder
```python
# Input: 2A + 2B outputs + competitor data
# Output: full strategy JSON (same schema as current Phase 9 output)

PROMPT_2C = """
ROLE: Senior SEO content strategist.

CONTEXT:
[Business analysis from 2A]
[Keyword intelligence from 2B]
Competitors: {competitor_summary}
  — each: domain | gaps | weaknesses | top_keywords

Content parameters:
  Velocity: {blogs_per_week}/week for {duration_weeks} weeks
  Mix: {content_mix}
  Cadence: {publishing_cadence}
  Guidance: {extra_guidance}

TASK:
Generate the complete strategy. Be specific. Reference actual keywords and pillars.

OUTPUT: Strict JSON only.
[Full strategy schema — see STRATEGY_README.md §7]
"""
```

#### Sub-Module 2D — Action Mapping
```python
# Input: 2C strategy output
# Output: execution instructions for Phase 7/8/10

PROMPT_2D = """
ROLE: SEO execution planner.

CONTEXT:
Strategy: {strategy_summary}
Priority pillars: {priority_pillars}
Quick wins: {quick_wins}

TASK:
Map strategy decisions to execution actions:
1. Keyword re-priority instructions (boost/demote scores)
2. Cluster reorder instructions
3. Calendar priority adjustments

OUTPUT: Strict JSON only.
{
  "keyword_boosts": [{"keyword": "", "boost_reason": "", "new_priority": "high|medium|low"}],
  "cluster_reorder": [{"cluster": "", "new_rank": 0, "reason": ""}],
  "calendar_priority": [{"title": "", "move_to_week": 0, "reason": ""}]
}
"""
```

### DB: New Table `kw2_strategy_versions`

```sql
CREATE TABLE IF NOT EXISTS kw2_strategy_versions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    strategy_json TEXT NOT NULL,         -- full Phase 2C output
    module_2a_json TEXT DEFAULT '{}',    -- business analysis
    module_2b_json TEXT DEFAULT '{}',    -- keyword intelligence
    module_2d_json TEXT DEFAULT '{}',    -- action mapping
    ai_provider TEXT DEFAULT 'auto',
    params_snapshot TEXT DEFAULT '{}',   -- content_params at generation time
    is_active INTEGER DEFAULT 1,
    notes TEXT DEFAULT '',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kw2_sv_session ON kw2_strategy_versions(session_id);
CREATE INDEX IF NOT EXISTS idx_kw2_sv_active ON kw2_strategy_versions(session_id, is_active);
```

### DB: New Table `kw2_strategy_edits`

```sql
CREATE TABLE IF NOT EXISTS kw2_strategy_edits (
    id TEXT PRIMARY KEY,
    strategy_version_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    field_path TEXT NOT NULL,            -- e.g. "pillar_strategies[0].priority"
    old_value TEXT,
    new_value TEXT,
    edited_by TEXT DEFAULT 'user',
    created_at TEXT
);
```

### API Endpoints (Phase 2)

```
POST /api/kw2/{pid}/sessions/{sid}/phase9           ← existing (upgrade)
GET  /api/kw2/{pid}/sessions/{sid}/strategy         ← existing (now returns active version)
GET  /api/kw2/{pid}/sessions/{sid}/strategy/versions ← NEW: list all versions
POST /api/kw2/{pid}/sessions/{sid}/strategy/activate/{version_id} ← NEW
PATCH /api/kw2/{pid}/sessions/{sid}/strategy/edit   ← NEW: save user edits
GET  /api/kw2/{pid}/sessions/{sid}/strategy/diff/{v1}/{v2} ← NEW: compare two versions
```

### Frontend Upgrades (Phase 2)

Inside `SessionStrategyPage.jsx → StrategyTab`:
- **Version badge** in metadata bar: "v3 · Generated 2h ago · Active"
- **Version history drawer**: list all versions, "Activate" / "Compare" buttons
- **Edit mode toggle**: per section (pillar priorities, content mix sliders, quick wins)
- **"Regenerate section"** button per card (calls sub-module endpoint)
- **Diff view**: side-by-side comparison of two versions

---

## Phase 3 — Question Intelligence Engine

**Goal:** Systematically generate structured intelligence questions from all data sources.  
**Status:** NEW — does not exist yet.  
**File:** `engines/kw2/question_engine.py` (new)

### Why Questions?

Strategy quality is not limited by the AI model. It is limited by the quality and structure of questions asked. This engine turns raw business data into a structured question framework that becomes the foundation for content decisions.

### 7 Intelligence Modules

Each module targets a different dimension of business understanding:

#### Module Q1 — Business Core Questions
```
What exactly are we selling?
Is this product, service, or hybrid?
What problem does this solve?
Why should someone choose this over others?
Are we premium, budget, or mid-market?
Local, national, or global?
```
- **Data source:** `kw2_business_profile`, `kw2_biz_intel`
- **AI output:** Positioning clarity, differentiation points

#### Module Q2 — Audience Intelligence Questions
```
Who is the ideal customer?
What are their demographics and lifestyle?
Where do they spend time online?
What triggers their purchase decision?
What do they fear? What do they desire?
What objections do they have?
```
- **Data source:** `kw2_biz_intel.audience_segments`, `kw2_validated_keywords` intent distribution
- **AI output:** Audience segment map with psychology

#### Module Q3 — Intent Mapping Questions
```
What questions do users ask before buying?
What problems are they trying to solve?
What comparisons are made before purchase?
What keywords indicate strong buying intent?
What pricing/availability queries exist?
```
- **Data source:** `kw2_validated_keywords` (all, not truncated)
- **AI output:** Full intent funnel mapping (TOFU/MOFU/BOFU per keyword)

#### Module Q4 — Customer Journey Questions
```
How do people discover this problem?
What early questions do they ask?
What do they compare at consideration stage?
What convinces them to convert?
What support do they need post-purchase?
```
- **Data source:** `kw2_validated_keywords.buyer_readiness`, intent distribution
- **AI output:** Full journey map with content type per stage

#### Module Q5 — Product/Service Deep Questions
```
How is each product/service used?
Who uses it, in what context, when?
What types/variations exist?
What mistakes do beginners make?
What does a beginner not know?
```
- **Data source:** `kw2_biz_pages`, `kw2_biz_intel.products_services`
- **AI output:** Usage intelligence, variation map, knowledge gap list

#### Module Q6 — Content Opportunity Questions
```
What educational topics should we cover?
What problems can we solve through content?
What comparisons matter to our audience?
What deep guides are missing from the web?
What industry questions go unanswered?
```
- **Data source:** All previous modules + competitor gaps
- **AI output:** Content angle list per pillar

#### Module Q7 — Competitive Intelligence Questions
```
What are competitors ranking for that we're not?
Where are competitors weak?
What topics are completely uncovered?
Which questions have high intent but weak existing content?
Where can we dominate a niche?
```
- **Data source:** `kw2_biz_competitors`, `kw2_biz_competitor_keywords`
- **AI output:** Gap matrix, opportunity ranking

### Prompt Template (Generic — No Hardcoding)

```python
PROMPT_QUESTION_MODULE = """
ROLE: {module_role}

BUSINESS CONTEXT:
{business_context_block}

DATA:
{module_specific_data}

TASK:
Generate high-value intelligence questions for this business.
Focus on: {module_focus}

Rules:
- Questions must be specific to THIS business/product/audience
- No generic questions that apply to any business
- Cover {dimension_list}
- Maximum {max_questions} questions

OUTPUT: Strict JSON only.
{
  "questions": [
    {
      "question": "",
      "category": "",
      "why_it_matters": "",
      "data_source": "keyword|competitor|biz_intel|ai_inference",
      "priority": "high|medium|low"
    }
  ]
}
"""
```

### DB: New Table `kw2_intelligence_questions`

```sql
CREATE TABLE IF NOT EXISTS kw2_intelligence_questions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_module TEXT NOT NULL,         -- Q1-Q7
    question TEXT NOT NULL,
    category TEXT DEFAULT '',
    why_it_matters TEXT DEFAULT '',
    data_source TEXT DEFAULT 'ai',
    priority TEXT DEFAULT 'medium',
    answer TEXT DEFAULT '',              -- filled by Phase 5 (enrichment)
    answer_confidence REAL DEFAULT 0.0,
    expansion_depth INTEGER DEFAULT 0,   -- 0 = seed, 1 = first expansion, etc
    parent_question_id TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',       -- pending|answered|expanded|deduped
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kw2_iq_session ON kw2_intelligence_questions(session_id);
CREATE INDEX IF NOT EXISTS idx_kw2_iq_module ON kw2_intelligence_questions(session_id, source_module);
CREATE INDEX IF NOT EXISTS idx_kw2_iq_status ON kw2_intelligence_questions(session_id, status);
CREATE INDEX IF NOT EXISTS idx_kw2_iq_parent ON kw2_intelligence_questions(parent_question_id);
```

### API Endpoints (Phase 3)

```
POST /api/kw2/{pid}/sessions/{sid}/question-engine/run     ← generate all Q1–Q7 questions
GET  /api/kw2/{pid}/sessions/{sid}/question-engine/questions ← list with filters
GET  /api/kw2/{pid}/sessions/{sid}/question-engine/summary  ← count per module
PATCH /api/kw2/{pid}/sessions/{sid}/question-engine/{qid}  ← edit/annotate a question
DELETE /api/kw2/{pid}/sessions/{sid}/question-engine/{qid} ← remove question
```

### Frontend: New "Intelligence" Tab in SessionStrategyPage

```
📊 Overview | 🔑 Keywords | 🧠 Intelligence | 🗺️ Strategy | ✍️ Content Plan | ...
```

**IntelligenceTab** displays:
- Module cards (Q1–Q7) with question counts, status badges
- Question list per module: question text, category, priority, answer (collapsed)
- Filter bar: module, priority, answered/unanswered, category
- "Generate Questions" button → runs Phase 3 engine
- "Answer All" button → runs Phase 5 enrichment
- Expandable answer panel per question

---

## Phase 4 — Expansion Engine (Recursive)

**Goal:** Take seed questions and explode them into thousands of variations across dimensions.  
**Status:** NEW  
**File:** `engines/kw2/expansion_engine.py` (new)

### Core Logic: Dynamic Dimension Extraction

No hardcoding. The engine first asks AI to **discover** expansion dimensions for this specific business:

```python
PROMPT_DISCOVER_DIMENSIONS = """
ROLE: Market research analyst.

CONTEXT:
{business_context_block}

TASK:
Identify all natural expansion dimensions for content generation.

Examples of dimension types: geography, use cases, audience types,
product variations, seasonal contexts, cultural differences, professional contexts.

Do NOT use generic dimensions — only what applies to THIS business.

OUTPUT: Strict JSON only.
{
  "dimensions": {
    "geography": {
      "levels": ["country", "region", "city"],
      "values": {
        "country": [],
        "region": [],
        "city": []
      }
    },
    "use_cases": [],
    "audience_types": [],
    "product_variations": [],
    "custom": {}
  }
}
"""
```

### Recursive Expansion Algorithm

```
Level 0: Seed questions (Phase 3 output)           ~50-200 questions
   ↓  expand across all discovered dimensions
Level 1: First expansion                           ~500-2000 questions
   ↓  expand each L1 question across sub-dimensions
Level 2: Second expansion                          ~5000-20000 questions

Controlled by config:
  max_depth: 3
  max_per_node: 10
  dedup_threshold: 0.85 (cosine similarity)
  max_total: 50000
```

### Expansion Prompt Template

```python
PROMPT_EXPAND = """
ROLE: Content strategist.

BASE QUESTION:
{base_question}

EXPANSION DIMENSIONS:
{dimensions_to_expand_across}

TASK:
Generate {target_count} question variations by applying each dimension.

Rules:
- Each variation must remain relevant to: {business_context}
- Change dimension-specific context, not the question intent
- No generic or off-topic variations

OUTPUT: Strict JSON only.
{
  "expanded_questions": [
    {
      "question": "",
      "dimension_applied": "",
      "dimension_value": "",
      "is_geographic": bool,
      "estimated_search_volume": "high|medium|low"
    }
  ]
}
"""
```

### DB: `kw2_intelligence_questions` (same table, expansion_depth tracks level)

```sql
-- expansion_depth = 0 is seed, 1 is first expansion, 2 is second, etc.
-- parent_question_id links to parent seed
-- status = 'pending' → 'expanded' once children are generated
```

### DB: New Table `kw2_expansion_config`

```sql
CREATE TABLE IF NOT EXISTS kw2_expansion_config (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    discovered_dimensions TEXT DEFAULT '{}',  -- JSON from dimension discovery
    max_depth INTEGER DEFAULT 2,
    max_per_node INTEGER DEFAULT 10,
    dedup_threshold REAL DEFAULT 0.85,
    max_total INTEGER DEFAULT 10000,
    geo_levels TEXT DEFAULT '["country","region","city"]',
    expand_audience BOOLEAN DEFAULT 1,
    expand_use_cases BOOLEAN DEFAULT 1,
    created_at TEXT
);
```

### API Endpoints (Phase 4)

```
POST /api/kw2/{pid}/sessions/{sid}/expansion/discover-dimensions
POST /api/kw2/{pid}/sessions/{sid}/expansion/run
GET  /api/kw2/{pid}/sessions/{sid}/expansion/status
GET  /api/kw2/{pid}/sessions/{sid}/expansion/config
PATCH /api/kw2/{pid}/sessions/{sid}/expansion/config
```

---

## Phase 5 — Enrichment Engine

**Goal:** Add intelligence metadata to each question — intent, audience, region, business relevance, content type.  
**Status:** NEW  
**File:** `engines/kw2/enrichment_engine.py` (new)

### What it adds to each question

```python
PROMPT_ENRICH = """
ROLE: SEO and content analyst.

For each question in the list:

TASK:
Add structured intelligence:
1. Search intent (informational | commercial | transactional | navigational)
2. Funnel stage (TOFU | MOFU | BOFU)
3. Target audience segment
4. Geographic relevance (local | regional | national | global)
5. Business relevance score (0-100)
6. Likely content type (blog | guide | comparison | landing-page | faq | video-script)
7. Estimated effort (low | medium | high)

BUSINESS CONTEXT: {business_context}

QUESTIONS (batch of {batch_size}):
{questions_json}

OUTPUT: Strict JSON only.
{
  "enriched": [
    {
      "id": "",
      "intent": "",
      "funnel_stage": "",
      "audience_segment": "",
      "geo_relevance": "",
      "business_relevance": 0,
      "content_type": "",
      "effort": ""
    }
  ]
}
"""
```

*Runs in parallel batches of 50 questions per AI call to control cost.*

### DB: Updates `kw2_intelligence_questions` with enrichment fields

```sql
ALTER TABLE kw2_intelligence_questions ADD COLUMN intent TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN funnel_stage TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN audience_segment TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN geo_relevance TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN business_relevance REAL DEFAULT 0.0;
ALTER TABLE kw2_intelligence_questions ADD COLUMN content_type TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN effort TEXT DEFAULT 'medium';
```

---

## Phase 6 — Deduplication & Clustering

**Goal:** Remove semantic duplicates and organise questions into content clusters.  
**Status:** NEW  
**File:** `engines/kw2/dedup_engine.py` (new)

### Deduplication Strategy

Two-pass approach:
1. **Exact/near-exact:** Levenshtein distance < 0.1 — immediate discard
2. **Semantic:** Embedding-based cosine similarity > threshold — keep highest-scored

```python
# Embedding model: use existing ollama embeddings or sentence_transformers
# Batch process in groups of 500

DEDUP_CONFIG = {
  "exact_threshold": 0.1,       # Levenshtein
  "semantic_threshold": 0.85,   # cosine similarity
  "keep_strategy": "highest_business_relevance"
}
```

### Clustering

Group deduplicated questions into topic clusters:

```python
PROMPT_CLUSTER = """
ROLE: Content taxonomist.

QUESTIONS (post-dedup):
{questions_json}

TASK:
Group these questions into content topic clusters.
Each cluster should represent a coherent content area.

Rules:
- Use only clusters relevant to this business
- No catch-all "other" category
- Each cluster must have at least 3 questions
- Maximum {max_clusters} clusters

OUTPUT: Strict JSON only.
{
  "clusters": [
    {
      "cluster_name": "",
      "description": "",
      "pillar": "",
      "intent_mix": {"informational": 0, "commercial": 0, "transactional": 0},
      "question_ids": []
    }
  ]
}
"""
```

### DB: New Table `kw2_content_clusters`

```sql
CREATE TABLE IF NOT EXISTS kw2_content_clusters (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    cluster_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    pillar TEXT DEFAULT '',
    intent_mix TEXT DEFAULT '{}',
    question_count INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'active',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kw2_cc_session ON kw2_content_clusters(session_id);
```

Update `kw2_intelligence_questions` to reference cluster:
```sql
ALTER TABLE kw2_intelligence_questions ADD COLUMN content_cluster_id TEXT DEFAULT '';
ALTER TABLE kw2_intelligence_questions ADD COLUMN is_duplicate INTEGER DEFAULT 0;
ALTER TABLE kw2_intelligence_questions ADD COLUMN duplicate_of TEXT DEFAULT '';
```

---

## Phase 7 — Scoring Engine

**Goal:** Score every question by strategic value to produce a rankable priority list.  
**Status:** NEW (generic, fully configurable — no hardcoding)  
**File:** `engines/kw2/scoring_engine.py` (new)

### Scoring Formula

```
FINAL_SCORE = (
  business_fit_score    × w1  +   # How well does this serve business goals?
  intent_value_score    × w2  +   # How strong is the search intent?
  demand_potential      × w3  +   # How many people likely search this?
  competition_ease      × w4  +   # How easy is it to rank for content around this?
  uniqueness_score      × w5      # How differentiated is this vs competitor content?
)
```

### Default Weights (User-Configurable)

```python
DEFAULT_SCORING_WEIGHTS = {
  "business_fit":    0.30,
  "intent_value":    0.20,
  "demand_potential": 0.20,
  "competition_ease": 0.15,
  "uniqueness":      0.15
}
```

Weights are stored per session and user-editable from the UI.

### How Each Component is Calculated

| Component | Calculation Method |
|---|---|
| `business_fit` | AI score from enrichment × pillar match bonus |
| `intent_value` | transactional=1.0, commercial=0.8, informational=0.6, navigational=0.4 |
| `demand_potential` | keyword volume signal (if available) or AI estimate |
| `competition_ease` | inverse of keyword difficulty; low-difficulty clusters boost score |
| `uniqueness` | penalise topics well-covered by competitors; reward gap topics |

### DB: Scoring weights table

```sql
CREATE TABLE IF NOT EXISTS kw2_scoring_config (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    weights TEXT NOT NULL DEFAULT '{}',   -- JSON weights object
    version INTEGER DEFAULT 1,
    created_at TEXT
);
```

Update `kw2_intelligence_questions`:
```sql
ALTER TABLE kw2_intelligence_questions ADD COLUMN final_score REAL DEFAULT 0.0;
ALTER TABLE kw2_intelligence_questions ADD COLUMN score_breakdown TEXT DEFAULT '{}';
```

### API Endpoints (Phase 7)

```
POST /api/kw2/{pid}/sessions/{sid}/scoring/run
GET  /api/kw2/{pid}/sessions/{sid}/scoring/config
PATCH /api/kw2/{pid}/sessions/{sid}/scoring/config   ← update weights
GET  /api/kw2/{pid}/sessions/{sid}/scoring/ranked    ← sorted by final_score
```

---

## Phase 8 — Selection Engine

**Goal:** From thousands of scored questions, select a balanced top set for content execution.  
**Status:** NEW  
**File:** `engines/kw2/selection_engine.py` (new)

### Selection Rules

```python
SELECTION_CONFIG = {
  "target_count": 1000,          # final selection target
  "diversity_rules": {
    "min_per_cluster": 5,         # minimum from each content cluster
    "max_per_cluster": 100,       # prevent single-cluster dominance
    "intent_distribution": {      # ensure intent balance
      "informational": 0.50,
      "commercial":    0.25,
      "transactional": 0.20,
      "navigational":  0.05
    },
    "geo_coverage": True,         # ensure geographic spread
    "funnel_coverage": True       # ensure TOFU/MOFU/BOFU coverage
  }
}
```

### DB: New Table `kw2_selected_questions`

```sql
CREATE TABLE IF NOT EXISTS kw2_selected_questions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    question_id TEXT NOT NULL,        -- FK to kw2_intelligence_questions
    selection_rank INTEGER NOT NULL,  -- 1 to target_count
    selection_reason TEXT DEFAULT '',
    cluster_id TEXT DEFAULT '',
    content_title_id TEXT DEFAULT '', -- set after Phase 9
    status TEXT DEFAULT 'selected',   -- selected|title_generated|article_created|published
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kw2_sq_session ON kw2_selected_questions(session_id);
CREATE INDEX IF NOT EXISTS idx_kw2_sq_rank ON kw2_selected_questions(session_id, selection_rank);
```

### API Endpoints (Phase 8)

```
POST /api/kw2/{pid}/sessions/{sid}/selection/run
GET  /api/kw2/{pid}/sessions/{sid}/selection/list
PATCH /api/kw2/{pid}/sessions/{sid}/selection/config
POST /api/kw2/{pid}/sessions/{sid}/selection/include/{question_id}  ← manual add
DELETE /api/kw2/{pid}/sessions/{sid}/selection/{question_id}        ← manual remove
```

---

## Phase 9 — Content Generation Engine

**Goal:** Convert selected questions into SEO-optimised content titles, then into full article briefs and content.  
**Status:** NEW (replaces ad-hoc brief generation in ContentPlanTab)  
**File:** `engines/kw2/content_title_engine.py` (new)

### Step 9A — Question → SEO Title

```python
PROMPT_TITLE_GENERATION = """
ROLE: SEO copywriter and content strategist.

BUSINESS: {universe}

QUESTIONS (batch of {batch_size}):
{questions_json}

TASK:
Convert each question into:
1. A high-CTR SEO content title
2. A URL-friendly slug
3. The primary target keyword
4. The H1 meta title variant

Rules:
- Titles must be specific, not generic
- Match user intent exactly
- Naturally include target keyword
- Between 40-65 characters for meta title
- No clickbait — clear, honest titles

OUTPUT: Strict JSON only.
{
  "titles": [
    {
      "question_id": "",
      "title": "",
      "slug": "",
      "primary_keyword": "",
      "meta_title": "",
      "content_type": "",
      "word_count_target": 0
    }
  ]
}
"""
```

### Step 9B — Title → Brief

Uses existing `api.generateBrief()` infrastructure. Upgrade: now linked to question intelligence for richer context.

### Step 9C — Brief → Article (Planned, Phase 11)

Full article generation from brief — connected to content hub.

### DB: New Table `kw2_content_titles`

```sql
CREATE TABLE IF NOT EXISTS kw2_content_titles (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    question_id TEXT NOT NULL,           -- FK to kw2_intelligence_questions
    selected_question_id TEXT DEFAULT '',-- FK to kw2_selected_questions
    title TEXT NOT NULL,
    slug TEXT DEFAULT '',
    primary_keyword TEXT DEFAULT '',
    meta_title TEXT DEFAULT '',
    content_type TEXT DEFAULT 'blog',
    word_count_target INTEGER DEFAULT 1500,
    pillar TEXT DEFAULT '',
    cluster_name TEXT DEFAULT '',
    intent TEXT DEFAULT '',
    funnel_stage TEXT DEFAULT 'TOFU',
    brief_json TEXT DEFAULT '{}',
    article_id TEXT DEFAULT '',          -- FK to articles table when generated
    status TEXT DEFAULT 'titled',        -- titled|briefed|writing|published
    scheduled_date TEXT DEFAULT '',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kw2_ct_session ON kw2_content_titles(session_id);
CREATE INDEX IF NOT EXISTS idx_kw2_ct_status ON kw2_content_titles(session_id, status);
CREATE INDEX IF NOT EXISTS idx_kw2_ct_pillar ON kw2_content_titles(session_id, pillar);
```

### API Endpoints (Phase 9)

```
POST /api/kw2/{pid}/sessions/{sid}/content-titles/generate  ← batch title generation
GET  /api/kw2/{pid}/sessions/{sid}/content-titles           ← list with filters
POST /api/kw2/{pid}/sessions/{sid}/content-titles/{id}/brief ← generate brief
POST /api/kw2/{pid}/sessions/{sid}/content-titles/{id}/article ← generate article
PATCH /api/kw2/{pid}/sessions/{sid}/content-titles/{id}     ← edit title/slug
```

---

## Phase 10 — Execution Layer (Content Hub Upgrade)

**Goal:** Make the Content Hub session-aware and strategy-driven.  
**Status:** UPGRADE existing Content Hub.

### Current Problem

Content Hub uses the old KI pipeline data (wrong data source). It is not session-aware.

### Required Changes

1. **All Content Hub queries must include `session_id`**
2. **Content Hub article list = `kw2_content_titles` table** (not ad-hoc)
3. **Pillar-based browsing:** Click pillar → see all titles for that pillar → expand cluster
4. **Smart prioritisation:** Titles ordered by `selection_rank` (from Phase 8)
5. **"What to do next" widget:** Surfaces top 3 quick wins from strategy

### "Next Action" Widget

```python
NEXT_ACTION_LOGIC = """
From kw2_selected_questions WHERE status = 'selected':
  1. Filter: intent = 'transactional' AND score > 80  → "Money" priority
  2. Filter: funnel_stage = 'TOFU' AND effort = 'low' → "Quick Win"
  3. Filter: cluster most questions belong to         → "Cluster momentum"

Display top 3 as actionable cards:
  Card: "Write this next" → click → opens article editor
"""
```

### Frontend: New ContentHub Layout

```
Content Hub (session-scoped)
  ├── "What to Do Next" widget (3 cards)
  ├── Filters: pillar | cluster | intent | funnel_stage | status
  ├── View: Grid or List
  ├── Titles from kw2_content_titles
  │     each: title, keyword, intent badge, funnel badge, score, status
  │     actions: Generate Brief | Edit | Schedule | Mark Published
  └── Bulk actions: select multiple → Generate All Briefs
```

---

## Phase 11 — Feedback & Learning Engine

**Goal:** Close the loop — track published content performance and improve scoring weights over time.  
**Status:** NEW (advanced, implement last)  
**File:** `engines/kw2/feedback_engine.py` (new)

### What Gets Tracked

```sql
CREATE TABLE IF NOT EXISTS kw2_content_performance (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    content_title_id TEXT NOT NULL,
    article_id TEXT DEFAULT '',
    tracked_date TEXT NOT NULL,
    google_position REAL DEFAULT 0.0,        -- SERP position (via GSC or manual)
    organic_clicks INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0.0,
    conversions INTEGER DEFAULT 0,
    data_source TEXT DEFAULT 'manual',       -- manual | gsc | analytics
    created_at TEXT
);
```

### Feedback → Scoring Update

```python
# After collecting performance data:
# 1. Compare predicted score vs actual performance
# 2. Update scoring weights via Bayesian adjustment
# 3. Re-run scoring on pending content title pool
# 4. Bubble up better-performing content types

FEEDBACK_ADJUSTMENT = {
  "observation_window_days": 60,
  "min_data_points": 5,        # minimum articles needed before adjusting
  "learning_rate": 0.1         # how aggressively to update weights
}
```

### API Endpoints (Phase 11)

```
POST /api/kw2/{pid}/sessions/{sid}/performance/record
GET  /api/kw2/{pid}/sessions/{sid}/performance/summary
POST /api/kw2/{pid}/sessions/{sid}/performance/apply-learnings
```

---

## Phase 12 — Prompt & Control Layer (Prompt Studio)

**Goal:** Make the entire engine transparent and user-customisable. No AI black boxes.  
**Status:** NEW  
**File:** `engines/kw2/prompt_manager.py` (new)

### Design Principles

- Every prompt used by the system is **visible to the user**
- Every prompt is **editable** with live preview
- Every prompt is **versioned** — rollback to any version
- Every prompt has **variable documentation** — user knows what `{business_context}` contains

### Prompt Registry

```python
PROMPT_REGISTRY = {
  "strategy_system":       { "id": "SYS-001", "phase": 2, "editable": True },
  "strategy_user":         { "id": "USR-001", "phase": 2, "editable": True },
  "business_analysis":     { "id": "MOD-2A",  "phase": 2, "editable": True },
  "keyword_intelligence":  { "id": "MOD-2B",  "phase": 2, "editable": True },
  "strategy_builder":      { "id": "MOD-2C",  "phase": 2, "editable": True },
  "action_mapping":        { "id": "MOD-2D",  "phase": 2, "editable": True },
  "question_gen_q1":       { "id": "Q-001",   "phase": 3, "editable": True },
  # ... one entry per prompt
  "title_generation":      { "id": "CT-001",  "phase": 9, "editable": True },
}
```

### DB: New Table `kw2_prompts`

```sql
CREATE TABLE IF NOT EXISTS kw2_prompts (
    id TEXT PRIMARY KEY,
    prompt_key TEXT NOT NULL UNIQUE,      -- e.g. "strategy_user"
    phase INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    template TEXT NOT NULL,               -- the actual prompt with {variables}
    variables TEXT DEFAULT '[]',          -- JSON list of {name, description, source}
    is_system INTEGER DEFAULT 0,          -- 0 = user editable, 1 = system only
    version INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS kw2_prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    template TEXT NOT NULL,
    version INTEGER NOT NULL,
    changed_by TEXT DEFAULT 'user',
    change_note TEXT DEFAULT '',
    created_at TEXT
);
```

### API Endpoints (Phase 12)

```
GET  /api/kw2/prompts                              ← list all prompts
GET  /api/kw2/prompts/{key}                        ← get prompt + variables
PATCH /api/kw2/prompts/{key}                       ← update template
POST /api/kw2/prompts/{key}/test                   ← test with sample data
GET  /api/kw2/prompts/{key}/versions               ← version history
POST /api/kw2/prompts/{key}/restore/{version}      ← rollback
```

### Frontend: Prompt Studio Tab

```
📋 Parameters | 🎯 Goals | 🔧 Prompt Studio
```

**PromptStudioTab** shows:
- List of all prompts grouped by phase
- For each prompt: name, phase badge, "edit" button
- Prompt editor: text area + variable reference panel
- "Test Prompt" → sends sample context → shows AI output
- Version history: diff view, restore button

---

## Integration Plan — Execution Order

### Milestone 1 — Data Integrity (Immediate)

Fix the split-brain problem first. Nothing else works correctly while two data sources co-exist.

```
1. Fix Analysis page → read from kw2_validated_keywords (not KI)
2. Fix Content Hub → read from kw2_content_titles / kw2_calendar
3. Fix Overview KPIs → read from kw2 session data
4. All queries: require session_id
```

**Effort:** 2–3 days backend + 1 day frontend  
**Impact:** Fixes ~40% of existing bugs

### Milestone 2 — Strategy v2 (Phase 2 Upgrade)

Upgrade Phase 9 to use richer data + versioning + editing.

```
1. Add kw2_strategy_versions table (migration)
2. Update StrategyEngine to use full keyword set + 4 sub-modules
3. Add version list API + diff API
4. Frontend: version badge, history drawer, edit toggles
5. Add "Regenerate section" per strategy card
```

**Effort:** 3–4 days backend + 2 days frontend  
**Impact:** Strategy quality improves dramatically, becomes useful

### Milestone 3 — Question Intelligence (Phase 3)

```
1. Create kw2_intelligence_questions table (migration)
2. Build question_engine.py with 7 modules
3. Add IntelligenceTab to SessionStrategyPage
4. Build answer enrichment (Phase 5) alongside
```

**Effort:** 3 days backend + 2 days frontend  
**Impact:** Foundation for all content generation intelligence

### Milestone 4 — Expansion + Scoring (Phases 4 + 6 + 7)

```
1. Build expansion_engine.py
2. Build dedup_engine.py
3. Build scoring_engine.py
4. Add scoring config UI (weights sliders in Parameters tab)
5. Show question counts at each stage in IntelligenceTab
```

**Effort:** 4 days backend + 1 day frontend  
**Impact:** Generates the 1000+ question pool with ranked priorities

### Milestone 5 — Content Title Engine (Phases 8 + 9)

```
1. Create kw2_content_titles table (migration)
2. Build content_title_engine.py
3. Update Content Hub to use kw2_content_titles
4. Add "What to do next" widget
5. Wire Phase 8 selection → Phase 9 title generation
```

**Effort:** 3 days backend + 3 days frontend  
**Impact:** Content Hub becomes the execution layer for strategy decisions

### Milestone 6 — Prompt Studio (Phase 12)

```
1. Create kw2_prompts table (migration)
2. Seed all existing prompts from prompts.py into table
3. Build prompt_manager.py helper
4. Add PromptStudioTab to SessionStrategyPage
5. Wire all AI calls to read from kw2_prompts instead of hardcoded strings
```

**Effort:** 3 days backend + 2 days frontend  
**Impact:** Full transparency + user customisation; product differentiator

### Milestone 7 — Feedback Loop (Phase 11)

```
1. Create kw2_content_performance table (migration)
2. Add manual performance input UI
3. Build feedback_engine.py with weight adjustment
4. Show performance dashboard in Overview tab
```

**Effort:** 3 days backend + 2 days frontend  
**Impact:** System gets smarter over time; long-term differentiation

---

## Complete New DB Tables Summary

| Table | Phase | Purpose |
|---|---|---|
| `kw2_strategy_versions` | 2 | Versioned strategy outputs |
| `kw2_strategy_edits` | 2 | User edits to strategy fields |
| `kw2_intelligence_questions` | 3–6 | All questions: seed + expanded + enriched + scored |
| `kw2_expansion_config` | 4 | Expansion engine configuration per session |
| `kw2_content_clusters` | 6 | Topic clusters from dedup phase |
| `kw2_scoring_config` | 7 | Per-session scoring weights |
| `kw2_selected_questions` | 8 | Top questions selected for content |
| `kw2_content_titles` | 9 | Generated SEO titles → briefs → articles |
| `kw2_content_performance` | 11 | Published article performance metrics |
| `kw2_prompts` | 12 | Prompt registry with templates |
| `kw2_prompt_versions` | 12 | Prompt version history |

---

## New Files to Create

| File | Phase | Description |
|---|---|---|
| `engines/kw2/question_engine.py` | 3 | Q1–Q7 question generation |
| `engines/kw2/expansion_engine.py` | 4 | Recursive question expansion |
| `engines/kw2/enrichment_engine.py` | 5 | Question enrichment with metadata |
| `engines/kw2/dedup_engine.py` | 6 | Deduplication and clustering |
| `engines/kw2/scoring_engine.py` | 7 | Generic weighted scoring |
| `engines/kw2/selection_engine.py` | 8 | Balanced top-N selection |
| `engines/kw2/content_title_engine.py` | 9 | Question → SEO title generation |
| `engines/kw2/feedback_engine.py` | 11 | Performance tracking and weight adjustment |
| `engines/kw2/prompt_manager.py` | 12 | Prompt registry CRUD |

### Upgrade Existing Files

| File | Changes |
|---|---|
| `engines/kw2/strategy_engine.py` | Add 4 sub-modules (2A–2D), full keyword set, version support |
| `engines/kw2/db.py` | Add all new table CREATE + migration ALTER statements |
| `engines/kw2/prompts.py` | Move prompts to DB (prompts.py becomes seed file) |
| `frontend/src/kw2/SessionStrategyPage.jsx` | Add IntelligenceTab, PromptStudioTab, version/edit UI |
| `frontend/src/kw2/api.js` | Add all new endpoint functions |
| `main.py` | Add all new route handlers |

---

## Design Principles (Non-Negotiable)

1. **No hardcoding** — every value derived from data, config or user input
2. **Session-first** — every query requires `session_id`; no cross-session bleed
3. **Prompt visibility** — user can see every prompt; no AI black boxes
4. **Prompt editability** — user can modify prompts per session
5. **Modular AI blocks** — each engine is independent; swap or skip any phase
6. **Generic business model** — zero assumptions about business type in engine logic
7. **Controlled expansion** — recursive growth bounded by configurable limits
8. **Strategy drives everything** — content, calendar, briefs all derive from strategy decisions
9. **Feedback loop** — system improves based on published content performance

---

## Updated Strategy Page Tab Structure

```
Current (7 tabs):
📊 Overview | 🔑 Keywords | 🗺️ Strategy | ✍️ Content Plan | 🔗 Links | 📋 Parameters | 🎯 Goals

v2 (10 tabs):
📊 Overview | 🔑 Keywords | 🧠 Intelligence | 🗺️ Strategy | 📝 Titles | ✍️ Content Plan | 🔗 Links | 📋 Parameters | 🎯 Goals | 🔧 Prompts
```

| New Tab | Phase | Key Actions |
|---|---|---|
| 🧠 Intelligence | 3–8 | Run question engine, view questions, see expansion, trigger scoring |
| 📝 Titles | 9 | View selected top titles, generate briefs, schedule articles |
| 🔧 Prompts | 12 | Edit any prompt, test, view history |

---

## What This Becomes

Current → "AI Strategy Generator" (generates, displays)

v2 → **SEO Intelligence Platform** that:
- Understands the business through structured questions
- Expands content opportunities across every relevant dimension
- Scores and ranks by real strategic value
- Drives content decisions from intelligence, not guesswork
- Learns from published performance to improve future decisions

The user experience becomes:

```
1. Set up session (business + geo + audience)
2. Run pipeline (Phases 1–8 — auto or manual)
3. Open Strategy Page → it's already thinking
4. Review Intelligence tab: see what questions the system generated
5. Review Strategy tab: see AI-built strategy with version control
6. Review Titles tab: see 1000 ranked content titles ready to execute
7. Click "Generate Brief" → edit → publish
8. Track performance → system updates priorities automatically
```

That is an autonomous SEO operating system.
