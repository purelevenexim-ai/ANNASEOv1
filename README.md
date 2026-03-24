# AnnaSEO v1

> AI-Powered Keyword & Content Operating System  
> Rank #1 on Google AND AI search (Perplexity, ChatGPT, Gemini)

---

## Quick start (April 1, 2026)

```bash
# 1. Clone
git clone https://github.com/purelevenexim-ai/ANNASEOv1
cd ANNASEOv1

# 2. Install Python deps
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 3. Install Ollama + DeepSeek
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull deepseek-r1:7b

# 4. Configure
cp .env.example .env
# Edit .env with your API keys

# 5. Database
python annaseo_wiring.py write-migrations .
alembic upgrade head

# 6. Start backend
uvicorn main:app --port 8000 --reload

# 7. Start frontend
cd frontend && npm install && npm run dev

# 8. Verify
curl http://localhost:8000/api/health
```

Open http://localhost:5173 → register → create first project → run keyword universe.

---

## Folder structure

```
ANNASEOv1/
│
├── main.py                        ← FastAPI entry (port 8000), JWT, SSE, routing
├── annaseo_wiring.py             ← GSC OAuth, Alembic migrations, Ruflo jobs
├── annaseo_product_growth.py     ← Team, webhooks, PDF reports, GA4, bulk import
├── CLAUDE.md                     ← Instructions for Claude Code (auto-read)
├── requirements.txt
├── .env.example
│
├── engines/                      ← Core processing engines
│   ├── ruflo_20phase_engine.py   ← Keyword universe P1–P20
│   ├── ruflo_content_engine.py   ← 7-pass content generation
│   ├── ruflo_strategy_dev_engine.py
│   ├── ruflo_final_strategy_engine.py
│   ├── ruflo_confirmation_pipeline.py ← 5-gate user approval
│   ├── ruflo_seo_audit.py        ← 14 checks + INP + AI bots
│   ├── ruflo_publisher.py        ← WordPress + Shopify
│   ├── annaseo_competitor_gap.py
│   ├── annaseo_content_refresh.py
│   ├── annaseo_ai_citation_monitor.py
│   ├── annaseo_intelligence_engines.py ← Multilingual, voice, prediction, seasonal
│   └── annaseo_advanced_engines.py     ← Entity, local SEO, algo updates
│
├── modules/                      ← Shared addon modules
│   ├── annaseo_addons.py         ← OffTopicFilter, HDBSCAN, lifecycle
│   └── annaseo_doc2_addons.py    ← Memory, PromptVersioning, ClusterType
│
├── quality/                      ← Quality intelligence system
│   ├── annaseo_qi_engine.py      ← Master quality intelligence + tuning
│   ├── annaseo_domain_context.py ← Per-project domain classification ⭐
│   ├── annaseo_quality_engine.py
│   ├── annaseo_data_store.py
│   └── annaseo_lineage_engine.py
│
├── rsd/                          ← Research & Self Development
│   ├── annaseo_rsd_engine.py     ← Code quality monitoring
│   └── annaseo_self_dev.py       ← Intelligence crawling
│
├── frontend/                     ← React 18 + Vite frontend
│   ├── src/
│   │   ├── App.jsx               ← All 8 pages
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── alembic/                      ← Database migrations
│   └── versions/
│
├── docs/                         ← Full documentation
│   ├── ENGINES.md                ← Every engine, inputs, outputs, failure modes
│   ├── API.md                    ← All API endpoints
│   ├── DATA_MODELS.md            ← All 35+ database tables
│   ├── DOMAIN_CONTEXT.md         ← Cross-domain vocabulary system
│   ├── DEVELOPMENT_PLAN.md       ← Week-by-week build checklist
│   ├── DISCUSSIONS.md            ← All design decisions and why
│   └── RSD.md                    ← Global vs project RSD scope
│
├── scripts/                      ← Utility scripts
└── tests/                        ← Test suite
```

---

## Keyword universe — 4-level hierarchy

AnnaSEO builds a 4-level keyword tree per project:

```
Universe  (customer input — e.g. "black pepper")
  └── Pillar  (competitor-traffic-driven — top pages on competitor sites)
        └── Cluster  (semantic group — HDBSCAN/embedding-based)
              └── Supporting keywords  (long-tail, language/region/religion variants)
```

**Key rule:** Pillars are NOT customer inputs. They are discovered from competitor SERP traffic.
A Universe is what the customer types. A Pillar is what ranks for competitors.

### Ruflo v3 keyword system

`engines/ruflo_v3_keyword_system.py` — `RufloV3KeywordSystem`

| Method | What it does |
|--------|-------------|
| `run_universe(seed)` | Full 20-phase pipeline for one seed |
| `run_all_universes(seeds)` | Parallel universe generation for all seeds |
| `get_universe_tree(project_id)` | Return JSON tree: Universe→Pillar→Cluster→Keywords |

### Keyword mix strategy (50/30/15/5)

| Bucket | KD range | Share | Goal |
|--------|----------|-------|------|
| Easy wins | KD < 10 | 50% | Quick rankings in 60–90 days |
| Medium | KD 10–30 | 30% | 6-month targets |
| Hard | KD 30–60 | 15% | Authority building |
| Authority | KD > 60 | 5% | Brand credibility |

### 8 long-tail generation methods

1. Question variants (who/what/where/why/how/when)
2. Modifier chains (best/cheap/organic/wholesale/near me)
3. Language variants (English → Malayalam/Hindi/Tamil)
4. Region variants (India → Kerala → Wayanad)
5. Religion-context variants (Ayurveda/Halal/Unani)
6. Comparison terms (vs/alternative/compare)
7. Intent variants (buy/review/guide/recipe)
8. Seasonal variants (Onam/Christmas/Ramadan)

---

## The domain isolation system ⭐

AnnaSEO is used by businesses in different industries. The same keyword means different things:

| Keyword | Spice project | Tourism project |
|---------|--------------|----------------|
| `cinnamon tour` | ❌ REJECT | ✅ ACCEPT |
| `ceylon cinnamon` | ✅ ACCEPT | ✅ ACCEPT |
| `buy cinnamon per kg` | ✅ ACCEPT | ❌ REJECT |
| `meme` | ❌ REJECT | ❌ REJECT |

**Rule:** Cross-domain words → `ProjectDomainProfile.reject_overrides` (isolated)  
**Rule:** Universal noise → `OffTopicFilter.GLOBAL_KILL` (all projects)  
Engine: `quality/annaseo_domain_context.py` → `DomainContextEngine.classify(keyword, project_id)`

---

## AI model routing (cost = ~$0.022/article)

| Task | Model | Cost |
|------|-------|------|
| Code writing, fixes | DeepSeek local (Ollama) | $0 |
| Analysis, scoring, specs | Gemini 1.5 Flash free tier | $0 |
| Test generation | Groq Llama free tier | $0 |
| Blog writing | Claude Sonnet | ~$0.022 |
| Final verification | Claude Sonnet | per-call |

---

## API ports

| Port | Service |
|------|---------|
| 8000 | Main FastAPI (main.py) |
| 5173 | React frontend |
| 11434 | Ollama |

---

## Documentation

| Doc | Contents |
|-----|---------|
| `docs/ENGINES.md` | Every engine with inputs, outputs, failure modes |
| `docs/API.md` | All REST API endpoints |
| `docs/DATA_MODELS.md` | All 35+ database tables |
| `docs/DOMAIN_CONTEXT.md` | Cross-domain vocabulary and project isolation |
| `docs/DEVELOPMENT_PLAN.md` | Week-by-week build checklist |
| `docs/DISCUSSIONS.md` | 20 design decisions and reasoning |

---

## Working with Claude Code

This repo includes `CLAUDE.md` at the root — Claude Code reads it automatically.  
Open the repo in Claude Code and it immediately understands the architecture.

```bash
# Open with Claude Code
cd ANNASEOv1
claude
```
