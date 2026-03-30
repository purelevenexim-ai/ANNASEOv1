# temp.md

Repository inventory and summaries

Generated: 2026-03-30

---

## Top-level entries

- .dockerignore
- .env
- .env.example
- .git/
- .github/
- .gitignore
- .pytest_cache/
- .superpowers/
- .tmp/
- .venv/
- CLAUDE.md
- Dockerfile
- ISSUES_FIXED_COMPREHENSIVE.md
- LINODE_SETUP.md
- ProF-os we use get_db() wrapper. We'll use raw DB via get_db and strategy.
- QUICKSTART.md
- README.md
- SESSION_SUMMARY.md
- TEST_GATE2_CHECKLIST.md
- TEST_GATE2_E2E.md
- __pycache__/
- alembic/
- alembic.ini
- annaseo.db
- annaseo.db-shm
- annaseo.db-wal
- annaseo_paths.py
- annaseo_product_growth.py
- annaseo_wiring.py
- backend.log
- cols', c.fetchall())
- core/
- deploy/
- docker-compose.postgres.yml
- docker-compose.yml
- docs/
- engines/
- ert error', e)
- frontend/
- jobqueue/
- main.py
- models/
- modules/
- pytest.ini
- pytests/
- quality/
- repro_strategy_run.py
- requirements.txt
- rsd/
- rsd_versions/
- ruflo_data/
- run_strategy_check.py
- s
- scripts/
- services/
- start.sh
- sweep_forbidden_terms.py
- test_all_issues.py
- test_and_startup.py
- test_gate2_quick.sh
- tests/
- todo_readme.md
- tools/
- venv/
- workers/
- ycopg2.connect(url) as conn:

---

## docs/ — full contents appended

The following sections contain verbatim copies of files from the `docs/` folder.

### File: [ANNASEOv1/docs/strategy_dashboard_ui.md](ANNASEOv1/docs/strategy_dashboard_ui.md)

Strategy Dashboard UI — Design & Implementation

Purpose
-------
Visual decision system for strategy review, prioritization, and execution.

Main page structure
-------------------
Dashboard
 ├── Strategy Overview
 ├── Priority Queue (timeline)
 ├── Content Briefs
 ├── Gap Opportunities
 ├── Internal Link Map
 └── Predictions

Key components
--------------
1. Strategy Overview (top block)
- Show `confidence`, `biggest_single_opportunity`, `critical_insight`.

2. Priority Queue
- Timeline view grouped by week, article cards with KD, why_this_week, CTA to freeze/approve.

3. Gap Opportunities
- Badge list of missing topics discovered by Gap Engine with quick-brief generator action.

4. Content Briefs view
- Accordion list: H2 structure, word targets, FAQs, entities to include.

5. Internal Link Graph
- Use `react-flow` or `d3` to render pillar → cluster → article → product graph.

6. Predictions chart
- Line chart (12 months) with top-3/top-10 keyword counts (use `recharts`).

7. Job progress UI
- Show `<Progress value={progress} />` and `currentPhase` from `/api/jobs/{job_id}`.

React snippets (examples)

Strategy Overview
```jsx
<Card>
	<h2>Strategy Score: {confidence}%</h2>
	<p>Biggest Opportunity: {strategy.biggest_single_opportunity}</p>
	<p>Insight: {strategy.critical_insight}</p>
</Card>
```

Priority Queue (render)
```jsx
{queue.map(week => (
	<div key={week.week}>
		<h3>Week {week.week}</h3>
		{week.articles.map(a => (
			<Card key={a.target_keyword}>
				<h4>{a.title}</h4>
				<p>KD: {a.kd_estimate}</p>
				<p>{a.why_this_week}</p>
			</Card>
		))}
	</div>
))}
```

Gap Opportunities
```jsx
<Card>
	<h3>Content Gaps</h3>
	{gaps.map(g => <Badge key={g}>{g}</Badge>)}
</Card>
```

Content Briefs (accordion)
```jsx
{briefs.map(b => (
	<AccordionItem key={b.article_title}>
		<h4>{b.article_title}</h4>
		<ul>{b.h2_structure.map(h => <li key={h}>{h}</li>)}</ul>
	</AccordionItem>
))}
```

