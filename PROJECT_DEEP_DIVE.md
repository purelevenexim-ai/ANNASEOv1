# AnnaSEO v1 — Complete Project Deep Dive

**Last Updated:** 2026-03-30
**Status:** Active Development (April 1 Release Target)

---

## 🎯 Executive Summary

**AnnaSEO v1** is an **AI-powered SEO and content operating system** that generates keyword universes and publishes articles to rank #1 on Google AND AI search engines (Perplexity, ChatGPT, Gemini).

### Core Problem Solved
- Traditional SEO tools give you keywords; AnnaSEO builds the entire ecosystem around them
- Single seed keyword → 40 clusters → 400 topics → 2,000+ blogs over 2 years
- Domain-aware classification: "cinnamon tour" is BAD for spice sellers, GOOD for travel agencies
- Multi-language, multi-region, religion-aware content generation

### Technology Stack
- **Backend:** FastAPI (main.py, 7204 lines) + SQLite (dev) / PostgreSQL (prod)
- **Engines:** 21 Python files (ruflo_* + annaseo_*)
- **Frontend:** React 18 + Vite + Zustand + React Query + TailwindCSS
- **AI Models:**
  - DeepSeek 7B (Ollama local, free) for code/fixes
  - Gemini 1.5 Flash (free tier) for analysis/scoring
  - Groq Llama (free tier) for test generation
  - Claude Sonnet ($0.022/article) for final verification

---

## 📊 Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (React 18 + Vite, port 5173)                            │
│  - Dashboard, Keywords, Strategy, Blogs, Rankings, Graph         │
└─────────────┬──────────────────────────────────────────────────────┘
              │ REST API + Server-Sent Events (SSE)
┌─────────────▼──────────────────────────────────────────────────────┐
│  FastAPI Backend (main.py, port 8000)                             │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ Routes: /api/run | /api/strategy | /api/blogs | /api/graph│   │
│  │ Auth: JWT + user_projects table + role-based access       │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │ CORE ENGINES                                              │     │
│  │ ├── RufloOrchestrator (20-phase pipeline)                │     │
│  │ ├── DomainContextEngine (per-project classification)     │     │
│  │ ├── ContentGenerationEngine (7-pass blog writing)        │     │
│  │ ├── StrategyDevEngine (audience×location×religion)       │     │
│  │ ├── RankingMonitor (diagnosis + alerts)                  │     │
│  │ ├── SEOAuditEngine (14 checks + INP + AI bots)           │     │
│  │ └── Publisher (WordPress + Shopify)                      │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │ SUPPORTING SYSTEMS                                        │     │
│  │ ├── JobQueue (Ruflo job scheduler)                        │     │
│  │ ├── QIEngine (quality intelligence + tuning)              │     │
│  │ ├── RSD Engine (code health monitoring)                   │     │
│  │ ├── GCS Analytics Pipeline (ranking import)               │     │
│  │ └── Memory & Experiment Engine (self-improving)           │     │
│  └──────────────────────────────────────────────────────────┘     │
└────────────────┬─────────────────────────────────────────────────┘
                 │
        ┌────────▼─────────┐
        │  SQLite DB       │
        │  45+ tables      │
        │  annaseo.db      │
        └──────────────────┘
