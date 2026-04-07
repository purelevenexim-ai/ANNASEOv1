# Content Page + AI Hub Full Rebuild — Design Spec
**Date:** 2026-04-06  
**Status:** Approved  
**React Query Version:** v5 (`@tanstack/react-query ^5.45.0`)  
**Scope:** ContentPage.jsx, AIHub.jsx, content_generation_engine.py, main.py

---

## Problem Statement

The Content page (3,167 lines), AI Hub, and content generation pipeline have accumulated critical bugs, architectural debt, and missing observability. Three categories of failure:

1. **Generation failures** — stuck pipelines, silent errors, misleading status
2. **Rate limiting** — provider 429s are invisible to the user; pipeline retries wrong providers; no token visibility
3. **UI/UX** — broken Regen button logic, duplicate polling, editor panel layout issues, no rate limit telemetry

---

## Goals

- Fix all critical code-level bugs (10+ identified)
- Restructure ContentPage.jsx into focused sub-components
- Add a full-telemetry Rate Limit Dashboard in AI Hub
- Add backend `/api/ai/status` endpoint (cache-read only, no live API calls)
- Add backend `/api/ai/usage` endpoint (per-step token usage tracking)
- Make article list polling adaptive (stops when nothing is generating)
- Make health checks cache-first (5-minute TTL before re-pinging providers)

---

## Architecture

### Frontend File Structure

```
frontend/src/
  ContentPage.jsx                  ← thin router/orchestrator, ~150 lines
  content/
    ArticleListPanel.jsx           ← article list + lifecycle strip + bulk actions
    EditorPanel.jsx                ← toolbar + TipTap editor + HTML/Logs view modes
    PipelinePanel.jsx              ← pipeline progress + console (uses shared hook)
    NewArticleModal.jsx            ← new article intake form (extracted from ContentPage)
    PromptsDrawer.jsx              ← prompt editor (extracted)
    MetaEditModal.jsx              ← metadata edit modal (extracted)
  hooks/
    usePipelineQuery.js            ← shared pipeline polling hook
    useArticlePolling.js           ← adaptive article list polling
  aihub/
    RateLimitDashboard.jsx         ← NEW: full provider telemetry panel
```

ReviewPanel and RulesPanel remain as-is (already isolated) but receive mutual exclusion fix.

### State Ownership Model

The `ContentPage.jsx` orchestrator owns shared state and passes it down as props:

| State | Owner | Notes |
|---|---|---|
| `selected` (selected article) | ContentPage | Passed to EditorPanel, PipelinePanel |
| `bulkSelected` (array of IDs) | ArticleListPanel | Local to list, surface to ContentPage via callback only for delete |
| `openPanel` ("review" \| "rules" \| null) | EditorPanel | Local — replaces separate reviewOpen/rulesOpen booleans |
| `reviewData`, `rulesData` | EditorPanel | Local — fetched when article is selected |
| `isDirty`, `viewMode`, `htmlContent` | EditorPanel | Local |
| `ruleDiff` | EditorPanel | Local |
| `fixing`, `fixingRule` | EditorPanel | Local |
| `rewriting`, `rewriteInstruction` | EditorPanel | Local |
| `showGenModal`, `showPrompts`, `editingMeta` | ContentPage | Modal visibility — owned at page level |

No Zustand or Context needed; prop passing is sufficient for this component depth (2 levels max).

### Backend Additions

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ai/status` | GET | Returns provider status from in-memory cache only. Zero live API calls. Sub-1ms. |
| `/api/ai/usage` | GET | Returns per-provider, per-step token usage for the current session. |

Modify `/api/ai/health`:
- Cache-first: return cached result if < 5 minutes old
- Only re-test providers whose cache entry is stale
- Expose cache TTL and last-checked timestamp in response

---

## Component Designs

### 1. `hooks/usePipelineQuery.js`

Single shared React Query hook used by `PipelinePanel`, pipeline compact view in `ArticleListPanel`, and `PipelineLogsView`. React Query v5 deduplicates queries with the same key — all three consumers share one in-flight request.

The paused-aware interval (5s when paused, 2s when running) applies to all three consumers including `PipelineConsole`. This is intentional — slowing to 5s when the pipeline is paused reduces backend load without losing responsiveness.

```js
// React Query v5 — refetchInterval receives the query object
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