Internal link graph
- Use `react-flow` nodes for pillars and cluster articles; allow drag & drop to adjust internal link suggestions.

Job progress polling (simple)
```js
useEffect(() => {
	const t = setInterval(async () => {
		const res = await fetch(`/api/jobs/${jobId}`)
		const data = await res.json()
		setJob(data)
	}, 1500)
	return () => clearInterval(t)
}, [jobId])
```

UX principles
-------------
- Show decisions (what to publish), not engine internals
- Keep controls business-facing: "Find Opportunities", "Lock Strategy", "Build First"
- Provide clear preview vs final actions: Strategy page = preview; Keyword page = execution

Integration notes
-----------------
- Backend endpoints to supply aggregates: `/api/dashboard/summary`, `/api/dashboard/opportunities`, `/api/strategy/{id}/briefs`
- Use limited sample sizes for preview endpoints to keep latency low
- Provide CSV/export and schedule publishing API for content calendar

Accessibility & performance
---------------------------
- Lazy-load heavy graphs and briefs
- Server-side paginate long lists (scored keywords)
- Add aria labels and keyboard navigation for accordion and graph

This doc is a concise, implementable UI spec that maps directly to the strategy outputs produced by the backend engines.

### File: [ANNASEOv1/docs/DISCUSSIONS.md](ANNASEOv1/docs/DISCUSSIONS.md)

AnnaSEO — Design Decisions & Discussions

All major design choices and the reasoning behind them.

---

## D1: Universe → Pillar → Cluster → Keyword hierarchy

**Decision:** 4-level hierarchy, not flat keyword list.

**Why:** A flat list of 2000 keywords has no structure for content planning. The hierarchy gives us:
- Universe = the business's core topic (e.g. "black pepper")
- Pillar = broad authoritative content area (e.g. "black pepper health benefits")
- Cluster = grouped related topics
- Keyword = specific search queries

**Impact:** 20-phase engine, knowledge graph, internal linking, content calendar — all depend on this hierarchy.

---

## D2: Industry enum on strategy engine

**Decision:** `Industry` enum with 12 values in `ruflo_strategy_dev_engine.py`.

**Why:** Different industries need different personas, content angles, and vocabulary. A healthcare project and a spice project cannot share the same prompt templates.

**Impact:** Led directly to the Domain Context Engine — same seed, different industry, different keyword verdict.

---

## D3: Domain Context solves cross-domain problem

**Decision:** Don't add "tour" to GLOBAL_KILL. Create per-project domain profiles instead.

**Why:** "Tour" is a legitimate keyword for a travel business. A global kill list cannot differentiate. The answer is per-project classification using industry-specific cross-domain vocabulary.

**The cinnamon example:**
- Spice project: "cinnamon tour" → REJECT ("tour" = travel, off-domain for spice seller)
- Travel project: "ceylon cinnamon tour" → ACCEPT ("cinnamon" = legitimate tourism attraction in Sri Lanka)
- Both projects share "ceylon cinnamon" as ACCEPT (product + destination are the same thing)

**Impact:** `annaseo_domain_context.py` — inserted at P2 output and P10 output in the pipeline.

---

## D4: Global vs Project tuning separation

**Decision:** Two distinct tuning types with different files, different scope, different approval audiences.

**Global tuning:** touches engine .py files. Fixes code bugs, algorithm thresholds, Layer 1 prompt. Affects all projects. Needs system admin approval.

**Project tuning:** touches `ProjectDomainProfile` config. Fixes per-project keyword and content issues. Affects only that project. Needs project owner approval.

**Rule of thumb:**
- Keyword wrong for THIS business → project tuning
- Keyword universally wrong (meme, viral) → global tuning
- Code bug → global tuning
- Business-specific content angle → project tuning

---

## D5: Data lineage for quality attribution

**Decision:** Every output item tagged with origin phase, function, and trace path.

**Why:** "Cinnamon tour" showed up as a pillar. Which engine produced it? Without a trace chain, you don't know where to fix. With a trace chain:

