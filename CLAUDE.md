# AnnaSEO — Instructions for Claude Code

## What this project is
AI-powered SEO and content operating system. Keyword universe generation (20 phases),
7-pass content writing, quality intelligence, per-project domain classification,
self-improving algorithm tuning. Target: rank #1 on Google AND AI search.

## Architecture
- Backend: FastAPI (main.py, port 8000) + SQLite (dev) / PostgreSQL (prod)
- Engines: 21 Python files organised under engines/, quality/, rsd/, modules/
- Frontend: React 18 + Vite (frontend/, port 5173)
- Orchestrator: Ruflo (job queue for background tasks)

## Non-negotiable rules

### 1. Domain isolation — the most important architectural rule
"cinnamon tour" is BAD for a spice project, GOOD for a tourism project.
- NEVER add cross-domain words to OffTopicFilter.GLOBAL_KILL
- Cross-domain words go into ProjectDomainProfile.reject_overrides (per project)
- Universal noise (meme, viral, tiktok) → GLOBAL_KILL
- The engine handling this: annaseo_domain_context.py → DomainContextEngine.classify()

### 2. AI model routing — free tools for work, Claude for verification only
- DeepSeek (Ollama local, free) → all code writing and fixes
- Gemini 1.5 Flash (free tier) → analysis, scoring, specifications
- Groq Llama (free tier) → test generation
- Claude Sonnet → final verification gate ONLY, never writes code
- Cost: Claude ~$0.022/article, everything else $0

### 3. Manual approval gate — no code change reaches production without human approval
- All engine tunings go to qi_tunings table with status='pending'
- All RSD code fixes go to rsd_approval_requests with status='pending'
- Nothing auto-applies to production
- Rollback snapshot saved before every change

### 4. INP not FID
FID was removed from Core Web Vitals in March 2024. Always check INP.
File: ruflo_seo_audit.py

### 5. No deprecated schema
HowTo schema: deprecated Sept 2023, never generate it.
FAQPage schema: restricted to healthcare/gov only since Aug 2023.
JSON-LD only, never Microdata.
File: ruflo_content_engine.py SchemaGenerator

## Wiring status — DONE
RawCollector, DomainContextEngine, and MetricsCollector are all wired via the
wrapper class `engines/ruflo_20phase_wired.py → WiredRufloOrchestrator`.
`main.py` imports `WiredRufloOrchestrator` directly — do NOT modify
`ruflo_20phase_engine.py` for wiring purposes; the wrapper handles it.

## File map
| File | Purpose |
|------|---------|
| main.py | FastAPI entry, JWT auth, SSE streaming, project CRUD |
| engines/ruflo_20phase_engine.py | P1–P20 keyword universe, RufloOrchestrator.run_seed() |
| engines/ruflo_20phase_wired.py | WiredRufloOrchestrator — RawCollector + DCE + Metrics wrapper |
| engines/ruflo_content_engine.py | ContentGenerationEngine.generate() — 7 passes |
| engines/ruflo_strategy_dev_engine.py | StrategyDevelopmentEngine.run() |
| engines/ruflo_confirmation_pipeline.py | ConfirmationPipeline — 5 gates |
| engines/ruflo_seo_audit.py | RufloSEOAudit.full_audit() |
| engines/ruflo_publisher.py | Publisher — WordPress + Shopify |
| quality/annaseo_domain_context.py | DomainContextEngine — per-project classification |
| quality/annaseo_qi_engine.py | QIEngine — quality scoring + tuning |
| quality/annaseo_quality_engine.py | Quality scoring |
| quality/annaseo_lineage_engine.py | Content lineage tracking |
| quality/annaseo_data_store.py | Data persistence layer |
| rsd/annaseo_rsd_engine.py | RSD — engine code health monitoring |
| rsd/annaseo_self_dev.py | SelfDevelopmentEngine — intelligence crawling |
| engines/annaseo_competitor_gap.py | CompetitorGapEngine |
| engines/annaseo_content_refresh.py | ContentRefreshEngine |
| engines/annaseo_ai_citation_monitor.py | AICitationMonitor |
| engines/annaseo_intelligence_engines.py | Multilingual, SERP features, voice, prediction, seasonal, intent |
| annaseo_product_growth.py | Team, webhooks, PDF, GA4, bulk import, brief export |
| engines/annaseo_advanced_engines.py | Entity, programmatic SEO, backlinks, local SEO, algo updates |
| annaseo_wiring.py | GSCConnector, Alembic migrations, Ruflo scheduler jobs |
| modules/annaseo_addons.py | OffTopicFilter, HDBSCANClustering, lifecycle |
| modules/annaseo_doc2_addons.py | MemorySystem, PromptVersioning, ClusterType |

## Database
SQLite for dev: ./annaseo.db
Run migrations: python annaseo_wiring.py write-migrations . && alembic upgrade head
All tables documented in: docs/DATA_MODELS.md

## Environment variables
See .env.example for all required variables.
Required: ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY
Local: OLLAMA_URL=http://localhost:11434

## Starting the project
```bash
uvicorn main:app --port 8000 --reload   # backend
cd frontend && npm run dev               # frontend
```

## Current build status
Week 1 (Apr 1): Foundation — run migrations, verify health endpoint
Week 2 (Apr 8): Wire RawCollector + DomainContextEngine into keyword pipeline
Week 3 (Apr 15): Wire content pipeline, test 7-pass generation
Week 4 (Apr 22): Test quality feedback loop end-to-end
Week 5 (Apr 29): Connect GSC OAuth, verify rankings import
Week 6 (May 6): Start RSD health monitoring
Week 7 (May 13): Replace frontend mock data with real API calls
Week 8 (May 20): Polish and launch

Full checklist: docs/DEVELOPMENT_PLAN.md
