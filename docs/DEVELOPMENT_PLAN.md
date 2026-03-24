# AnnaSEO — Development Plan

**Start date:** April 1, 2026  
**MVP target:** May 26, 2026 (8 weeks)  
**Team assumption:** 1–2 developers

---

## Week 1 (Apr 1–7): Foundation ✅ DONE

### Goal: FastAPI wired, DB migrated, all engines importable

**Tasks:**
- [x] Create `main.py` — FastAPI entry, JWT auth, SSE streaming
- [x] DB schema auto-created on startup (SQLite dev mode)
- [x] Verify all 18 engine files import without errors
- [x] Install and test Ollama with `deepseek-r1:7b`
- [x] Test Gemini API key with free tier
- [x] Test Groq API key with Llama 3.3
- [x] Create `.env` file from `.env.example`
- [x] Wire `annaseo_domain_context.py` into project creation flow
- [x] `GET /api/health` returns engine status for all modules

**Ports:**
- 8000 — main FastAPI app
- 8004 — RSD engine (standalone dev/test)
- 8005 — Self Dev engine (standalone)
- 8006 — QI engine (standalone)
- 8007 — Domain Context engine (standalone)

---

## Week 2 (Apr 8–14): Keyword Pipeline ✅ DONE

### Goal: Seed → Pillars working end-to-end

**Tasks:**
- [x] Wire `RawCollector` + `DomainContextEngine` via `WiredRufloOrchestrator` (ruflo_20phase_wired.py)
- [x] SSE console output wired to all phase logs
- [x] `POST /api/projects/{id}/runs` → SSE stream of 20 phases
- [x] All 150 failing tests fixed (OffTopicFilter, P5 intent, P6 cache, P8 topic dedup)
- [x] Domain isolation verified: "cinnamon tour" → REJECT for spice, ACCEPT for tourism

---

## Week 3 (Apr 15–21): Content Pipeline

### Goal: Pillar keyword → Published article

**Tasks:**
- [ ] Wire `ContentGenerationEngine.generate()` (7 passes)
- [ ] Wire `RawCollector` for each content pass result
- [ ] Test all 7 passes with a real keyword
- [ ] Verify E-E-A-T score > 75 threshold
- [ ] Verify GEO score > 75 threshold
- [ ] Verify AI watermark scrubber runs in Pass 7
- [ ] Test `SchemaGenerator` — JSON-LD output valid
- [ ] Wire `Publisher` for WordPress test publish
- [ ] Wire `Publisher` for Shopify test publish
- [ ] Test `QIEngine.job_score_run()` on content results

**Deliverable:** Full run: keyword → article → published → QI scored

---

## Week 4 (Apr 22–28): Quality Intelligence

### Goal: QI dashboard working with real project data

**Tasks:**
- [ ] QI Engine: review queue shows real items from Week 2/3 runs
- [ ] Test user feedback flow: mark item bad → attribution → tuning generated
- [ ] Test tuning approval: approve filter tuning → annaseo_addons.py updated
- [ ] Test rollback: undo filter tuning → file restored
- [ ] Phase health report: shows P10 quality below P3
- [ ] Domain Context feedback: "cinnamon tour" bad for spice → PROJECT tuning
- [ ] Domain Context feedback: "meme" bad → GLOBAL tuning
- [ ] Test `TuningRegistry.get_project_kill_list()` isolated per project

**Deliverable:** QI dashboard at `GET /api/qi/dashboard?project_id=proj_001`

---

## Week 5 (Apr 29–May 5): SEO Audit + Rankings

### Goal: Technical SEO checks and GSC monitoring

**Tasks:**
- [ ] Wire `RufloSEOAudit` — all 14 technical checks
- [ ] Test INP check (not FID — FID is dead since March 2024)
- [ ] Test AI crawler check (14 bots including ClaudeBot, GPTBot)
- [ ] Test llms.txt generation
- [ ] Test citability scorer
- [ ] Wire GSC OAuth for P20_RankingFeedback
- [ ] Test daily rank import
- [ ] Wire ranking alerts
- [ ] Test `QIEngine` on audit findings

**Deliverable:** `POST /api/projects/{id}/audit` returns full technical report

---

## Week 6 (May 6–12): RSD Engine + Self Development

### Goal: Engine health monitoring and intelligence crawling live

**Tasks:**
- [ ] Wire `MetricsCollector.observe()` into all engines
- [ ] Test `EngineScorer.score()` — all 8 dimensions
- [ ] Test fine-tuning pipeline (no AI keys needed for dry run)
- [ ] Test approval gate: request → approve → code deployed
- [ ] Wire `IntelligenceCrawler` — RSS feeds for 10 sources
- [ ] Test GitHub API crawler for trending SEO repos
- [ ] Test arXiv crawler for GEO papers
- [ ] Wire `UserContentManager` — user adds custom URL
- [ ] Test full self-dev pipeline: crawl → gap → implement → approve

**Deliverable:** RSD dashboard shows live engine health scores

---

## Week 7 (May 13–19): React Frontend ✅ DONE (ahead of schedule)

### Goal: 8 pages functional (not polished)

**Pages built (all in `frontend/src/App.jsx`):**
- [x] `Dashboard` — universe summary cards (universes/pillars/clusters/keywords), projects grid, cost overview
- [x] `Keywords/Universe` — SSE console, run keyword universe, 20-phase live output
- [x] `KeywordTree` — D3.js collapsible tree
- [x] `Content` — generate, lifecycle pipeline visual (draft→review→approved→published), approve/freeze
- [x] `Calendar` — real API wired (`/api/projects/{id}/calendar-items`), 12-month grid, freeze/unfreeze
- [x] `SEOChecker` — technical audit, 14 checks, INP/CWV
- [x] `Rankings` — position distribution cards, mini bar chart, GSC connect
- [x] `Quality` — QI review queue + phase health
- [x] `Settings` — API key form, test connection, AI routing display
- [x] `NewProject` — 4-step wizard (business → universe seeds + competitors → language/region/religion → publishing)