```
P2._google_autosuggest → fetched "cinnamon tour"
P3_Normalization       → passed through (no filter matched)
OffTopicFilter         → passed through ("tour" not in GLOBAL_KILL)
P8_TopicDetection      → clustered into "Cinnamon Tourism"
P10_PillarIdentification → promoted to pillar
```

The fix is at `OffTopicFilter` (GLOBAL_KILL missing "tour") AND `P10_PillarIdentification.PILLAR_PROMPT` (no domain exclusion). Not at P2 which just fetched what Google gave it.

**Impact:** `annaseo_qi_engine.py` ENGINE_ANATOMY map — every phase's known failure modes documented from reading the actual code.

---

## D6: AI model routing — free tools for coding, Claude only for verification

**Decision:** Gemini + Groq + DeepSeek do all the work. Claude only does final verification.

**Why:**
- Gemini 1.5 Flash: free tier, good at analysis and spec writing
- Groq Llama 3.1: very fast, free tier, good at test generation
- DeepSeek local (Ollama): free, runs on your machine, good at code
- Claude: ~$0.022/article, best quality — worth it for content and final code review

This separation means the quality loop (score → feedback → fix) costs essentially $0. Only content generation and code verification use Claude.

---

## D7: Manual approval gate — non-negotiable

**Decision:** Every production change requires human approval. No exceptions.

**Why:** AI-generated fixes can introduce regressions. The system is self-modifying — if a bad fix gets auto-applied, it could affect all projects. A human must verify.

**Implementation:**
- All tunings → `qi_tunings` table with `status='pending'`
- Frontend shows diff, Claude's confidence score, evidence
- Human clicks Approve → code applied, snapshot saved
- Rollback available instantly — no downtime required

---

## D8: INP replaces FID in SEO audit

**Decision:** Check INP, never FID. FID was removed from Core Web Vitals in March 2024.

**Why:** Google officially removed First Input Delay (FID) from the Core Web Vitals metrics in March 2024 and replaced it with Interaction to Next Paint (INP). Any SEO tool still checking FID is outdated.

**Impact:** `ruflo_seo_audit.py` — all CWV checks use INP.

---

## D9: Schema.org deprecated types

**Decision:** Never generate HowTo or FAQ schema for non-healthcare/gov sites.

**Why:**
- HowTo schema: Google stopped showing rich results for HowTo in September 2023
- FAQPage schema: Restricted to authoritative gov/healthcare sites in August 2023

**Impact:** `ruflo_seo_audit.py` and `ruflo_content_engine.py` — schema generator only creates Article, Product, Organization, LocalBusiness, BreadcrumbList.

---

## D10: JSON-LD only — never Microdata or RDFa

**Decision:** All structured data as JSON-LD. Microdata and RDFa are not supported.

**Why:** Google strongly prefers JSON-LD. It's easier to inject and maintain. Microdata and RDFa are tied to HTML structure and break when HTML changes.

**Impact:** `ruflo_content_engine.py` `SchemaGenerator` — always outputs `<script type="application/ld+json">` blocks.

---

## D11: One-at-a-time publishing

**Decision:** Publisher processes one article at a time, 30s delay between publishes.

**Why:** WordPress and Shopify rate limits. Parallel publishing causes 429 errors. One-at-a-time with retry logic is more reliable.

**Impact:** `ruflo_publisher.py` — SQLite queue, `publish_one_at_a_time()`, 3× retry.

---

## D12: p95 latency, not average

**Decision:** All performance scoring uses p95, not mean.

**Why:** Average hides outliers. An engine that takes 2 seconds 95% of the time but 45 seconds 5% of the time has a terrible user experience. p95 catches the slow tail.

**Impact:** `annaseo_rsd_engine.py` `EngineScorer._score_execution_time()`.

---

## D13: HDBSCAN primary, KMeans fallback

Decision and many more entries...

### File: [ANNASEOv1/docs/level3.md](ANNASEOv1/docs/level3.md)

# Level 3: Production Gaps, Bug Inventory, and Fix Plan

Date: 2026-03-30

## 1. Verified behavioral workflow (from project to P6/Clusters)