```

---

## 🔄 The 20-Phase Keyword Universe Pipeline

Every seed keyword goes through **20 phases** to build a complete keyword ecosystem:

### Phase Breakdown

| Phase | Name | What It Does | Input | Output |
|-------|------|-------------|-------|--------|
| **P1** | Seed Input | Normalize the seed keyword | "cinnamon" | Seed object |
| **P2** | Keyword Expansion | Find related keywords from 5 sources | Seed | ~1,000 raw keywords |
| **P3** | Normalization | Clean & dedupe keywords | Raw keywords | ~300 clean keywords |
| **P4** | Entity Detection | Extract named entities (spaCy) | Keywords | Entity map |
| **P5** | Intent Classification | Classify keyword intent (buy/learn/review/navigate) | Keywords + entities | Intent map |
| **P6** | SERP Intelligence | Fetch Google top 10 for each keyword | Keywords | SERP results + KD scores |
| **P6.6** | Competitor Mining | Extract keywords from competitor pages | SERP results | Extra keywords |
| **P7** | Opportunity Scoring | Score by volume × KD × intent relevance | All data so far | Score map (0-100) |
| **P7B** | Top Keyword Selector | Select top 100 with intent diversity | Scores + intent | top100_keywords[] |
| **P8** | Topic Detection | SBERT + HDBSCAN clustering | Keywords + scores | Topic assignments |
| **P9** | Cluster Formation | Group topics into semantic clusters | Topics | 40 clusters |
| **P10** | Pillar Identification | Identify pillar pages (main content hubs) | Clusters | Pillar map |
| **P11** | Knowledge Graph | Build semantic relationships | Pillars + intent + SERP | Knowledge graph object |
| **P12** | Internal Linking | Map cross-links between articles | Knowledge graph | Link map |
| **P13** | Content Calendar | Schedule 2,000+ articles over 2 years | Pillars + pace | Calendar[] |
| **P14** | Dedup Prevention | Remove duplicates of existing articles | Calendar | Final calendar |
| **P15** | Content Brief | Generate briefs for each article | Calendar | Brief objects |
| **P16** | Claude Generation | Write full articles | Briefs | Article objects |
| **P17** | SEO Optimization | Optimize titles, meta, readability | Articles | Optimized articles |
| **P18** | Schema & Metadata | Add JSON-LD schema + meta tags | Articles | Final articles |
| **P19** | Publishing | Push to WordPress/Shopify (if enabled) | Articles | Published URLs |
| **P20** | Ranking Feedback | Monitor rankings, feed back to tune engine | Published articles + GSC | Tuning signals |

### Key Architectural Features

**THREE-TIER CACHING**
- **L1:** In-memory LRU (hot keywords, fast lookups)
- **L2:** SQLite disk cache (SERP: 14d TTL, suggestions: 7d)
- **L3:** File checkpoints (.json.gz per phase, resume after crash)

**MEMORY MANAGEMENT**
- Each phase has a budget (P4 Entity: 150MB, P8 Clustering: 380MB)
- Heavy phases (P4, P8) never run simultaneously
- Large datasets stream in 500-item chunks

**CHECKPOINT RESUME**
- After each phase, checkpoint saved to disk
- If crash occurs, resume from last checkpoint (no re-work)

**CONFIGURABLE PACE**
```python
ContentPace(
    duration_years=2,
    blogs_per_day=3,
    parallel_claude_calls=5,
    per_pillar_overrides={...},
    seasonal_priorities={...}
)
```

---

## 🎓 Domain Isolation System (⭐ Most Important)

### The Problem
The same keyword means different things in different industries:

```
Keyword: "cinnamon tour"
├── Spice Project (FOOD_SPICES)
│   └── REJECT (tourism is off-topic)
├── Travel Project (TOURISM)
│   └── ACCEPT (cinnamon is a Kerala tourism attraction)
└── E-commerce Project (ECOMMERCE)
    └── REJECT (product sales, not tours)
```

### The Solution
**File:** `quality/annaseo_domain_context.py`

```python
class DomainContextEngine:
    def classify(keyword: str, project_id: str) -> (ACCEPT/REJECT, reason)
    def cross_domain_check(keyword, project_id) -> bool
    def score_for_domain(keyword, project_id) -> 0-100
