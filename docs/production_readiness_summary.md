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

Create job (idempotent)

```py
import hashlib, json

def create_job(conn, job_id, universe_result):
	lock_key = hashlib.sha256(
		json.dumps(universe_result, sort_keys=True).encode()
	).hexdigest()

	with conn.cursor() as cur:
		cur.execute(
			"""
			SELECT id FROM strategy_jobs
			WHERE lock_key=%s AND status IN ('queued','running')
			LIMIT 1
			""",
			(lock_key,)
		)
		existing = cur.fetchone()
		if existing:
			return existing[0]

		cur.execute(
			"""
			INSERT INTO strategy_jobs (id, status, lock_key)
			VALUES (%s, %s, %s)
			""",
			(job_id, 'queued', lock_key)
		)
		conn.commit()

	return job_id
```

Worker lock enforcement

```py
def acquire_lock(conn, job_id):
	with conn.cursor() as cur:
		cur.execute(
			"""
			UPDATE strategy_jobs
			SET is_locked=TRUE
			WHERE id=%s AND is_locked=FALSE
			RETURNING id
			""",
			(job_id,)
		)
		return cur.fetchone() is not None

# in worker runtime
if not acquire_lock(conn, job_id):
	# another worker holds the lock — exit gracefully
	return
```

Resume failed jobs

```py
def set_progress(conn, job_id, step_index, steps):
	progress = int((step_index / len(steps)) * 100)
	with conn.cursor() as cur:
		cur.execute(
			"""
			UPDATE strategy_jobs
			SET progress=%s, current_step=%s, last_completed_step=%s
			WHERE id=%s
			""",
			(progress, steps[step_index], step_index, job_id)
		)
		conn.commit()

# resume logic
job = get_job(conn, job_id)
start_step = job.get('last_completed_step', 0)
```

2) REPLACE `_jobs` COMPLETELY

- Remove any remaining in-memory `_jobs = {}` usage. All job lifecycle state must be persisted in `strategy_jobs` and exposed via the `/api/jobs/{job_id}` endpoint.

3) REAL SERP LAYER (NOT OPTIONAL)

- Replace canned `raw_competitors` with real SERP data (SerpAPI, DataForSEO, etc.) and add a cache layer.

Example SERP fetcher

```py
import requests

SERP_API_KEY = os.getenv('SERP_API_KEY')
def fetch_serp(keyword):
	url = 'https://serpapi.com/search'
	params = {'q': keyword, 'api_key': SERP_API_KEY, 'engine': 'google'}
	r = requests.get(url, params=params, timeout=30)
	r.raise_for_status()
	data = r.json()
	return [
		{'title': x.get('title'), 'url': x.get('link'), 'snippet': x.get('snippet')}
		for x in data.get('organic_results', [])[:10]
	]
```

SERP cache table

```sql
CREATE TABLE serp_cache (
	keyword TEXT PRIMARY KEY,
	results JSONB,
	fetched_at TIMESTAMP
);
```

Cached fetch pseudocode

```py
def get_serp_cached(conn, keyword, ttl_seconds=86400):
	row = query_one(conn, 'SELECT results, fetched_at FROM serp_cache WHERE keyword=%s', (keyword,))
	if row and not expired(row['fetched_at'], ttl_seconds):
		return row['results']
	results = fetch_serp(keyword)
	upsert_serp_cache(conn, keyword, results)
	return results
```

4) SINGLE-CALL CLAUDE (YOU MUST DO THIS NEXT)

Problem

- The current multi-step LLM pipeline breaks continuity and increases token consumption, causing inconsistent or conflicting outputs.

Solution (high-level)

- Replace the STEP1→STEP5 chain with a single, carefully-crafted master prompt that returns the complete `strategy` JSON in one call.

Master prompt sketch

```py
StrategyPrompts.FULL = """
You are the world's most effective SEO strategist.

INPUT DATA:
{context_json}

TASK:
Generate a COMPLETE SEO STRATEGY as strictly-formed JSON matching the schema in this document.

STRICT RULES:
- JSON ONLY
- NO markdown or explanation
- Fill required fields
"""
```

Engine.run replacement (concept)

```py
def run(self, universe_result, project, gsc_data=None):
	ctx = self.context_builder.build(...)
	ctx_json = ctx.to_compressed_json()
	prompt = self.prompts.FULL.format(context_json=ctx_json)
	text, tokens = AI.claude(system=self.prompts.SYSTEM, messages=[{"role":"user","content":prompt}], max_tokens=6000)
	strategy = AI.parse_json(text)
	validation = self.validator.validate(strategy, ctx.universe)
	return StrategyOutput(...)
```

