# Content Page + AI Hub Full Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 9 critical bugs, split the 3,167-line ContentPage into focused components, add a real-time Rate Limit Dashboard, and make AI provider health checks cache-first.

**Architecture:** Frontend splits into `content/` sub-components backed by two shared React Query hooks. Backend gains two zero-cost endpoints (`/api/ai/status`, `/api/ai/usage`) that read from existing in-memory caches without live API calls. Health check becomes cache-first with 5-minute TTL.

**Tech Stack:** React 18 + Vite 5, React Query v5 (`@tanstack/react-query ^5.45.0`), Vitest 0.34, FastAPI, Python 3.12, httpx (sync), SQLite/PostgreSQL

**Spec:** `docs/superpowers/specs/2026-04-06-content-page-rebuild-design.md`

**No commits in this plan** — save/checkpoint frequently.

---

## File Map

### New files to create

| File | Responsibility |
|---|---|
| `frontend/src/hooks/usePipelineQuery.js` | Shared React Query v5 hook for pipeline polling |
| `frontend/src/hooks/useArticlePolling.js` | Adaptive article list polling |
| `frontend/src/content/ArticleListPanel.jsx` | Article list, lifecycle strip, bulk actions |
| `frontend/src/content/EditorPanel.jsx` | TipTap editor, toolbar, ReviewPanel/RulesPanel wiring |
| `frontend/src/content/PipelinePanel.jsx` | Pipeline progress + console, uses shared hook |
| `frontend/src/content/NewArticleModal.jsx` | New article intake form |
| `frontend/src/content/PromptsDrawer.jsx` | Prompt editor drawer |
| `frontend/src/content/MetaEditModal.jsx` | Metadata edit modal |
| `frontend/src/aihub/RateLimitDashboard.jsx` | Per-provider token telemetry panel |

### Files to modify

| File | Changes |
|---|---|
| `frontend/src/ContentPage.jsx` | Thin down to ~150-line router using extracted components |
| `frontend/src/AIHub.jsx` | Add Rate Limit tab, import RateLimitDashboard |
| `main.py` | Add `/api/ai/status`, `/api/ai/usage` endpoints; health check cache |
| `engines/content_generation_engine.py` | Add `_SESSION_USAGE`, `_live_key_for`, instrument `_run_provider()` |

---

## Part 1 — Backend

### Task 1: Backend — `/api/ai/status` endpoint

**Files:**
- Modify: `engines/content_generation_engine.py` (add `_live_key_for` helper)
- Modify: `main.py` (add endpoint, import new helper)
- Test: `tests/test_ai_status_endpoint.py`

Context: Two in-memory caches already exist in `engines/content_generation_engine.py`:
- `_provider_health_cache` (line 251): `provider_name → {"status": reason, "until": timestamp}`
- `_key_health` (line 181): `sha256(key)[:16] → {"remaining_tokens", "remaining_requests", "daily_exhausted", "ts"}`
- `_key_hash(key)` already exists (line 183)
- `_live_groq_key()` already exists (line 69)

**Auth note:** The correct auth dependency in `main.py` is `Depends(current_user)` (line 644: `async def current_user(token: str=Depends(oauth2_scheme))`). Do NOT use `Depends(get_current_user)` — that function name does not exist in `main.py`.

- [ ] **Step 1: Add `_live_key_for` helper to `engines/content_generation_engine.py`**

Add this after the `_resolve_key_pool` function (around line 100):

```python
def _live_key_for(provider: str) -> str:
    """Return the primary API key for a provider (for key_health lookup)."""
    mapping = {
        "groq": lambda: os.getenv("GROQ_API_KEY", ""),
        "gemini_free": lambda: os.getenv("GEMINI_API_KEY", ""),
        "gemini_paid": lambda: os.getenv("GEMINI_PAID_API_KEY", ""),
        "anthropic": lambda: os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_PAID_API_KEY", ""),
        "openai_paid": lambda: os.getenv("OPENAI_API_KEY", "") or os.getenv("OPENAI_PAID_API_KEY", ""),
        "openrouter": lambda: os.getenv("OPENROUTER_API_KEY", ""),
    }
    fn = mapping.get(provider)
    return fn() if fn else ""
```

- [ ] **Step 2: Write failing test for `/api/ai/status`**

Create `tests/test_ai_status_endpoint.py`:

```python
"""Tests for /api/ai/status endpoint — reads from cache, no live API calls."""
import time
import pytest
from fastapi.testclient import TestClient

from main import app, current_user
import engines.content_generation_engine as cge

# Bypass auth for all tests in this file by overriding the dependency
# (tests/conftest.py has no get_test_token — override the dependency instead)
app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_ai_status_returns_canonical_providers():
    """Endpoint should return entries for all canonical providers."""
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    for provider in ["groq", "gemini_free", "gemini_paid", "anthropic", "ollama"]:
        assert provider in data, f"Expected {provider} in response"

def test_ai_status_rate_limited_provider():
    """When a provider is in _provider_health_cache, status should be rate_limited."""
    cge._provider_health_cache["groq"] = {
        "status": "rate_limited",
        "until": time.time() + 60,
    }
    try:
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert data["groq"]["status"] == "rate_limited"
        assert data["groq"]["seconds_remaining"] > 0
    finally:
        cge._provider_health_cache.pop("groq", None)

def test_ai_status_expired_cache_entry():
    """Expired cache entries (until in the past) should resolve to 'ok'."""
    cge._provider_health_cache["groq"] = {
        "status": "rate_limited",
        "until": time.time() - 10,  # already expired
    }
    try:
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert data["groq"]["status"] == "ok"
    finally:
        cge._provider_health_cache.pop("groq", None)

def test_ai_status_no_live_api_calls(monkeypatch):
    """The endpoint must not make any external HTTP calls (no httpx.get or httpx.post)."""
    import httpx
    called = []
    def mock_get(url, *args, **kwargs): called.append(("get", url))
    def mock_post(url, *args, **kwargs): called.append(("post", url))
    monkeypatch.setattr(httpx, "get", mock_get)
    monkeypatch.setattr(httpx, "post", mock_post)
    client.get("/api/ai/status")
    assert len(called) == 0, f"Made unexpected HTTP calls: {called}"
```

- [ ] **Step 3: Run tests to verify they fail correctly**

```bash
cd /root/ANNASEOv1
python -m pytest tests/test_ai_status_endpoint.py -v 2>&1 | head -40
```