```

### Two-Level Tuning
1. **GLOBAL Tuning** (touches engine code, thresholds)
   - Core quality rules
   - Algorithm bugs
   - Engine health thresholds
   - Applied to ALL projects

2. **PROJECT Tuning** (per-project config)
   - Kill words (`ProjectDomainProfile.reject_overrides`)
   - Accept overrides
   - Prompt adjustments
   - Domain-specific scoring rules
   - Only affects THIS project

### Key Rule ⚠️
- **NEVER** add cross-domain words to `OffTopicFilter.GLOBAL_KILL`
- Cross-domain words go in `ProjectDomainProfile.reject_overrides` (isolated per project)
- Universal noise (meme, viral, tiktok) → `GLOBAL_KILL` (all projects)

---

## 💾 Database Schema (45+ Tables)

### Core Tables

**users** — User accounts
- `user_id`, `email`, `name`, `role` (user/admin), `pw_hash`

**projects** — Client projects
- `project_id`, `name`, `industry`, `description`, `seed_keywords[]`
- `wp_url`, `wp_user`, `wp_pass_enc` (WordPress credentials)
- `shopify_store`, `shopify_token_enc` (Shopify credentials)
- `language`, `region`, `religion` (content targeting)
- `target_languages[]`, `target_locations[]`, `business_type`, `usp`
- `audience_personas[]`, `competitor_urls[]`, `customer_reviews`

**runs** — Pipeline executions
- `run_id`, `project_id`, `seed`, `status`, `current_phase`
- `pillars_json[]`, `keywords_json[]`, `blog_suggestions_json[]`
- `current_gate`, `gate_1_confirmed` through `gate_5_confirmed`
- `result{}` (final output), `error`, `cost_usd`

**content_blogs** — Blog articles (freeze system)
- `blog_id`, `project_id`, `keyword`, `title`, `body`, `meta_desc`
- `status` (draft/approved/frozen/published)
- `frozen_at`, `scheduled_date`, `published_url`
- `seo_score`, `eeat_score`, `word_count`, `version`
- `internal_links[]`, `schema_json`

**content_freeze_queue** — Publication schedule
- `blog_id`, `project_id`, `scheduled_date`, `published`
- Publishing happens: draft → approved → frozen → queue → published

**rankings** — Keyword positions
- `project_id`, `keyword`, `position`, `ctr`, `impressions`, `clicks`

**ranking_alerts** — Position changes
- `project_id`, `keyword`, `old_position`, `new_position`, `change`
- `severity` (warning/critical), `status` (new/acknowledged/resolved)
- `diagnosis_json` (AI diagnosis of why rank changed)

**strategy_sessions** — Strategy development
- `session_id`, `project_id`, `engine_type`, `status`
- `input_json`, `result_json`, `confidence`

**strategy_jobs** — Long-running strategy jobs
- `job_id`, `project_id`, `status`, `progress`, `current_step`
- `input_payload`, `result_payload`, `raw_llm_response`
- `control_state` (running/paused/cancelled), `cancel_requested`
- `lock_key`, `is_locked`, `last_heartbeat`

**audience_profiles** — Per-project audience data
- `project_id`, `website_url`, `target_locations[]`, `target_languages[]`
- `personas[]`, `business_type`, `usp`, `products[]`
- `customer_reviews`, `ad_copy`, `seasonal_events[]`
- `pillar_support_map{}` (which pillars support which personas)

**serp_cache** — Google SERP cache
- `keyword`, `location`, `device`, `results`, `fetched_at`
- `provider` (SerpAPI/Playwright), `cost`
- TTL: 14 days (auto-invalidate)

**ai_usage** — Cost tracking
- `project_id`, `run_id`, `model`, `input_tokens`, `output_tokens`
- `cost_usd`, `purpose` (keyword_expansion/content_generation/etc.)

---

## 🚀 API Endpoints (FastAPI)

### Authentication
```
POST   /api/register          — Register user
POST   /api/login             — Login (returns JWT)
POST   /api/logout            — Logout
GET    /api/me                — Get current user
```

### Projects
```
GET    /api/projects          — List user's projects
POST   /api/projects          — Create project
GET    /api/projects/{id}     — Get project details
PUT    /api/projects/{id}     — Update project
DELETE /api/projects/{id}     — Delete project
```

### Keywords & Runs
```
POST   /api/run               — Start keyword universe pipeline
GET    /api/runs/{run_id}     — Get run status + result
GET    /api/runs              — List runs for project
```

### Strategy
```
POST   /api/strategy/develop  — Run strategy development engine
POST   /api/strategy/final    — Run final strategy engine
GET    /api/strategy/jobs/{id}— Get job status
POST   /api/strategy/pause    — Pause job
POST   /api/strategy/resume   — Resume job
POST   /api/strategy/cancel   — Cancel job
```

### Content
```
GET    /api/blogs             — List blog articles
POST   /api/blogs             — Create blog
PUT    /api/blogs/{id}        — Update blog
DELETE /api/blogs/{id}        — Delete blog
POST   /api/blogs/{id}/approve— Approve for publishing
POST   /api/blogs/{id}/freeze — Freeze article
```

### Rankings
```
GET    /api/rankings          — Get current rankings
GET    /api/ranking-history   — Get ranking history
GET    /api/ranking-alerts    — Get position drop alerts
POST   /api/rankings/import   — Import from Google Search Console
POST   /api/rankings/diagnose — Diagnose position drop
```

### Graph & Visualization
```
GET    /api/graph             — Get knowledge graph (D3 format)
GET    /api/tree              — Get keyword tree (hierarchical)
```

### SEO & Publishing
```
POST   /api/audit             — Run full SEO audit
POST   /api/publish           — Publish to WordPress/Shopify
GET    /api/seo-audit/{id}    — Get audit result
```

### Analytics & GSC
```
POST   /api/gsc/import        — Sync Google Search Console data
POST   /api/ga4/import        — Sync Google Analytics 4 data
GET    /api/analytics         — Get analytics dashboard
```

---

## 🎨 Frontend Structure (React 18 + Vite)

### Main Components

**App.jsx** (Main shell)
- Global store (Zustand): user, token, project, page
- API client wrapper
- Design tokens (colors, spacing)
- Routing logic

**KeywordInput.jsx** (Page 1: Keyword Universe)
- Seed keyword input
- 5 confirmation gates
- Live progress (P1-P20 status)
- Results visualization (tree, cluster count, pillar count)

**StrategyPage.jsx** (Page 2: Strategy Development)
- **Tab 1:** Audience Setup
  - Personas, locations, languages
  - Business type + USP
  - Customer reviews
- **Tab 2:** Run Strategy
  - Select audience variants
  - Launch StrategyDevEngine
  - Monitor progress
- **Tab 3:** Results
  - Generated strategies
  - ROI predictions
- **Tab 4:** Priority Queue
  - Articles scheduled for publishing

**Dashboard (implied in App)**
- Project list
- Quick stats (keywords, articles, rankings)
- Recent runs

**KeywordWorkflow.jsx**
- Visual workflow: P1 → P2 → ... → P20
- Gate confirmations
- Result summaries

### Key UI Patterns
1. **Real-time progress:** SSE streaming from backend
2. **Confirmation gates:** Customer approves at key milestones
3. **Modal dialogs:** For confirmations + detailed views
4. **D3.js visualization:** Keyword tree, knowledge graph
5. **Chart.js:** Ranking trends over time

---

## 🔑 Key Non-Negotiable Rules

### 1. Domain Isolation
- Cross-domain words are per-project (`reject_overrides`)
- Universal noise is global (`GLOBAL_KILL`)
- "cinnamon tour" ≠ bad everywhere

### 2. AI Model Routing
- **Free tools for work:**
  - DeepSeek (Ollama) → code writing + fixes
  - Gemini Flash → analysis + scoring
  - Groq Llama → test generation
- **Claude Sonnet for verification ONLY** (never code writing)
- Cost: ~$0.022/article

### 3. Manual Approval Gate
- All tunings → `qi_tunings` table with `status='pending'`
- All RSD fixes → `rsd_approval_requests` with `status='pending'`
- Nothing auto-applies to production
- Rollback snapshot saved before every change

### 4. INP Not FID
- FID was removed March 2024
- Always check INP in SEO audits
- File: `ruflo_seo_audit.py`

### 5. No Deprecated Schema
- HowTo schema: deprecated Sept 2023
- FAQPage schema: healthcare/gov only since Aug 2023
- JSON-LD only (never Microdata)

---

## 🏗️ Key Files & Folders

### Engines (21 Python files)
```
engines/
├── ruflo_20phase_engine.py           (P1-P20 orchestration, 3,600+ lines)
├── ruflo_20phase_wired.py            (WiredRufloOrchestrator wrapper)
├── ruflo_v3_keyword_system.py        (Keyword universe logic)
├── ruflo_supporting_keyword_engine.py
├── ruflo_content_engine.py           (7-pass blog writing)
├── ruflo_strategy_dev_engine.py      (Audience × location × religion)
├── ruflo_final_strategy_engine.py    (Claude CoT strategies)
├── ruflo_confirmation_pipeline.py    (5-gate approval system)
├── ruflo_seo_audit.py                (14-point SEO checks)
├── ruflo_publisher.py                (WordPress + Shopify)
├── annaseo_p2_enhanced.py            (P2 keyword expansion)
├── annaseo_competitor_gap.py
├── annaseo_content_refresh.py
├── annaseo_ai_citation_monitor.py
├── annaseo_intelligence_engines.py   (Multilingual, voice, prediction)
├── annaseo_advanced_engines.py       (Entity, local SEO, algo updates)
├── annaseo_ai_brain.py
├── annaseo_keyword_input.py
├── annaseo_keyword_scorer.py
├── seo_keyword_pipeline.py
└── serp.py
```

### Quality & Intelligence
```
quality/
├── annaseo_domain_context.py         (Per-project classification ⭐)
├── annaseo_qi_engine.py              (Quality scoring + tuning)
├── annaseo_quality_engine.py
├── annaseo_data_store.py
└── annaseo_lineage_engine.py         (Content lineage tracking)
```

### Services & Supporting
```
services/
├── job_tracker.py                    (Run tracking)
├── ranking_monitor.py                (Position alerts + diagnosis)
├── rank_predictor.py
├── quota.py                          (API quota management)
├── llm_audit.py                      (LLM validation)
├── serp_intelligence/
└── internal_linking/
```

### Core Infrastructure
```
core/
├── gsc_analytics_pipeline.py         (Google Search Console + GA4)
├── memory_engine.py                  (Pattern memory)
├── global_memory_engine.py
├── meta_learning.py                  (Self-improvement)
├── experiment.py                     (A/B testing)
├── metrics.py                        (Prometheus metrics)
├── logging.py
├── otel.py                           (OpenTelemetry)
└── trace.py                          (Distributed tracing)
```

### Job Queue & Workers
```
jobqueue/
├── connection.py                     (Redis job queues)
├── jobs.py                           (Background job runners)
└── ...
```

### Database & Models
```
models/
└── error_log.py