Fix `_call_strategy_model`

```py
def _call_strategy_model(self, prompt, max_tokens=6000):
	return AI.claude(system=self.prompts.SYSTEM, messages=[{"role":"user","content":prompt}], max_tokens=max_tokens)
```

5) STRUCTURED LOGGING + METRICS

- Add `structlog` (or similar), ensure every major event is logged with structured fields (job_id, step, duration_ms, error). Export metrics to Prometheus / pushgateway.

6) AUTH, RATE LIMIT & COST CONTROLS

- Add API key middleware (FastAPI dependency) and a rate limiter (`slowapi`). Enforce project-level quotas: `MAX_SERP_CALLS`, `MAX_TOKENS`.

7) PARALLELIZATION, RETRIES & BACKOFF

- Keep heavy runs in RQ workers. Use RQ's retry and backoff strategies for transient failures. Parallelize safe phases with `ThreadPoolExecutor` behind idempotency safeguards.

8) HARDEN JSON PARSING

- Implement a robust `parse_json` with regex fallback and 1–2 automatic reattempts before failing. Persist the raw LLM output in `strategy_jobs` for auditing and debugging.

9) MIGRATIONS, TESTS & ROLL-OUT

- Add migrations for `strategy_jobs` and `serp_cache`.
- Add unit and integration tests for: idempotency, resume, parsing, and SERP caching logic.

Roadmap (recommended order)

1. DB migrations for `strategy_jobs` and `serp_cache`.
2. Implement `services/job_tracker.py` and replace `_jobs` references.
3. Add idempotency and `acquire_lock` semantics.
4. Perform Single-call Claude refactor and fix `_call_strategy_model`.
5. Integrate SERP provider and caching.
6. Add structured logging, metrics, auth, rate limiting, and cost controls.
7. Add tests and stage rollout.

Final verdict after fixes: production-grade AI strategy system with durability, idempotency, recovery, observability, and control.

Next actions (pick one):

- "Claude refactor" — refactor `engines/ruflo_final_strategy_engine.py` to a single-call flow (recommended first code change).
- "SERP engine" — add `engines/serp.py`, `serp_cache` migration, and replace competitors.
- "Job tracker" — add `services/job_tracker.py`, DB migration, and replace in-memory `_jobs`.

Tell me which and I'll implement it next.

---

## Production Checklist (concrete status)

- **DB migrations**: `strategy_jobs`, `serp_cache` — NOT STARTED (required).
- **Job tracker**: `services/job_tracker.py` and replace in-memory `_jobs` — NOT STARTED (required).
- **Idempotency & resume semantics**: DB `lock_key`, `last_completed_step`, worker `acquire_lock()` — NOT STARTED (required).
- **Queue & workers**: Redis + RQ/Celery, worker scaffolding and retry/backoff — NOT STARTED (required).
- **Single-call LLM**: Replace multi-step chain with a single-call `Claude` flow; fix `_call_strategy_model` — NOT STARTED (required).
- **SERP integration & cache**: Real SerpAPI provider + `serp_cache` + 24h fresh / 72h stale fallback — COMPLETED.
- **Auth, rate limits & cost controls**: API keys, `slowapi` or similar, `MAX_TOKENS` limits — NOT STARTED (required).
- **Logging, metrics & alerting**: `structlog`, Prometheus metrics, Sentry/alerts — NOT STARTED (required).
- **Health checks & readiness**: Add `/healthz`, readiness/liveness endpoints and container probes — NOT STARTED (required).
- **CI/CD & deployment manifests**: Dockerfile, Compose/k8s manifests, deploy pipeline, staging rollouts — NOT STARTED (required).
- **Secrets & config management**: Centralized secrets, env validation, rotations — NOT STARTED (required).
- **Testing & load/staging validation**: Unit and integration tests, chaos/load tests in staging — NOT STARTED (required).
- **Docs & runbooks**: Runbooks, incident response, rollback steps — NOT STARTED.
- **Frontend build**: `frontend/dist/` — DONE.
- **Backend startup**: `uvicorn main:app` — DONE (startup verified; publisher import warning fixed).

### Phase 1 — Completion Notes

- **Code changes**: Fixed `engines/ruflo_publisher.py` Pydantic model to avoid `schema_json` shadowing (use `schema_json_` with alias). No heavy import moved; change is minimal and backwards-compatible for API clients.
- **Tests added**: `pytests/test_startup.py` — lightweight tests calling `health()` and `system_status()` directly to validate startup.
- **Validation performed**: Ran `uvicorn` (reload) and confirmed `/api/health` shows all engines `ok` and `/api/system-status` responds. Ran focused pytest for startup tests (passed).
- **Missing / follow-ups**: Add CI step to run focused startup tests; add httpx to dev requirements if TestClient-based tests are later added; consider guarding long-running background threads during test runs.

