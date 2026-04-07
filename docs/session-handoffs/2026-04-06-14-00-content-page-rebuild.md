# Session Handoff: Content Page Full Rebuild

**Created:** 2026-04-06
**Context usage at handoff:** ~90% (user requested fresh session)
**Reason for handoff:** User chose "Fresh session" for execution
**Session type:** Plan + execution handoff

---

## CRITICAL: The Next Session Has ZERO Context

The agent reading this has no memory of the previous session. Everything needed to continue is in this document.

---

## Session Configuration (MUST)

- **Commit preference:** No commits — user explicitly chose "No" for commits in plan
- **Question style:** Direct, decisive; user makes choices via lettered options and responds with single letter/word
- **Scope boundaries:** AnnaSEO v1 app at `/root/ANNASEOv1/`. Do not touch files outside this directory.
- **Planned workflow:** Plan written and approved → execute it now using `superpowers:subagent-driven-development`
- **Current position in workflow:** Plan is COMPLETE and APPROVED. Zero tasks executed yet. Ready to start Task 1.

## User Preferences Discovered (MUST)

- No commits during implementation (stated explicitly)
- Decisive style — prefers lettered option menus, responds with single character
- User chose "Full rebuild" (Approach C) — complete file extraction, not surgical patches
- User chose "Full telemetry" for rate limit dashboard
- User wants ALL three bug categories addressed equally (generation failures + rate limiting + UI/UX)
- Do not ask to verify before proceeding; trust the plan and execute
- User is comfortable with parallel subagent dispatching

## Task Overview (MUST)

**Original goal (quoted):** "Noticing too many issues, failure, bugs and problems with the Content page. The Content generation, Ai Hub and features are having too many issues and bugs. list all the critical code level and UI level bugs all 200 bugs only critical and fix them. /superpowers:brainstorm develop ideas to make this page clean and working fine without issues. Also ai models are rate limited at each internal I need a clean way of identification how much tokens are used, what is pending, which API is working, which is not. what are the issues with rate limit. how to reduce or handle rate limiting very efficiently. /superpowers:cleanup review complete code and do a cleanup. Develop plan and start executing"

**Approach decided:** Full rebuild (Approach C) — split 3,167-line ContentPage.jsx into focused components, add real-time Rate Limit Dashboard, and make AI provider health checks cache-first. Chosen because surgical fixes would leave the monolith intact and bugs would re-accumulate.

## Progress Summary (MUST)

### Completed
- [x] Critical bugs identified and documented
- [x] Architecture designed (component layout, state ownership, API design)
- [x] Spec written: `docs/superpowers/specs/2026-04-06-content-page-rebuild-design.md`
- [x] Implementation plan written and reviewed (2 rounds): `docs/superpowers/plans/2026-04-06-content-page-rebuild.md`
- [x] All plan review issues resolved (5 critical issues fixed across 2 review rounds)

### In Progress
- Nothing in progress — plan is approved, execution not started

### Remaining (all 13 plan tasks)
- [ ] Task 1: Backend — `/api/ai/status` endpoint
- [ ] Task 2: Backend — `/api/ai/usage` endpoint + instrumentation
- [ ] Task 3: Backend — Health check cache fix
- [ ] Task 4: Shared pipeline query hook (`usePipelineQuery`)
- [ ] Task 5: Adaptive article list polling hook (`useArticlePolling`)
- [ ] Task 6: Extract PromptsDrawer + MetaEditModal
- [ ] Task 7: Extract NewArticleModal
- [ ] Task 8: Extract ArticleListPanel
- [ ] Task 9: Extract PipelinePanel
- [ ] Task 10: Extract EditorPanel
- [ ] Task 11: Slim down ContentPage.jsx to ~150 lines
- [ ] Task 12: RateLimitDashboard component
- [ ] Task 13: Wire RateLimitDashboard into AIHub

## Files Being Modified (MUST)