Expected: `FAILED` with `404` or `AttributeError` (endpoint doesn't exist yet).

- [ ] **Step 4: Add `/api/ai/status` to `main.py`**

Add this near the existing `/api/ai/health` endpoint (around line 1728). Import `_provider_health_cache`, `_key_health`, `_key_hash`, `_live_key_for` from the engine at the top of the relevant section or at the module import block:

```python
# Add near top of main.py with other engine imports
from engines.content_generation_engine import (
    _provider_health_cache,
    _key_health,
    _key_hash,
    _live_key_for,
)

@app.get("/api/ai/status", tags=["AI Hub"])
async def ai_status_check(current_user=Depends(current_user)):
    """
    Read provider status from in-memory caches. Zero live API calls.
    Returns rate-limit state, cooldown timers, and key-level token health.
    """
    import time as _t
    now = _t.time()
    canonical = ["groq", "gemini_free", "gemini_paid", "anthropic", "openai_paid", "ollama", "openrouter"]
    result = {}
    for provider in canonical:
        entry = _provider_health_cache.get(provider, {})
        blocked_until = entry.get("until")
        is_blocked = bool(blocked_until and now < blocked_until)
        row = {
            "status": entry.get("status", "ok") if is_blocked else "ok",
            "blocked_until": blocked_until if is_blocked else None,
            "seconds_remaining": max(0, int(blocked_until - now)) if is_blocked else 0,
            "rate_limit_info": {},
        }
        # Attach key-level token health (Groq + OpenRouter expose these via response headers)
        key = _live_key_for(provider)
        if key:
            kh = _key_health.get(_key_hash(key), {})
            if kh:
                row["rate_limit_info"] = {
                    "tokens_remaining": kh.get("remaining_tokens"),
                    "requests_remaining": kh.get("remaining_requests"),
                    "daily_exhausted": kh.get("daily_exhausted", False),
                    "last_seen": kh.get("ts"),
                }
        result[provider] = row
    return result
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd /root/ANNASEOv1
python -m pytest tests/test_ai_status_endpoint.py -v
```

Expected: all 4 tests PASS.

---

### Task 2: Backend — `/api/ai/usage` endpoint + instrumentation

**Files:**
- Modify: `engines/content_generation_engine.py` (add `_SESSION_USAGE`, instrument `_run_provider`)
- Modify: `main.py` (add endpoint)
- Test: `tests/test_ai_usage_endpoint.py`

Context: `_run_provider()` is the central AI call dispatcher (around lines 760–840 in `content_generation_engine.py`). It's called with `(provider, prompt, ...)` and returns a result string. After a successful call is the right place to log usage.

- [ ] **Step 1: Add `_SESSION_USAGE` list to `engines/content_generation_engine.py`**

Add after `_provider_health_cache` declaration (around line 251):

```python
# Session-level usage log — in-memory, wiped on process restart.
# Entries appended by _run_provider() after each successful AI call.
_SESSION_USAGE: list = []
_SESSION_USAGE_MAX = 500  # cap to prevent unbounded growth

def _log_usage(provider: str, step: int, step_name: str, result_text: str, article_id: str = None):
    """Append a token usage entry. Estimates tokens from word count for providers without headers."""
    word_count = len(result_text.split()) if result_text else 0
    tokens_estimated = int(word_count * 1.35)  # rough tokens-per-word ratio
    if len(_SESSION_USAGE) >= _SESSION_USAGE_MAX:
        _SESSION_USAGE.pop(0)
    _SESSION_USAGE.append({
        "provider": provider,
        "step": step,
        "step_name": step_name,
        "tokens_estimated": tokens_estimated,
        "ts": _time.time(),
        "article_id": article_id,
    })
```

- [ ] **Step 2: Add `contextvars.ContextVar` for step context + instrument `_exec_ai_with_fallback`**

**Why not function attributes:** `_run_provider` is defined as a **nested async function** inside `_call_ai_with_chain` / `_call_ai_raw_with_chain` — it is recreated on every call. Setting attributes on it from outside is impossible because callers never hold a reference to the inner function object. Use `contextvars.ContextVar` instead (safe for async/await pipelines, no thread-local issues).

Add near the top of `engines/content_generation_engine.py`, after imports:
```python
import contextvars as _cv
_step_ctx_var: _cv.ContextVar[dict] = _cv.ContextVar("_step_ctx", default={})
```

Change `_log_usage` signature to read from context (update the function from Step 1):
```python
def _log_usage(provider: str, result_text: str):
    """Append usage entry; reads step context from _step_ctx_var."""
    ctx = _step_ctx_var.get()
    word_count = len(result_text.split()) if result_text else 0
    tokens_estimated = int(word_count * 1.35)
    if len(_SESSION_USAGE) >= _SESSION_USAGE_MAX:
        _SESSION_USAGE.pop(0)
    _SESSION_USAGE.append({
        "provider": provider,
        "step": ctx.get("step", 0),
        "step_name": ctx.get("step_name", ""),
        "tokens_estimated": tokens_estimated,
        "ts": _time.time(),
        "article_id": ctx.get("article_id"),
    })
```

At the start of each `_step_N` method in `SEOContentPipeline`, set the context:
```python
# Example — search for all methods matching async def _step_ in the class
_step_ctx_var.set({"step": 1, "step_name": "Research", "article_id": getattr(self, "article_id", None)})
```

**There is no function named `_exec_ai_with_fallback`.** The two outer methods containing `_run_provider` nested functions are:

1. `_call_ai_with_chain` (line 3713) — JSON path. Inside the nested `_run_provider`, the success path is line 3765: `return self._normalize_json_fields(cr.json_data)`. Add logging just before this return.
2. `_call_ai_raw_with_chain` (line 3827) — raw text path. Inside its nested `_run_provider`, the success path is line 3879: `return cr.text`. Add logging just before this return.

Add the same pattern in both locations:
```python
# Add BEFORE the return statement at line 3765 (JSON path):
try:
    _log_usage(provider, cr.text if hasattr(cr, "text") and cr.text else str(cr.json_data))
except Exception:
    pass  # Never let logging break the pipeline
return self._normalize_json_fields(cr.json_data)

# Add BEFORE the return statement at line 3879 (raw text path):
try:
    _log_usage(provider, cr.text)
except Exception:
    pass  # Never let logging break the pipeline
return cr.text
```

- [ ] **Step 3: Write failing test**

Create `tests/test_ai_usage_endpoint.py`:

```python
"""Tests for /api/ai/usage endpoint and _log_usage instrumentation."""
import pytest
from fastapi.testclient import TestClient
from main import app, current_user
import engines.content_generation_engine as cge

app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_usage_endpoint_returns_list():
    resp = client.get("/api/ai/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "usage" in data
    assert isinstance(data["usage"], list)

def test_log_usage_appends_entry():
    # _log_usage(provider, result_text) reads step context from _step_ctx_var
    cge._step_ctx_var.set({"step": 1, "step_name": "Research", "article_id": "article-123"})
    before = len(cge._SESSION_USAGE)
    cge._log_usage("groq", "This is a test result with some words")
    assert len(cge._SESSION_USAGE) == before + 1
    entry = cge._SESSION_USAGE[-1]
    assert entry["provider"] == "groq"
    assert entry["step"] == 1
    assert entry["tokens_estimated"] > 0
    assert entry["article_id"] == "article-123"

def test_usage_filter_by_article_id():
    cge._step_ctx_var.set({"step": 2, "step_name": "Structure", "article_id": "test-article-xyz"})
    cge._log_usage("groq", "filtered content")
    resp = client.get("/api/ai/usage?article_id=test-article-xyz")
    data = resp.json()
    assert all(e["article_id"] == "test-article-xyz" for e in data["usage"])

def test_log_usage_caps_at_max():
    """Should not grow beyond _SESSION_USAGE_MAX."""
    cge._SESSION_USAGE.clear()
    cge._step_ctx_var.set({"step": 1, "step_name": "Test", "article_id": None})
    for i in range(cge._SESSION_USAGE_MAX + 10):
        cge._log_usage("groq", "x")
    assert len(cge._SESSION_USAGE) <= cge._SESSION_USAGE_MAX
```

- [ ] **Step 4: Run tests — expect fail**

```bash
python -m pytest tests/test_ai_usage_endpoint.py -v 2>&1 | head -30
```

Expected: FAIL (`ImportError` or `404`).

- [ ] **Step 5: Add `/api/ai/usage` to `main.py`**

Add near `/api/ai/status`:

```python
from engines.content_generation_engine import _SESSION_USAGE, _log_usage

@app.get("/api/ai/usage", tags=["AI Hub"])
async def ai_usage_log(article_id: Optional[str] = None, current_user=Depends(current_user)):
    """Per-provider, per-step token usage log for the current server session."""
    data = list(_SESSION_USAGE)  # snapshot
    if article_id:
        data = [e for e in data if e.get("article_id") == article_id]
    return {"usage": data[-200:]}
```

- [ ] **Step 6: Run tests — expect pass**

```bash
python -m pytest tests/test_ai_usage_endpoint.py -v
```

Expected: all 4 tests PASS.

---

### Task 3: Backend — Health check cache fix

**Files:**
- Modify: `main.py` (add `_HEALTH_CACHE`, `_health_cached` helper, wrap each provider block)
- Test: `tests/test_health_check_cache.py`

Context: `ai_health_check` at line 1728 in `main.py` has separate test blocks for Ollama (static + dynamic remote), Groq, Gemini free/paid, Anthropic, OpenAI, and OpenRouter. Each block uses synchronous `httpx.get()`/`httpx.post()` calls.

**Important:** `main.py` already has a 5-minute caching mechanism: `_provider_live_status_cache`, `_cached_live_test(key)`, `_cache_live_test(key, result)` at lines 2445–2467. **Gemini free and paid already use this cache** (lines 1790, 1812). The fix extends this same pattern to the other providers (Groq, Ollama, Anthropic, OpenAI, OpenRouter) — do NOT create a separate `_HEALTH_CACHE` dict. Reuse what's already there.

- [ ] **Step 1: Write failing test**

Create `tests/test_health_check_cache.py`:

```python
"""Health check should return cached results within 5 minutes."""
import time
import pytest
from fastapi.testclient import TestClient
from main import app, current_user, _provider_live_status_cache

app.dependency_overrides[current_user] = lambda: {"username": "test"}
client = TestClient(app)

def test_second_health_check_uses_cache(monkeypatch):
    """Second call within TTL should not make new HTTP calls for any provider."""
    import httpx
    call_counts = {"get": 0, "post": 0}
    orig_get, orig_post = httpx.get, httpx.post
    def counting_get(url, *a, **kw):
        call_counts["get"] += 1
        return orig_get(url, *a, **kw)
    def counting_post(url, *a, **kw):
        call_counts["post"] += 1
        return orig_post(url, *a, **kw)
    monkeypatch.setattr(httpx, "get", counting_get)
    monkeypatch.setattr(httpx, "post", counting_post)
    _provider_live_status_cache.clear()
    client.get("/api/ai/health")
    first_total = call_counts["get"] + call_counts["post"]
    client.get("/api/ai/health")
    second_total = call_counts["get"] + call_counts["post"]
    assert second_total == first_total, "Second health check should be fully cached"

def test_force_param_bypasses_cache(monkeypatch):
    """?force=true should bypass the cache and make live calls."""
    import httpx
    call_counts = {"get": 0, "post": 0}
    orig_get, orig_post = httpx.get, httpx.post
    def counting_get(url, *a, **kw): call_counts["get"] += 1; return orig_get(url, *a, **kw)
    def counting_post(url, *a, **kw): call_counts["post"] += 1; return orig_post(url, *a, **kw)
    monkeypatch.setattr(httpx, "get", counting_get)
    monkeypatch.setattr(httpx, "post", counting_post)
    _provider_live_status_cache.clear()
    client.get("/api/ai/health")
    first_total = call_counts["get"] + call_counts["post"]
    client.get("/api/ai/health?force=true")
    second_total = call_counts["get"] + call_counts["post"]
    assert second_total > first_total, "force=true should bypass cache and make new calls"
```

- [ ] **Step 2: Run tests — expect fail**

```bash
python -m pytest tests/test_health_check_cache.py -v 2>&1 | head -20
```

Expected: FAIL — second call makes the same number of HTTP calls as first (providers not wrapped in cache logic yet).

- [ ] **Step 3: Add `_health_cached` helper to `main.py`**

`main.py` already has `_provider_live_status_cache`, `_cached_live_test(key)`, `_cache_live_test(key, result)` at lines 2445–2467. **Do NOT create a new `_HEALTH_CACHE` dict.** Add a thin wrapper that reuses the existing infrastructure — place it immediately after `_cache_live_test` (around line 2468):

```python
def _health_cached(provider: str, live_fn, force: bool = False) -> dict:
    """
    Cache wrapper for health check blocks — reuses existing _provider_live_status_cache.
    live_fn is a zero-arg sync callable (httpx.get/post, no await).
    TTL is 300s (inherited from _PROVIDER_STATUS_CACHE_TTL via _cached_live_test).

    NOTE: `provider` is passed as the cache key string (e.g. "groq", "anthropic").
    _cached_live_test hashes it consistently via SHA-256 — this is correct intentional
    usage. The variable name in _cached_live_test's docstring says "API key" but the
    function just hashes whatever string is given; provider names work fine as keys.
    """
    if not force:
        cached = _cached_live_test(provider)  # provider name is the cache key
        if cached is not None:
            return {**cached, "_cached": True}
    result = live_fn()
    _cache_live_test(provider, result)
    return result
```

Also add the `force` query param to the health check endpoint signature:
```python
@app.get("/api/ai/health", tags=["AI"])
async def ai_health_check(force: bool = False):
```

- [ ] **Step 4: Wrap each provider block in `ai_health_check` with `_health_cached`**

Gemini free/paid may already call `_cached_live_test`/`_cache_live_test` directly (lines ~1790, 1812). Convert them to use `_health_cached` for consistency, then wrap all remaining providers.

For example, the Groq block (around line 1769) becomes:

```python
results["groq"] = _health_cached("groq", lambda: <existing groq test block code>, force=force)
```

For dynamic Ollama remote servers (loaded from DB), use the server's ID as the cache key:
```python
results[f"ollama_remote_{row['server_id']}"] = _health_cached(
    f"ollama_remote_{row['server_id']}",
    lambda row=row: <existing remote ollama test block>,
    force=force
)
```

Wrap all provider blocks: `ollama_local`, `groq`, `gemini_free`, `gemini_paid`, `anthropic`, `openai_paid`, `openrouter`, and each dynamic `ollama_remote_*`.

- [ ] **Step 5: Run tests — expect pass**

```bash
python -m pytest tests/test_health_check_cache.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run full backend test suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```

Expected: no new failures. If any existing tests fail, investigate before continuing.

---

## Part 2 — Frontend Hooks

### Task 4: Shared pipeline query hook

**Files:**
- Create: `frontend/src/hooks/usePipelineQuery.js`
- Test: `frontend/src/hooks/usePipelineQuery.test.js`

Context: React Query v5 is installed. `refetchInterval` in v5 receives the query object (not raw data). The hook replaces three separate, identical `useQuery` calls currently in `PipelineProgress`, `PipelineConsole`, and `PipelineLogsView` inside `ContentPage.jsx`.

- [ ] **Step 1: Write test for hook config logic**

Create `frontend/src/hooks/usePipelineQuery.test.js`:

```js
import { test, expect } from 'vitest'

// Test the refetchInterval logic in isolation (pure function)
function calcRefetchInterval(articleId, data) {
  if (!articleId || !data || data.status !== "generating") return false
  return data.is_paused ? 5000 : 2000
}

test('returns false when articleId is null', () => {
  expect(calcRefetchInterval(null, { status: "generating" })).toBe(false)
})

test('returns false when data is null', () => {
  expect(calcRefetchInterval("art-1", null)).toBe(false)
})

test('returns false when status is draft', () => {
  expect(calcRefetchInterval("art-1", { status: "draft" })).toBe(false)
})

test('returns 2000 when generating and not paused', () => {
  expect(calcRefetchInterval("art-1", { status: "generating", is_paused: false })).toBe(2000)
})

test('returns 5000 when generating and paused', () => {
  expect(calcRefetchInterval("art-1", { status: "generating", is_paused: true })).toBe(5000)
})
```

- [ ] **Step 2: Run tests — expect pass (pure logic)**

```bash
cd /root/ANNASEOv1/frontend && npx vitest run src/hooks/usePipelineQuery.test.js
```

Expected: 5 tests PASS (pure logic, no React Query needed).

- [ ] **Step 3: Create `frontend/src/hooks/usePipelineQuery.js`**

```js
import { useQuery } from "@tanstack/react-query"
import { api } from "../App"

/**
 * Shared pipeline polling hook.
 * All consumers (PipelinePanel, compact list item, PipelineLogsView) share
 * one in-flight request via React Query's key deduplication.
 *
 * Polling schedule:
 *   - not generating: off
 *   - generating + paused: every 5s
 *   - generating + running: every 2s
 */
export function usePipelineQuery(articleId) {
  return useQuery({
    queryKey: ["pipeline", articleId],
    queryFn: () => api.get(`/api/content/${articleId}/pipeline`),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!articleId || !data || data.status !== "generating") return false
      return data.is_paused ? 5000 : 2000
    },
    enabled: !!articleId,
    staleTime: 0,
  })
}
```

---

### Task 5: Adaptive article list polling hook

**Files:**
- Create: `frontend/src/hooks/useArticlePolling.js`
- Test: `frontend/src/hooks/useArticlePolling.test.js`

- [ ] **Step 1: Write test for polling interval logic**

Create `frontend/src/hooks/useArticlePolling.test.js`:

```js
import { test, expect } from 'vitest'

function calcArticleInterval(articles) {
  if (!articles || articles.length === 0) return false
  return articles.some(a => a.status === "generating") ? 3000 : false
}

test('returns false for empty array', () => {
  expect(calcArticleInterval([])).toBe(false)
})

test('returns false when no articles are generating', () => {
  const articles = [
    { status: "draft" },
    { status: "approved" },
    { status: "published" },
  ]
  expect(calcArticleInterval(articles)).toBe(false)
})

test('returns 3000 when any article is generating', () => {
  const articles = [
    { status: "draft" },
    { status: "generating" },
  ]
  expect(calcArticleInterval(articles)).toBe(3000)
})

test('returns 3000 when generating article is also paused (paused = sub-state of generating)', () => {
  // is_paused is a sub-state; top-level status remains "generating"
  const articles = [{ status: "generating", is_paused: true }]
  expect(calcArticleInterval(articles)).toBe(3000)
})
```

- [ ] **Step 2: Run tests — expect pass**

```bash
cd /root/ANNASEOv1/frontend && npx vitest run src/hooks/useArticlePolling.test.js
```

- [ ] **Step 3: Create `frontend/src/hooks/useArticlePolling.js`**

```js
import { useQuery } from "@tanstack/react-query"
import { api } from "../App"

/**
 * Adaptive article list polling.
 * Polls every 3s while any article is generating; stops otherwise.
 * Paused articles retain status "generating" so they continue at 3s (intentional).
 */
export function useArticlePolling(projectId) {
  return useQuery({
    queryKey: ["articles", projectId],
    queryFn: () =>
      projectId
        ? api.get(`/api/projects/${projectId}/content`).then(d => Array.isArray(d) ? d : [])
        : Promise.resolve([]),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const articles = query.state.data || []
      return articles.some(a => a.status === "generating") ? 3000 : false
    },
  })
}
```

---

## Part 3 — Frontend Component Extraction

### Task 6: Extract PromptsDrawer + MetaEditModal

**Files:**
- Create: `frontend/src/content/PromptsDrawer.jsx`
- Create: `frontend/src/content/MetaEditModal.jsx`
- Modify: `frontend/src/ContentPage.jsx` (replace inline definitions with imports)

These are pure extractions — zero behavior changes.

- [ ] **Step 1: Create `frontend/src/content/MetaEditModal.jsx`**

Cut the entire `MetaEditModal` function from `ContentPage.jsx` (lines ~1220–1260). Paste into new file:

```jsx
import { useState } from "react"
import { T, Btn } from "../App"

export default function MetaEditModal({ article, onClose, onSave }) {
  // ... (exact code from ContentPage.jsx, no changes)
}
```

- [ ] **Step 2: Create `frontend/src/content/PromptsDrawer.jsx`**

Cut the entire `PromptsDrawer` function from `ContentPage.jsx` (lines ~1262–1428). Paste into new file:

```jsx
import { useState, useEffect } from "react"
import { T, api, Btn } from "../App"

export default function PromptsDrawer({ onClose, onTest }) {
  // ... (exact code from ContentPage.jsx, no changes)
}
```

- [ ] **Step 3: Add imports to `ContentPage.jsx`**

Replace the deleted function bodies with imports at the top of the file:

```jsx
import MetaEditModal from "./content/MetaEditModal"
import PromptsDrawer from "./content/PromptsDrawer"
```

- [ ] **Step 4: Verify in browser**

Start the app if not running:
```bash
cd /root/ANNASEOv1/frontend && npm run dev
```

Navigate to Content page → click ✏️ (prompts button) → drawer should open as before.
Click edit meta on an article → modal should open as before.

---

### Task 7: Extract NewArticleModal

**Files:**
- Create: `frontend/src/content/NewArticleModal.jsx`
- Modify: `frontend/src/ContentPage.jsx`

This contains all the constants: `INTENT_OPTIONS`, `WC_OPTIONS`, `CT_OPTIONS`, `PAGE_TYPE_OPTIONS`, `PAGE_TYPE_WC`, `AI_PROVIDERS_BASE`, `ROUTING_TASKS`, `ROUTING_PRESETS`, `DEFAULT_ROUTING`, `EMPTY_FORM`, `_buildProviders`, `AI_PROVIDER_OPTIONS`, `_providerMeta`, plus the `NewArticleModal` component itself.

- [ ] **Step 1: Create `frontend/src/content/NewArticleModal.jsx`**

Cut from `ContentPage.jsx` (lines ~1431–2286):
- All the constants listed above
- The `NewArticleModal` function
- `RESEARCH_AI_OPTIONS` constant

Add these imports at the top of the new file:
```jsx
import { useState, useEffect } from "react"
import { T, api, Btn } from "../App"
```

Export the component as default. Also named-export the constants that other files need:
```jsx
export { AI_PROVIDERS_BASE, AI_PROVIDER_OPTIONS, _buildProviders, _providerMeta, ROUTING_PRESETS, DEFAULT_ROUTING }
export default NewArticleModal
```

- [ ] **Step 2: Update `ContentPage.jsx` imports**

```jsx
import NewArticleModal, {
  AI_PROVIDERS_BASE, AI_PROVIDER_OPTIONS, _buildProviders, _providerMeta, ROUTING_PRESETS, DEFAULT_ROUTING
} from "./content/NewArticleModal"
```

Note: `AI_PROVIDERS_BASE` and helper functions are also used by `AIHub.jsx`. Check `AIHub.jsx` imports — if it currently defines its own provider constants, no change needed there. Only update if it imports from `ContentPage`.

- [ ] **Step 3: Verify in browser**

Open Content → "New Article" button → modal appears with all tabs, routing presets, page type selector, form fields working correctly.

---

### Task 8: Extract ArticleListPanel

**Files:**
- Create: `frontend/src/content/ArticleListPanel.jsx`
- Modify: `frontend/src/ContentPage.jsx`

Bug fixes bundled in:
- **Bug #1:** `ArticleItem` Regen button `|| 100` → `|| 0` (line ~821)
- **Bug #7:** `bulkDelete` stale closure — pass IDs via mutation argument

- [ ] **Step 1: Create `frontend/src/content/ArticleListPanel.jsx`**

This component receives:
```jsx
// Props:
// projectId, selected, onSelect, onEditMeta, onShowGenModal, onShowPrompts, onTestKeyword
```

Cut from `ContentPage.jsx`:
- `STATUS_COLOR`, `LIFECYCLE` constants (or import from a shared constants file — but since they're small, include them)
- `LifecycleStrip` component
- `ArticleItem` component
- The left-panel JSX (article list, lifecycle strip, bulk toolbar)
- Bulk selection state (`bulkSelected`, `setBulkSelected`)
- `bulkDelete` and `bulkRetry` mutations

The component manages its own bulk state internally and calls `onSelect(article)` when an article is selected.

**Fix Bug #1** in `ArticleItem`:
```jsx
// BEFORE (line ~821):
{a.status === "draft" && (a.review_score || a.seo_score || 100) < 65 && (

// AFTER:
{a.status === "draft" && (a.review_score || a.seo_score || 0) < 65 && (
```

**Fix Bug #7** — bulkDelete mutation:
```jsx
// BEFORE: reads bulkSelected from closure in onSuccess
const bulkDelete = useMutation({
  mutationFn: (ids) => Promise.all(ids.map(id => api.delete(`/api/content/${id}`))),
  onSuccess: () => {
    qclient.invalidateQueries(["articles", activeProject])
    setBulkSelected([])
    if (selected && bulkSelected.includes(selected.article_id)) onSelect(null)
  },
})

// AFTER: use mutation.variables to avoid stale closure
const bulkDelete = useMutation({
  mutationFn: (ids) => Promise.all(ids.map(id => api.delete(`/api/content/${id}`))),
  onSuccess: (_data, ids) => {  // ids = the argument passed to mutate()
    qclient.invalidateQueries(["articles", projectId])
    setBulkSelected([])
    if (selected && ids.includes(selected.article_id)) onSelect(null)
  },
})
```

Use `useArticlePolling` hook instead of the old `useQuery`:
```jsx
import { useArticlePolling } from "../hooks/useArticlePolling"
// ...
const { data: articles, isLoading } = useArticlePolling(projectId)
```

**Task ordering note:** At the time Task 8 runs, `PipelineProgress` still lives inside `ContentPage.jsx` and uses its own `useQuery` (Task 9 hasn't moved it yet). For the compact progress indicator inside `ArticleItem`, do one of:
- Include a minimal inline version (just a progress bar reading from `usePipelineQuery(article.article_id)`) — simplest
- Or import `PipelineProgress` directly from `ContentPage.jsx` as a named export temporarily

In Task 9, the full `PipelineProgress` (using `usePipelineQuery`) will be extracted to `PipelinePanel.jsx`. At that point, update `ArticleItem` to import it from `"./PipelinePanel"` or the hooks directly.

- [ ] **Step 2: Update `ContentPage.jsx`**

Replace the left-panel JSX block and related state with:
```jsx
import ArticleListPanel from "./content/ArticleListPanel"
// ...
<ArticleListPanel
  projectId={activeProject}
  selected={selected}
  onSelect={setSelected}
  onEditMeta={setEditingMeta}
  onShowGenModal={() => setShowGenModal(true)}
  onShowPrompts={() => setShowPrompts(true)}
  onTestKeyword={setTestKeyword}
/>
```

- [ ] **Step 3: Verify in browser**

- Article list loads and scrolls
- Clicking an article selects it (center panel updates)
- Bulk select checkboxes work
- Bulk delete removes articles and correctly clears selection
- "Regen" button appears on a draft article with score 0 or no score
- Lifecycle strip shows correct counts

---

### Task 9: Extract PipelinePanel

**Files:**
- Create: `frontend/src/content/PipelinePanel.jsx`
- Modify: `frontend/src/ContentPage.jsx`

Bug fixes bundled in:
- **Bug #2:** All three components use `usePipelineQuery` shared hook (replaces 3 separate polls)
- **Bug #3:** `onComplete` false trigger — add previous-status ref

- [ ] **Step 1: Create `frontend/src/content/PipelinePanel.jsx`**

Contains:
- `STEP_DEFS` constant (the 11 pipeline steps)
- `_normalizeProviderId`, `_getProviderColor`, `_getProviderLabel` helper functions (or import from App)
- `AISelect` component
- `HealthBadge` component
- `PipelineProgress` component — **replace its `useQuery` with `usePipelineQuery` from hooks**
- `PipelineConsole` component — **replace its `useQuery` with `usePipelineQuery` from hooks**
- `PipelineLogsView` component — **replace its `useQuery` with `usePipelineQuery` from hooks**
- The generating-view JSX (header + PipelineProgress + PipelineConsole)

**Fix Bug #3** in `PipelineProgress` — the `onComplete` effect:
```jsx
// BEFORE (line ~132):
useEffect(() => {
  if (data?.status && data.status !== "generating") {
    qc.invalidateQueries(["articles"])
    if (onComplete) onComplete()
  }
}, [data?.status])

// AFTER: only fire when transitioning FROM "generating"
const prevStatusRef = useRef(null)
useEffect(() => {
  const prev = prevStatusRef.current
  prevStatusRef.current = data?.status
  if (prev === "generating" && data?.status && data.status !== "generating") {
    qc.invalidateQueries(["articles"])
    if (onComplete) onComplete()
  }
}, [data?.status])  // eslint-disable-line
```

**Replace the three separate `useQuery` calls with `usePipelineQuery`:**
```jsx
// In PipelineProgress, PipelineConsole, PipelineLogsView — change:
const { data, isLoading } = useQuery({
  queryKey: ["pipeline", articleId],
  queryFn: () => api.get(`/api/content/${articleId}/pipeline`),
  refetchInterval: ...
  ...
})

// To:
import { usePipelineQuery } from "../hooks/usePipelineQuery"
const { data, isLoading } = usePipelineQuery(articleId)
```

All three components using the same key means React Query serves them from a single in-flight request.

**Fix `runHealthCheck` quota drain:** `PipelineProgress` has a `runHealthCheck` call that hits `/api/ai/health` and triggers live API calls. Replace it to use `/api/ai/status` instead (reads from cache, sub-ms, no quota cost):
```jsx
// BEFORE:
const runHealthCheck = async () => {
  const result = await api.get("/api/ai/health")
  // ...
}

// AFTER:
const runHealthCheck = async () => {
  const result = await api.get("/api/ai/status")  // cache-read only, zero live calls
  // ...
}
```
If the user needs to force a live re-check, use `/api/ai/health?force=true` only on an explicit "Refresh" button click.

- [ ] **Step 2: Update `ContentPage.jsx`**

```jsx
import PipelinePanel from "./content/PipelinePanel"
```

Replace the generating-view block with `<PipelinePanel articleId={selected.article_id} onComplete={...} />`.

- [ ] **Step 3: Verify in browser**

- Open Network tab in DevTools → filter by `/pipeline` → when an article is generating, only ONE request should be in-flight at a time (not 3)
- Pipeline steps show correctly with expand/collapse
- When pipeline finishes, article list refreshes exactly once
- Paused state shows correctly

---

### Task 10: Extract EditorPanel

**Files:**
- Create: `frontend/src/content/EditorPanel.jsx`
- Modify: `frontend/src/ContentPage.jsx`

Bug fixes bundled in:
- **Bug #1 (second location):** Editor toolbar Regen button `|| 100` → `|| 0` (~line 2948)
- **Bug #8:** `acceptRuleFix` awaits `runReview()`
- **Bug #9:** ReviewPanel + RulesPanel mutual exclusion via `openPanel` state

- [ ] **Step 1: Create `frontend/src/content/EditorPanel.jsx`**

This component receives:
```jsx
// Props:
// article (the selected article object)
// projectId
// onStatusChange (called when status mutates — triggers article list refresh)
```

Internally manages:
- `viewMode` state ("editor" | "html" | "logs")
- `isDirty`, `htmlContent` state
- `openPanel` state — "review" | "rules" | null (replaces separate reviewOpen + rulesOpen)
- `reviewData`, `rulesData`, `ruleDiff` state
- `fixing`, `fixingRule`, `rewriting`, `rewriteInstruction`, `showInstruction` state
- `editorRef`, `saveTimer` refs
- All handler functions: `handleEditorChange`, `switchToHtml`, `switchToEditor`, `runReview`, `fetchRules`, `fixIssues`, `fixSingleRule`, `acceptRuleFix`, `rejectRuleFix`, `rewriteFull`, `rewriteSelection`, `exportShopify`

**Fix Bug #9 — mutual exclusion:**
```jsx
// BEFORE: two separate boolean states
const [reviewOpen, setReviewOpen] = useState(false)
const [rulesOpen, setRulesOpen] = useState(false)

// AFTER: single state
const [openPanel, setOpenPanel] = useState(null) // "review" | "rules" | null

// Usage:
const reviewOpen = openPanel === "review"
const rulesOpen = openPanel === "rules"
// Toggle functions:
const toggleReview = () => setOpenPanel(p => p === "review" ? null : "review")
const toggleRules = () => { if (openPanel !== "rules") fetchRules(); setOpenPanel(p => p === "rules" ? null : "rules") }
```

**Fix Bug #1 (editor toolbar):**
```jsx
// BEFORE (~line 2948):
{selected.status === "draft" && (selected.review_score || selected.seo_score || 100) < 65 && (

// AFTER:
{article.status === "draft" && (article.review_score || article.seo_score || 0) < 65 && (
```

**Fix Bug #8 — await runReview:**
```jsx
// BEFORE:
const acceptRuleFix = async () => {
  // ...
  if (res?.saved && editorRef.current) {
    // ...
    runReview()  // NOT awaited
  }
}

// AFTER:
const acceptRuleFix = async () => {
  // ...
  if (res?.saved && editorRef.current) {
    // ...
    try {
      await runReview()
    } catch (e) {
      console.warn("Review after fix failed:", e)
    }
  }
}
```

Also move `ReviewPanel` and `RulesPanel` components into this file (they were already declared inline in ContentPage — keep them local to EditorPanel).

- [ ] **Step 2: Update `ContentPage.jsx`**

```jsx
import EditorPanel from "./content/EditorPanel"
// ...
{selected && selected.status !== "generating" && (
  <EditorPanel
    article={selected}
    projectId={activeProject}
    onStatusChange={() => qclient.invalidateQueries(["articles", activeProject])}
  />
)}
```

- [ ] **Step 3: Verify in browser**

- Open an article → editor loads with content
- Click "AI Review" → review panel opens on the right
- Click "Rules" → rules panel opens and review panel closes (not both at once)
- Open review + click "Rules" again → review closes, rules open
- Regen button: a draft article with 0% score should show it; an article with no score should show it
- Fix a rule → accept → review re-runs and score updates (no silent failures)
- HTML tab → edit source → switch back to Editor → changes apply

---

### Task 11: Slim down ContentPage.jsx

**Files:**
- Modify: `frontend/src/ContentPage.jsx`

After all extractions, `ContentPage.jsx` should only contain:
- Imports (extracted components + hooks)
- `ContentPage` default export function
- Page-level state: `tab`, `selected`, `showGenModal`, `showPrompts`, `testKeyword`, `editingMeta`
- The top-level layout JSX routing between Articles / Pipeline / AI Hub tabs

Target: ~150 lines.

- [ ] **Step 1: Remove all extracted code from ContentPage.jsx**

Verify the following are no longer in ContentPage.jsx (they've been moved):
- `MetaEditModal` function ✓ (Task 6)
- `PromptsDrawer` function ✓ (Task 6)
- `NewArticleModal` and all its constants ✓ (Task 7)
- `LifecycleStrip`, `ArticleItem` ✓ (Task 8)
- `PipelineProgress`, `PipelineConsole`, `PipelineLogsView` ✓ (Task 9)
- `ReviewPanel`, `RulesPanel` ✓ (Task 10)
- `STEP_DEFS`, `AI_PROVIDERS_BASE`, `ROUTING_PRESETS`, etc. ✓ (Tasks 7, 9)

- [ ] **Step 2: Check line count**

```bash
wc -l /root/ANNASEOv1/frontend/src/ContentPage.jsx
```

Expected: 150–250 lines (the main function + imports + layout JSX).

- [ ] **Step 3: Full smoke test in browser**

Navigate through all Content sub-tabs:
- Articles: list, select, edit, approve, delete
- Pipeline: ContentPipelineTab renders
- AI Hub: AIHub renders

---

## Part 4 — Rate Limit Dashboard

### Task 12: RateLimitDashboard component

**Files:**
- Create: `frontend/src/aihub/RateLimitDashboard.jsx`

Context: Fetches from `/api/ai/status` (Task 1) and `/api/ai/usage` (Task 2). Uses React Query v5 `refetchInterval: 5000, refetchIntervalInBackground: false`.

- [ ] **Step 1: Create `frontend/src/aihub/` directory and `RateLimitDashboard.jsx`**

```bash
mkdir -p /root/ANNASEOv1/frontend/src/aihub
```

```jsx
import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { T, api } from "../App"

const PROVIDER_LABELS = {
  groq: "⚡ Groq",
  gemini_free: "💎 Gemini Free",
  gemini_paid: "💎 Gemini Paid",
  anthropic: "🧠 Claude",
  openai_paid: "🤖 ChatGPT",
  ollama: "🦙 Ollama",
  openrouter: "🌐 OpenRouter",
}

// Countdown timer that decrements client-side between API refreshes
function CountdownTimer({ seconds }) {
  const [remaining, setRemaining] = useState(seconds)
  useEffect(() => {
    setRemaining(seconds)
    if (seconds <= 0) return
    const id = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000)
    return () => clearInterval(id)
  }, [seconds])
  if (remaining <= 0) return <span style={{ color: T.teal, fontWeight: 600 }}>Ready</span>
  return <span style={{ color: T.red, fontWeight: 600 }}>Resets in {remaining}s</span>
}

function TokenBar({ label, remaining, limit, color }) {
  const pct = limit > 0 ? Math.min(100, Math.round((remaining / limit) * 100)) : null
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
        <span style={{ color: T.textSoft }}>{label}</span>
        <span style={{ fontWeight: 600 }}>
          {remaining != null ? remaining.toLocaleString() : "—"}
          {limit ? ` / ${limit.toLocaleString()}` : ""}
        </span>
      </div>
      {pct != null && (
        <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
          <div style={{
            height: 4, borderRadius: 99, transition: "width 0.4s",
            width: `${pct}%`,
            background: pct > 50 ? T.teal : pct > 20 ? T.amber : T.red,
          }} />
        </div>
      )}
    </div>
  )
}

function ProviderRow({ id, info }) {
  const label = PROVIDER_LABELS[id] || id
  const rl = info.rate_limit_info || {}
  const isBlocked = info.status !== "ok"
  return (
    <div style={{
      padding: "10px 14px", borderRadius: 10, marginBottom: 8,
      background: isBlocked ? "#FFF0EB" : "#F9F9F9",
      border: `1px solid ${isBlocked ? "#FF3B3040" : T.border}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: rl.tokens_remaining != null ? 8 : 0 }}>
        <span style={{ fontSize: 14, fontWeight: 600, flex: 1, color: T.text }}>{label}</span>
        <span style={{
          fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
          background: isBlocked ? "#FF3B3020" : "#34C75920",
          color: isBlocked ? "#CC3300" : "#1B7A2E",
        }}>
          {isBlocked ? info.status.replace("_", " ") : "OK"}
        </span>
        {isBlocked && <CountdownTimer seconds={info.seconds_remaining} />}
      </div>
      {rl.tokens_remaining != null && (
        <TokenBar label="Tokens remaining" remaining={rl.tokens_remaining} limit={null} />
      )}
      {rl.requests_remaining != null && (
        <TokenBar label="Requests remaining" remaining={rl.requests_remaining} limit={null} />
      )}
      {rl.daily_exhausted && (
        <div style={{ fontSize: 10, color: T.red, fontWeight: 600 }}>⚠ Daily token quota exhausted</div>
      )}
    </div>
  )
}