### 2. `hooks/useArticlePolling.js`

Adaptive polling: fast (3s) while any article is generating, off otherwise.

```js
export function useArticlePolling(projectId) {
  return useQuery({
    queryKey: ["articles", projectId],
    queryFn: () => api.get(`/api/projects/${projectId}/content`)
      .then(d => Array.isArray(d) ? d : []),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const articles = query.state.data || []
      return articles.some(a => a.status === "generating") ? 3000 : false
    },
  })
}
```

### 3. `RateLimitDashboard.jsx`

New component in AI Hub. Fetches from `/api/ai/status` every 5 seconds (only when tab is visible). Displays:

- Per-provider status row: name, icon, status badge, token bar (used/limit), request bar (used/limit), reset countdown timer
- Session usage table: per-step breakdown of tokens consumed and which provider served each step
- Estimated session cost (calculated frontend-side from token counts and published rates)
- Rate limited providers highlighted in red with live countdown to reset

Data sources:
- `/api/ai/status` — provider status, rate limit info (from cache)
- `/api/ai/usage` — session token usage log

Auto-refreshes every 5 seconds using `refetchInterval: 5000, refetchIntervalInBackground: false`. The `refetchIntervalInBackground: false` option is the React Query built-in for tab-visibility gating — no custom `visibilitychange` listener needed. Reset timers decrement client-side between refreshes using `Date.now()` math.

### 4. `ArticleListPanel.jsx`

Extracted from ContentPage. Manages:
- Lifecycle strip
- "+ New Article" button
- Bulk selection state and toolbar
- Article item list (with adaptive polling via `useArticlePolling`)

Key fix: the compact `PipelineProgress` inside each article item uses `usePipelineQuery` (shared cache) instead of its own polling loop.

### 5. `EditorPanel.jsx`

Extracted from ContentPage. Manages:
- View mode toggle: Editor / HTML / Logs
- Toolbar: Approve, AI Review, Rules, Options, Rewrite, Shopify export, Regenerate
- TipTap editor with auto-save
- ReviewPanel + RulesPanel side panels (mutually exclusive: opening one closes the other)
- Rule diff preview bar

### 6. `PipelinePanel.jsx`

Extracted from ContentPage. Shows when `article.status === "generating"`. Uses `usePipelineQuery` shared hook. Contains:
- Step cards with expand/collapse
- AI chain selectors per step
- Per-step logs
- Console log panel at bottom

---

## Bug Fixes

| # | Location | Bug | Fix |
|---|---|---|---|
| 1 | ArticleItem (~line 821) and editor toolbar (~line 2948) | `\|\| 100` fallback makes `(score \|\| 100) < 65` always false for unscored articles — Regen button never shows | Change fallback to `\|\| 0` in both locations |
| 2 | PipelineProgress, PipelineConsole, PipelineLogsView | Three separate `useQuery` instances poll the same `/api/content/{id}/pipeline` endpoint independently | Replace all with `usePipelineQuery` shared hook; React Query deduplicates by key |
| 3 | PipelineProgress `useEffect` (~line 132) | `onComplete` fires on initial load for any article not in "generating" state | Add `useRef(null)` for previous status; only fire `onComplete` when transitioning away from `"generating"` |
| 4 | main.py:1728 `/api/ai/health` | Makes live API calls to all providers on every invocation — consumes rate limit quota | Cache-first: return cached result if < 5 minutes old; note that Ollama remote servers are dynamic (keyed by `server_id`) and must be included in the cache key |
| 5 | content_generation_engine.py | `_provider_health_cache` (correct name) tracks bad providers but frontend health check ignores it and retests anyway | New `/api/ai/status` endpoint reads directly from `_provider_health_cache` + `_key_health` |
| 6 | ContentPage articles query (~line 2322) | `refetchInterval: 10000` always — polls even when no articles are generating | Replace with `useArticlePolling` hook: fast (3s) when any article has `status === "generating"`, `false` otherwise; note paused articles retain `status === "generating"` so they continue to poll at 3s (intentional) |
| 7 | bulkDelete `onSuccess` (~line 2357) | Reads `bulkSelected` from stale closure — may fail to identify deleted article | Pass `ids` as the mutation's `variables`; read `mutation.variables` in `onSuccess` |
| 8 | `acceptRuleFix` (~line 2603) | Calls `runReview()` without `await` — errors are swallowed | `await runReview()` and wrap in try/catch with error display |
| 9 | ContentPage editor area | ReviewPanel and RulesPanel can be simultaneously open, crushing editor to unreadable width | Replace `reviewOpen` + `rulesOpen` booleans with single `openPanel: "review" \| "rules" \| null` state |