alembic/
└── versions/                         (Migration history)
```

### Frontend (React)
```
frontend/
├── src/
│   ├── App.jsx                       (Main shell + routing)
│   ├── KeywordInput.jsx              (Keyword universe flow)
│   ├── StrategyPage.jsx              (Strategy development)
│   ├── KeywordWorkflow.jsx           (Visual workflow)
│   ├── components/                   (Gate confirmations, notifications)
│   ├── utils/
│   ├── store/
│   └── main.jsx
├── index.html
├── package.json
└── vite.config.js
```

---

## 📈 Data Flow Example: Seed "Cinnamon"

```
1. User enters "cinnamon" → KeywordInput.jsx
   ├─ Frontend validates
   └─ POST /api/run with { seed: "cinnamon", pace, project_id }

2. Backend starts WiredRufloOrchestrator.run_seed()
   ├─ RawCollector (wired) collects metrics
   ├─ DomainContextEngine (wired) validates per-project
   └─ MetricsCollector (wired) tracks costs

3. P1-P20 pipeline executes:
   ├─ P1:   Seed object created
   ├─ P2:   5 sources → ~1,000 keywords
   ├─ P3:   Clean → ~300 keywords
   ├─ GATE A: User confirms universe
   ├─ P4-P8: Heavy analysis (entities, intent, SERP, clustering)
   ├─ GATE B: User confirms pillars
   ├─ P9-P12: Clusters → pillars → knowledge graph → internal links
   ├─ P13: Content calendar (2,000+ articles over 2 years)
   ├─ GATE C: User confirms pace
   ├─ P14: Dedup check
   ├─ P15-P19: (Optional) Generate + publish articles
   └─ P20: Monitor rankings, collect feedback