| File | Status | Notes |
|------|--------|-------|
| `docs/superpowers/plans/2026-04-06-content-page-rebuild.md` | Created | The plan — read this before doing anything |
| `docs/superpowers/specs/2026-04-06-content-page-rebuild-design.md` | Created | Architecture spec |
| `frontend/src/ContentPage.jsx` | Planned (3,167 lines) | To be thinned to ~150 lines via extraction |
| `frontend/src/AIHub.jsx` | Planned (1,250 lines) | Add Rate Limits tab |
| `main.py` | Planned | Add `/api/ai/status`, `/api/ai/usage` endpoints; health check cache |
| `engines/content_generation_engine.py` | Planned | Add `_SESSION_USAGE`, `_live_key_for`, `_log_usage`, `_step_ctx_var`, instrument `_run_provider` |
| `frontend/src/hooks/usePipelineQuery.js` | To create | Shared pipeline polling hook |
| `frontend/src/hooks/useArticlePolling.js` | To create | Adaptive article list polling |
| `frontend/src/content/ArticleListPanel.jsx` | To create | Article list, lifecycle strip, bulk actions |
| `frontend/src/content/EditorPanel.jsx` | To create | TipTap editor, toolbar, ReviewPanel/RulesPanel |
| `frontend/src/content/PipelinePanel.jsx` | To create | Pipeline progress + console |
| `frontend/src/content/NewArticleModal.jsx` | To create | New article intake form |
| `frontend/src/content/PromptsDrawer.jsx` | To create | Prompt editor drawer |
| `frontend/src/content/MetaEditModal.jsx` | To create | Metadata edit modal |
| `frontend/src/aihub/RateLimitDashboard.jsx` | To create | Per-provider token telemetry |
| `tests/test_ai_status_endpoint.py` | To create | Tests for `/api/ai/status` |
| `tests/test_ai_usage_endpoint.py` | To create | Tests for `/api/ai/usage` |
| `tests/test_health_check_cache.py` | To create | Tests for health check caching |
| `frontend/src/hooks/usePipelineQuery.test.js` | To create | Pure-logic tests for pipeline hook |
| `frontend/src/hooks/useArticlePolling.test.js` | To create | Pure-logic tests for polling hook |

## Key Technical Decisions (MUST)

1. **React Query v5 `refetchInterval` signature:** In v5 (`@tanstack/react-query ^5.45.0`), `refetchInterval` receives the full query object — use `(query) => query.state.data?.status` not `(data) => data?.status`. This is different from v4.

2. **Auth dependency name:** In `main.py`, the correct auth dependency is `Depends(current_user)` at line 644: `async def current_user(token: str=Depends(oauth2_scheme))`. There is NO function named `get_current_user` — that name does not exist and will crash imports.

3. **Test auth pattern:** `tests/conftest.py` has NO `get_test_token` function. All test files must use: `app.dependency_overrides[current_user] = lambda: {"username": "test"}` at module level.

4. **`_run_provider` is a nested async function:** It's defined inside `_call_ai_with_chain` (line 3713) and `_call_ai_raw_with_chain` (line 3827) in `content_generation_engine.py`. It's recreated on every call so function-attribute tricks (`_run_provider._step = 1`) do NOT work. Must use `contextvars.ContextVar` for cross-call state propagation.

5. **Existing health check cache:** `main.py` already has `_provider_live_status_cache`, `_cached_live_test(key)`, `_cache_live_test(key, result)` at lines 2445–2467 with 300s TTL. Gemini free/paid already use it. Do NOT create a new `_HEALTH_CACHE` dict — extend the existing pattern to other providers via a thin `_health_cached(provider, live_fn, force)` wrapper.

6. **No new Zustand/Context:** State is prop-drilled max 2 levels. `openPanel: "review" | "rules" | null` replaces two separate boolean states.

7. **`_log_usage` signature:** Final 2-arg form: `_log_usage(provider: str, result_text: str)`. Step context (step number, step name, article_id) is read from `_step_ctx_var: contextvars.ContextVar` — not passed as arguments. Tests must call `_step_ctx_var.set({...})` before calling `_log_usage`.

8. **Vitest version:** `^0.34.0` — no `@testing-library/react`. Frontend tests are pure-function tests only (no React component rendering). Test command: `npx vitest run src/`.