function UsageTable({ usage }) {
  if (!usage || usage.length === 0) {
    return <div style={{ fontSize: 11, color: T.textSoft, textAlign: "center", padding: 12 }}>No usage data since last server restart</div>
  }
  const byProvider = {}
  usage.forEach(e => {
    if (!byProvider[e.provider]) byProvider[e.provider] = 0
    byProvider[e.provider] += e.tokens_estimated || 0
  })
  const total = Object.values(byProvider).reduce((a, b) => a + b, 0)
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 6 }}>
        Session Token Usage — Est. total: {total.toLocaleString()} tokens
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {Object.entries(byProvider).sort((a, b) => b[1] - a[1]).map(([prov, tokens]) => (
          <div key={prov} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
            <span style={{ color: T.textSoft }}>{PROVIDER_LABELS[prov] || prov}</span>
            <span style={{ fontWeight: 600 }}>{tokens.toLocaleString()} tokens</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: T.textSoft, marginBottom: 4 }}>Recent calls</div>
        {usage.slice(-10).reverse().map((e, i) => (
          <div key={i} style={{ fontSize: 10, color: T.textSoft, padding: "2px 0" }}>
            {new Date(e.ts * 1000).toLocaleTimeString()} · Step {e.step} {e.step_name} · {PROVIDER_LABELS[e.provider] || e.provider} · ~{(e.tokens_estimated || 0).toLocaleString()} tokens
          </div>
        ))}
      </div>
    </div>
  )
}