---

## Backend: `/api/ai/status` Endpoint

**Auth:** Requires JWT auth (`Depends(get_current_user)`) — same as all other endpoints.

**Data sources (both exist in `content_generation_engine.py`):**
- `_provider_health_cache: Dict[str, Dict]` — maps provider name → `{"status": reason, "until": timestamp}`. This is the cooldown/bad-provider cache populated by `_mark_provider_bad()`.
- `_key_health: dict` — maps `sha256(key)[:16]` → `{"remaining_tokens": int, "remaining_requests": int, "daily_exhausted": bool, "ts": float}`. Populated by `_update_key_health()` from Groq response headers.

**Implementation:** The endpoint lives in `main.py` and imports these two dicts from `content_generation_engine`. To produce per-provider token counts, join them:

```python
@app.get("/api/ai/status")
async def ai_status(user=Depends(get_current_user)):
    now = time.time()
    result = {}
    canonical_providers = ["groq", "gemini_free", "gemini_paid", "anthropic", "openai_paid", "ollama", "openrouter"]
    for provider in canonical_providers:
        entry = _provider_health_cache.get(provider, {})
        blocked_until = entry.get("until")
        is_blocked = blocked_until and now < blocked_until
        row = {
            "status": entry.get("status", "ok") if is_blocked else "ok",
            "blocked_until": blocked_until if is_blocked else None,
            "seconds_remaining": max(0, int(blocked_until - now)) if is_blocked else 0,
            "rate_limit_info": {},
        }
        # Join key-level token health for providers that expose it via headers (Groq)
        # _key_hash already exists in content_generation_engine.py (line 183)
        # _live_key_for is a NEW helper to implement: returns the currently-active API key
        # string for a given provider name (e.g. "groq" → os.getenv("GROQ_API_KEY", "")).
        # Can call the existing _live_groq_key(), _live_openrouter_key(), etc. per provider.
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

Note: `rate_limit_info` will be empty for providers that don't return token-count headers (Gemini, Anthropic, OpenAI). Only Groq and OpenRouter populate these values today. The frontend renders them when present and omits them gracefully when absent.

**Response shape:**
```json
{
  "groq": {
    "status": "rate_limited",
    "blocked_until": 1712345678,
    "seconds_remaining": 42,
    "rate_limit_info": {
      "tokens_remaining": 3766,
      "requests_remaining": 8,
      "daily_exhausted": false,
      "last_seen": 1712345636.2
    }
  },
  "gemini_free": { "status": "ok", "blocked_until": null, "seconds_remaining": 0, "rate_limit_info": {} },
  "anthropic": { "status": "rate_limited", "blocked_until": 1712345720, "seconds_remaining": 71, "rate_limit_info": {} }
}
```

Sub-millisecond response. No external API calls.

## Backend: `/api/ai/usage` Endpoint

**Auth:** Requires JWT auth (`Depends(get_current_user)`).

**Data source:** A new module-level list `_SESSION_USAGE` in `content_generation_engine.py`. Entries are appended in `_run_provider()` (the central AI call dispatcher, around lines 760–840) after a successful response. Token counts come from `_key_health` which is already populated by `_update_key_health()` from Groq response headers. For providers without token headers (Gemini, Anthropic), estimate from word count: `len(text.split()) * 1.3`.

**Instrumentation point — add in `_run_provider()` after a successful call:**
```python
# After successful response, append usage entry
_SESSION_USAGE.append({
    "provider": provider,
    "step": getattr(_current_step_ctx, "step", 0),   # thread-local or passed param
    "step_name": getattr(_current_step_ctx, "name", ""),
    "tokens_estimated": _estimate_tokens(result_text),
    "ts": _time.time(),
    "article_id": getattr(_current_step_ctx, "article_id", None),
})
```

**Note on persistence:** `_SESSION_USAGE` is in-memory. It is wiped on process restart (which happens on every deploy). The frontend handles this gracefully by showing "No data since last restart" when the list is empty. This is acceptable — usage data is for in-session observability, not billing.

**Endpoint:**
```python
@app.get("/api/ai/usage")
async def ai_usage(article_id: Optional[str] = None, user=Depends(get_current_user)):
    data = _SESSION_USAGE
    if article_id:
        data = [e for e in data if e.get("article_id") == article_id]
    return {"usage": data[-200:]}  # cap at 200 entries