### TODO and Implementation Plan (updated)

1. **Phase 1 — Boot & readiness** (in-progress)
   - [x] `GET /api/health` exists
   - [x] startup event loads DB & engines
   - [x] itemize missing runtime issues

2. **Phase 2 — Core migration layer** (in-progress)
   - [x] `strategy_jobs` columns exist
   - [x] Add `serp_cache` table + schema (new)

3. **Phase 3 — Job Tracker & Idempotency** (in-progress)
   - [x] `services/job_tracker.py` with lock/resume semantics
   - [x] `acquire_job_lock` + `release_job_lock` exists
   - [ ] Add test for lock contention

4. **Phase 4 — SERP enrichment and cache** (implementing now)
   - [ ] Implement cache usage in `/api/enrich`
   - [ ] Add 1h/24h TTL policy
   - [ ] Add tests for cache hit/miss scenarios

5. **Phase 5 — Single-call Claude**
   - [ ] Replace multi-step chain with master prompt in `engines/ruflo_final_strategy_engine.py`
   - [ ] Add robust JSON parse fallback

6. **Phase 6 — Observability**
   - [ ] structlog structured logs
   - [ ] Prometheus metrics
   - [ ] Sentry events & alerting

7. **Phase 7 — Resilience and controls**
   - [ ] Rate limiting
   - [ ] API key quota
   - [ ] Retry/backoff

8. **Phase 8 — Production deployment**
   - [ ] Docker compose (api+worker+redis+db)
   - [ ] CI pipeline tests
   - [ ] Health+readiness probes

---

## Architecture plan (executive summary)

- Build *one primary workflow* in frontend:
  - Project selection -> keyword input + enrichment -> run strategy -> results dashboard.
- Keep *backend pipeline* stateful in `strategy_jobs` DB table; no in-memory `_jobs`.
- Use *Job tracker* and *worker* pairs with locking, retry, resume:
  - `queued` → `running` → `completed`/`failed`.
  - `is_locked`, `lock_key`, `last_completed_step`, `progress` tracked.
- Add SERP caching table to reduce API calls & cost.
- Add a dedicated API module at `frontend/src/lib/api/strategy.ts`.
- Support both polling and websocket updates (initially polling).
- Ensure each new behavior is backed by tests.

## Do we have everything to go to production?

Short answer: No.

Why not (concise):
- **Critical runtime blocker**: the backend currently fails to start; no API available for enqueueing or status.
- **No durable job persistence**: `_jobs` is still in-memory; `strategy_jobs` migrations and `job_tracker` aren't implemented.
- **Missing durable queue**: workers and Redis/RQ scaffolding not present or wired in.
- **LLM flow and SERP are incomplete**: multi-step LLM chain needs single-call refactor; SERP is a stub and requires caching + provider configuration.
- **Operational gaps**: no logging/metrics, alerting, auth/rate-limits, CI/CD, secrets management, or staged rollout testing.

Immediate recommended next steps (minimal path to a safe staging rollout):

1. Fix backend startup (capture traceback, patch failing import/runtime). — marked in todo as in-progress.
2. Add DB migrations for `strategy_jobs` and `serp_cache` and verify local Postgres.
3. Implement `services/job_tracker.py` and replace `_jobs` with DB-backed tracker; add GET `/api/jobs/{job_id}`.
4. Add Redis + RQ worker scaffolding and a simple worker that can run the current engine loop.
5. Perform the single-call `Claude` refactor and harden JSON parsing; persist raw LLM output for auditing.
6. Integrate SERP provider + caching and add cost controls.
7. Add structured logging, Prometheus metrics, Sentry alerts, and health endpoints.
8. Write tests (idempotency, resume) and create Docker/CI pipeline for staged deployment.

After these steps, run staging load tests and a small canary rollout before declaring production readiness.

## 20-Phase Implementation Plan

The following phased plan breaks the remaining work into 20 discrete, testable phases. Treat each phase as a small milestone with clear acceptance criteria so we can safely progress toward production.

Phase 1 — Fix Backend Boot (BLOCKER)
- Goal: Ensure `uvicorn main:app` starts reliably in local and CI environments.
- Deliverables: fix import/runtime errors, `GET /docs` returns 200, basic health endpoint passes.

Phase 2 — DB Migrations (Foundation)
- Goal: Add safe, idempotent migrations for `strategy_jobs`, `serp_cache`, and any missing columns.
- Deliverables: migration SQL scripts and a local migration runner.