**Tech:** React 18 + Vite + TailwindCSS + D3.js + Chart.js + Zustand + React Query

---

## Week 8 (May 20–26): Polish + Launch

**Tasks:**
- [ ] End-to-end test with 2 real projects (different industries)
- [ ] Test "cinnamon tour" scenario: spice project rejects, travel project accepts
- [ ] Test 3 full article generation runs
- [ ] Test WordPress + Shopify publish
- [ ] Test QI → feedback → tuning → approve → next run improves
- [ ] Test RSD → engine low score → fine-tune → approve
- [ ] Fix all critical bugs found in weeks 1–7
- [ ] Deploy to production server
- [ ] Set up Ruflo scheduler for automated runs
- [ ] Write user onboarding guide

---

## Critical Dependencies

| Dependency | Install | Notes |
|-----------|---------|-------|
| Ollama | `curl -fsSL https://ollama.ai/install.sh \| sh` | Needs 8GB+ RAM |
| DeepSeek | `ollama pull deepseek-r1:7b` | ~4GB model |
| spaCy model | `python -m spacy download en_core_web_sm` | Small model |
| sentence-transformers | `pip install sentence-transformers` | Needs 380MB RAM |
| HDBSCAN | `pip install hdbscan` | Needs gcc |
| Playwright | `playwright install chromium` | For SERP crawling |

---

## Must-Test Scenarios Before Launch

1. **Domain isolation:** Spice project seed "cinnamon" → "cinnamon tour" = BAD pillar
2. **Domain isolation:** Tourism project seed "ceylon tour" → "ceylon cinnamon tour" = GOOD pillar
3. **Cross-domain:** "plantation" = ACCEPT for both spice and tourism
4. **Cross-domain:** "meme" = REJECT for all projects (global)
5. **Project tuning:** Mark "cinnamon tour" bad in spice project → PROJECT kill list updated, travel project unchanged
6. **Global tuning:** Mark "meme" bad anywhere → GLOBAL kill list updated, affects all projects
7. **Content quality:** Article with GEO < 75 → Pass 7 humanize runs → GEO improves
8. **Rollback:** Approve filter tuning → verify words added → rollback → words removed
9. **Engine health:** Artificially lower a score → fine-tune pipeline triggers → approval requested
10. **Schema rules:** HowTo schema NOT generated (deprecated Sept 2023), FAQPage only for healthcare/gov

---

## Ports and Services

| Port | Service |
|------|---------|
| 8000 | Main AnnaSEO FastAPI app |
| 8004 | RSD Engine (dev/standalone) |
| 8005 | Self Dev Engine (dev/standalone) |
| 8006 | QI Engine (dev/standalone) |
| 8007 | Domain Context Engine (dev/standalone) |
| 11434 | Ollama (DeepSeek local) |
| 5432 | PostgreSQL (production; SQLite for dev) |
| 5173 | React frontend (Vite dev server) |

---

## Completed engines (added beyond original plan)

### Round 1 (built from brainstorm)
- [x] `annaseo_main.py` — FastAPI glue file, JWT auth, SSE runs, content workflow, cost tracker
- [x] `annaseo_competitor_gap.py` — competitor crawl → keyword gap → attack plan
- [x] `annaseo_content_refresh.py` — ranking drop detection → surgical update instructions
- [x] `annaseo_ai_citation_monitor.py` — weekly AI search citation tracking

### Round 2 (intelligence engines pack)
- [x] `annaseo_intelligence_engines.py` — 6 engines in one file:
  - `MultilingualContentEngine` — Malayalam/Hindi/Tamil/Arabic cultural adaptation
  - `SERPFeatureTargetingEngine` — Featured Snippet/PAA/ImagePack targeting
  - `VoiceSearchOptimiser` — question intent + spoken answer briefs
  - `RankingPredictionEngine` — predict position before writing, track accuracy
  - `SeasonalKeywordCalendar` — publish 8 weeks before seasonal peak
  - `SearchIntentShiftDetector` — weekly intent re-check, shift alerts

### Round 3 (product growth pack)
- [x] `annaseo_product_growth.py` — 6 engines in one file:
  - `TeamACL` — project roles (Admin/Editor/Analyst/Viewer)
  - `WebhookEngine` — Slack/Discord/Zapier notifications for 12 event types
  - `PDFReportEngine` — monthly client reports (white-label HTML+PDF)
  - `GA4Integration` — organic traffic + ROI per article
  - `BulkKeywordImporter` — CSV upload → domain-classified → universe
  - `ContentBriefExporter` — briefs as Markdown/Notion/Google Doc for human writers

---

## Still pending (post-MVP v2)
- [ ] Entity authority builder (Knowledge Panel entity strengthening)
- [ ] Programmatic SEO page builder (template → N unique pages, gates at 100/500)
- [ ] Backlink opportunity engine (post-publish link building)
- [ ] Local SEO engine (GeoLevel enum → LocalBusiness schema + NAP)
- [ ] White-label mode (agency branding on all UI)
- [ ] Competitor monitoring dashboard (ongoing, not just one-time analysis)
- [ ] Algorithm update impact assessor (when core update drops → auto-score all articles)