```

---

## Health Check Cache Fix

The real `ai_health_check` in `main.py` has special-case blocks per provider (Ollama, Groq, Gemini free/paid, Anthropic, OpenAI, OpenRouter) rather than a generic loop. It also handles dynamic Ollama remote servers loaded from the DB (`ollama_remote_{server_id}`). The cache layer wraps each existing block individually:

```python
_HEALTH_CACHE: dict = {}  # cache_key → {"result": {...}, "ts": float}
_HEALTH_TTL = 300         # 5 minutes

def _health_cached(cache_key: str, live_fn):
    """Return cached health result if fresh; otherwise call live_fn() and cache it."""
    now = time.time()
    cached = _HEALTH_CACHE.get(cache_key)
    if cached and (now - cached["ts"]) < _HEALTH_TTL:
        return {**cached["result"], "_cached": True, "_cached_age_s": int(now - cached["ts"])}
    result = live_fn()
    _HEALTH_CACHE[cache_key] = {"result": result, "ts": now}
    return result
```

Each existing provider test block calls `_health_cached(provider_name, lambda: <existing test code>)`. For dynamic Ollama servers, the cache key is `ollama_remote_{server_id}`. The TTL resets on any explicit `/api/ai/health` call where the caller passes `?force=true` (new query param), which bypasses the cache.

Note: `_health_cached` is synchronous. The live test blocks in `ai_health_check` use `httpx.get()`/`httpx.post()` (blocking, not `await`), so the sync helper pattern is correct here.

---

## Error Handling

- Pipeline generation failures: surface the exact failed step and provider in the UI (already partially done, needs consistent display)
- Rate limit errors: show reset timer immediately in the pipeline step card when the step's provider is rate-limited
- Editor save failures: show a toast notification (not silent) with retry button
- Rule fix failures: await `runReview()` call, catch and show error message

---

## Testing Checklist

- [ ] Regen button shows on articles with score 0 or no score
- [ ] Three pipeline query consumers share one network request (verify in DevTools Network tab)
- [ ] `onComplete` does not fire on initial load when article is in stable state
- [ ] Health check returns cached results within 5 minutes; makes no external calls
- [ ] `/api/ai/status` returns rate limit info without triggering any API calls
- [ ] Article list stops polling when no articles are generating
- [ ] Bulk delete correctly identifies the deleted articles in `onSuccess`
- [ ] Review and Rules panels cannot be open simultaneously
- [ ] Rate Limit Dashboard shows token bars, reset countdowns, and session usage
- [ ] All 11 pipeline steps visible and functional in PipelinePanel (STEP_DEFS has 11 entries; authoritative count is 11, not 10 as the class docstring says)