9. **`_health_cached` cache key semantics:** Provider name strings like `"groq"`, `"anthropic"` are passed to `_cached_live_test()`. That function SHA-256 hashes whatever string it receives — using provider names works correctly even though the function's comment says "API key". This is intentional.

10. **No commits** — user explicitly does not want commits during this implementation.

## Context and Constraints (MUST)

- **Production-only deployment:** FastAPI + SQLite (dev) / PostgreSQL (prod). The app runs at `/root/ANNASEOv1/`.
- **`main.py` health checks are synchronous:** `ai_health_check` uses `httpx.get()`/`httpx.post()` (no `await`). The `_health_cached` wrapper must use sync `live_fn` callables. Don't accidentally add `await`.
- **`_provider_health_cache` vs `_provider_live_status_cache`:** Two different dicts. `_provider_health_cache` is in `content_generation_engine.py` (line 251) and stores rate-limit state (provider → blocked status/until). `_provider_live_status_cache` is in `main.py` (line 2447) and stores live-test results. They serve different purposes.
- **`_key_health` keyed by hash:** `_key_health` in `content_generation_engine.py` is keyed by `_key_hash(key)` which is `sha256(key)[:16]`. To look up token data for a provider, call `_live_key_for(provider)` → get the key → call `_key_hash(key)` → look up in `_key_health`.
- **`_live_key_for` must be added:** It does NOT yet exist in `content_generation_engine.py`. Task 1 Step 1 adds it.
- **Ollama health check has two sub-variants:** static local and dynamic remote (loaded from DB). Dynamic remotes use `row['server_id']` as cache key.
- **ContentPage.jsx extraction order matters:** Tasks 6–11 extract components in dependency order. Task 8 (ArticleListPanel) needs PipelineProgress but Task 9 hasn't moved it yet. See plan Task 8 for the resolution (include a minimal inline progress bar or temporarily import from ContentPage.jsx).

## Open Questions (SHOULD)

- None blocking. All decisions were made and locked.

## Test Status (MUST)

- **Tests passing:** Not run yet (no implementation started)
- **New tests to add:**
  - `tests/test_ai_status_endpoint.py`
  - `tests/test_ai_usage_endpoint.py`
  - `tests/test_health_check_cache.py`
  - `frontend/src/hooks/usePipelineQuery.test.js`
  - `frontend/src/hooks/useArticlePolling.test.js`
- **How to run backend tests:** `cd /root/ANNASEOv1 && python -m pytest tests/ -v --tb=short -q`
- **How to run frontend tests:** `cd /root/ANNASEOv1/frontend && npx vitest run src/`

## Next Steps (MUST)

When resuming, the agent MUST:

1. **Read the full plan first:** `docs/superpowers/plans/2026-04-06-content-page-rebuild.md` — it has all implementation steps, code snippets, and test content.

2. **Use `superpowers:subagent-driven-development`** skill to execute the plan task by task (user chose subagent-driven execution).

3. **Start with Task 1** (Backend — `/api/ai/status` endpoint):
   - Add `_live_key_for()` helper to `engines/content_generation_engine.py` after `_resolve_key_pool` (~line 100)
   - Write failing test at `tests/test_ai_status_endpoint.py` (full test code is in the plan)
   - Run tests to verify they fail
   - Add `/api/ai/status` endpoint to `main.py` near existing `/api/ai/health` (~line 1728)
   - Run tests to verify they pass

4. **Follow TDD red-green cycle** for each backend task (write failing test → implement → verify pass).

5. **No commits** at any point — just save/checkpoint files.

6. **After all 13 tasks complete:** Use `superpowers:finishing-a-development-branch` to review and present completion options to user.

## Related Files (SHOULD)

- **Plan:** `docs/superpowers/plans/2026-04-06-content-page-rebuild.md` (READ THIS FIRST)
- **Spec:** `docs/superpowers/specs/2026-04-06-content-page-rebuild-design.md`
- **This handoff:** `docs/session-handoffs/2026-04-06-14-00-content-page-rebuild.md`