4. Result object returned:
   {
     "seed": {...},
     "keyword_count": 312,
     "top100_keywords": [...],
     "cluster_count": 42,
     "pillar_count": 12,
     "calendar_count": 2400,
     "cost_preview": {...},
     "_graph": {...},
     "_calendar": [...]
   }

5. Frontend displays:
   ├─ Progress bars (P1, P2, ... P20)
   ├─ Results summary
   ├─ Knowledge graph visualization (D3)
   ├─ Content calendar (table)
   └─ Links to individual articles

6. User clicks "Approve & Publish"
   ├─ Articles submitted to Ruflo job queue
   ├─ Background workers generate + publish
   ├─ WordPress/Shopify credentials used
   └─ Published URLs stored in content_blogs table

7. RankingMonitor periodically:
   ├─ Imports Google Search Console data
   ├─ Tracks position changes
   ├─ Generates alerts for drops > threshold
   └─ Feeds ranking signals back to RSD tuning engine
```

---

## 🎯 Development Roadmap (8 Weeks)

**Week 1 (Apr 1-7):** Foundation
- Run migrations, verify health endpoint
- Test database schema

**Week 2 (Apr 8-14):** Wire RawCollector + DomainContextEngine
- Integrate metric collection
- Per-project classification working

**Week 3 (Apr 15-21):** Wire content pipeline
- Test 7-pass generation
- Verify article output quality

**Week 4 (Apr 22-28):** Quality feedback loop
- QIEngine integrated end-to-end
- Tuning captures + approval gates working

**Week 5 (Apr 29-May 5):** GSC + Rankings
- Connect Google Search Console OAuth
- Verify rankings import

**Week 6 (May 6-12):** RSD health monitoring
- Code quality monitoring active
- Self-improvement loops running

**Week 7 (May 13-19):** Frontend polish
- Replace mock data with real API calls
- Full integration testing

**Week 8 (May 20-26):** Launch
- Performance testing
- Security audit
- Production deployment

---

## 🔍 How to Navigate the Codebase

### "I want to understand keyword expansion (P2)"
→ Read: `engines/ruflo_20phase_engine.py:P2_KeywordExpansion`

### "I want to add a new domain industry"
→ Edit: `quality/annaseo_domain_context.py:CROSS_DOMAIN_VOCABULARY`

### "I want to understand content generation"
→ Read: `engines/ruflo_content_engine.py:ContentGenerationEngine`

### "I want to add a new API endpoint"
→ Edit: `main.py` + add route + add corresponding component to frontend

### "I want to understand strategy development"
→ Read: `engines/ruflo_strategy_dev_engine.py:StrategyDevelopmentEngine`

### "I want to monitor rankings"
→ Read: `services/ranking_monitor.py` + `quality/annaseo_qi_engine.py`

### "I want to add a new database table"
→ Add to `get_db()` schema script in `main.py:301-348` (both CREATE and migration)

---

## 📝 Database Initialization

```bash
# 1. Ensure .env is configured
cp .env.example .env
# Edit .env with API keys