Phase 3 — Job Tracker Service
- Goal: Implement `services/job_tracker.py` with CRUD, progress updates, and idempotency helpers.
- Deliverables: module, unit tests, and example usage.

Phase 4 — Replace In‑Memory Jobs
- Goal: Remove `_jobs` map and persist job lifecycle in `strategy_jobs`; add `GET /api/jobs/{job_id}`.
- Deliverables: API endpoints, DB-backed state, and SSE/stream integration.

Phase 5 — Queue & Worker Scaffolding
- Goal: Wire Redis + RQ (or Celery) with a simple worker capable of executing runs and emitting progress.
- Deliverables: `queue/connection.py`, `queue/worker.py`, docker-compose dev services.

Phase 6 — Idempotency & Locking
- Goal: Implement `lock_key` creation, `create_job` idempotency, and `acquire_lock()` semantics for workers.
- Deliverables: SQL + code + tests validating no double-execution on retries.

Phase 7 — Resume & Progress Semantics
- Goal: Persist `last_completed_step`, `current_step`, and `progress` so runs can resume after crashes.
- Deliverables: resume logic in workers and API-visible progress fields.

Phase 8 — Single‑Call LLM Refactor
- Goal: Replace the multi-step LLM chain with a single-call Claude flow producing strict JSON.
- Deliverables: refactored `engines/ruflo_final_strategy_engine.py`, validator tests, persisted raw output.

Phase 9 — Harden Model Call & Parsing
- Goal: Implement `_call_strategy_model` wrapper with retries, parse fallbacks, and token limits; persist raw responses.
- Deliverables: robust parsing util and retry tests.

Phase 10 — Real SERP Integration
- Goal: Replace stubs with a configurable SERP provider (SerpAPI/DataForSEO) and implement `engines/serp_engine.py`.
- Deliverables: provider adapter, config via env/API settings, and basic tests.

Phase 11 — SERP Cache & Policies
- Goal: Add `serp_cache` table, TTL logic, and cache invalidation policies to reduce cost and rate usage.
- Deliverables: cache upsert logic, TTL tests, cache hit/miss metrics.

Phase 12 — Structured Logging & Error Reporting
- Goal: Add `structlog` and Sentry error reporting; standardize logs with `job_id`, `phase`, `duration_ms`.
- Deliverables: logging config, Sentry integration, and sample alerts.

Phase 13 — Metrics & Observability
- Goal: Instrument key metrics (job counts, latencies, token usage) and expose `/metrics` for Prometheus.
- Deliverables: metrics middleware, dashboards, alert rules draft.

Phase 14 — Auth, Rate Limits & Quotas
- Goal: Add API key / JWT enforcement, `slowapi` rate limiting, and per-project quota enforcement (`MAX_TOKENS`, `MAX_SERP_CALLS`).
- Deliverables: middleware and tests for enforcement.

Phase 15 — Health, Readiness & Probes
- Goal: Implement `/healthz`, readiness/liveness endpoints and container probe docs for k8s/Compose.
- Deliverables: endpoints, docs, and smoke tests.

Phase 16 — Docker & CI/CD Pipeline
- Goal: Add `Dockerfile`, `docker-compose.yml` (api + worker + redis + db) and CI workflows to build/test/push images.
- Deliverables: working compose up for dev and CI pipeline templates.

Phase 17 — Tests & Staging Validation
- Goal: Add unit, integration, and end-to-end tests (idempotency, resume, SERP, engine run). Run tests in CI and staging.
- Deliverables: test suites and staging validation plan.

Phase 18 — Frontend Dashboard & Job UI
- Goal: Add Job Progress UI component and Strategy Dashboard scaffold integrated with job/status APIs.
- Deliverables: React components, API hooks, and staging UI build.

Phase 19 — Ranking Tracker & Change Detection
- Goal: Implement GSC client, `keyword_rankings` + `ranking_history` tables, change detection engine, and trigger diagnostics.
- Deliverables: `gsc_client.py`, scheduler job, and detection tests.

Phase 20 — Feedback Loop & Auto‑Strategy
- Goal: Map diagnosis -> actions -> apply suggestions or trigger strategy reruns with safety gates and audit logs.
- Deliverables: `feedback_engine.py`, auto-rerun triggers, manual approval gates, and runbooks.

---

If this phase breakdown looks good, I can start immediately on Phase 1 (fix backend boot). Which phase should I begin with, and do you have preferences for queue technology (RQ vs Celery) or the primary DB (Postgres vs SQLite) for production?