1. Post `/api/projects` with `name`, `industry`, `seed_keywords` successfully creates project.
2. GET `/api/projects/{project_id}` confirms data exists.
3. POST `/api/ki/{project_id}/input` saves pillars/supporting keywords and creates KI session.
4. GET `/api/ki/{project_id}/pillars` returns persisted pillars.
5. POST `/api/ki/{project_id}/generate/{session_id}` starts generation.
6. Poll `/api/ki/{project_id}/session/{session_id}` to check stage/total.
7. POST `/api/ki/{project_id}/confirm/{session_id}` confirms and persists universe.
8. GET `/api/ki/{project_id}/clusters` returns derived clusters from persisted runs.
9. POST `/api/ki/{project_id}/clusters/generate` works with fallback cluster names if LLM call fails.

Tests added:
- `pytests/test_e2e_real_company_flow.py` covering Cooking and Education scenarios.
- run: `pytest pytests/test_e2e_real_company_flow.py -q` (2 passed).

## 2. Snapshots of discovered issues (some flashpoints of "vanishing data")

- Project existence may fail in some routes when a project is only in KI DB but not in `projects`; fixed via main.py `_validate_project_exists()` fallback from KI DB.
- Project list endpoint in tests returns plain list, not `{projects: [...]}`; adapt client code accordingly. This may cause frontend treats as missing data.
- In-memory state / local browser: page refresh can lose unsaved session if backend does not rehydrate `session_id` properly. Need check UI `session` persistence on reload.
- `api/ki/{project_id}/clusters/generate` uses OLLAMA URL and fallback; if no model, returns manual clusters (no error), so user may not see consistent cluster names.
- `strategy_jobs` and `trian_*` job tracker not fully production-ready (DB presence/unlock semantics missing) as listed in `docs/production_readiness_summary.md`.

... (level3.md continues)

### File: [ANNASEOv1/docs/production_readiness_summary.md](ANNASEOv1/docs/production_readiness_summary.md)

when you complete each phase respect below: update

1. code completion.
2. ask question when in doubt,
3. ckean coding practice
4. identify missing pieces
5. brainstorm ideas
6. respect memory usage, code for optimization
7. create test casaes and test every modules and make sure no break, bugs or issues.
8. read mains.py , readiness, keyword strategy and all files before making changes.
9. if required make frontend also.

# Production Readiness Summary

Date: 2026-03-27

Verdict: Not production-ready — prototype with major operational gaps. This document has been expanded into a concrete, actionable fix plan to close all gaps and reach production-grade reliability.

Reality check

- You already have: Queue (RQ), Worker, Basic DB, Progress tracking ✅
- Missing production guarantees: durability, idempotency, resume semantics, observability, and operational control ❌

COMPLETE FIX PLAN (CLOSING ALL GAPS)

1) IDEMPOTENCY + RESUME (CRITICAL)

Problem

- If a worker crashes, a job is retried, or a user double-submits, the pipeline can duplicate work or corrupt shared state.

DB changes (SQL)

```sql
ALTER TABLE strategy_jobs
ADD COLUMN lock_key TEXT,
ADD COLUMN is_locked BOOLEAN DEFAULT FALSE,
ADD COLUMN last_completed_step INT DEFAULT 0;
```

... (production_readiness_summary continues)

### File: [ANNASEOv1/docs/ENGINES.md](ANNASEOv1/docs/ENGINES.md)

# AnnaSEO — Engines Reference

## File Map

| File | Lines | Role | Port |
|------|-------|------|------|
| `ruflo_20phase_engine.py` | 2,269 | 20-phase keyword universe (P1–P20) | 8000 |
| `ruflo_20phase_wired.py` | — | WiredRufloOrchestrator — RawCollector + DCE wrapper | 8000 |
| `ruflo_v3_keyword_system.py` | — | Ruflo v3 — 4-level universe hierarchy | 8000 |
| `ruflo_content_engine.py` | 1,645 | 7-pass content generation | 8000 |
| `ruflo_strategy_dev_engine.py` | 1,309 | Business strategy + personas | 8000 |
| `ruflo_final_strategy_engine.py` | 1,295 | Claude strategy synthesis | 8000 |
| `ruflo_confirmation_pipeline.py` | 1,715 | 5-gate user approval | 8000 |
| `ruflo_seo_audit.py` | 1,677 | 14 checks + AI visibility | 8000 |
| `ruflo_publisher.py` | 1,337 | WordPress + Shopify publish | 8000 |
| `annaseo_addons.py` | 929 | HDBSCAN, OffTopicFilter, lifecycle | — |
| `annaseo_doc2_addons.py` | 933 | ClusterType, Memory, Versioning | — |
| `annaseo_qi_engine.py` | 1,698 | Quality intelligence master | 8006 |
| `annaseo_domain_context.py` | ~700 | Per-project domain classification | 8007 |
| `annaseo_rsd_engine.py` | 2,061 | Code quality + engine tuning | 8004 |
| `annaseo_self_dev.py` | 1,948 | Intelligence crawling + features | 8005 |