# 2. Initialize database
python annaseo_wiring.py write-migrations .
alembic upgrade head

# 3. Verify
python -c "import main; db = main.get_db(); print(db.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())"
```

---

## ⚡ Running the Project

```bash
# Terminal 1: Backend
uvicorn main:app --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm install
npm run dev

# Terminal 3: Job Queue (if using Ruflo jobs)
python -m jobqueue.worker

# Access: http://localhost:5173
```

---

## 🚨 Critical Concepts to Internalize

1. **Domain Isolation is CORE:** Same keyword ≠ same verdict for all projects
2. **20 Phases are Sequential:** P1→P20, with gates + checkpoints
3. **Caching is 3-Tier:** L1 (memory), L2 (SQLite), L3 (files)
4. **Heavy Phases are Sequenced:** P4 + P8 never run simultaneously
5. **Claude is Expensive:** ~$0.022/article; use DeepSeek for code
6. **Approval Gates Everywhere:** No changes to production without human OK
7. **Knowledge Graph is Central:** Drives internal linking + content calendar
8. **Pace Controls Everything:** blogs_per_day, duration_years, parallel calls

---

## 📞 Key Functions to Know

### RufloOrchestrator (Main Engine)
```python
ruflo = RufloOrchestrator()
result = ruflo.run_seed(
    keyword="cinnamon",
    pace=ContentPace(duration_years=2, blogs_per_day=3),
    project_id="proj_123",
    generate_articles=False
)
```

### DomainContextEngine (Classification)
```python
engine = DomainContextEngine()
verdict = engine.classify("cinnamon tour", project_id="proj_123")
# returns: (ACCEPT/REJECT, reason)
```

### ContentGenerationEngine (Blog Writing)
```python
content_engine = ContentGenerationEngine()
article = content_engine.generate(brief, project_id, language="english")
# returns: article object with title, body, meta, schema
```

### RankingMonitor (Diagnostics)
```python
monitor = RankingMonitor()
diagnosis = monitor.diagnose_drop(
    project_id="proj_123",
    keyword="cinnamon",
    old_position=3,
    new_position=8
)
# returns: AI diagnosis of why rank dropped
```

---

## 🎓 Code Quality Rules

1. **Never hardcode API keys** → Use .env
2. **Never truncate errors** → Log full stack trace
3. **Always handle None** → Check for null results from phases
4. **Cache aggressive** → Avoid re-work with checkpoint system
5. **Memory aware** → Check MemoryManager budget before heavy work
6. **Test early** → Use pytest; test_*.py files in pytests/
7. **Document decisions** → Comments for non-obvious logic
8. **Type hints** → Use typing.Dict, List, Optional, etc.

---

## 📚 Full Documentation

| Doc | Contents |
|-----|----------|
| `docs/ENGINES.md` | Every engine, inputs, outputs, failure modes |
| `docs/API.md` | All REST endpoints |
| `docs/DATA_MODELS.md` | All 45+ database tables |
| `docs/DOMAIN_CONTEXT.md` | Cross-domain vocabulary system |
| `docs/DEVELOPMENT_PLAN.md` | Week-by-week build checklist |
| `docs/DISCUSSIONS.md` | 20 design decisions + reasoning |
| `docs/STRATEGY_ENGINE.md` | Strategy engines + cost estimates |
| `docs/RANKING_INTELLIGENCE.md` | Ranking monitor + diagnosis flow |
| `docs/CONTENT_FREEZE.md` | Blog lifecycle: draft → publish |
| `CLAUDE.md` | Instructions for Claude Code |
| `README.md` | Quick start guide |

---

## 🎉 Summary

**AnnaSEO v1** is a sophisticated, multi-layered SEO + content operating system with:
- **20-phase keyword pipeline** for complete keyword ecosystems
- **Domain-aware classification** for multi-industry projects
- **Knowledge graph core** driving internal linking + content calendars
- **7-pass content generation** for high-quality blogs
- **Self-improving feedback loops** via RSD + QI engines
- **Production-grade architecture** with checkpoint resume + memory management
- **Full audit trail** via approval gates + tuning registries

The codebase is well-structured, documented, and ready for active development toward the April 1 release.