export default function RateLimitDashboard() {
  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api.get("/api/ai/status"),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })

  const { data: usageData } = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api.get("/api/ai/usage"),
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })

  const providers = statusData || {}
  const usage = usageData?.usage || []
  const blockedCount = Object.values(providers).filter(p => p.status !== "ok").length

  return (
    <div style={{ padding: "16px 18px", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Rate Limit Dashboard</div>
        {blockedCount > 0 && (
          <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: "#FF3B3020", color: "#CC3300" }}>
            {blockedCount} blocked
          </span>
        )}
        {statusLoading && <span style={{ fontSize: 10, color: T.textSoft }}>Refreshing…</span>}
      </div>

      {/* Provider status rows */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Provider Status
        </div>
        {Object.entries(providers).map(([id, info]) => (
          <ProviderRow key={id} id={id} info={info} />
        ))}
        {Object.keys(providers).length === 0 && (
          <div style={{ fontSize: 11, color: T.textSoft }}>Loading provider status…</div>
        )}
      </div>

      {/* Session usage */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Session Usage
        </div>
        <UsageTable usage={usage} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify component renders without error**

```bash
cd /root/ANNASEOv1/frontend && npm run dev
```

Navigate to Content → AI Hub → Rate Limit tab (added in next task). Component should render with provider rows and no JS errors in console.

---

### Task 13: Wire RateLimitDashboard into AIHub

**Files:**
- Modify: `frontend/src/AIHub.jsx`

- [ ] **Step 1: Import RateLimitDashboard**

At the top of `AIHub.jsx`:
```jsx
import RateLimitDashboard from "./aihub/RateLimitDashboard"
```

- [ ] **Step 2: Add "Rate Limits" tab to the AIHub tab bar**

Find the tab navigation in `AIHub.jsx` and add a new tab:
```jsx
{ key: "ratelimits", label: "Rate Limits" }
```

- [ ] **Step 3: Render RateLimitDashboard when tab is active**

In the AIHub render function, add:
```jsx
{activeTab === "ratelimits" && (
  <div style={{ flex: 1, overflowY: "auto" }}>
    <RateLimitDashboard />
  </div>
)}
```

- [ ] **Step 4: Full end-to-end verification**

Check each of the 13 items in the spec's testing checklist:

```
1. [ ] Regen button shows on articles with score 0 or no score
2. [ ] Three pipeline query consumers share one network request (DevTools → Network → filter /pipeline → one request at a time)
3. [ ] onComplete does not fire on initial load
4. [ ] Health check returns cached results on second call (check response time < 50ms)
5. [ ] /api/ai/status returns data without external HTTP calls (check server logs — no outbound requests)
6. [ ] Article list stops polling when no articles are generating (Network tab — no /content requests after all articles are stable)
7. [ ] Bulk delete correctly identifies deleted articles
8. [ ] Review and Rules panels cannot be open simultaneously
9. [ ] Rate Limit Dashboard shows provider rows with status and timers
10. [ ] Rate Limit Dashboard shows session usage table (generate an article first to populate it)
11. [ ] Countdown timers tick down client-side between API refreshes
12. [ ] All 11 pipeline steps visible in PipelinePanel
13. [ ] Prompts drawer and Meta modal still work after extraction
```

- [ ] **Step 5: Run backend tests**

```bash
cd /root/ANNASEOv1 && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Run frontend tests**

```bash
cd /root/ANNASEOv1/frontend && npx vitest run src/
```

Expected: all tests pass (the two new hook test files + existing parseError test).

---

## Quick Reference: Bug Fix Locations

| Bug | File | What to change |
|---|---|---|
| Regen `\|\| 100` in article list | `content/ArticleListPanel.jsx` (from ContentPage ~821) | `\|\| 100` → `\|\| 0` |
| Regen `\|\| 100` in editor toolbar | `content/EditorPanel.jsx` (from ContentPage ~2948) | `\|\| 100` → `\|\| 0` |
| Triple pipeline polling | `content/PipelinePanel.jsx` | Replace 3× `useQuery` with `usePipelineQuery` |
| `onComplete` false trigger | `content/PipelinePanel.jsx` in PipelineProgress | Add `prevStatusRef`, only fire on transition |
| Health check burns quota | `main.py` `ai_health_check` | Wrap with `_health_cached()`, add `force` param |
| Engine cache not exposed | `main.py` + `content_generation_engine.py` | New `/api/ai/status` endpoint |
| Always-on article polling | `content/ArticleListPanel.jsx` | Use `useArticlePolling` hook |
| bulkDelete stale closure | `content/ArticleListPanel.jsx` | Use `onSuccess(_data, ids)` — read from mutation variables |
| `acceptRuleFix` silent fail | `content/EditorPanel.jsx` | `await runReview()` with try/catch |
| Review+Rules both open | `content/EditorPanel.jsx` | Replace 2 booleans with `openPanel` state |
