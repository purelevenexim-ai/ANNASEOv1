# Strategy Engine — Complete Reference

**Last Updated:** April 2026  
**System:** kw2 Phase 9 (the active strategy engine)  
**Backend engine:** `engines/kw2/strategy_engine.py`  
**Backend endpoint:** `POST /api/kw2/{project_id}/sessions/{session_id}/phase9`  
**Frontend:** `frontend/src/kw2/SessionStrategyPage.jsx`

> **IMPORTANT:** An older document (`STRATEGY_ENGINE.md`) and an older UI (`Step4Strategy.jsx`) exist in the repo from the previous "ki" pipeline. They are **deprecated**. Everything described here is the current kw2 Phase 9 system.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Full Architecture & Data Flow](#2-full-architecture--data-flow)
3. [Input Parameters (What the User Configures)](#3-input-parameters)
4. [Data Sources (What Feeds the AI)](#4-data-sources)
5. [AI Providers & Cascade Logic](#5-ai-providers--cascade-logic)
6. [Prompt Templates](#6-prompt-templates)
7. [Full Strategy JSON Output Schema](#7-full-strategy-json-output-schema)
8. [Frontend UI — SessionStrategyPage.jsx](#8-frontend-ui)
9. [API Endpoints](#9-api-endpoints)
10. [Backend Code Reference](#10-backend-code-reference)
11. [Database Tables](#11-database-tables)
12. [Keyword Segmentation System](#12-keyword-segmentation-system)
13. [Health Score Calculation](#13-health-score-calculation)
14. [Known Issues & Pending Features](#14-known-issues--pending-features)
15. [Files Reference](#15-files-reference)

---

## 1. System Overview

The **kw2 Phase 9 Strategy Engine** is the final phase of the kw2 keyword intelligence pipeline. It synthesises every piece of data collected in Phases 1–8 — validated keywords, clusters, a content calendar, internal links, business intelligence, crawled pages, and competitor analysis — into a comprehensive, AI-generated SEO/AEO content strategy.

### Where it sits in the pipeline

```
Phase 1  — Session setup & seed keywords
Phase 2  — Keyword expansion (AI)
Phase 3  — Keyword validation (search intent, scoring)
Phase 4  — Pillar assignment
Phase 5  — Business intelligence crawl (website pages, USPs, goals)
Phase 6  — Competitor intelligence
Phase 7  — Keyword scoring (P7++) & internal link mapping
Phase 8  — Content calendar generation
Phase 9  — STRATEGY GENERATION ← this engine
```

Phase 9 is gated: **it requires `phase8_done = True`** in the session row before it will run.

---

## 2. Full Architecture & Data Flow

```
User configures Content Parameters (ContentParametersTab)
  │
  ▼
POST /api/kw2/{project_id}/sessions/{session_id}/phase9
  │  body: _Phase9Body (see §3)
  ▼
main.py → StrategyEngine(db).generate(project_id, session_id, ai_provider, content_params)
  │
  ├─ Load from DB ─────────────────────────────────────────────────────────────────
  │   kw2_business_profiles  →  universe, pillars[], audience, geo_scope, business_type
  │   kw2_biz_intel           →  usps[], goals[], audience_segments[], products_services[],
  │   (phase 5 output)            brand_voice, knowledge_summary, seo_strategy, website_summary
  │   kw2_biz_pages           →  page_type, primary_topic, search_intent, keywords_extracted[]
  │   (phase 5 output)
  │   kw2_biz_competitors     →  domain, missed_opportunities[], weaknesses[], top_keywords[]
  │   (phase 6 output)
  │   kw2_validated_keywords  →  top 30 rows: keyword, score, intent, pillar, buyer_readiness
  │   kw2_clusters            →  top 20 rows: cluster_name, top_keyword
  │   kw2_calendar            →  count, first_date, last_date
  │
  ├─ Render STRATEGY_USER prompt with all context (see §6)
  │
  ├─ kw2_ai_call(provider, system, user) → raw AI response
  │   │  cascade: auto → groq → ollama → gemini → claude
  │   ▼
  ├─ kw2_extract_json(raw_response) → strategy dict
  │   │  fallback: wraps raw text + top 10 keywords as quick_wins
  │   ▼
  └─ db.update_session(session_id, phase9_done=1, strategy_json=json.dumps(strategy))
       │
       ▼
     Returned to frontend
       │
       ▼
GET /api/kw2/{project_id}/sessions/{session_id}/strategy  ← cached retrieval
       │
       ▼
SessionStrategyPage.jsx — displays in 7 tabs (see §8)
```

---

## 3. Input Parameters

The user configures these in the **Parameters tab** before clicking "Generate Strategy".

### `_Phase9Body` model (`main.py`)

```python
class _Phase9Body(BaseModel):
    ai_provider:        Optional[str]   = None  # see §5
    blogs_per_week:     Optional[int]   = None  # 1–7 (default 3)
    duration_weeks:     Optional[int]   = None  # 1–52 (default 12)
    content_mix:        Optional[dict]  = None  # {informational, transactional, commercial} must sum ~100
    publishing_cadence: Optional[list]  = None  # e.g. ["Mon","Wed","Fri"]
    extra_prompt:       Optional[str]   = None  # free-text strategy focus guidance
    start_date:         Optional[str]   = None  # ISO date string; used by frontend for date calc
```

### Frontend defaults (`CP_DEFAULTS` in `SessionStrategyPage.jsx`)

```js
const CP_DEFAULTS = {
  blogs_per_week: 3,
  duration_weeks: 12,
  content_mix: { informational: 60, transactional: 20, commercial: 20 },
  publishing_cadence: ["Mon", "Wed", "Fri"],
  ai_provider: "auto",
  extra_prompt: "",
  start_date: "",   // empty = today
}
```

---

## 4. Data Sources

Every column the AI sees comes from the database. Nothing is fabricated.

| Source Table | Column(s) Used | Used For |
|---|---|---|
| `kw2_business_profiles` | `universe`, `pillars`, `audience`, `geo_scope`, `business_type` | Core business identity in prompt |
| `kw2_biz_intel` | `usps`, `goals`, `audience_segments`, `products_services`, `brand_voice`, `knowledge_summary`, `seo_strategy`, `website_summary` | Rich business context block |
| `kw2_biz_pages` | `page_type`, `primary_topic`, `search_intent`, `keywords_extracted` | Existing site structure |
| `kw2_biz_competitors` | `domain`, `missed_opportunities`, `weaknesses`, `top_keywords` | Competitive gap analysis |
| `kw2_validated_keywords` | Top 30 rows by score: `keyword`, `score`, `intent`, `pillar`, `buyer_readiness` | Primary keyword data |
| `kw2_clusters` | Top 20 rows: `cluster_name`, `top_keyword` | Topic clusters |
| `kw2_calendar` | `COUNT(*)`, `MIN(date)`, `MAX(date)` | Content velocity metadata |

### Biz Intel block (appended to prompt)

```
BUSINESS INTELLIGENCE:
Website: {website_summary}
Knowledge: {knowledge_summary}
USPs: {usps}
Goals: {goals}
Audience segments: {audience_segments}
Products/services: {products_services}
Brand voice: {brand_voice}
SEO strategy: {seo_strategy}
Pages: [{page_type} | {primary_topic} | intent:{search_intent} | kw:{keywords_extracted}]
Competitors: [{domain} | gaps:{missed_opportunities} | weaknesses:{weaknesses} | top_kw:{top_keywords}]
```

### Content Plan block (appended to prompt)

```
CONTENT PLAN:
Velocity: {blogs_per_week} articles/week for {duration_weeks} weeks
Cadence: {publishing_cadence}
Mix: {content_mix}
{extra_prompt}
```

---

## 5. AI Providers & Cascade Logic

| ID | Label | Model | Speed | Cost |
|---|---|---|---|---|
| `auto` | Auto | Groq → Ollama → Gemini cascade | Fast | Free |
| `groq` | Groq | llama-3.1-8b-instant | Fastest | Free tier |
| `ollama` | Local | qwen2.5:3b | Moderate | Free (on-device) |
| `gemini` | Gemini | gemini-flash | Fast | ~$0.001/run |
| `claude` | Claude | claude-3-haiku | Best quality | ~$0.012/run |

All calls go through `kw2_ai_call()` which handles retries and cascade fallback.  
All AI cost/usage is logged to `kw2_ai_cost_log`.

---

## 6. Prompt Templates

### System prompt (`STRATEGY_SYSTEM` in `engines/kw2/prompts.py`)

```
You are a senior SEO strategist. Generate a comprehensive content strategy based on validated keyword data.
Output ONLY valid JSON.
```

### User prompt (`STRATEGY_USER`)

```
Business: {universe} ({business_type})
Pillars: {pillars}
Top keywords ({count}): {top_keywords}
  — each row: keyword | score | intent | pillar
Clusters: {clusters}
  — each row: cluster_name | top_keyword
Audience: {audience}
Geo: {geo_scope}

[BUSINESS INTELLIGENCE block — see §4]
[CONTENT PLAN block — see §4]
```

The prompt instructs the AI to output the full JSON schema described in §7.

---

## 7. Full Strategy JSON Output Schema

```json
{
  "strategy_summary": {
    "headline":           "One-sentence strategy",
    "biggest_opportunity":"Underserved keyword gap or persona",
    "why_we_win":         "Specific competitive advantage"
  },

  "priority_pillars": ["pillar1", "pillar2"],

  "pillar_strategies": [
    {
      "pillar":          "Pillar name",
      "target_keyword":  "Primary keyword for this pillar",
      "key_topics":      ["topic1", "topic2"],
      "word_count":      2000,
      "difficulty":      "medium",
      "rank_timeline":   "3–6 months"
    }
  ],

  "executive_summary":  "Full strategy narrative text",

  "positioning_statement": "One-paragraph brand position",

  "quick_wins": [
    {
      "keyword":      "target keyword",
      "intent":       "informational|transactional|commercial",
      "content_type": "blog|guide|comparison|landing-page",
      "reason":       "Why this is a quick win"
    }
  ],

  "content_gaps":    ["topics competitors cover that we don't"],

  "competitive_gaps": [
    { "competitor": "domain.com", "opportunity": "specific gap" }
  ],

  "content_priorities": [
    { "priority": 1, "title": "Article title", "effort": "low|medium|high", "impact": "low|medium|high" }
  ],

  "key_messages": ["Brand message string"],

  "seo_tactics": ["Tactic string"],

  "seo_recommendations": [
    {
      "area":     "Content depth|Technical SEO|Link building|etc.",
      "priority": "high|medium|low",
      "action":   "Specific action to take",
      "impact":   "Expected impact"
    }
  ],

  "monthly_themes": [
    { "month": "January", "theme": "Theme name", "keywords": ["kw1", "kw2"] }
  ],

  "weekly_plan": [
    {
      "week": 1,
      "focus_pillar": "Pillar name",
      "articles": [
        {
          "title":           "Article title",
          "primary_keyword": "target keyword",
          "intent":          "informational",
          "page_type":       "blog|guide|landing"
        }
      ]
    }
  ],

  "link_building_plan": "Text description or structured object",

  "timeline": [
    { "phase": "Phase name", "action": "Action description", "keywords": ["kw1"] }
  ],

  "aeo_strategy": {
    "ai_visibility_targets":  ["query1", "query2"],
    "structured_data_plan":   ["Article", "BlogPosting", "FAQPage"],
    "featured_snippet_targets": ["question-style query"]
  },

  "90_day_plan": [
    {
      "month": 1,
      "focus": "Foundation",
      "deliverables": ["Deliverable 1", "Deliverable 2"]
    }
  ],

  "content_strategy": {
    "pillar_plan": [
      {
        "pillar":             "Pillar name",
        "priority":           "high|medium|low",
        "content_types":      ["blog", "guide", "comparison"],
        "target_intent":      "informational|transactional|commercial",
        "estimated_articles": 15,
        "quick_wins":         ["keyword1", "keyword2"]
      }
    ]
  },

  "confidence": 0.85
}
```

### Field notes

- `weekly_plan` — primary for ContentPlanTab; the frontend also accepts `content_calendar` (legacy alias)
- `aeo_strategy` — rendered in StrategyTab AEO section and OverviewTab AEO card
- `90_day_plan` — rendered as checklist cards in StrategyTab
- `content_strategy.pillar_plan` — rendered as pillar cards in StrategyTab
- `seo_recommendations` — rendered as priority cards in StrategyTab
- `confidence` — float 0–1, shown in StrategyTab metadata bar
- Fallback: if JSON extraction fails, engine wraps the raw text + top 10 keywords into `quick_wins`

---

## 8. Frontend UI

**File:** `frontend/src/kw2/SessionStrategyPage.jsx` (~3400 lines)

### 7 Tabs

```
📊 Overview  |  🔑 Keywords  |  🗺️ Strategy  |  ✍️ Content Plan  |  🔗 Link Building  |  📋 Parameters  |  🎯 Goals
```

### Tab: Overview (`OverviewTab`)

Displays at-a-glance session health before strategy is generated. Shows:
- Phase pipeline status (which phases are done, click to go to params)
- **Health Score card** — 5-dimension radial score (see §13)
- **AEO Visibility card** — shows `aeo_strategy` targets if strategy exists
- **Business Intelligence card** — USPs, goals, knowledge summary
- Session statistics: total keywords, validated, clusters, pages, pillars

Props: `session, validatedData, pillarStats, strat, bizContext, onRunPhase9, running, logs, projectId`

---

### Tab: Keywords (`KeywordsTab`)

Full keyword explorer with:
- **Segmentation cards** (clickable filters):
  - 💰 **Money** — buyer_readiness ≥ 70, transactional/commercial intent
  - 🌱 **Growth** — score ≥ 60, informational intent, long-tail
  - 🤝 **Support** — navigational intent, low difficulty
  - ⚡ **Quick Wins** — high score + low difficulty combination
- Search input (filters keyword column)
- Sortable columns: keyword, score, intent, pillar, buyer_readiness
- Pagination (20 per page)
- Intent colour badges, score colour indicators

Props: `validatedData, pillarStats, bizContext`

Data fetched via: `api.getValidated(projectId, sessionId)`

---

### Tab: Strategy (`StrategyTab`)

Primary strategy display. Sections rendered (all conditional on data presence):
1. **Context Used banner** — shows when strategy was generated, which AI provider, confidence score
2. **Metadata bar** — priority pillars, confidence badge, "Run Strategy" button if not yet generated
3. **Strategy Summary** — headline, biggest opportunity, why we win
4. **Executive Summary** — full narrative paragraph
5. **Quick Wins** — card-per-win with intent badge, content-type badge, reason text
6. **Content Priorities** — ordered list with effort/impact badges
7. **Key Messages** — bullet list
8. **SEO Tactics** — bullet list  
9. **Monthly Themes** — month → theme → keywords
10. **Timeline** — phase → action → keywords
11. **SEO Recommendations** — cards sorted by priority (high → medium → low), each with area, action, impact
12. **AEO / AI Search Strategy** — 3-column grid: AI Visibility Targets, Structured Data Plan, Featured Snippet Targets
13. **90-Day Plan** — monthly cards (Month 1/2/3) with focus + deliverables checklist
14. **Content Strategy Pillar Plan** — pillar cards with priority, content types, intent, article count, quick wins

Props: `strat, session, bizContext, onRunPhase9, running`

---

### Tab: Content Plan (`ContentPlanTab`)

Displays `strategy.weekly_plan` as article cards. Features:
- Week selector (all weeks from plan)
- Article cards per week with title, keyword, intent badge, page type
- **Actual dates** computed from `start_date` parameter (week 1 = start_date + 7×(week-1) days)
- **Generate Brief** button per article → calls `api.generateBrief(projectId, articleData, briefConfig)`
- Brief config per article: AI provider + custom prompt
- Brief output displayed inline as expandable panel

Props: `strat, calendarData, projectId, sessionId, startDate`

Data fetched via: `api.getCalendar(projectId, sessionId)`

---

### Tab: Link Building (`LinkBuildingTab`)

Displays internal link recommendations from Phase 7:
- Groups links by source page
- Shows anchor text, target URL, relevance score
- No action buttons (read-only)

Props: `linksData`

Data fetched via: `api.getLinks(projectId, sessionId)`

---

### Tab: Parameters (`ContentParametersTab`)

Full configuration form for Phase 9 inputs. Fields:
- **AI Provider** — radio cards (Auto / Groq / Local / Gemini / Claude) with cost estimate
- **Blogs per week** — number input (1–7)
- **Duration** — number input in weeks (1–52)
- **Content Mix** — three sliders: Informational / Transactional / Commercial (must sum ≤ 100)
- **Publishing Days** — day-of-week checkboxes (Mon–Sun)
- **Campaign Start Date** — date picker (ISO string; empty = today)
- **Strategy Focus** — free-text textarea (`extra_prompt`)
- **Generate Strategy** — large CTA button (disabled while running)
- **Live log** — scrollable console showing AI generation progress
- **Current AI Usage** — cost tracker for the session

Props: `params, setParams, onGenerate, running, hasStrategy, projectId, sessionId`

---

### Tab: Goals (`GoalsTab`)

Business goal management. Features:
- Goal form: title, description, target metric, target value, deadline
- Save / update goals via `POST /api/kw2/{pid}/goal-progress`
- Goal progress tracker
- **"From AI Business Intelligence" sidebar card**: shows goals discovered during Phase 5 crawl
  - Each discovered goal has a "Use" button that pre-fills the form
  - **"Pre-fill from BI" button** in form header — auto-fills first discovered goal
- Discovered USPs and audience segments shown as additional context

Props: `projectId, session, bizContext`

---

### Data Queries (main component, lines 3083–3180)

```js
// All fetched on mount with react-query
api.getValidated(projectId, sessionId)         → validatedData
api.getStrategy(projectId, sessionId)          → strat (cached strategy JSON)
api.getCalendar(projectId, sessionId)          → calendarData
api.getLinks(projectId, sessionId)             → linksData
api.getPillarStats(projectId, sessionId)       → pillarStats
api.getBizContextPreview(projectId, sessionId) → bizContextData
api.getSessionAiUsage(projectId, sessionId)    → aiUsage (shown in Parameters tab)
```

### Phase 9 trigger (line ~3171)

```js
const result = await api.runPhase9(projectId, sessionId, contentParams)
// contentParams = CP_DEFAULTS merged with user edits from Parameters tab
// On success: invalidate "ssp-strategy" query → triggers re-fetch → StrategyTab populates
```

---

## 9. API Endpoints

### Strategy endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/kw2/{project_id}/sessions/{session_id}/phase9` | Run Phase 9 (generate strategy) |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/strategy` | Get cached strategy JSON |

### Supporting endpoints used by the strategy page

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/validated-keywords` | All validated keywords |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/calendar` | Content calendar (Phase 8) |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/links` | Internal link recommendations (Phase 7) |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/pillar-stats` | Pillar keyword distribution |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/biz-context-preview` | Business intelligence summary |
| `GET` | `/api/kw2/{project_id}/sessions/{session_id}/ai-usage` | AI cost tracker for session |
| `POST` | `/api/kw2/{project_id}/generate-brief` | Generate article brief (from Content Plan tab) |

### Gate check (in `main.py` Phase 9 handler)

```python
session = db.get_session(session_id)
if not session.get("phase8_done"):
    raise HTTPException(400, "Phase 8 must be completed before generating strategy")
```

---

## 10. Backend Code Reference

### `engines/kw2/strategy_engine.py`

```python
class StrategyEngine:
    def __init__(self, db):
        self.db = db

    def generate(self, project_id, session_id, ai_provider=None, content_params=None) -> dict:
        # 1. Load all data from DB (see §4)
        profile       = self.db.load_business_profile(project_id)
        biz_intel     = self.db.get_biz_intel(session_id)
        biz_pages     = self.db.get_biz_pages(session_id)
        biz_competitors = self.db.get_biz_competitors(session_id)
        keywords      = self.db.load_validated_keywords(session_id)[:30]
        cluster_rows  = SELECT * FROM kw2_clusters WHERE session_id=? LIMIT 20
        calendar_rows = SELECT COUNT(*), MIN(date), MAX(date) FROM kw2_calendar WHERE session_id=?

        # 2. Render prompt
        prompt = STRATEGY_USER.format(universe=..., pillars=..., ...)

        # 3. AI call
        raw = kw2_ai_call(ai_provider, STRATEGY_SYSTEM, prompt)

        # 4. Extract JSON
        strategy = kw2_extract_json(raw)  # fallback: wrap raw text + quick_wins from keywords

        # 5. Persist
        self.db.update_session(session_id, phase9_done=1, strategy_json=json.dumps(strategy))
        return strategy

    def get_strategy(self, session_id) -> dict | None:
        # Returns strategy_json from kw2_sessions, parsed; None if not run yet
```

### `engines/kw2/prompts.py`

Contains:
- `STRATEGY_SYSTEM` — system message
- `STRATEGY_USER` — full user template (renders all data blocks listed in §6)

### `main.py` — Phase 9 endpoint (line ~21973)

```python
@app.post("/api/kw2/{project_id}/sessions/{session_id}/phase9")
async def kw2_phase9(project_id, session_id, body: _Phase9Body, db=Depends(get_db)):
    session = db.get_session(session_id)
    if not session.get("phase8_done"):
        raise HTTPException(400, "Complete Phase 8 first")
    engine = StrategyEngine(db)
    strategy = engine.generate(project_id, session_id, body.ai_provider, body.dict())
    return {"strategy": strategy, "phase9_done": True}

@app.get("/api/kw2/{project_id}/sessions/{session_id}/strategy")
async def kw2_get_strategy(project_id, session_id, db=Depends(get_db)):
    engine = StrategyEngine(db)
    strat = engine.get_strategy(session_id)
    if not strat:
        raise HTTPException(404, "Strategy not generated yet")
    return strat
```

---

## 11. Database Tables

### Core kw2 tables

| Table | Key Columns | Role in Strategy |
|---|---|---|
| `kw2_sessions` | `session_id`, `project_id`, `phase1_done`…`phase9_done`, `strategy_json` | Phase gate flags; stores final strategy JSON |
| `kw2_business_profiles` | `project_id`, `universe`, `pillars` (JSON), `audience`, `geo_scope`, `business_type` | Business identity |
| `kw2_validated_keywords` | `session_id`, `keyword`, `score`, `intent`, `pillar`, `buyer_readiness`, `search_volume`, `difficulty` | Keyword data (top 30 to AI) |
| `kw2_clusters` | `session_id`, `cluster_name`, `top_keyword`, `keyword_count` | Topic clusters (top 20 to AI) |
| `kw2_internal_links` | `session_id`, `source_page`, `target_url`, `anchor_text`, `relevance_score` | Phase 7 link map (Link Building tab) |
| `kw2_calendar` | `session_id`, `date`, `title`, `keyword`, `intent`, `pillar`, `page_type` | Phase 8 publishing calendar |
| `kw2_biz_intel` | `session_id`, `usps`, `goals`, `audience_segments`, `products_services`, `brand_voice`, `knowledge_summary`, `seo_strategy`, `website_summary` | Phase 5 business intelligence |
| `kw2_biz_pages` | `session_id`, `url`, `page_type`, `primary_topic`, `search_intent`, `keywords_extracted` | Phase 5 crawled site pages |
| `kw2_biz_competitors` | `session_id`, `domain`, `missed_opportunities`, `weaknesses`, `top_keywords` | Phase 6 competitor analysis |
| `kw2_ai_cost_log` | `session_id`, `task`, `provider`, `tokens_in`, `tokens_out`, `cost_usd` | Per-task AI cost tracking |

---

## 12. Keyword Segmentation System

The **Keywords tab** segments all validated keywords into 4 strategy-relevant buckets. Clicking a segment card filters the keyword table.

| Segment | Icon | Filter Logic | Strategic Purpose |
|---|---|---|---|
| **Money** | 💰 | `buyer_readiness >= 70` AND intent in `[transactional, commercial]` | Direct revenue drivers; prioritise for landing pages |
| **Growth** | 🌱 | `score >= 60` AND intent = `informational` (long-tail) | Content marketing engine; build topical authority |
| **Support** | 🤝 | intent = `navigational` OR low difficulty | Brand reinforcement, help centre, retention |
| **Quick Wins** | ⚡ | `score >= 70` AND `difficulty <= 30` | Low-effort, fast-ranking opportunities |

These segments map directly to strategy sections:
- Money → `pillar_strategies` + `content_priorities`
- Growth → `weekly_plan` informational articles
- Quick Wins → `quick_wins` array in strategy JSON
- Support → navigational pages, FAQ content

---

## 13. Health Score Calculation

`computeHealthScore(session, bizContext, strat, validatedData)` — returns 0–100.

Displayed as an SVG radial gauge in the Overview tab before strategy is generated.

| Dimension | Max Points | Criteria |
|---|---|---|
| Business Intelligence | 25 | Phase 5 done = 25 pts; partial data = 10–20 pts; none = 0 |
| Keywords | 30 | `>= 50` validated = 30 pts; `>= 20` = 20 pts; `>= 5` = 10 pts |
| Pillars | 20 | `>= 3` pillars in profile = 20 pts; `>= 1` = 10 pts |
| Pipeline | 15 | Phases 7+8 done = 15 pts; phase 7 only = 8 pts; neither = 0 |
| Strategy | 10 | Phase 9 done (`strat` exists) = 10 pts |

Score interpretation:
- **80–100**: Excellent — strategy will be high quality
- **60–79**: Good — most data present
- **40–59**: Fair — consider completing missing phases first
- **< 40**: Poor — significant data gaps

---

## 14. Known Issues & Pending Features

### Current limitations

| Issue | Severity | Detail |
|---|---|---|
| Strategy is read-only | High | No UI to edit pillar priorities, content mix, timelines post-generation |
| No strategy re-run with diff | Medium | Can re-run but cannot diff two versions side-by-side |
| Strategy doesn't feed back to pipeline | Medium | Strategy insights don't reorder Phase 7/8 output |
| Business Discovery Module 2 not built | Medium | Customer URL deep-analysis (from `business_intent.customer_url`) not implemented |
| P7++ 6-factor scoring not implemented | High | Using simpler scoring; full formula = BusinessFit + IntentValue + RankingFeasibility + TrafficPotential + CompetitorGap + ContentEase |
| No intent funnel mapping | Medium | TOFU/MOFU/BOFU labelling not done |
| No cannibalization detection | Medium | Keywords that would compete with existing pages not flagged |
| Confidence decay | Low | Keywords not acted on over time don't get a lower priority score |

### Planned features (from roadmap docs)

- **Strategy editing UI** — inline edit of pillar strategies, 90-day plan, content mix
- **Strategy version comparison** — diff two generated strategies
- **DAG-based phase execution** — run phases in parallel where independent (partially planned)
- **Auto-brief from clusters** — one-click brief generation for an entire cluster
- **Competitor Intelligence Module 3** — deeper competitor URL crawl + gap scoring
- **Live SERP snapshots** — re-validate keyword rankings at strategy time
- **AEO structured data generator** — auto-generate JSON-LD from strategy targets
- **Session comparison** — track keyword evolution across multiple kw2 sessions

### Architecture decisions (from `docs/DISCUSSIONS.md`)

- **D1**: Each project gets isolated kw2 sessions; no cross-project bleed
- **D5**: Phase 9 is always synchronous (no SSE streaming); returns full strategy in one response
- **D9**: AI output is always JSON-only (no markdown wrapping accepted by `kw2_extract_json`)
- **D14**: `start_date` is a frontend-only field; backend does not use it for date calculations

---

## 15. Files Reference

### Engine

| File | Purpose |
|---|---|
| `engines/kw2/strategy_engine.py` | `StrategyEngine` class — `generate()` and `get_strategy()` |
| `engines/kw2/prompts.py` | `STRATEGY_SYSTEM`, `STRATEGY_USER` prompt templates |
| `engines/kw2/db.py` | All DB helpers: `load_validated_keywords`, `get_biz_intel`, `get_biz_pages`, `get_biz_competitors`, `load_business_profile`, `update_session` |

### Backend

| File | Lines | Purpose |
|---|---|---|
| `main.py` | ~21973–22020 | Phase 9 endpoint, `_Phase9Body` model, cached retrieval endpoint |

### Frontend

| File | Lines | Purpose |
|---|---|---|
| `frontend/src/kw2/SessionStrategyPage.jsx` | ~3400 | Main strategy page (7 tabs, all components) |
| `frontend/src/kw2/api.js` | — | All kw2 API functions including `runPhase9`, `getStrategy`, `getBizContextPreview`, `getPillarStats`, `getValidated`, `getCalendar`, `getLinks` |

### Documentation

| File | Purpose |
|---|---|
| `docs/STRATEGY_README.md` | This file — complete current reference |
| `docs/STRATEGY_AUDIT_2026-03-30.md` | Audit of data flow gaps and scoring issues |
| `docs/strategy_dashboard_ui.md` | AEO UI design spec |
| `docs/strategy_intelliegence.md` | Module 1/2/3 intelligence architecture |
| `docs/DISCUSSIONS.md` | Architecture decisions D1–D16 |
| `docs/DEVELOPMENT_PLAN.md` | Week-by-week development plan |
| `docs/IMPLEMENTATION_PLAN.md` | Block A (pipeline quality), Block B (visibility), Block C (strategy UI) |
| `docs/RANKING_INTELLIGENCE.md` | P7++ scoring formula details |
| `keywordupgrade.md` | Money/Growth/Support/QuickWins segmentation design |
| `STRATEGY_JOB_BUG_ANALYSIS.md` | Job stuck detection and queue analysis |

### Deprecated (do not use)

| File | Why deprecated |
|---|---|
| `docs/STRATEGY_ENGINE.md` | Old Step 4 / `ki` pipeline — replaced by kw2 Phase 9 |
| `frontend/src/workflow/Step4Strategy.jsx` | Old workflow UI — replaced by `SessionStrategyPage.jsx` |
| `engines/ruflo_strategy_engine.py` | Standalone `StrategyDevelopmentEngine` — not in kw2 flow |
| `engines/ruflo_final_strategy_engine.py` | Standalone `FinalStrategyEngine` — not in kw2 flow |