---

### File: [ANNASEOv1/docs/DATA_MODELS.md](ANNASEOv1/docs/DATA_MODELS.md)

# AnnaSEO — Data Models

**Database:** SQLite (dev) → PostgreSQL (prod)
**ORM:** SQLAlchemy + Alembic migrations
**Total tables:** 45+

---

### File: [ANNASEOv1/docs/strategy_result_schema.json](ANNASEOv1/docs/strategy_result_schema.json)

{ "type": "object", "additionalProperties": false, "required": [ "strategy_meta", "market_analysis", "keyword_strategy", "content_strategy", "authority_strategy", "execution_plan" ], "properties": { "strategy_meta": { "type": "object", "additionalProperties": false, "required": [ "project_id", "generated_at", "execution_mode" ], "properties": { "project_id": { "type": "string" }, "generated_at": { "type": "string" }, "execution_mode": { "type": "string", "enum": [ "single_call" ] }, "version": { "type": "string" } } }, "market_analysis": { "type": "object", "additionalProperties": false, "required": [ "target_audience", "search_intent_types", "pain_points" ], "properties": { "target_audience": { "type": "array", "items": { "type": "string" } }, "search_intent_types": { "type": "array", "items": { "type": "string", "enum": [ "informational", "commercial", "transactional", "navigational" ] } }, "pain_points": { "type": "array", "items": { "type": "string" } } } }, "keyword_strategy": { "type": "object", "additionalProperties": false, "required": [ "primary_keywords", "secondary_keywords", "long_tail_keywords" ], "properties": { "primary_keywords": { "type": "array", "items": { "$ref": "#/definitions/keyword" } }, "secondary_keywords": { "type": "array", "items": { "$ref": "#/definitions/keyword" } }, "long_tail_keywords": { "type": "array", "items": { "$ref": "#/definitions/keyword" } } } }, "content_strategy": { "type": "object", "additionalProperties": false, "required": [ "pillar_pages", "cluster_topics" ], "properties": { "pillar_pages": { "type": "array", "items": { "$ref": "#/definitions/content_piece" } }, "cluster_topics": { "type": "array", "items": { "$ref": "#/definitions/content_piece" } } } }, "authority_strategy": { "type": "object", "additionalProperties": false, "required": [ "backlink_plan", "topical_depth" ], "properties": { "backlink_plan": { "type": "array", "items": { "type": "string" } }, "topical_depth": { "type": "array", "items": { "type": "string" } } } }, "execution_plan": { "type": "object", "additionalProperties": false, "required": [ "phases" ], "properties": { "phases": { "type": "array", "items": { "type": "object", "additionalProperties": false, "required": [ "phase_name", "tasks" ], "properties": { "phase_name": { "type": "string" }, "tasks": { "type": "array", "items": { "$ref": "#/definitions/task" } } } } } } } }, "definitions": { "keyword": { "type": "object", "additionalProperties": false, "required": [ "keyword", "intent", "difficulty", "priority" ], "properties": { "keyword": { "type": "string" }, "intent": { "type": "string", "enum": [ "informational", "commercial", "transactional", "navigational" ] }, "difficulty": { "type": "number", "minimum": 0, "maximum": 100 }, "priority": { "type": "number", "minimum": 1, "maximum": 5 } } }, "content_piece": { "type": "object", "additionalProperties": false, "required": [ "title", "target_keyword", "search_intent", "outline" ], "properties": { "title": { "type": "string" }, "target_keyword": { "type": "string" }, "search_intent": { "type": "string", "enum": [ "informational", "commercial", "transactional" ] }, "outline": { "type": "array", "items": { "type": "string" } } } }, "task": { "type": "object", "additionalProperties": false, "required": [ "task_name", "priority" ], "properties": { "task_name": { "type": "string" }, "priority": { "type": "number", "minimum": 1, "maximum": 5 } } } } }

### File: [ANNASEOv1/docs/RUFLO_ARCHITECTURE_V2.md](ANNASEOv1/docs/RUFLO_ARCHITECTURE_V2.md)

# RUFLO v2 — UPDATED APPLICATION ARCHITECTURE
## With Console Output, Content Strategy Module & Full Flexibility System

---

... (RUFLO v2 architecture and large content included)

### File: [ANNASEOv1/docs/API.md](ANNASEOv1/docs/API.md)

# AnnaSEO — API Reference

**Base URL:** `http://localhost:8000`
**Auth:** JWT (to be implemented in Week 1)
**Format:** JSON everywhere

---

## Projects

```
POST   /api/projects                          Create project
GET    /api/projects                          List all projects
GET    /api/projects/{id}                     Get project details
PUT    /api/projects/{id}                     Update project settings
DELETE /api/projects/{id}                     Delete project
```

... (API reference continues)

### File: [ANNASEOv1/docs/KEYWORD_PROMPTS.md](ANNASEOv1/docs/KEYWORD_PROMPTS.md)

Keyword Prompts — Templates and Usage
===================================

This document describes the prompt templates implemented in `tools/keyword_prompts.py`.

Templates:

- `render_seed_expansion(seed, industry, region)`
	- Purpose: Expand a seed keyword into modifiers, long-tail ideas, and regional variants.
	- Returns: plain text list; suitable for feeding into embedding or clustering.

- `render_clustering_prompt(seed, topics, n_clusters)`
	- Purpose: Given topic names, ask the model to group them into thematic clusters.
	- Important: This prompt includes the instruction `Return ONLY valid JSON`.

- `render_priority_prompt(keywords)`
	- Purpose: Ask the model to rate intent, SERP difficulty, and priority score per keyword.
	- Important: This prompt includes the instruction `Return ONLY valid JSON`.

Usage notes:
- Use the seed expansion for P2 debugging or as an optional generator step.
- Use clustering prompt for P9 candidate cluster formation if LLM clustering is desired.
- Use priority prompt to synthesize SERP heuristics or when human-in-the-loop prioritization is required.

Example (paste into agent):
```
{prompt}
```

### File: [ANNASEOv1/docs/DEVELOPMENT_PLAN.md](ANNASEOv1/docs/DEVELOPMENT_PLAN.md)

# AnnaSEO — Development Plan

**Start date:** April 1, 2026
**MVP target:** May 26, 2026 (8 weeks)
**Team assumption:** 1–2 developers

---

... (development plan continues)

### File: [ANNASEOv1/docs/serp_gap_engine.md](ANNASEOv1/docs/serp_gap_engine.md)

# SERP Gap Engine — Implementation Guide

Purpose
-------
Turn keywords into real, data-backed strategy inputs by extracting competitor signals and detecting missing topics competitors ignore.

Overview
--------
Keyword → SERP → Competitor Extraction → Content Analysis → Gap Detection → Strategy Input

1) engines/serp_engine.py — fetch + cache

```py
import os
import requests
from services.db import get_serp_cache, save_serp_cache

SERP_API_KEY = os.getenv('SERP_API_KEY')

class SERPEngine:
		def fetch_serp(self, keyword):
				cached = get_serp_cache(keyword)
				if cached:
						return cached

				url = 'https://serpapi.com/search'
				params = {'q': keyword, 'api_key': SERP_API_KEY, 'engine': 'google', 'num': 10}

				r = requests.get(url, params=params, timeout=30)
				r.raise_for_status()
				data = r.json()

				results = [
						{'title': r.get('title'), 'url': r.get('link'), 'snippet': r.get('snippet')}
						for r in data.get('organic_results', [])[:10]
				]

				save_serp_cache(keyword, results)
				return results
```

... (serp gap engine content continues)

---

End of appended docs.

