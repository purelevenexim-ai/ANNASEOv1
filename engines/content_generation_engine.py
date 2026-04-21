"""
10-Step SEO Content Generation Pipeline
Real multi-pass content creation: crawl → structure → write → review → refine
"""

import asyncio
import contextvars as _cv
import gc
import json
import logging
import os
import re
import time as _time
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Context var for step metadata (used by _log_usage) ──────────────────────
_step_ctx_var: _cv.ContextVar[dict] = _cv.ContextVar("_step_ctx", default={})

import requests
from bs4 import BeautifulSoup

from core.ai_provider_manager import (
    AIProviderManager as _APM,
    CallResult as _CallResult,
)
from core.model_profiler import get_profiler, init_profiler
from core.checkpoint_manager import get_checkpoint_manager
from core.progress_tracker import create_progress_tracker

from core.routing_schema import ContentState
from engines.humanize.editorial_intelligence import EditorialIntelligenceEngine
try:
    import textstat
    HAS_TEXTSTAT = True
except ImportError:
    HAS_TEXTSTAT = False

try:
    from engines.ruflo_seo_audit import AIWatermarkScrubber
    _scrubber = AIWatermarkScrubber()
except ImportError:
    _scrubber = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Key constants (module-level, for backwards compat only — prefer _key() helpers below)
GROQ_KEY          = os.getenv("GROQ_API_KEY", "")
GEMINI_FREE_KEY   = os.getenv("GEMINI_API_KEY", "")                              # free tier — general
GEMINI_PAID_KEY   = os.getenv("GEMINI_PAID_API_KEY", "")                         # paid tier — content gen
GEMINI_KEY        = GEMINI_PAID_KEY or GEMINI_FREE_KEY                            # backwards compat
OPENAI_FREE_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_PAID_KEY   = os.getenv("OPENAI_PAID_API_KEY", "")
OPENAI_KEY        = OPENAI_PAID_KEY or OPENAI_FREE_KEY                            # backwards compat
OPENAI_MODEL      = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_FREE_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_PAID_KEY = os.getenv("ANTHROPIC_PAID_API_KEY", "")
ANTHROPIC_KEY     = ANTHROPIC_PAID_KEY or ANTHROPIC_FREE_KEY                      # backwards compat
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
CRAWL_TIMEOUT  = 12           # seconds per URL

# ── Live key helpers — always read from os.environ so settings-page saves apply instantly ──
def _live_groq_key() -> str:
    return os.getenv("GROQ_API_KEY", "") or GROQ_KEY

def _all_keys_for(provider: str) -> list:
    """Return all enabled API keys for a provider from the ALL_KEYS env pool.
    Falls back to the single env-var key if no pool exists.
    """
    pool_env = os.getenv(f"{provider.upper()}_ALL_KEYS", "")
    keys = []
    if pool_env:
        for k in pool_env.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


def _resolve_key_pool(provider: str) -> list:
    """Get all available API keys for a provider, using pool with single-key fallback."""
    base = provider.replace("_paid", "").replace("_free", "")
    if base in ("chatgpt",):
        base = "openai"
    if base in ("claude",):
        base = "anthropic"
    if base.startswith("or_"):
        base = "openrouter"
    pool = _all_keys_for(base)
    if pool:
        return pool
    _fns = {
        "groq": lambda: _live_groq_key(),
        "openai": lambda: _live_openai_key(paid=("_paid" in provider)),
        "anthropic": lambda: _live_anthropic_key(paid=("_paid" in provider)),
        "openrouter": lambda: _live_openrouter_key(),
    }
    fn = _fns.get(base)
    if fn:
        k = fn()
        return [k] if k else []
    return []

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

def _live_gemini_key(paid: bool = False) -> str:
    if paid:
        return os.getenv("GEMINI_PAID_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return os.getenv("GEMINI_API_KEY", "") or os.getenv("GEMINI_PAID_API_KEY", "")

def _live_gemini_all_keys() -> list:
    """Return all enabled Gemini API keys (from multi-key pool + env vars), deduplicated."""
    keys = []
    # Primary: all keys synced from provider_keys DB via GEMINI_ALL_KEYS env var
    all_keys_env = os.getenv("GEMINI_ALL_KEYS", "")
    if all_keys_env:
        for k in all_keys_env.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    # Fallback: individual env vars
    for k in [os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_PAID_API_KEY", "")]:
        if k and k not in keys:
            keys.append(k)
    return [k for k in keys if k]

def _live_anthropic_key(paid: bool = False) -> str:
    if paid:
        k = os.getenv("ANTHROPIC_PAID_API_KEY", "")
        return k if k and not k.endswith("xxxx") else _live_anthropic_key(paid=False)
    k = os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_PAID_API_KEY", "")
    return k if k and not k.endswith("xxxx") else ""

def _live_openai_key(paid: bool = False) -> str:
    if paid:
        return os.getenv("OPENAI_PAID_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    return os.getenv("OPENAI_API_KEY", "") or os.getenv("OPENAI_PAID_API_KEY", "")

def _live_claude_model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

def _live_ollama_url() -> str:
    """Get Ollama URL from environ (reads from settings page changes)."""
    return os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")

def _live_ollama_model() -> str:
    """Get Ollama model from environ (reads from settings page changes)."""
    return os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")

def _live_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")

def _live_openrouter_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")

# ── OpenRouter Model Registry ────────────────────────────────────────────────
# Each entry maps a short provider ID to a specific OpenRouter model.
# These IDs can be used in StepAIConfig chains just like groq, gemini_paid, etc.
OPENROUTER_MODELS = {
    # ── Primary — free / very cheap, good for small tasks ──────────────────
    "or_qwen":          {"model": "openai/gpt-oss-120b:free",         "label": "GPT-OSS 120B",           "tier": "primary",   "cost": "Free"},
    "or_qwen_next":     {"model": "openai/gpt-oss-20b:free",          "label": "GPT-OSS 20B",            "tier": "primary",   "cost": "Free"},
    "or_deepseek":      {"model": "deepseek/deepseek-v3.2",           "label": "DeepSeek V3.2",          "tier": "primary",   "cost": "$0.26/M"},
    "or_gemini_flash":  {"model": "google/gemini-2.5-flash",          "label": "Gemini 2.5 Flash",       "tier": "primary",   "cost": "$0.30/M"},
    "or_gemini_lite":   {"model": "google/gemini-2.0-flash-lite-001", "label": "Gemini 2.0 Flash Lite",  "tier": "primary",   "cost": "$0.07/M"},
    "or_glm":           {"model": "z-ai/glm-5-turbo",                 "label": "GLM 5 Turbo",            "tier": "primary",   "cost": "$1.20/M"},
    "or_qwq":           {"model": "qwen/qwq-32b:free",                "label": "QwQ 32B",                "tier": "primary",   "cost": "Free"},
    "or_phi4":          {"model": "microsoft/phi-4-reasoning:free",    "label": "Phi-4 Reasoning",        "tier": "primary",   "cost": "Free"},
    "or_gemma3":        {"model": "google/gemma-3-27b-it:free",        "label": "Gemma 3 27B",            "tier": "primary",   "cost": "Free"},
    "or_mistral":       {"model": "mistralai/mistral-small-3.2-24b-instruct:free", "label": "Mistral Small 3.2", "tier": "primary", "cost": "Free"},
    "or_maverick_free": {"model": "meta-llama/llama-4-maverick:free",  "label": "Llama 4 Maverick Free",  "tier": "primary",   "cost": "Free"},
    "or_haiku":         {"model": "anthropic/claude-haiku-4.5",        "label": "Claude Haiku 4.5",       "tier": "primary",   "cost": "$0.80/M"},
    # ── Secondary — premium paid models ────────────────────────────────────
    "or_gpt4o":         {"model": "openai/gpt-4o",                    "label": "GPT-4o",                 "tier": "secondary", "cost": "$2.50/M"},
    "or_claude":        {"model": "anthropic/claude-sonnet-4",         "label": "Claude Sonnet 4",        "tier": "secondary", "cost": "$3.00/M"},
    "or_llama":         {"model": "meta-llama/llama-4-maverick",       "label": "Llama 4 Maverick",       "tier": "secondary", "cost": "$0.20/M"},
    "or_qwen_coder":    {"model": "qwen/qwen3-coder:free",            "label": "Qwen3 Coder 480B",       "tier": "secondary", "cost": "Free"},
    "or_deepseek_r1":   {"model": "deepseek/deepseek-r1-0528",        "label": "DeepSeek R1",            "tier": "secondary", "cost": "$0.45/M"},
    "or_gemini_pro":    {"model": "google/gemini-2.5-pro",             "label": "Gemini 2.5 Pro",         "tier": "secondary", "cost": "$1.25/M"},
    "or_o4_mini":       {"model": "openai/o4-mini",                    "label": "o4-mini",                "tier": "secondary", "cost": "$1.10/M"},
    "or_claude_opus":   {"model": "anthropic/claude-opus-4",           "label": "Claude Opus 4",          "tier": "secondary", "cost": "$15/M"},
    "openrouter":       {"model": None,                                "label": "OpenRouter (default)",   "tier": "secondary", "cost": "Varies"},
}

# ── Key health tracking — sort keys by remaining capacity ─────────────────────
import hashlib as _hashlib
_key_health: dict = {}   # sha256(key) → {"remaining_tokens": int, "remaining_requests": int, "daily_exhausted": bool, "ts": float}

def _key_hash(key: str) -> str:
    return _hashlib.sha256(key.encode()).hexdigest()[:16]

def _update_key_health(key: str, headers: dict = None, status_code: int = 0, error_body: str = ""):
    """Update health info for a key from response headers and status."""
    h = _key_hash(key)
    info = _key_health.get(h, {})
    info["ts"] = _time.time()
    if status_code == 429 and "tokens per day" in error_body.lower():
        info["daily_exhausted"] = True
        info["daily_exhausted_at"] = _time.time()
        log.info(f"[KeyHealth] {h} marked daily-exhausted")
    elif status_code == 200:
        info["daily_exhausted"] = False
        if headers:
            rt = headers.get("x-ratelimit-remaining-tokens", "")
            rr = headers.get("x-ratelimit-remaining-requests", "")
            if rt:
                info["remaining_tokens"] = int(rt)
            if rr:
                info["remaining_requests"] = int(rr)
    _key_health[h] = info

def _sort_keys_by_health(keys: list) -> list:
    """Sort keys: daily-exhausted last, then by remaining tokens descending."""
    now = _time.time()
    def score(key):
        h = _key_hash(key)
        info = _key_health.get(h, {})
        # Auto-reset daily_exhausted after 1 hour (conservative)
        if info.get("daily_exhausted") and (now - info.get("daily_exhausted_at", 0)) < 3600:
            return -1_000_000
        return info.get("remaining_tokens", 999_999)
    return sorted(keys, key=score, reverse=True)


# ── Per-key rate limit cooldown ──────────────────────────────────────────────
# Keys from different accounts / GCP projects have INDEPENDENT rate limit pools.
# When one key hits 429, only THAT key is cooled down — others stay available.
_key_cooldowns: dict = {}   # key_hash → {"until": float, "reason": str}

def _mark_key_rate_limited(key: str, cooldown: int = 45, reason: str = "rate_limited"):
    """Mark a specific key as rate-limited. Other keys for the same provider stay available."""
    h = _key_hash(key)
    _key_cooldowns[h] = {"until": _time.time() + cooldown, "reason": reason}
    log.info(f"[KeyRL] Key {h} rate-limited for {cooldown}s ({reason})")

def _clear_key_rate_limit(key: str):
    """Clear rate-limit cooldown for a key on success."""
    h = _key_hash(key)
    _key_cooldowns.pop(h, None)

def _is_key_available(key: str) -> bool:
    """Check if a specific key is currently available (not in cooldown)."""
    h = _key_hash(key)
    entry = _key_cooldowns.get(h)
    if not entry:
        return True
    if _time.time() > entry["until"]:
        _key_cooldowns.pop(h, None)
        return True
    return False

def _get_available_keys(provider: str) -> list:
    """Get non-rate-limited keys for a provider, sorted by health.
    Keys from different accounts/GCP projects are tracked independently."""
    all_keys = _resolve_key_pool(provider)
    available = [k for k in all_keys if _is_key_available(k)]
    return _sort_keys_by_health(available)

def _provider_has_available_keys(provider: str) -> bool:
    """Check if a provider has at least one non-rate-limited key."""
    all_keys = _resolve_key_pool(provider)
    if not all_keys:
        return True   # no key pool (e.g. ollama) — defer to provider-level check
    return any(_is_key_available(k) for k in all_keys)


class _GeminiKeyRateLimited(Exception):
    """Raised when a specific Gemini key hits 429/503 — triggers per-key rotation."""
    pass


def _resolve_openrouter_model(provider: str) -> str:
    """Resolve an or_* provider ID to its OpenRouter model string."""
    entry = OPENROUTER_MODELS.get(provider)
    if entry and entry["model"]:
        return entry["model"]
    return _live_openrouter_model()  # fallback to env var

# Reasoning models need extra token budget for thinking before the actual answer
_OR_REASONING_MODELS = {"or_deepseek_r1", "or_glm", "or_o4_mini", "or_phi4", "or_qwq"}

def _or_adjust_max_tokens(provider: str, max_tokens: int) -> int:
    """Boost max_tokens for reasoning models so they have budget for thinking + answer."""
    if provider in _OR_REASONING_MODELS:
        # Reasoning models use 50-70% of tokens for thinking; need 4-5x base
        return max(max_tokens * 5, 4000)
    return max_tokens

# ── Global Ollama Concurrency Guard ──────────────────────────────────────────
# Protects ALL Ollama calls app-wide (not just the section writer).
# qwen2.5:3b on 4-CPU/8GB needs exclusive access — concurrent requests cause
# OOM, swap thrash, or timeouts.
_ollama_global_sem: asyncio.Semaphore | None = None

def _get_ollama_sem() -> asyncio.Semaphore:
    """Get the global Ollama semaphore (created lazily for the running event loop)."""
    global _ollama_global_sem
    if _ollama_global_sem is None:
        _ollama_global_sem = asyncio.Semaphore(2)  # 2 = allow 2 concurrent remote Ollama requests
    return _ollama_global_sem

# ── Provider Health Cache ────────────────────────────────────────────────────
# Tracks recently-failed providers so we skip them instead of wasting time.
# Entries auto-expire after cooldown period.
_provider_health_cache: Dict[str, Dict] = {}

# ── Session-level usage log ──────────────────────────────────────────────────
# In-memory, wiped on process restart.
from collections import deque as _deque
_SESSION_USAGE: _deque = _deque(maxlen=500)
_SESSION_USAGE_MAX = 500  # kept for test compatibility

def _log_usage(provider: str, result_text: str,
               input_tokens: int = 0, output_tokens: int = 0,
               model: str = "", db=None):
    """Append usage entry; reads step context from _step_ctx_var. Persists to DB when db provided."""
    ctx = _step_ctx_var.get()
    word_count = len(result_text.split()) if result_text else 0
    # Use actual tokens if provided, else estimate from word count
    if input_tokens or output_tokens:
        tokens_estimated = input_tokens + output_tokens
    else:
        tokens_estimated = int(word_count * 1.35)
        input_tokens = int(tokens_estimated * 0.70)
        output_tokens = tokens_estimated - input_tokens

    _SESSION_USAGE.append({  # deque auto-evicts oldest when maxlen reached
        "provider": provider,
        "step": ctx.get("step", 0),
        "step_name": ctx.get("step_name", ""),
        "tokens_estimated": tokens_estimated,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "ts": _time.time(),
        "article_id": ctx.get("article_id"),
    })

    # Persist to DB if database connection available
    if db:
        try:
            from core.ai_pricing import get_cost
            project_id = ctx.get("project_id", "")
            article_id = ctx.get("article_id", "")
            step = ctx.get("step", 0)
            step_name = ctx.get("step_name", "")
            keyword = ctx.get("keyword", "")
            cost_usd = get_cost(provider, model or None, input_tokens, output_tokens)
            db.execute(
                "INSERT INTO ai_usage (project_id, run_id, model, input_tokens, output_tokens, cost_usd, purpose, provider, article_id, task_type, step, step_name) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, article_id, model or provider, input_tokens, output_tokens,
                 cost_usd, step_name or f"step_{step}", provider, article_id,
                 "content_generation", step, step_name),
            )
            db.commit()
        except Exception:
            pass  # Never let logging break the pipeline

def _mark_provider_bad(provider: str, reason: str = "error", cooldown: int = 60):
    """Mark a provider as temporarily unavailable."""
    _provider_health_cache[provider] = {
        "status": reason,
        "until": _time.time() + cooldown,
    }
    log.info(f"Provider {provider} marked {reason} — cooldown {cooldown}s")

def _mark_provider_ok(provider: str):
    """Clear a provider's bad status on success."""
    _provider_health_cache.pop(provider, None)

def _is_provider_available(provider: str) -> bool:
    """Check if a provider is currently available.
    For providers with key pools: available if ANY key is not rate-limited,
    even if the provider was marked bad (keys from different accounts recover independently).
    """
    if provider in _force_disabled:
        return False
    entry = _provider_health_cache.get(provider)
    if not entry:
        return True
    if _time.time() > entry["until"]:
        _provider_health_cache.pop(provider, None)
        return True
    # For rate_limited: check if any key has recovered (different accounts/projects)
    if entry.get("status") == "rate_limited" and _provider_has_available_keys(provider):
        _provider_health_cache.pop(provider, None)
        return True
    return False

# ── Manually disabled providers ──────────────────────────────────────────────
# Populated at startup from DB and updated via /api/ai/providers/toggle.
_force_disabled: set = set()

def _set_provider_disabled(provider: str, disabled: bool) -> None:
    """Permanently disable or re-enable a provider (survives cooldown resets)."""
    if disabled:
        _force_disabled.add(provider)
        log.info(f"Provider {provider} force-disabled")
    else:
        _force_disabled.discard(provider)
        _provider_health_cache.pop(provider, None)
        log.info(f"Provider {provider} re-enabled")


# ── Emergency fallback chain ─────────────────────────────────────────────────
# Used when a user's configured chain has no usable providers (all disabled,
# in cooldown, or out of credits). Picks the FIRST configured provider that
# is currently available. Order: cheapest reliable → premium fallback.
_EMERGENCY_FALLBACK_CHAIN = [
    "or_gemini_flash",   # cheapest paid OR ($0.30/M)
    "or_gemini_lite",    # cheapest OR ($0.07/M)
    "or_deepseek",       # cheap reliable OR ($0.26/M)
    "or_qwen",           # free OR
    "groq",              # free fast (non-OR)
    "gemini_free",       # direct gemini fallback
    "gemini_paid",       # last resort — historically prone to status=0 errors
    "ollama",            # local last resort
]

def _build_emergency_chain(exclude: set = None) -> list:
    """Return a list of currently-available providers from the emergency
    fallback list, excluding any in `exclude` (e.g. providers that already
    failed in the user's chain).
    """
    exclude = exclude or set()
    chain = []
    for p in _EMERGENCY_FALLBACK_CHAIN:
        if p in exclude:
            continue
        if _is_provider_available(p):
            chain.append(p)
        if len(chain) >= 3:
            break
    return chain


def _is_valid_json_response(data) -> bool:
    """Return True if `data` looks like a usable JSON response, False if it
    looks like an error envelope. Truthy `{"error": "..."}` payloads should
    NOT win the parallel race against a slower-but-real success.
    """
    if not data or not isinstance(data, dict):
        return False
    # Heuristic: if only "error"/"status"/"message" keys are present and
    # status indicates failure, treat as invalid.
    keys = set(data.keys())
    error_only_keys = {"error", "status", "message", "code", "detail"}
    if keys and keys.issubset(error_only_keys):
        status = str(data.get("status", "")).lower()
        if status in {"error", "failed", "fail"} or "error" in data:
            return False
    # Explicit success=False
    if data.get("success") is False:
        return False
    return True


# ── Fallback content sentinels ───────────────────────────────────────────────
# Lower-case sub-strings that MUST NOT appear in published content. The pre-save
# scanner (see _scan_for_fallback_phrases) rejects any article containing them.
# These represent generic placeholder text injected by last-resort fallbacks
# when AI generation fails. If an article reaches the saver with these strings,
# something went wrong upstream and the content is not publishable.
_FALLBACK_MARKER_PHRASES = [
    "answer coming soon",
    "coming soon",
    "this section covers ",            # generic skeleton paragraph from minimal_draft
    "is an important consideration when evaluating",
    "is an important question about",
    "key factors include quality, pricing, and availability",
    "quality and authenticity are the most important factors",
    "always verify sourcing certifications and compare prices",
]

# ── Memory Helpers ───────────────────────────────────────────────────────────

def _get_mem_pct() -> float:
    """Return current memory usage as a percentage (0-100)."""
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
            total = info.get("MemTotal", 1)
            avail = info.get("MemAvailable", total)
            return round((1 - avail / total) * 100, 1)
    except Exception:
        return 0.0

def _ollama_unload_model():
    """Tell Ollama to unload the model immediately, freeing ~2GB RAM."""
    try:
        requests.post(
            f"{_live_ollama_url()}/api/generate",
            json={"model": _live_ollama_model(), "keep_alive": 0},
            timeout=5,
        )
        log.info(f"Ollama model {_live_ollama_model()} unloaded (keep_alive=0)")
    except Exception as e:
        log.debug(f"Ollama unload request failed (non-critical): {e}")

def _force_gc():
    """Force garbage collection to reclaim Python memory."""
    gc.collect()

# Backward-compatible alias (old code references this)
_ollama_writer_sem: asyncio.Semaphore | None = None

def _get_ollama_writer_sem() -> asyncio.Semaphore:
    """Legacy alias — now delegates to the global Ollama semaphore."""
    return _get_ollama_sem()
# Gemini models in priority order (newer = higher quality but may hit rate limits)
GEMINI_MODELS  = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
]
CRAWL_HEADERS  = {    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrawledPage:
    url: str
    title: str
    headings: List[str]
    paragraphs: List[str]
    word_count: int
    meta_desc: str

@dataclass
class PipelineStep:
    step: int
    name: str
    status: str          # pending | running | done | error | paused
    summary: str = ""
    details: Dict = field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""

@dataclass
class PipelineState:
    article_id: str
    keyword: str
    intent: str
    project_name: str
    steps: List[PipelineStep]
    draft_html: str = ""
    final_html: str = ""
    title: str = ""
    meta_title: str = ""
    meta_desc: str = ""
    seo_score: float = 0
    readability: float = 0
    word_count: int = 0
    issues_found: int = 0
    editorial_instructions: List[str] = field(default_factory=list)

@dataclass
class StepAIConfig:
    """Priority chain for a single pipeline step.
    Values: ollama | groq | gemini_free | gemini_paid | gemini | chatgpt | openai_paid
            | claude | anthropic | anthropic_paid | openrouter | or_qwen | or_deepseek
            | or_gemini_flash | or_gemini_lite | or_glm | or_gpt4o | or_claude
            | or_llama | or_qwen_coder | or_deepseek_r1 | skip
    """
    first:  str = "or_gemini_flash"
    second: str = "or_deepseek"
    third:  str = "or_gemini_lite"


@dataclass
class AIRoutingConfig:
    """Per-task AI priority chains for the full 12-step pipeline.

    ── SMART BALANCE TEMPLATE ── right-size AI to task complexity ──────────────
    TIER 1 — Trivial (URL matching, link planning)
      or_gemini_lite ($0.07/M) → or_qwen (free)
    TIER 2 — Simple JSON (research themes, structure, verify, review, score)
      or_gemini_flash ($0.30/M) → groq (fast fallback) → or_qwen (free last resort)
    TIER 3 — Content writing (draft, humanize, quality loop, redevelop)
      or_gemini_flash ($0.30/M) → or_deepseek ($0.26/M, strong writer) → gemini_paid (reliable last resort)
    TIER 4 — Score/timing-critical
      groq (fastest inference) → or_gemini_flash → skip

    Proven by real usage data (Apr 2026):
      or_gemini_flash Redevelop: 10.3K tokens = $0.0034  (vs gemini_paid = $0.025)
      or_gemini_flash QualityLoop: 10.5K tokens = $0.0028 (vs or_claude = $0.0112)
    ─────────────────────────────────────────────────────────────────────────────
    """
    # Steps 1-4 (research & structure) — JSON tasks
    # FIX 51-52: Remove Groq from Gemini chains to prevent rate limits
    # NOTE: Chains are pure-OR (all `or_*` providers). _call_ai_with_chain detects
    # this and switches to SEQUENTIAL fallback mode, avoiding the parallel race
    # that wastes ~2s/call on broken non-OR providers. Mixing in `gemini_paid`
    # here re-enables the race and burns retries — keep all entries `or_*` or `skip`.
    research:     StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "or_deepseek"))
    structure:    StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))
    verify:       StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    links:        StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    references:   StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    # Steps 6-9 (content writing) — quality matters, flash proven best value
    draft:        StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))
    recovery:     StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))
    review:       StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    issues:       StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    humanize:     StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))
    redevelop:    StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))
    # Steps 10-12 (scoring & improvement loop)
    score:        StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_gemini_lite", "skip"))
    quality_loop: StepAIConfig = field(default_factory=lambda: StepAIConfig("or_gemini_flash", "or_deepseek",    "or_gemini_lite"))

    # Phase C feature flag (2026-04-21): enable targeted per-section regeneration
    # for sections flagged by the per-section scorer. Default ON because the cost
    # ceiling is hard-capped (max 2 sections × 2 attempts = +4 LLM calls/article).
    # Set False to disable for legacy/lean presets where cost matters more than quality.
    targeted_regen: bool = True

def _routing_from_legacy(research_ai: str) -> "AIRoutingConfig":
    """Backward-compat: convert old single research_ai string to a full AIRoutingConfig."""
    cfg = AIRoutingConfig()
    if research_ai in ("ollama", "groq", "gemini"):
        second = "groq" if research_ai != "groq" else "gemini"
        cfg.research = StepAIConfig(research_ai, second, "gemini")
    return cfg


STEP_DEFS = [
    (1,  "Topic Research & Crawl"),
    (2,  "Structure Generation"),
    (3,  "Structure Verification"),
    (4,  "Internal Link Planning"),
    (5,  "Wikipedia References"),
    (6,  "Content Drafting"),
    (7,  "AI Quality Review"),
    (8,  "Issue Identification"),
    (9,  "Humanize"),
    (10, "Final Scoring"),
    (11, "Quality Improvement Loop"),
    (12, "Content Redevelopment"),
]

MIN_QUALITY_SCORE = 90  # Minimum acceptable content score (percentage) — target 95+

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

class SEOContentPipeline:
    """
    10-step SEO content generation pipeline with real AI + crawling.
    Each step builds on previous. Designed to be run as a background task.
    """

    def __init__(self, article_id: str, keyword: str, intent: str = "informational",
                 project_name: str = "", title: str = "", word_count: int = 2000,
                 project_id: str = "", db=None,
                 supporting_keywords: List[str] = None,
                 product_links: List[Dict] = None,
                 target_audience: str = "",
                 content_type: str = "blog",
                 research_ai: str = "auto",
                 ai_routing: "AIRoutingConfig" = None,
                 page_type: str = "article",
                 page_inputs: Dict = None,
                 pipeline_mode: str = "standard"):
        self.article_id  = article_id
        self.pipeline_mode = pipeline_mode or "standard"  # "standard" | "lean"
        self.keyword     = keyword
        self.intent      = intent
        self.project_name = project_name
        self.custom_title = title or ""
        self.page_type   = page_type or "article"
        self.page_inputs = page_inputs or {}
        # Adjust word-count minimum based on page type
        _wc_min = {"homepage": 500, "product": 800, "about": 500, "landing": 600, "service": 800}.get(self.page_type, 2000)
        self.target_wc   = max(word_count, _wc_min)
        self.project_id  = project_id
        self.db          = db          # caller passes get_db() result
        self.supporting_keywords = supporting_keywords or []
        self.product_links       = product_links or []
        self.target_audience     = target_audience or ""
        self.content_type        = content_type or "blog"
        self.research_ai         = research_ai or "auto"

        # Resolve routing: explicit AIRoutingConfig takes precedence over legacy string
        if ai_routing is not None:
            self.routing = ai_routing
        else:
            self.routing = _routing_from_legacy(self.research_ai)

        # Ollama server URL overrides: {server_id: url} — populated by main.py from DB
        self._ollama_servers: Dict[str, str] = {}

        self.state = PipelineState(
            article_id=article_id,
            keyword=keyword,
            intent=intent,
            project_name=project_name,
            steps=[PipelineStep(s, n, "pending") for s, n in STEP_DEFS],
        )
        self.content_state = ContentState()

        # Pipeline event log — captured during generation, stored in schema_json
        self._logs: List[Dict] = []

        # AI recovery state — set when all providers fail mid-step
        self._ai_recovery_needed: bool = False
        self._ai_recovery_provider: str = ""

        # Accumulated research data
        self._crawled_pages: List[CrawledPage] = []
        self._wiki_text: str = ""
        self._wiki_links: List[Dict] = []
        self._structure: Dict = {}
        self._structure_improvements: List[str] = []   # from Step 3 verification
        self._internal_links: List[Dict] = []
        self._external_links: List[Dict] = []
        self._authority_urls: List[str] = []
        self._reference_links: List[Dict] = []
        self._research_data: Dict = {}   # Deep research: facts, stats, wiki sections, sources
        self._issues: List[Dict] = []
        self._intent_data: Dict = {}
        self._target_entities: List[str] = []
        self._semantic_variations: List[str] = []
        self._blueprint = None  # Optional blueprint object for editorial intelligence

        # Unique trace ID for this pipeline run (correlates all AI calls)
        import uuid as _uuid
        self._pipeline_trace_id: str = _uuid.uuid4().hex[:16]

        # Initialize model profiler for dynamic timeout calculation
        self._profiler = get_profiler(db)
        if db:
            self._profiler.create_tables()

        # Initialize checkpoint manager and progress tracker
        self._checkpoint_mgr = get_checkpoint_manager(db)
        self._progress = create_progress_tracker(article_id, db) if db else None

        # Customer context — loaded from audience_profiles table for customer-aware rules & prompts
        self._customer_ctx: Dict = self._load_customer_context()

    def _load_customer_context(self) -> Dict:
        """Load customer/business context from audience_profiles + projects tables."""
        ctx = {
            "brand_name": self.project_name or "",
            "business_type": "",
            "target_locations": "",
            "customer_url": "",
            "usp": "",
            "personas": "",
            "products": "",
            "competitor_urls": "",
            "allowed_topics": "",
            "blocked_topics": "",
        }
        if not self.db or not self.project_id:
            return ctx
        try:
            # audience_profiles has the richest data
            row = self.db.execute(
                "SELECT website_url, business_type, usp, target_locations, business_locations, "
                "personas, products, competitor_urls, allowed_topics, blocked_topics "
                "FROM audience_profiles WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()
            if row:
                r = dict(row)
                ctx["customer_url"] = r.get("website_url") or ""
                ctx["business_type"] = r.get("business_type") or ""
                ctx["usp"] = r.get("usp") or ""
                ctx["target_locations"] = r.get("target_locations") or r.get("business_locations") or ""
                ctx["personas"] = r.get("personas") or ""
                ctx["products"] = r.get("products") or ""
                ctx["competitor_urls"] = r.get("competitor_urls") or ""
                ctx["allowed_topics"] = r.get("allowed_topics") or ""
                ctx["blocked_topics"] = r.get("blocked_topics") or ""

            # Fallback to projects table for missing fields
            proj = self.db.execute(
                "SELECT name, customer_url, business_type, target_locations, business_locations, usp "
                "FROM projects WHERE project_id = ?",
                (self.project_id,),
            ).fetchone()
            if proj:
                p = dict(proj)
                if not ctx["brand_name"]:
                    ctx["brand_name"] = p.get("name") or ""
                if not ctx["customer_url"]:
                    ctx["customer_url"] = p.get("customer_url") or ""
                if not ctx["business_type"]:
                    ctx["business_type"] = p.get("business_type") or ""
                if not ctx["target_locations"]:
                    ctx["target_locations"] = p.get("target_locations") or p.get("business_locations") or ""
                if not ctx["usp"]:
                    ctx["usp"] = p.get("usp") or ""
        except Exception as e:
            log.warning(f"Failed to load customer context: {e}")
        return ctx

    # ── Pipeline event log ──────────────────────────────────────────────────

    def _customer_context_block(self) -> str:
        """Build a prompt block with customer/business context for injection into AI prompts."""
        c = self._customer_ctx
        lines = []
        if c.get("brand_name"):
            lines.append(f"BRAND: {c['brand_name']}")
        if c.get("business_type"):
            lines.append(f"BUSINESS TYPE: {c['business_type'].upper()}")
        if c.get("customer_url"):
            lines.append(f"WEBSITE: {c['customer_url']}")
        if c.get("target_locations"):
            lines.append(f"TARGET LOCATIONS: {c['target_locations']}")
        if self.target_audience:
            lines.append(f"TARGET AUDIENCE: {self.target_audience}")
        if c.get("usp"):
            lines.append(f"UNIQUE SELLING POINT: {c['usp']}")
        if c.get("personas"):
            lines.append(f"BUYER PERSONAS: {c['personas'][:600]}")
        if c.get("products"):
            lines.append(f"PRODUCTS/SERVICES: {c['products'][:600]}")
        if c.get("blocked_topics"):
            lines.append(f"BLOCKED TOPICS (never mention): {c['blocked_topics']}")
        if not lines:
            return ""
        return "\n━━━ CUSTOMER CONTEXT (use this to personalise content) ━━━\n" + "\n".join(lines) + "\n"

    def _ensure_meta_title(self):
        """Ensure meta_title exists and is 30-65 chars with keyword for R10."""
        kw = self.keyword
        mt = self.state.meta_title or ""
        if mt and 30 <= len(mt) <= 65 and kw.lower() in mt.lower():
            return  # already good
        # Build from title or keyword
        base = self.state.title or kw.title()
        if kw.lower() not in base.lower():
            base = f"{kw.title()} — {base}"
        if len(base) < 30:
            base = f"{base} — Complete Guide"
        self.state.meta_title = base[:65]

    def _ensure_meta_desc(self):
        """Ensure meta_desc exists and is 100-165 chars for R11."""
        md = self.state.meta_desc or ""
        if md and 100 <= len(md) <= 165:
            return
        kw = self.keyword.lower()
        if not md and self.state.final_html:
            plain = re.sub(r"<[^>]+>", " ", self.state.final_html)
            plain = " ".join(plain.split())
            md = plain[:155]
        if not md:
            md = f"Discover everything about {kw}. Expert tips, buying guide, benefits, and more."
        if kw not in md.lower():
            md = f"{kw.title()}: {md}"
        if len(md) < 100:
            md = md.rstrip(".") + f". Your complete resource for {kw}."
        self.state.meta_desc = md[:160]

    def _scoring_customer_kwargs(self) -> Dict:
        """Return keyword arguments for check_all_rules() customer context."""
        c = self._customer_ctx
        return {
            "brand_name": c.get("brand_name", ""),
            "business_type": c.get("business_type", ""),
            "target_locations": c.get("target_locations", ""),
            "target_audience": self.target_audience,
            "customer_url": c.get("customer_url", ""),
        }

    def _resolve_ollama_url(self, provider: str) -> str:
        """Resolve the Ollama URL for a given provider tag.
        - 'ollama'              → env OLLAMA_URL (remote server)
        - 'ollama_remote'       → primary remote server from DB
        - 'ollama_remote_{id}'  → specific server from DB
        """
        if provider == "ollama_remote":
            # Use first registered remote or fall back to env
            for url, _model in self._ollama_servers.values():
                return url
            return _live_ollama_url()
        if provider.startswith("ollama_remote_"):
            sid = provider[len("ollama_remote_"):]
            entry = self._ollama_servers.get(sid)
            return entry[0] if entry else _live_ollama_url()
        return _live_ollama_url()

    def _resolve_ollama_model(self, provider: str) -> str:
        """Resolve the Ollama model for a given provider tag."""
        if provider == "ollama_remote":
            for _url, model in self._ollama_servers.values():
                return model or _live_ollama_model()
            return _live_ollama_model()
        if provider.startswith("ollama_remote_"):
            sid = provider[len("ollama_remote_"):]
            entry = self._ollama_servers.get(sid)
            return entry[1] if entry else _live_ollama_model()
        return _live_ollama_model()

    def _add_log(self, level: str, message: str, step: int = 0):
        """Append a timestamped log entry. level: info|warn|error|success"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "step": step,
            "msg": message,
        }
        self._logs.append(entry)
        # Keep max 500 entries to avoid unbounded growth
        if len(self._logs) > 500:
            self._logs = self._logs[-400:]

    # ── Page-type helpers ────────────────────────────────────────────────────

    def _page_type_context(self) -> str:
        """Return extra prompt context describing what kind of page we're generating."""
        if self.page_type == "article":
            return ""
        pi = self.page_inputs
        lines = [f"PAGE TYPE: {self.page_type.upper()}"]
        if self.page_type == "homepage":
            lines.append("Generate a professional homepage. Include: hero section with headline, services overview, trust signals/testimonials, and call-to-action sections.")
            if pi.get("business_name"):
                lines.append(f"Business: {pi['business_name']}")
            if pi.get("tagline"):
                lines.append(f"Tagline: {pi['tagline']}")
            if pi.get("services_list"):
                lines.append(f"Services: {pi['services_list']}")
            if pi.get("unique_selling_points"):
                lines.append(f"USPs: {pi['unique_selling_points']}")
            if pi.get("target_locations"):
                lines.append(f"Target Locations: {pi['target_locations']}")
        elif self.page_type == "product":
            lines.append("Generate a product page. Include: product description, features list, specifications table, benefits, FAQ, and purchase CTA.")
            if pi.get("product_name"):
                lines.append(f"Product: {pi['product_name']}")
            if pi.get("price"):
                lines.append(f"Price: {pi['price']}")
            if pi.get("features_list"):
                lines.append(f"Features: {pi['features_list']}")
            if pi.get("benefits"):
                lines.append(f"Benefits: {pi['benefits']}")
            if pi.get("specifications"):
                lines.append(f"Specifications: {pi['specifications']}")
        elif self.page_type == "about":
            lines.append("Generate an About Us page. Include: company story, mission/vision, team overview, milestones/achievements, and values.")
            if pi.get("company_story"):
                lines.append(f"Story: {pi['company_story']}")
            if pi.get("founding_year"):
                lines.append(f"Founded: {pi['founding_year']}")
            if pi.get("mission"):
                lines.append(f"Mission: {pi['mission']}")
            if pi.get("values"):
                lines.append(f"Values: {pi['values']}")
            if pi.get("achievements"):
                lines.append(f"Achievements: {pi['achievements']}")
        elif self.page_type == "landing":
            lines.append("Generate a landing page. Include: hero with headline + CTA, pain points → solution, benefits with proof, social proof/testimonials, and strong conversion CTA.")
            if pi.get("offer_headline"):
                lines.append(f"Offer: {pi['offer_headline']}")
            if pi.get("target_action"):
                lines.append(f"Target Action: {pi['target_action']}")
            if pi.get("pain_points"):
                lines.append(f"Pain Points: {pi['pain_points']}")
            if pi.get("benefits"):
                lines.append(f"Benefits: {pi['benefits']}")
            if pi.get("social_proof"):
                lines.append(f"Social Proof: {pi['social_proof']}")
        elif self.page_type == "service":
            lines.append("Generate a service page. Include: service overview, how it works (process steps), pricing information, FAQ, testimonials, and contact CTA.")
            if pi.get("service_name"):
                lines.append(f"Service: {pi['service_name']}")
            if pi.get("service_description"):
                lines.append(f"Description: {pi['service_description']}")
            if pi.get("process_steps"):
                lines.append(f"Process: {pi['process_steps']}")
            if pi.get("pricing_hint"):
                lines.append(f"Pricing: {pi['pricing_hint']}")
            if pi.get("faq_items"):
                lines.append(f"FAQ: {pi['faq_items']}")
        return "\n".join(lines)

    def _page_type_label(self) -> str:
        """Human-readable page type label for prompts."""
        return {"article": "SEO blog article", "homepage": "homepage", "product": "product page",
                "about": "About Us page", "landing": "landing page", "service": "service page"}.get(self.page_type, "SEO page")

    # ── Provider pre-flight health check ─────────────────────────────────────

    async def _preflight_provider_check(self):
        """Quick connectivity test for all providers used in routing chains.
        Marks unreachable providers as bad BEFORE pipeline starts.
        Prevents wasting 120s per step on unreachable Ollama instances.
        """
        import httpx

        # Collect unique providers from all routing chains
        providers_to_check = set()
        for cfg_name in ("research", "structure", "verify", "links", "references",
                         "draft", "review", "issues", "redevelop", "score", "quality_loop"):
            cfg = getattr(self.routing, cfg_name, None)
            if cfg:
                for p in (cfg.first, cfg.second, cfg.third):
                    if p and p != "skip":
                        providers_to_check.add(p)

        log.info(f"Pre-flight: checking {len(providers_to_check)} providers: {providers_to_check}")
        self._add_log("info", f"Pre-flight health check: {', '.join(sorted(providers_to_check))}")

        _or_checked = False  # Only test OR endpoint once, even if multiple or_* providers in chain
        _or_ok = False  # Whether the OR check succeeded
        for provider in providers_to_check:
            if provider in _force_disabled:
                continue
            try:
                if provider == "groq":
                    key = _live_groq_key()
                    if not key:
                        _mark_provider_bad("groq", "no_key", 3600)
                        self._add_log("warn", "Pre-flight: Groq — no API key configured")
                        continue
                    # Quick models list call (lightweight, no tokens consumed)
                    r = await asyncio.get_event_loop().run_in_executor(None, lambda: httpx.get(
                        "https://api.groq.com/openai/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=10,
                    ))
                    if r.status_code == 200:
                        self._add_log("success", "Pre-flight: Groq — reachable")
                        _mark_provider_ok("groq")
                    elif r.status_code == 401:
                        _mark_provider_bad("groq", "invalid_key", 3600)
                        self._add_log("error", "Pre-flight: Groq — invalid API key")
                    else:
                        self._add_log("warn", f"Pre-flight: Groq — HTTP {r.status_code}")

                elif provider in ("gemini", "gemini_free", "gemini_paid"):
                    key = _live_gemini_key(paid=(provider == "gemini_paid"))
                    if not key:
                        _mark_provider_bad(provider, "no_key", 3600)
                        self._add_log("warn", f"Pre-flight: {provider} — no API key configured")
                        continue
                    # Quick model list check
                    r = await asyncio.get_event_loop().run_in_executor(None, lambda k=key: httpx.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={k}",
                        timeout=10,
                    ))
                    if r.status_code == 200:
                        self._add_log("success", f"Pre-flight: {provider} — reachable")
                        _mark_provider_ok(provider)
                    elif r.status_code == 400:
                        _mark_provider_bad(provider, "invalid_key", 3600)
                        self._add_log("error", f"Pre-flight: {provider} — invalid API key")
                    else:
                        self._add_log("warn", f"Pre-flight: {provider} — HTTP {r.status_code}")

                elif provider == "ollama" or provider.startswith("ollama_"):
                    url = self._resolve_ollama_url(provider)
                    model = self._resolve_ollama_model(provider)
                    # Quick version check (tiny request, no model loading)
                    r = await asyncio.get_event_loop().run_in_executor(None, lambda u=url: httpx.get(
                        f"{u}/api/version",
                        timeout=5,
                    ))
                    if r.status_code == 200:
                        self._add_log("success", f"Pre-flight: {provider} ({url}) — reachable")
                        _mark_provider_ok(provider)
                        # Pre-warm: generate 1 token to load model into GPU memory
                        # This avoids cold-start delays on the first real call
                        is_remote = url and "localhost" not in url and "127.0.0.1" not in url
                        if is_remote:
                            # Skip warm-up — it blocks the queue if Ollama is busy
                            # from orphaned requests. The first real call handles cold
                            # start naturally with a few seconds extra latency.
                            self._add_log("info", f"Pre-flight: {model} on {url} — skipping warm-up")
                    else:
                        _mark_provider_bad(provider, "unreachable", 300)
                        self._add_log("error", f"Pre-flight: {provider} ({url}) — HTTP {r.status_code}")

                elif provider.startswith("or_") or provider == "openrouter":
                    if _or_checked:
                        # Already tested OR endpoint this pre-flight — reuse result
                        if _or_ok:
                            _mark_provider_ok(provider)
                        else:
                            _mark_provider_bad(provider, "or_endpoint_failed", 300)
                        continue
                    _or_checked = True
                    key = _live_openrouter_key()
                    if not key:
                        _mark_provider_bad(provider, "no_key", 3600)
                        self._add_log("error", f"Pre-flight: OpenRouter — no API key configured")
                        # Mark all OR providers bad if key missing
                        for _op in list(providers_to_check):
                            if _op.startswith("or_") or _op == "openrouter":
                                if not _is_provider_available(_op):
                                    continue
                                _mark_provider_bad(_op, "no_key", 3600)
                        continue
                    # Lightweight check: fetch OR models list (no tokens consumed)
                    r = await asyncio.get_event_loop().run_in_executor(None, lambda k=key: httpx.get(
                        "https://openrouter.ai/api/v1/models",
                        headers={"Authorization": f"Bearer {k}"},
                        timeout=8,
                    ))
                    if r.status_code == 200:
                        _or_ok = True
                        self._add_log("success", f"Pre-flight: OpenRouter — reachable ({provider})")
                        # Mark all OR providers in this chain as OK
                        for _op in providers_to_check:
                            if _op.startswith("or_") or _op == "openrouter":
                                _mark_provider_ok(_op)
                    elif r.status_code == 401:
                        _mark_provider_bad(provider, "invalid_key", 3600)
                        self._add_log("error", "Pre-flight: OpenRouter — invalid API key")
                    else:
                        self._add_log("warn", f"Pre-flight: OpenRouter — HTTP {r.status_code} ({provider})")

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                _mark_provider_bad(provider, "unreachable", 300)
                self._add_log("error", f"Pre-flight: {provider} — unreachable ({type(e).__name__})")
                log.warning(f"Pre-flight: {provider} unreachable: {e}")
            except Exception as e:
                log.warning(f"Pre-flight: {provider} check failed: {e}")
                self._add_log("warn", f"Pre-flight: {provider} — check failed ({str(e)[:80]})")

    # ── Step runner ──────────────────────────────────────────────────────────

    async def run(self, on_step=None, step_mode: str = "auto", start_step: int = 1):
        """
        Execute pipeline steps.
        step_mode:
          "auto"  — run all steps without pausing (default, backward-compat)
          "pause" — pause BEFORE each step so user can select AI, then click Continue
        start_step: 1-based step to start from (skip earlier steps)
        """
        # Pause/resume event — signaled by /continue endpoint
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # initially not paused (step 1 starts immediately in auto; in pause mode first step waits below)
        self._step_mode = step_mode
        self._ai_recovery_event = asyncio.Event()
        self._ai_recovery_event.set()  # set = no recovery in progress
        self._cancelled = False
        self._consecutive_all_failed = 0  # Track consecutive all-providers-failed events

        # ── Iteration loop state (steps 10-12) ────────────────────────────
        self._iteration_review_event = asyncio.Event()
        self._iteration_review_event.set()  # not waiting
        self._iteration_finalized = False    # user clicked "Finalize"
        self._iteration_current = 0          # current iteration number
        self._iteration_max = 3              # max iterations
        self._iteration_target_score = 80    # score threshold to stop
        self._iteration_waiting = False      # True when waiting for user review

        # ── LEAN MODE: minimal 3-call pipeline ───────────────────────────
        if self.pipeline_mode == "lean":
            await self._run_lean(on_step, start_step)
            
            # ── Optional: Multi-AI Review (if enabled) ──────────────────
            if getattr(self, 'enable_multi_ai_review', False):
                await self._multi_ai_review()
            
            self._save_final_to_db()
            mem_before = _get_mem_pct()
            _ollama_unload_model()
            _force_gc()
            mem_after = _get_mem_pct()
            log.info(f"Lean pipeline done for {self.article_id}: memory {mem_before}% → {mem_after}%")
            return

        # Steps 1-9 run linearly; steps 10-12 run in iteration loop
        linear_fns = [
            self._step1_research,
            self._step2_structure,
            self._step3_verify_structure,
            self._step4_internal_links,
            self._step5_wikipedia,
            self._step6_draft,
            self._step7_review,
            self._step8_identify_issues,
            self._step9_humanize,
        ]
        # Iteration loop functions: Score → Quality Loop → Redevelop
        loop_fns = [
            (self._step11_score, 9),         # idx 9 → step 10
            (self._step12_quality_loop, 10),  # idx 10 → step 11
            (self._step10_redevelop, 11),     # idx 11 → step 12
        ]

        # ── Pre-flight provider health check ──────────────────────────────
        await self._preflight_provider_check()

        # ── Phase 1: Linear steps 1-9 ────────────────────────────────────
        for idx, fn in enumerate(linear_fns):
            s = self.state.steps[idx]
            if await self._run_single_step(s, fn, start_step, on_step) == "cancel":
                break
            await asyncio.sleep(2.0)

        # ── Phase 2: Iteration loop for steps 10-12 ─────────────────────
        if not self._cancelled:
            await self._run_iteration_loop(loop_fns, start_step, on_step)

        # ── Optional: Multi-AI Review (if enabled) ──────────────────────
        if getattr(self, 'enable_multi_ai_review', False):
            await self._multi_ai_review()

        # Save final article
        self._save_final_to_db()

        # ── Clean memory release ─────────────────────────────────────────
        mem_before = _get_mem_pct()
        _ollama_unload_model()
        _force_gc()
        mem_after = _get_mem_pct()
        log.info(f"Pipeline done for {self.article_id}: memory {mem_before}% → {mem_after}%")

    # ─────────────────────────────────────────────────────────────────────────
    # LEAN PIPELINE: 3-call budget mode ($0.08-$0.20 per article)
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_lean(self, on_step=None, start_step: int = 1):
        """
        Ultra-lean pipeline: 3 AI calls only.
          L1: Combined Research + Structure (1 JSON call)
          L2: Wikipedia/Web references (0 AI calls — web fetch only)
          L3: Full article draft with self-correction (1 text call)
          L4: Local scoring + programmatic SEO fixes (0 AI calls)

        Cost: ~$0.08-$0.20 per article (vs $1.5-$3 standard).
        Uses routing.research for L1, routing.draft for L3.
        """
        self._add_log("info", "⚡ LEAN MODE — 3-call budget pipeline", 1)

        # Override routing for lean mode — ensure we use reliable, cheap providers
        # regardless of what the user/DB has configured (DB config may have broken providers).
        # EXCEPTION: if the caller explicitly supplied an Ollama-only routing (Phase F.3
        # local-only test mode), respect it — do not silently override.
        _user_forced_ollama = (
            getattr(self.routing, "draft", None) is not None
            and self.routing.draft.first == "ollama"
            and self.routing.research.first == "ollama"
        )
        if _user_forced_ollama:
            self._add_log("info", "Lean routing: respecting caller's ollama-only chain", 1)
        else:
            lean_cfg = StepAIConfig("or_gemini_flash", "or_deepseek", "groq")
            self.routing.research = lean_cfg
            self.routing.draft = lean_cfg
            self.routing.references = StepAIConfig("or_gemini_flash", "groq", "skip")
            self._add_log("info", f"Lean routing: or_gemini_flash → or_deepseek → groq", 1)

        # ── L1: Combined Research + Structure (1 AI call) ─────────────────
        s1 = self.state.steps[0]  # step 1
        s1.status = "running"
        s1.started_at = datetime.now(timezone.utc).isoformat()
        self._add_log("info", "Step 1: Research + Structure — started (lean combined)", 1)
        self._db_persist_status("step_1_running")
        if on_step:
            on_step(1, "Research + Structure", "running", "")

        try:
            await self._lean_step1_plan()
            s1.status = "done"
            s1.ended_at = datetime.now(timezone.utc).isoformat()
            s1.summary = f"Plan: H1 + {len(self._structure.get('h2_sections', []))} sections + {len(self._structure.get('faqs', []))} FAQs (lean)"
            self._add_log("success", f"Step 1: Research + Structure — completed. {s1.summary}", 1)
            if on_step:
                on_step(1, "Research + Structure", "done", s1.summary)
        except Exception as e:
            s1.status = "error"; s1.summary = str(e)
            self._add_log("error", f"Step 1 failed: {e}", 1)
            log.error(f"Lean L1 failed: {e}", exc_info=True)
            self._structure = self._default_structure()

        self._db_persist_status(f"step_1_{s1.status}")
        await asyncio.sleep(1.0)

        # Mark steps 2-4 as skipped (lean mode consolidates them)
        for idx in [1, 2, 3]:  # steps 2, 3, 4
            s = self.state.steps[idx]
            s.status = "done"
            s.summary = "Merged into Step 1 (lean mode)"
            s.started_at = s.ended_at = datetime.now(timezone.utc).isoformat()

        # ── L2: Wikipedia + Web research (0 AI calls) ─────────────────────
        s5 = self.state.steps[4]  # step 5
        s5.status = "running"
        s5.started_at = datetime.now(timezone.utc).isoformat()
        self._add_log("info", "Step 5: Wikipedia References — started", 5)
        self._db_persist_status("step_5_running")
        if on_step:
            on_step(5, "Wikipedia References", "running", "")

        try:
            await self._step5_wikipedia()
            s5.status = "done"
            s5.ended_at = datetime.now(timezone.utc).isoformat()
            if on_step:
                on_step(5, s5.name, "done", s5.summary)
        except Exception as e:
            s5.status = "done"
            s5.ended_at = datetime.now(timezone.utc).isoformat()
            s5.summary = f"Wikipedia failed (non-blocking): {str(e)[:80]}"
            self._add_log("warn", f"Step 5: Wikipedia — {s5.summary}", 5)

        self._db_persist_status(f"step_5_{s5.status}")
        await asyncio.sleep(1.0)

        # ── L3: Full article draft (1 AI call, single pass) ──────────────
        s6 = self.state.steps[5]  # step 6
        s6.status = "running"
        s6.started_at = datetime.now(timezone.utc).isoformat()
        self._add_log("info", "Step 6: Full Article Draft — started (lean single-call)", 6)
        self._db_persist_status("step_6_running")
        if on_step:
            on_step(6, "Content Drafting", "running", "")

        try:
            await self._lean_step3_draft()
            s6.status = "done"
            s6.ended_at = datetime.now(timezone.utc).isoformat()
            s6.summary = f"Draft written: {self.state.word_count} words (lean single-call)"
            self._add_log("success", f"Step 6: Draft — completed. {s6.summary}", 6)
            if on_step:
                on_step(6, "Content Drafting", "done", s6.summary)
        except Exception as e:
            s6.status = "error"; s6.summary = str(e)
            self._add_log("error", f"Step 6 failed: {e}", 6)
            log.error(f"Lean L3 draft failed: {e}", exc_info=True)
            # Use structural placeholder if all fails
            self.state.draft_html = self._minimal_draft_from_structure()
            self.state.final_html = self.state.draft_html
            self.state.title = self._structure.get("h1", self.keyword.title())
            self.state.meta_title = self._structure.get("meta_title", self.keyword[:60])
            self.state.meta_desc = self._structure.get("meta_description", "")[:160]
            self.state.word_count = len(re.sub(r"<[^>]+>", " ", self.state.draft_html).split())

        self._db_persist_status(f"step_6_{s6.status}")
        await asyncio.sleep(1.0)

        # Mark steps 7, 8, 9 as skipped
        for idx in [6, 7, 8]:  # steps 7, 8, 9
            s = self.state.steps[idx]
            s.status = "done"
            s.summary = "Skipped (lean mode — no humanize/review)"
            s.started_at = s.ended_at = datetime.now(timezone.utc).isoformat()

        # ── L4: Local scoring + programmatic SEO fixes (0 AI calls) ──────
        s10 = self.state.steps[9]  # step 10
        s10.status = "running"
        s10.started_at = datetime.now(timezone.utc).isoformat()
        self._add_log("info", "Step 10: Local Scoring — started (lean, no AI)", 10)
        self._db_persist_status("step_10_running")
        if on_step:
            on_step(10, "Final Scoring", "running", "")

        try:
            # Apply programmatic post-processing (links, density, R17/R27/R34/R43 etc.)
            self.state.final_html = self._post_draft_inject(self.state.final_html)
            self.state.final_html = self._scrub_ai_patterns(self.state.final_html)
            self.state.final_html = await self._enforce_readability(self.state.final_html)
            self.state.final_html = self._intelligence_post_process(self.state.final_html)

            # ── Integrity scan: detect mid-word corruption (trust killer) ──
            self.state.final_html = self._check_content_integrity(self.state.final_html)

            # ── Phase B: per-section scoring (read-only) ──
            self._score_all_sections(self.state.final_html)

            # ── Phase C: targeted regen of weak sections (feature-flagged) ──
            try:
                self.state.final_html = await self._run_targeted_regen(self.state.final_html)
            except Exception as _regen_err:
                log.warning(f"Targeted regen skipped (non-fatal): {_regen_err}")

            # Run the scoring (local only, no AI)
            await self._step11_score()
            await self._step11_score()
            if on_step:
                on_step(10, "Final Scoring", "done", s10.summary)
        except Exception as e:
            s10.status = "done"
            s10.summary = f"Scoring failed: {str(e)[:80]}"
            self._add_log("warn", f"Step 10: {s10.summary}", 10)

        self._db_persist_status(f"step_10_{s10.status}")

        # Mark steps 11, 12 as skipped (no iteration loop in lean)
        for idx in [10, 11]:  # steps 11, 12
            s = self.state.steps[idx]
            s.status = "done"
            s.summary = "Skipped (lean mode — no iteration loop)"
            s.started_at = s.ended_at = datetime.now(timezone.utc).isoformat()

        self._add_log("success", f"⚡ LEAN pipeline complete — score: {self.state.seo_score}% · {self.state.word_count} words · 3 AI calls", 10)

    async def _lean_step1_plan(self):
        """L1: Combined Research + Structure + Links in a single AI call."""
        self._consecutive_all_failed = 0  # Fresh start
        pt_ctx = self._page_type_context()
        pt_label = self._page_type_label()
        customer_ctx = self._customer_context_block()

        prompt = f"""Research and plan a comprehensive SEO {pt_label} about: "{self.keyword}"

Intent: {self.intent}
Business: {self.project_name or "the business"}
{"Target Audience: " + self.target_audience if self.target_audience else ""}
{"Supporting keywords: " + ', '.join(self.supporting_keywords[:8]) if self.supporting_keywords else ""}
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
{customer_ctx}

Return a JSON object with:
- "h1": compelling H1 title with keyword (<65 chars)
- "meta_title": SEO meta title (<60 chars, includes keyword)
- "meta_description": meta description (<160 chars, includes keyword)
- "intro_plan": 1-sentence intro plan (hook + overview)
- "conclusion_plan": 1-sentence conclusion plan (summary + CTA)
- "themes": [5 key themes/angles to cover]
- "key_facts": [5 specific facts/data points about this topic]
- "h2_sections": [
    {{"h2": "Section Title", "anchor": "section-slug", "h3s": ["Sub 1", "Sub 2"], "word_target": 200}}
  ] (6-8 sections)
- "faqs": [{{"q": "Question?", "a": "Brief answer hint"}}] (5-6 FAQs)
- "internal_links": [{{"href": "/relevant-page", "anchor_text": "descriptive text"}}] (4 links)
- "external_links": [{{"href": "https://authority-site.com/page", "anchor_text": "descriptive text"}}] (3 links)
- "toc_anchors": ["anchor1", "anchor2"] (matching h2 anchors)

REQUIREMENTS:
- Include one H2 about "How to Choose" / buyer guidance
- Include one H2 with comparisons / pros and cons
- H2 anchors should be URL-friendly slugs
- Facts should be specific, not generic
- External links should be real, well-known authority sites (government, Wikipedia, educational)
- Internal links should use relative paths starting with /

Return ONLY valid JSON, no markdown fences."""

        data = await self._call_ai_with_chain(self.routing.research, prompt, temperature=0.4, max_tokens=2000)

        if not data:
            self._structure = self._default_structure()
            return

        # Store structure
        self._structure = {
            "h1": data.get("h1", self.keyword.title()),
            "meta_title": data.get("meta_title", self.keyword[:60]),
            "meta_description": data.get("meta_description", "")[:160],
            "intro_plan": data.get("intro_plan", ""),
            "conclusion_plan": data.get("conclusion_plan", ""),
            "h2_sections": data.get("h2_sections", []),
            "faqs": data.get("faqs", []),
            "toc_anchors": [s.get("anchor", "") for s in data.get("h2_sections", [])],
        }

        # Store research data
        self.state.steps[0].details["analysis"] = {
            "themes": data.get("themes", []),
            "key_facts": data.get("key_facts", []),
            "gaps": [],
            "angles": [],
        }

        # Store links
        self._internal_links = data.get("internal_links", [])
        self._external_links = data.get("external_links", [])

        # Intent classification
        try:
            from services.seo_brief_generator import classify_intent
            self._intent_data = {"primary_intent": classify_intent(self.keyword)}
        except Exception:
            self._intent_data = {"primary_intent": self.intent}

        # Phase D: structured intent plan (lean path)
        try:
            from engines.intent_planner import build_intent_plan
            self._intent_data["plan"] = build_intent_plan(
                keyword=self.keyword,
                primary_intent=self._intent_data.get("primary_intent", ""),
                research_themes=data.get("themes", []) if isinstance(data, dict) else [],
            )
        except Exception:
            pass

        # Semantic variations for keyword density
        kw_words = self.keyword.lower().split()
        if len(kw_words) >= 2:
            self._semantic_variations = [
                " ".join(reversed(kw_words)),
                f"premium {' '.join(kw_words[-2:])}",
                f"quality {' '.join(kw_words[-2:])}",
                f"authentic {' '.join(kw_words[-2:])}",
                f"best {' '.join(kw_words[-2:])}",
            ]
        elif kw_words:
            self._semantic_variations = [
                f"premium {kw_words[0]}", f"quality {kw_words[0]}",
                f"authentic {kw_words[0]}", f"best {kw_words[0]}",
            ]

    async def _lean_step3_draft(self):
        """L3: Full article in a single AI call with self-correction baked in."""
        # Reset consecutive failure counter — W5 wiki step may have incremented it
        self._consecutive_all_failed = 0
        structure = self._structure
        h2_sections = structure.get("h2_sections", [])
        research_block = self._research_context_block()
        customer_ctx = self._customer_context_block()
        pt_label = self._page_type_label()
        kw = self.keyword

        # Build structure spec
        sections_spec = ""
        for s in h2_sections:
            h3_list = ""
            if s.get("h3s"):
                # Defensive: some models return list of dicts ({"text": "..."}) instead of strings.
                _h3_strs = []
                for _h in s["h3s"]:
                    if isinstance(_h, str):
                        _h3_strs.append(_h)
                    elif isinstance(_h, dict):
                        _h3_strs.append(_h.get("text") or _h.get("h3") or _h.get("title") or "")
                _h3_strs = [x for x in _h3_strs if x]
                if _h3_strs:
                    h3_list = "\n      H3s: " + ", ".join(_h3_strs)
            sections_spec += f'\n    <h2 id="{s.get("anchor", "")}">{s["h2"]}</h2> (~{s.get("word_target", 200)} words){h3_list}'

        # Build links block
        links_block = ""
        if self._internal_links:
            links_block += "\nINTERNAL LINKS (embed naturally in paragraphs):\n" + "\n".join(
                f'  <a href="{lk.get("href","")}">{lk.get("anchor_text","")}</a>' for lk in self._internal_links[:5])
        if self._external_links:
            links_block += "\nEXTERNAL LINKS (embed naturally):\n" + "\n".join(
                f'  <a href="{lk.get("href","")}" target="_blank" rel="noopener">{lk.get("anchor_text","")}</a>' for lk in self._external_links[:4])
        if self._reference_links:
            links_block += "\nWIKIPEDIA REFERENCES:\n" + "\n".join(
                f'  <a href="{r["url"]}" target="_blank" rel="noopener">{r["title"]} (Wikipedia)</a>' for r in self._reference_links[:3])

        # Build FAQ spec
        faqs = structure.get("faqs", [])
        faq_spec = ""
        if faqs:
            faq_spec = "\n\nFAQ SECTION:\n" + "\n".join(
                f'  - {f.get("q", f.get("question", ""))}' for f in faqs[:6])

        # Phase D: render intent-plan constraint block (lean draft)
        try:
            from engines.intent_planner import render_intent_block
            _lean_intent_block = render_intent_block(self._intent_data.get("plan") or {})
        except Exception:
            _lean_intent_block = ""
        _lean_intent_block_section = (_lean_intent_block + "\n\n") if _lean_intent_block else ""

        prompt = f"""Write a complete SEO {pt_label} about "{kw}".

{_lean_intent_block_section}TITLE (H1): {structure.get("h1", kw.title())}
Intent: {self._intent_data.get('primary_intent', self.intent)}
Business: {self.project_name or "the business"}
Target word count: {max(self.target_wc, 2000)} words MINIMUM (aim for 2000-2500 words — longer is better)

STRUCTURE:{sections_spec}

{research_block}

{links_block}

{faq_spec}

{customer_ctx}

WRITING RULES:
- KEYWORD: "{kw}" — use naturally 2-3 times per section. Density target: 1.0-1.5%.
- Start first paragraph with "{kw}" and include a definition ("{kw} refers to..." or "{kw} is a...") in the first 150 words.

── READABILITY (Target Flesch 60-70) ──
- Sentence length: Average 15-20 words. Mix short (8-12w) with medium (18-25w). Break any >30w sentences.
- Active voice >80% (subject → verb → object). Example: "Cinnamon reduces" not "Cinnamon is known to reduce".
- Replace complex words: utilize→use, facilitate→help, commence→start, ascertain→find, endeavor→try
- Add transitions between paragraphs: However, Moreover, Additionally, Meanwhile, Therefore
- Vary paragraph length: 2-4 sentences (~60-100 words). Never 5 consecutive paragraphs of same length.
- Max 3 sentences/paragraph. Max 80 words/paragraph.

── SENTENCE VARIETY (20+ Different Openers) ──
- Limit "The" starters to <20% of all sentences
- Questions (10%+ of sentences): "How do you choose?", "What makes X better?", "Why does this matter?"
- Imperatives: Do, Try, Consider, Start, Use, Avoid, Compare, Check, Look for, Remember
- Transitional: However, Moreover, Therefore, Meanwhile, Subsequently, Nevertheless, Furthermore
- Subordinate clauses: While, Although, Because, Since, If, When, After, Before, Unless
- Avoid 3+ consecutive sentences starting the same way
- Mix: declarative, interrogative, occasional exclamatory (for emphasis)
- Adverbs occasionally: Typically, Generally, Often, Sometimes, Usually, Frequently, Rarely
- Coordinating (sparingly): And, But, So (for emphasis only, not >5% of sentences)

── CALLS-TO-ACTION (3 Required: Intro/Mid/End) ──
1. SOFT CTA in intro (after 2-3 paragraphs):
   Format: "Discover the benefits of {kw} for [specific benefit]"
   Verbs: Discover, Learn, Explore, Find out, Uncover
2. MID-CONTENT CTA (after 40% of sections):
   Format: <div class="cta-box"><strong>Ready to [action]?</strong> [urgent benefit statement]</div>
   Verbs: Try, Compare, Download, Subscribe, Get started, Shop, Browse
3. CONCLUSION CTA (strong action in final paragraph):
   Required verbs: Buy, Shop, Order, Contact, Get, Start, Compare
   Add urgency: "Start today", "Don't wait", "Limited time", "Act now"
   Add benefit: "...and enjoy [specific benefit]"

── DATA CREDIBILITY (5+ Sourced Statistics) ──
- Government: FDA, USDA, NIH, CDC, WHO (with year: "According to FDA (2024)...")
- Academic: PubMed studies, university research ("Harvard study (2023) found...")
- Industry: Grand View Research, IBISWorld, Statista ("Grand View Research reports (2024)...")
- Expert quotes: Named experts with credentials ("Dr. Jane Smith, PhD from MIT, states...")
- Attribution format: "According to [Source] ([Year]), [statistic]..."
- Use ranges for estimates: "approximately 20-30%" not unsourced "23.4%"
- NEVER state precise statistics without naming the source in the same sentence

── STORYTELLING & VOICE (2+ Each) ──
Narrative elements:
- Use third-person scenarios: "A buyer sourcing {kw} for restaurant use will find...", "Consider a home cook comparing two suppliers..."
- Specific examples grounded in cited evidence (Spices Board India, USDA, ISO standards) — never fabricated personal anecdotes
- Before/after scenarios tied to documented data, not invented testing
- Brief customer-style scenarios (2-3 sentences, third-person, plausible) — but NEVER fabricate named experts ("Chef X of Y Lab")
- Analogies: "Think of {kw} like...", "This works similarly to..."
- Sensory descriptions (for food/physical products): smell,taste, texture, appearance
Opinion signals (NEUTRAL framing — no fake first-person):
- Take stance: "The strongest option here is X because Y", "Avoid X when Y", "For most buyers, prefer X over Y"
- Contrarian views (if supported by a citation): "Contrary to popular belief, [source] shows..."
- DO NOT write "we tested", "in our testing", "our team evaluated", "hands-on review", "after putting this to the test", "we've found" — these fabricated authority claims are dishonest if no real testing happened and reviewers will flag them.
- Specific over general: NOT "many benefits", YES "improved energy within 2-3 days (per [cited source])"

── BUYER GUIDANCE ──
- Include buyer guidance: "how to choose", "what to look for", "best for", "pros and cons".
- Cite SPECIFIC named sources (e.g. "FDA guidelines", "a 2024 study by Harvard"). Unsourced stats are BAD.
- Show expertise through SPECIFIC details (cultivar names, grade thresholds, processing steps, measurable claims with units). Do NOT use first-person testing claims ("we tested", "in our experience", "hands-on", "our team") — they sound fabricated and damage trust.
- Write like a knowledgeable human with real opinions. Use contractions (don't, isn't, you'll).
- Include nuance: "however", "that said", "the catch is", "on the other hand".

── FORBIDDEN ──
- Words: delve, multifaceted, landscape, tapestry, nuanced, robust, myriad, paradigm, foster, holistic, pivotal, streamline, cutting-edge, plethora, underscore
- Phrases: "let's explore", "when it comes to", "in today's world", "let's dive in", "furthermore/moreover/additionally" in chains

FORMAT:
- Introduction (150-200w) with hook + TL;DR box (<div class="key-takeaway">) + SOFT CTA at end of intro
- TOC: <nav><ul> with anchor links to H2s
- Body sections with H2/H3, <p>, <ul>, <ol>, <table>, <strong>, <a>
- Include 1 comparison <table> with 3+ rows × 3+ columns
- MID-CONTENT CTA: After section 2 or 3, insert <div class="cta-box"><strong>Ready to [action]?</strong> [benefit]</div>
- FAQ section: each question as <h3> with 40-60 word <p> answers
- Conclusion (100-150w) with STRONG ACTION CTA (buy/shop/order/contact/start)

SELF-CHECK before output:
- Remove any AI-sounding phrases
- Verify keyword is in first sentence
- Ensure all links from above are embedded
- Check no paragraph exceeds 80 words
- Verify varied sentence openers

Return ONLY the final HTML article. No markdown fences, no explanations."""

        draft = await self._call_ai_raw_with_chain(
            self.routing.draft, prompt, temperature=0.6, max_tokens=8000
        )

        if not draft or len(draft) < 300:
            log.warning("Lean draft failed — using structural placeholder")
            draft = self._minimal_draft_from_structure()

        # Clean code fences
        draft = re.sub(r"```html\n?", "", draft)
        draft = re.sub(r"```\n?", "", draft).strip()

        self.state.draft_html = draft
        self.state.final_html = draft
        self.state.title = structure.get("h1", self.keyword.title())
        self.state.meta_title = structure.get("meta_title", self.keyword[:60])
        self.state.meta_desc = structure.get("meta_description", "")[:160]
        self.state.word_count = len(re.sub(r"<[^>]+>", " ", draft).split())

    async def _run_single_step(self, s, fn, start_step, on_step) -> str:
        """Execute one pipeline step with pause/cancel handling. Returns 'cancel' or 'ok'."""
        # Skip already-completed steps (for resume from step N)
        if s.step < start_step:
            if s.status != "done":
                s.status = "done"
                s.summary = s.summary or "skipped (resumed from later step)"
            return "ok"

        # Check if cancelled
        if self._cancelled:
            s.status = "pending"
            s.summary = "Cancelled by user"
            self._add_log("warn", f"Step {s.step}: {s.name} — cancelled", s.step)
            return "cancel"

        # In step-by-step mode: pause BEFORE each step so user can select AI first
        if self._step_mode == "pause":
            s.status = "paused"
            self._pause_event.clear()
            self._add_log("info", f"⏸ Ready for Step {s.step}: {s.name} — select AI then click Continue", s.step)
            self._db_persist_status(f"step_{s.step}_ready")
            try:
                await asyncio.wait_for(self._pause_event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                self._add_log("warn", "Pipeline timed out waiting — auto-resuming")
            if self._cancelled:
                s.status = "pending"
                s.summary = "Cancelled by user"
                return "cancel"

        # Wait for any externally set pause
        elif not self._pause_event.is_set():
            self._add_log("info", f"Pipeline paused before Step {s.step}", s.step)
            self._db_persist_status(f"step_{s.step}_paused")
            try:
                await asyncio.wait_for(self._pause_event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                self._add_log("warn", "Pipeline timed out waiting — auto-resuming")

        s.status = "running"
        s.started_at = datetime.now(timezone.utc).isoformat()
        self._add_log("info", f"Step {s.step}: {s.name} — started", s.step)
        self._db_persist_status(f"step_{s.step}_running")
        if on_step:
            on_step(s.step, s.name, "running", "")

        try:
            await fn()
            s.status = "done"
            s.ended_at = datetime.now(timezone.utc).isoformat()
            self._add_log("success", f"Step {s.step}: {s.name} — completed. {s.summary}", s.step)
            if on_step:
                on_step(s.step, s.name, "done", s.summary)
        except Exception as e:
            s.status = "error"
            s.summary = str(e)
            s.ended_at = datetime.now(timezone.utc).isoformat()
            self._add_log("error", f"Step {s.step}: {s.name} — FAILED: {e}", s.step)
            log.error(f"Pipeline step {s.step} failed: {e}", exc_info=True)
            if on_step:
                on_step(s.step, s.name, "error", str(e))
            # Safety fallbacks so downstream steps still have data to work with
            if s.step == 2 and not self._structure.get("h2_sections"):
                self._structure = self._default_structure()
                log.info("Step 2 errored — using default structure as fallback")
            if s.step == 6 and not self.state.draft_html:
                self.state.draft_html = self._minimal_draft_from_structure()
                self.state.final_html = self.state.draft_html
                self.state.title = self._structure.get("h1", self.keyword.title())
                self.state.meta_title = self._structure.get("meta_title", self.keyword[:60])
                self.state.meta_desc = self._structure.get("meta_description", "")[:160]
                self.state.word_count = len(re.sub(r"<[^>]+>", " ", self.state.draft_html).split())
                s.summary = f"AI failed — structural placeholder draft ({self.state.word_count}w)"
                log.info("Step 6 errored — using minimal structural draft as fallback")

        self._db_persist_status(f"step_{s.step}_{s.status}")
        return "ok"

    async def _run_iteration_loop(self, loop_fns, start_step, on_step):
        """Run Score→Quality Loop→Redevelop in a loop up to 3 times.
        After each iteration: wait 15s for user review. Auto-continue if no response.
        Stop if: score >= 80, user clicks Finalize, or 3 iterations done.
        """
        for iteration in range(1, self._iteration_max + 1):
            if self._cancelled or self._iteration_finalized:
                break

            self._iteration_current = iteration
            self._add_log("info", f"🔄 Iteration {iteration}/{self._iteration_max} — starting Score → Quality → Redevelop", 10)
            self._db_persist_status(f"iteration_{iteration}_start")

            # Reset step statuses for re-run (iterations 2+)
            if iteration > 1:
                for fn, step_idx in loop_fns:
                    s = self.state.steps[step_idx]
                    s.status = "pending"
                    s.summary = ""
                    s.started_at = None
                    s.ended_at = None

            # Run all 3 loop steps
            for fn, step_idx in loop_fns:
                s = self.state.steps[step_idx]
                if self._cancelled or self._iteration_finalized:
                    break
                result = await self._run_single_step(s, fn, start_step, on_step)
                if result == "cancel":
                    return
                await asyncio.sleep(2.0)

            # Check score after this iteration
            current_score = self.state.seo_score or 0
            self._add_log("info",
                f"🔄 Iteration {iteration}/{self._iteration_max} complete — score: {current_score}%",
                10)

            # If score meets threshold, stop
            if current_score >= self._iteration_target_score:
                self._add_log("success",
                    f"✓ Score {current_score}% ≥ {self._iteration_target_score}% — iteration loop complete",
                    10)
                break

            # If this was the last iteration, stop
            if iteration >= self._iteration_max:
                self._add_log("warn",
                    f"⚠ Max {self._iteration_max} iterations reached (score: {current_score}%) — stopping",
                    10)
                break

            # ── Review gate: wait 15s for user to click Finalize ─────────
            self._iteration_waiting = True
            self._iteration_review_event.clear()
            self._add_log("info",
                f"⏳ Waiting 15s for review — click 'Finalize' to accept, or auto-continues to iteration {iteration + 1}",
                10)
            self._db_persist_status(f"iteration_{iteration}_review")

            try:
                await asyncio.wait_for(self._iteration_review_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                # No user response → auto-continue
                self._add_log("info",
                    f"⏳ No response — auto-continuing to iteration {iteration + 1}",
                    10)

            self._iteration_waiting = False

            if self._iteration_finalized:
                self._add_log("success",
                    f"✓ User finalized at iteration {iteration} (score: {current_score}%)",
                    10)
                break

            if self._cancelled:
                break

        self._iteration_waiting = False
        self._db_persist_status("iteration_loop_done")

    def finalize_iteration(self):
        """Called when user clicks 'Finalize' during iteration review gate."""
        self._iteration_finalized = True
        self._iteration_review_event.set()  # unblock the wait

    # ── Pipeline control ────────────────────────────────────────────────────

    def resume(self, switch_to_auto: bool = False):
        """Resume a paused pipeline. Called from /continue endpoint."""
        if switch_to_auto:
            self._step_mode = "auto"
        self._pause_event.set()  # unblock the waiting step — run loop sets status to "running"

    def pause(self):
        """Switch a running auto-mode pipeline to step-by-step pause mode.
        The pipeline will pause after the currently running step completes."""
        self._step_mode = "pause"
        # Don't clear _pause_event here — let the current step finish,
        # the run() loop will pause after it because _step_mode == "pause"

    def cancel(self):
        """Cancel pipeline — remaining steps will be skipped."""
        self._cancelled = True
        self._pause_event.set()  # unblock if waiting

    def update_step_routing(self, step_num: int, first: str = None, second: str = None, third: str = None):
        """Change the AI routing for a specific step during execution."""
        _step_routing_key = {
            1: "research", 2: "structure", 3: "verify", 4: "links", 5: "references",
            6: "draft", 7: "review", 8: "issues", 9: "humanize",
            10: "score", 11: "quality_loop", 12: "redevelop",
        }
        key = _step_routing_key.get(step_num)
        if not key:
            return
        cfg = getattr(self.routing, key, None)
        if not cfg:
            return
        if first is not None:
            cfg.first = first
        if second is not None:
            cfg.second = second
        if third is not None:
            cfg.third = third
        # Clear health cooldown for explicitly selected providers so user's choice isn't bypassed
        for prov in [first, second, third]:
            if prov and prov not in ("skip", ""):
                _mark_provider_good(prov)
        self._add_log("info", f"Step {step_num} AI updated: {cfg.first} → {cfg.second} → {cfg.third}", step_num)
        # Immediately persist so the UI reflects the new routing choice
        self._db_persist_status(f"step_{step_num}_routing_updated")

    # ── DB helpers ───────────────────────────────────────────────────────────

    def _db_persist_status(self, status: str):
        if not self.db:
            return
        try:
            pipeline_json = json.dumps(self._pipeline_snapshot(), ensure_ascii=False)
            self.db.execute(
                "UPDATE content_articles SET schema_json=? WHERE article_id=?",
                (pipeline_json, self.article_id)
            )
            self.db.commit()
        except Exception:
            pass

    def _scan_for_fallback_phrases(self, html: str) -> list:
        """Scan content for sentinel placeholder phrases that indicate a
        last-resort fallback fired during generation. Returns the list of
        matched phrases (empty list if content is clean).
        """
        if not html:
            return []
        low = html.lower()
        return [p for p in _FALLBACK_MARKER_PHRASES if p in low]

    async def _multi_ai_review(self):
        """
        Multi-AI content review: Get feedback from Claude and GPT via OpenRouter.
        Logs review results for quality analysis and continuous improvement.
        
        Reviews content for:
        - Fake authority/testing claims
        - Templated filler phrases
        - Unsourced statistics
        - Mid-word text corruption
        - Link relevance
        - Overall content quality (1-10 score)
        """
        html = self.state.final_html or self.state.draft_html
        if not html or len(html) < 200:
            log.warning("Multi-AI review skipped: insufficient content")
            return
        
        # Strip HTML for text analysis
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text_preview = text[:2000]  # First 2000 chars for review
        
        review_prompt = f"""Review this SEO article for quality issues. Provide a structured assessment.

ARTICLE EXCERPT (first 2000 chars):
{text_preview}

KEYWORD: {self.keyword}
WORD COUNT: {len(text.split())}

REVIEW CRITERIA:
1. **Fake Authority** (score 1-10, 10=clean): Check for fabricated testing claims like "we tested", "in our testing", "our team evaluated", "hands-on review", "after putting to the test". Deduct points for each instance.

2. **Templated Fillers** (score 1-10, 10=none): Look for overused phrases like "this directly impacts", "what most people miss", "in practice", "experienced buyers check", "this is especially relevant". Deduct points for repetition.

3. **Unsourced Statistics** (score 1-10, 10=all sourced): Check if percentage claims have attribution (e.g., "According to FDA (2024), 30%..."). Deduct points for vague claims like "studies show" without naming the source.

4. **Text Corruption** (score 1-10, 10=clean): Look for mid-word capital injections ("hin That said"), broken word fragments, or garbled text that indicates AI generation artifacts.

5. **Link Relevance** (score 1-10, 10=highly relevant): Assess if included links (Wikipedia,external sources) are actually relevant to the keyword and content context.

6. **Overall Quality** (score 1-10): General assessment of content depth, clarity, and value to the reader.

OUTPUT FORMAT (JSON):
```json
{{
  "fake_authority_score": <1-10>,
  "fake_authority_examples": ["quote1", "quote2"],
  "filler_score": <1-10>,
  "filler_examples": ["phrase1", "phrase2"],
  "unsourced_stats_score": <1-10>,
  "unsourced_stats_examples": ["claim1", "claim2"],
  "corruption_score": <1-10>,
  "corruption_examples": ["artifact1", "artifact2"],
  "link_relevance_score": <1-10>,
  "overall_quality_score": <1-10>,
  "top_improvement": "<single most important fix>"
}}
```"""
        
        reviews = {}

        # Use quality_loop routing so the user controls which models are used here
        reviewer_1 = self.routing.quality_loop.first
        reviewer_2 = self.routing.quality_loop.second

        # Review 1: first model in quality_loop chain
        if reviewer_1 and reviewer_1 != "skip":
            try:
                log.info(f"Multi-AI Review: Requesting {reviewer_1} feedback for {self.article_id}")
                r1_response = await self._call_ai_raw(
                    reviewer_1,
                    review_prompt,
                    temperature=0.3,
                    max_tokens=800,
                    use_prompt_directly=True
                )
                reviews['reviewer_1'] = self._parse_review_json(r1_response)
                log.info(f"Review 1 ({reviewer_1}): Overall {reviews['reviewer_1'].get('overall_quality_score', 'N/A')}/10")
            except Exception as e:
                log.warning(f"Review 1 ({reviewer_1}) failed: {e}")
                reviews['reviewer_1'] = {"error": str(e)}

        # Review 2: second model in quality_loop chain
        if reviewer_2 and reviewer_2 != "skip":
            try:
                log.info(f"Multi-AI Review: Requesting {reviewer_2} feedback for {self.article_id}")
                r2_response = await self._call_ai_raw(
                    reviewer_2,
                    review_prompt,
                    temperature=0.3,
                    max_tokens=800,
                    use_prompt_directly=True
                )
                reviews['reviewer_2'] = self._parse_review_json(r2_response)
                log.info(f"Review 2 ({reviewer_2}): Overall {reviews['reviewer_2'].get('overall_quality_score', 'N/A')}/10")
            except Exception as e:
                log.warning(f"Review 2 ({reviewer_2}) failed: {e}")
                reviews['reviewer_2'] = {"error": str(e)}
        
        # Log consolidated review summary
        if reviews:
            self._log_review_summary(reviews)
        
        # Store reviews in state for later access
        if not hasattr(self.state, 'ai_reviews'):
            self.state.ai_reviews = {}
        self.state.ai_reviews = reviews
    
    def _parse_review_json(self, response: str) -> dict:
        """Extract JSON from review response."""
        import json
        import re
        
        # Try to extract JSON from code fence
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try raw JSON parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_response": response, "parse_error": True}
    
    def _log_review_summary(self, reviews: dict):
        """Log consolidated multi-AI review summary."""
        log.info("=" * 80)
        log.info(f"MULTI-AI REVIEW SUMMARY: {self.article_id}")
        log.info("=" * 80)
        
        for ai_name, review in reviews.items():
            if "error" in review:
                log.warning(f"{ai_name.upper()}: ERROR - {review['error']}")
                continue
            
            if review.get("parse_error"):
                log.warning(f"{ai_name.upper()}: Parse error - raw response logged")
                continue
            
            log.info(f"\n{ai_name.upper()} SCORES:")
            log.info(f"  Fake Authority: {review.get('fake_authority_score', 'N/A')}/10")
            log.info(f"  Filler Phrases: {review.get('filler_score', 'N/A')}/10")
            log.info(f"  Unsourced Stats: {review.get('unsourced_stats_score', 'N/A')}/10")
            log.info(f"  Text Corruption: {review.get('corruption_score', 'N/A')}/10")
            log.info(f"  Link Relevance: {review.get('link_relevance_score', 'N/A')}/10")
            log.info(f"  OVERALL QUALITY: {review.get('overall_quality_score', 'N/A')}/10")
            if review.get('top_improvement'):
                log.info(f"  Top Fix: {review['top_improvement']}")
        
        log.info("=" * 80)

    def _save_final_to_db(self):
        if not self.db:
            return
        try:
            body = self.state.final_html or self.state.draft_html

            # If no content was generated at all, mark as failed
            if not body or len(body.strip()) < 200:
                self.db.execute(
                    "UPDATE content_articles SET status='failed', updated_at=? WHERE article_id=?",
                    (datetime.now(timezone.utc).isoformat(), self.article_id),
                )
                self.db.commit()
                log.error(f"Article {self.article_id}: no content generated — marked failed")
                return

            # Generate meta_desc from body if not set
            if not self.state.meta_desc and self.state.final_html:
                plain = re.sub(r"<[^>]+>", " ", self.state.final_html)
                plain = " ".join(plain.split())
                self.state.meta_desc = plain[:158] + "…" if len(plain) > 158 else plain

            # Generate meta_title from title if not set
            if not self.state.meta_title and self.state.title:
                self.state.meta_title = self.state.title[:60]
            self._ensure_meta_title()
            self._ensure_meta_desc()

            # ── Pre-save fallback-phrase scan ───────────────────────────────
            # Detect placeholder text that leaked from last-resort fallbacks
            # (_minimal_draft_from_structure, _ollama_section_writer, etc.).
            # If found, mark article as needs_review so the user knows manual
            # editing is required before publishing.
            body_to_save = self.state.final_html or self.state.draft_html
            fallback_hits = self._scan_for_fallback_phrases(body_to_save)
            article_status = "draft"
            if fallback_hits:
                article_status = "needs_review"
                self._add_log(
                    "warn",
                    f"Fallback placeholder content detected ({len(fallback_hits)} phrase(s)): "
                    f"{', '.join(fallback_hits[:3])}{'…' if len(fallback_hits) > 3 else ''}. "
                    f"Article marked 'needs_review' — manual editing required before publish.",
                )
                log.warning(
                    f"Article {self.article_id}: fallback markers present {fallback_hits} -> needs_review"
                )

            steps_json = json.dumps(self._pipeline_snapshot(), ensure_ascii=False)
            self.db.execute(
                """UPDATE content_articles
                   SET title=?, body=?, meta_title=?, meta_desc=?,
                       seo_score=?, readability=?, word_count=?,
                       status=?, schema_json=?, updated_at=?
                   WHERE article_id=?""",
                (
                    self.state.title or self.keyword.title(),
                    self.state.final_html or self.state.draft_html,
                    self.state.meta_title or self.keyword[:60],
                    self.state.meta_desc or "",
                    self.state.seo_score,
                    self.state.readability,
                    self.state.word_count,
                    article_status,
                    steps_json,
                    datetime.now(timezone.utc).isoformat(),
                    self.article_id,
                )
            )
            self.db.commit()
        except Exception as e:
            log.error(f"Failed to save article to DB: {e}")

    def _pipeline_snapshot(self) -> Dict:
        _step_routing_key = {
            1: "research", 2: "structure", 3: "verify", 4: "links", 5: "references",
            6: "draft", 7: "review", 8: "issues", 9: "humanize",
            10: "score", 11: "quality_loop", 12: "redevelop",
        }
        def _ai_first(step_num: int) -> str:
            key = _step_routing_key.get(step_num)
            if not key:
                return ""
            cfg = getattr(self.routing, key, None)
            return cfg.first if cfg else ""

        def _ai_routing(step_num: int) -> Dict:
            key = _step_routing_key.get(step_num)
            if not key:
                return {"first": "", "second": "", "third": ""}
            cfg = getattr(self.routing, key, None)
            if not cfg:
                return {"first": "", "second": "", "third": ""}
            return {"first": cfg.first, "second": cfg.second, "third": cfg.third}

        snapshot = {
            "article_id": self.article_id,
            "keyword": self.keyword,
            "step_mode": getattr(self, '_step_mode', 'auto'),
            "is_paused": hasattr(self, '_pause_event') and not self._pause_event.is_set(),
            "ai_recovery_needed": getattr(self, '_ai_recovery_needed', False),
            "iteration": {
                "current": getattr(self, '_iteration_current', 0),
                "max": getattr(self, '_iteration_max', 3),
                "target_score": getattr(self, '_iteration_target_score', 80),
                "waiting_review": getattr(self, '_iteration_waiting', False),
                "finalized": getattr(self, '_iteration_finalized', False),
                "score": self.state.seo_score or 0,
            },
            "steps": [
                {
                    "step": s.step, "name": s.name, "status": s.status, "summary": s.summary,
                    "ai_first": _ai_first(s.step),
                    "ai_routing": _ai_routing(s.step),
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                }
                for s in self.state.steps
            ],
            "issues_found": self.state.issues_found,
        }
        # Include rule_results if available (set at Steps 8 and 10)
        if hasattr(self, '_rule_results') and self._rule_results:
            snapshot["rule_results"] = self._rule_results
        # Include pipeline logs for real-time console display
        if self._logs:
            snapshot["logs"] = self._logs[-200:]  # Last 200 entries
        return snapshot

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: TOPIC RESEARCH & CRAWL
    # ─────────────────────────────────────────────────────────────────────────

    async def _step1_research(self):
        """
        Crawl competitor websites via DuckDuckGo, then run AI research analysis.
        AI research is always performed — even if crawl fails — using the selected
        AI provider (Ollama → Groq → Gemini in auto mode).
        """
        _step_ctx_var.set({"step": 1, "step_name": "Research", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[0]

        # 1a. Find URLs via DuckDuckGo HTML search (no API key needed)
        urls = await self._ddg_search(self.keyword, n=5)
        step.details["search_urls"] = urls

        # 1b. Crawl each URL
        crawled = []
        for url in urls:
            page = await self._crawl_page(url)
            if page:
                crawled.append(page)
                await asyncio.sleep(0.5)  # polite crawl

        self._crawled_pages = crawled

        # 1c. Build research brief from crawled content
        crawl_context = "\n\n".join([
            f"SOURCE: {p.url}\nTITLE: {p.title}\nHEADINGS:\n" +
            "\n".join(p.headings[:10]) +
            "\nKEY CONTENT:\n" + " ".join(p.paragraphs[:5])[:800]
            for p in crawled
        ]) if crawled else ""

        # 1d. AI research analysis — runs regardless of crawl success
        analysis = await self._ai_research_analysis(crawl_context)
        step.details["analysis"] = analysis

        themes_n = len(analysis.get("themes", []))
        gaps_n   = len(analysis.get("gaps", []))
        ai_label = self.research_ai.upper() if self.research_ai != "auto" else "AI"

        # ── Intent classification (feeds into Step 2 structure) ──
        try:
            from services.seo_brief_generator import classify_intent
            primary_intent = classify_intent(self.keyword)
            self._intent_data = {"primary_intent": primary_intent}
            log.info(f"Intent classified: {primary_intent}")
        except Exception as e:
            log.warning(f"Intent classification failed: {e}")
            self._intent_data = {"primary_intent": self.intent or "informational"}

        # ── Phase D: structured intent plan (angle + must-include + avoid) ──
        try:
            from engines.intent_planner import build_intent_plan
            plan = build_intent_plan(
                keyword=self.keyword,
                primary_intent=self._intent_data.get("primary_intent", ""),
                research_themes=analysis.get("themes", []) if isinstance(analysis, dict) else [],
            )
            self._intent_data["plan"] = plan
            log.info(f"Intent plan built: type={plan.get('article_type')} angle_len={len(plan.get('angle',''))}")
        except Exception as e:
            log.warning(f"Intent plan build failed: {e}")

        # ── Entity extraction from crawled competitor pages ──
        try:
            entities = set()
            for page in crawled:
                page_text = " ".join(page.paragraphs[:10])
                # Extract multi-word Title Case proper nouns
                for m in re.finditer(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", page_text):
                    ent = m.group().strip()
                    if len(ent.split()) >= 2 and len(ent) > 5:
                        entities.add(ent)
            self._target_entities = list(entities)[:20]
            if self._target_entities:
                log.info(f"Extracted {len(self._target_entities)} entities from competitors")
        except Exception as e:
            log.warning(f"Entity extraction failed: {e}")

        # ── Generate semantic keyword variations (for R34 density control) ──
        kw_words = self.keyword.lower().split()
        if len(kw_words) >= 2:
            self._semantic_variations = [
                " ".join(reversed(kw_words)),
                f"premium {' '.join(kw_words[-2:])}",
                f"quality {' '.join(kw_words[-2:])}",
                f"authentic {' '.join(kw_words[-2:])}",
                f"best {' '.join(kw_words[-2:])}",
                f"top {kw_words[-1]} options",
            ]
        elif kw_words:
            self._semantic_variations = [
                f"premium {kw_words[0]}",
                f"quality {kw_words[0]}",
                f"authentic {kw_words[0]}",
            ]

        # ── Post-research quality gate ──
        facts_n = len(analysis.get("key_facts", []))
        if themes_n < 3 or facts_n < 3:
            log.warning(f"Research thin: {themes_n} themes, {facts_n} facts — padding with fallback")
            fb = {
                "themes": [f"Overview of {self.keyword}", f"Benefits of {self.keyword}", f"How to use {self.keyword}", f"Buying guide for {self.keyword}", f"Expert tips for {self.keyword}"],
                "gaps": ["Lacks specific data", "Missing step-by-step guidance", "No comparison"],
                "angles": ["Expert-backed guide", "Data-driven with numbers", "Practical advice"],
                "key_facts": [f"{self.keyword} is a highly searched topic", "Quality and sourcing are key factors", "Expert guidance is valued", "Optimal selection criteria matter", "Proper usage maximises results"],
            }
            for field in ("themes", "gaps", "angles", "key_facts"):
                existing = analysis.get(field, [])
                needed = 5 - len(existing) if field in ("themes", "key_facts") else 3 - len(existing)
                if needed > 0:
                    analysis[field] = existing + fb[field][:needed]
            self._add_log("warn", f"Research padded: {themes_n}→{len(analysis['themes'])} themes, {facts_n}→{len(analysis['key_facts'])} facts", 1)

        if crawled:
            step.summary = f"Crawled {len(crawled)} pages + {ai_label} research: {len(analysis.get('themes',[]))} themes · {gaps_n} gaps"
        else:
            step.summary = f"DDG unavailable — {ai_label} knowledge research: {len(analysis.get('themes',[]))} themes · {gaps_n} gaps"

    async def _ai_research_analysis(self, crawl_context: str = "") -> Dict:
        """
        Run AI-powered SEO research. Uses crawl_context when available;
        otherwise generates research purely from AI knowledge.
        Routes through the provider selected by self.research_ai:
          auto   → tries Ollama, then Groq, then Gemini
          ollama → Ollama only (falls back to Groq internally via _ollama)
          groq   → Groq only
          gemini → Gemini only
        """
        kw         = self.keyword
        supporting = f" (supporting keywords: {', '.join(self.supporting_keywords)})" if self.supporting_keywords else ""
        audience   = f" Target audience: {self.target_audience}." if self.target_audience else ""
        ctype      = f" Content type: {self.content_type}." if self.content_type else ""
        pt_ctx     = self._page_type_context()
        pt_label   = self._page_type_label()

        if crawl_context:
            user_prompt = f"""Analyse these competitor pages about "{kw}":{supporting}{audience}
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
{crawl_context[:4000]}

Identify:
1. TOP 5 themes every competitor covers
2. TOP 3 content gaps (angles missing or underdeveloped)
3. TOP 3 unique differentiated angles we can take
4. Key facts/statistics competitors mention (include numbers where possible)

{"Focus the analysis on what makes an excellent " + pt_label + "." if pt_ctx else ""}

Return JSON: {{"themes": [...], "gaps": [...], "angles": [...], "key_facts": [...]}}

{self._pm_block("step1_research_instructions")}"""  
        else:
            user_prompt = f"""You are an expert SEO researcher with deep knowledge of digital marketing and content strategy.

Perform deep research on the topic: "{kw}"{supporting}{audience}{ctype}
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
Based on your expert knowledge, identify:
1. TOP 5 themes and subtopics that high-ranking {pt_label}s about "{kw}" typically cover
2. TOP 3 content gaps — angles often missing or underdeveloped in most {pt_label}s on this topic
3. TOP 3 unique differentiated angles to stand out from competitors
4. 5+ key facts, statistics, or data points about "{kw}" that make {pt_label}s authoritative

Return JSON: {{"themes": [...], "gaps": [...], "angles": [...], "key_facts": [...]}}

{self._pm_block("step1_research_instructions")}"""

        system = "You are an expert SEO researcher. Be specific and data-driven. Return only valid JSON."
        log.info(f"Research step: routing chain = {self.routing.research.first} → {self.routing.research.second} → {self.routing.research.third}")
        result = await self._call_ai_with_chain(
            self.routing.research, user_prompt,
            system=system, temperature=0.3, max_tokens=1500,
        )

        if not result.get("themes"):
            log.warning("All AI research providers returned empty — using fallback research")
            result = {
                "themes": [f"Overview of {kw}", f"Benefits of {kw}", f"How to use {kw}", f"Buying guide for {kw}", f"Expert tips for {kw}"],
                "gaps": ["Lack of specific data and statistics", "Missing practical step-by-step guidance", "No comparison with alternatives"],
                "angles": ["Expert-backed authoritative guide", "Data-driven with specific numbers", "Practical actionable advice"],
                "key_facts": [f"{kw} is a highly searched topic with growing interest", "Quality and sourcing are key purchase factors", "Expert guidance is valued by readers"],
            }

        # Normalize: AI sometimes returns lists of objects instead of strings.
        # Coerce every list field to a flat list of strings.
        def _to_str_list(val) -> List[str]:
            if not isinstance(val, list):
                return []
            out = []
            for item in val:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    # Try common text keys, fallback to first string value
                    for k in ("title", "theme", "gap", "angle", "fact", "text", "description"):
                        if isinstance(item.get(k), str):
                            out.append(item[k])
                            break
                    else:
                        sv = next((v for v in item.values() if isinstance(v, str)), None)
                        if sv:
                            out.append(sv)
            return out

        for field in ("themes", "gaps", "angles", "key_facts"):
            result[field] = _to_str_list(result.get(field, []))

        return result

    async def _ddg_search(self, query: str, n: int = 5) -> List[str]:
        """Get top N URLs for query using DuckDuckGo HTML results (non-blocking)."""
        def _sync_ddg():
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            resp = requests.get(url, headers=CRAWL_HEADERS, timeout=CRAWL_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a in soup.select(".result__a")[:n]:
                href = a.get("href", "")
                if href.startswith("http") and "duckduckgo.com" not in href:
                    links.append(href)
            return links[:n]

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_ddg)
        except Exception as e:
            log.warning(f"DDG search failed: {e}")
            return []

    async def _crawl_page(self, url: str) -> Optional[CrawledPage]:
        """Crawl a single URL and extract structured data (non-blocking)."""
        def _sync_crawl():
            resp = requests.get(url, headers=CRAWL_HEADERS, timeout=CRAWL_TIMEOUT,
                                allow_redirects=True)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header",
                             "aside", "form", "button", "iframe"]):
                tag.decompose()

            title = soup.title.get_text(strip=True) if soup.title else ""
            meta_desc = ""
            meta = soup.find("meta", attrs={"name": "description"})
            if meta:
                meta_desc = meta.get("content", "")[:200]

            headings = [h.get_text(strip=True) for h in soup.find_all(["h1","h2","h3"])[:15]]
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 60][:10]
            body_text = soup.get_text(" ", strip=True)
            word_count = len(body_text.split())

            return CrawledPage(url=url, title=title, headings=headings,
                               paragraphs=paragraphs, word_count=word_count, meta_desc=meta_desc)

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_crawl)
        except Exception as e:
            log.debug(f"Failed crawl {url}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: STRUCTURE GENERATION (Ollama)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step2_structure(self):
        """
        Use Ollama (local, free) to generate a comprehensive article outline:
        H1, H2s, H3s, FAQ, introduction plan, conclusion plan.
        """
        _step_ctx_var.set({"step": 2, "step_name": "Structure", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[1]
        research = self.state.steps[0].details.get("analysis", {})
        themes = research.get("themes", [])
        gaps   = research.get("gaps", [])
        angles = research.get("angles", [])
        facts  = research.get("key_facts", [])

        pt_ctx = self._page_type_context()
        pt_label = self._page_type_label()

        # Page-type-specific structure requirements
        if self.page_type == "homepage":
            struct_reqs = """Requirements:
- 1 clear H1 headline (keyword included, compelling, <65 chars)
- 4-6 H2 sections: Hero/Headline, Services Overview, Why Choose Us, Testimonials/Trust, How It Works, Contact/CTA
- 1-2 H3s under each H2
- No long introduction — go straight to value proposition
- FAQ section with 4-5 questions potential customers ask
- Strong CTA at the end"""
        elif self.page_type == "product":
            struct_reqs = """Requirements:
- 1 clear H1 product title (keyword + product name, <65 chars)
- 5-7 H2 sections: Product Overview, Key Features, Specifications, Benefits, How to Use, FAQ, Buy Now
- Include a specifications table plan
- 2-3 H3s under each H2
- FAQ section with 5-6 product-specific questions
- Purchase CTA at the end"""
        elif self.page_type == "about":
            struct_reqs = """Requirements:
- 1 clear H1 (e.g. "About [Company] — Our Story")
- 4-6 H2 sections: Our Story, Mission & Vision, Our Team, Milestones, Values, Connect With Us
- 1-2 H3s under each H2
- No FAQ required (optional)
- CTA to contact or learn more"""
        elif self.page_type == "landing":
            struct_reqs = """Requirements:
- 1 clear H1 headline (benefit-driven, keyword included, <65 chars)
- 4-6 H2 sections: Hero + CTA, Problem/Pain Points, Solution/Benefits, Social Proof, How It Works, Final CTA
- 1-2 H3s under each H2
- FAQ section with 4 objection-handling questions
- Multiple CTA placements planned"""
        elif self.page_type == "service":
            struct_reqs = """Requirements:
- 1 clear H1 service title (keyword included, <65 chars)
- 5-7 H2 sections: Service Overview, How It Works, What's Included, Pricing, Benefits, FAQ, Get Started
- 2-3 H3s under each H2
- FAQ section with 5-6 service-specific questions
- Contact/booking CTA at the end"""
        else:
            struct_reqs = """Requirements:
- 1 clear H1 title (keyword included, compelling, <65 chars)
- 6-8 H2 sections (keyword variations where natural)
- 2-3 H3 sub-sections under each H2
- Introduction plan (hook + what reader learns)
- MUST include one H2 covering "How to Choose" or buyer guidance (decision factors, what to look for, best for)
- MUST include one H2 with "Pros and Cons" or "Advantages and Disadvantages"
- FAQ section with 6 specific questions users actually ask
- Conclusion plan (summary + CTA)"""

        prompt = f"""Create a comprehensive SEO {pt_label} structure for the keyword: "{self.keyword}"
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
Intent: {self.intent}
Key themes to cover: {', '.join(themes[:5]) if themes else 'General topic coverage'}
Content gaps to fill: {', '.join(gaps[:3]) if gaps else 'In-depth analysis'}
Unique angles: {', '.join(angles[:2]) if angles else 'Expert insights'}
Key facts available: {', '.join(facts[:3]) if facts else 'Research-based'}
{"Supporting keywords to weave in: " + ', '.join(self.supporting_keywords) if self.supporting_keywords else ""}
{"Target audience: " + self.target_audience if self.target_audience else ""}
Content type: {self.content_type}

{struct_reqs}
- Estimated word count per section

{self._pm_block("step2_structure_rules")}

Return ONLY valid JSON:
{{
  "h1": "Article title here",
  "meta_title": "60-char meta title",
  "meta_description": "150-160 char compelling meta description with keyword",
  "intro_plan": "Brief description of introduction hook and structure",
  "h2_sections": [
    {{
      "h2": "Main section heading",
      "type": "definition|benefits|how_to|comparison|buyers_guide|pros_cons|use_cases|trust|expert_tips|faq",
      "h3s": ["Sub-section 1", "Sub-section 2", "Sub-section 3"],
      "word_target": 350,
      "content_angle": "What this section should uniquely cover",
      "authority_note": "What authority signal, study, or data point to include here",
      "link_slot": "internal|external|wikipedia|none"
    }}
  ],
  "toc_anchors": [
    {{"id": "url-safe-anchor", "heading": "H2 text"}}
  ],
  "faqs": [
    {{"q": "Question?", "a_plan": "Brief answer plan"}}
  ],
  "conclusion_plan": "Brief description of conclusion and CTA"
}}"""

        log.info(f"Structure step: routing chain = {self.routing.structure.first} → {self.routing.structure.second} → {self.routing.structure.third}")
        structure = await self._call_ai_with_chain(
            self.routing.structure, prompt,
            system="You are a precise SEO content strategist. Return ONLY valid JSON.",
            temperature=0.4, max_tokens=1200,
        )

        if not structure.get("h2_sections"):
            log.warning("Structure: all configured AI providers failed — using default structure")
            structure = self._default_structure()

        self._structure = structure

        h2_count = len(structure.get("h2_sections", []))
        faq_count = len(structure.get("faqs", []))
        step.summary = f"H1 + {h2_count} sections + {faq_count} FAQs planned"
        step.details["structure"] = structure

    def _default_structure(self) -> Dict:
        """Generate a sensible default structure when AI fails."""
        kw = self.keyword.title()
        kw_lower = self.keyword.lower()
        pi = self.page_inputs

        # ── Page-type-specific default structures ────────────────────────────
        if self.page_type == "homepage":
            biz = pi.get("business_name", kw)
            h2s = [
                {"h2": f"Welcome to {biz} — {kw}", "h3s": ["What We Do", "Why Choose Us"], "word_target": 200, "content_angle": "Hero section"},
                {"h2": f"Our Services for {kw}", "h3s": ["Service 1", "Service 2", "Service 3"], "word_target": 250, "content_angle": "Services overview"},
                {"h2": f"Why Thousands Trust {biz}", "h3s": ["Quality Guarantee", "Customer Results"], "word_target": 200, "content_angle": "Trust signals"},
                {"h2": f"How {biz} Works", "h3s": ["Step 1", "Step 2", "Step 3"], "word_target": 200, "content_angle": "Process overview"},
                {"h2": f"Get Started with {kw} Today", "h3s": ["Contact Us", "Free Consultation"], "word_target": 150, "content_angle": "CTA section"},
            ]
            return {
                "h1": f"{biz} — {kw}",
                "meta_title": f"{biz} — {kw_lower[:45]}",
                "meta_description": f"{biz}: your trusted source for {kw_lower}. Explore our services, see why customers choose us, and get started today.",
                "intro_plan": f"Hero headline about {kw_lower} and {biz}.",
                "h2_sections": h2s,
                "toc_anchors": [{"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]} for s in h2s],
                "faqs": [
                    {"q": f"What does {biz} offer?", "a_plan": "Overview of services"},
                    {"q": f"Why choose {biz} for {kw_lower}?", "a_plan": "Key differentiators"},
                    {"q": f"How do I get started?", "a_plan": "Steps to begin"},
                    {"q": f"Where is {biz} located?", "a_plan": "Location info"},
                ],
                "conclusion_plan": f"CTA to contact {biz} for {kw_lower}.",
            }

        if self.page_type == "product":
            prod = pi.get("product_name", kw)
            h2s = [
                {"h2": f"{prod} Overview", "h3s": ["What It Is", "Who It's For"], "word_target": 250, "content_angle": "Product intro"},
                {"h2": f"Key Features of {prod}", "h3s": ["Feature 1", "Feature 2", "Feature 3"], "word_target": 300, "content_angle": "Feature details"},
                {"h2": f"{prod} Specifications", "h3s": ["Technical Details", "Dimensions & Weight"], "word_target": 200, "content_angle": "Specs table"},
                {"h2": f"Benefits of Choosing {prod}", "h3s": ["Primary Benefits", "Compared to Alternatives"], "word_target": 250, "content_angle": "Benefits"},
                {"h2": f"How to Use {prod}", "h3s": ["Getting Started", "Tips for Best Results"], "word_target": 200, "content_angle": "Usage guide"},
                {"h2": f"Buy {prod} — Pricing & Availability", "h3s": ["Pricing Options", "Where to Buy"], "word_target": 200, "content_angle": "Purchase CTA"},
            ]
            return {
                "h1": f"{prod} — {kw}",
                "meta_title": f"{prod} — Buy {kw_lower[:40]}",
                "meta_description": f"Discover {prod}: features, specifications, benefits, and pricing. The best {kw_lower} for your needs.",
                "intro_plan": f"Brief product hook about {prod}.",
                "h2_sections": h2s,
                "toc_anchors": [{"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]} for s in h2s],
                "faqs": [
                    {"q": f"What is {prod}?", "a_plan": "Product definition"},
                    {"q": f"How much does {prod} cost?", "a_plan": "Pricing info"},
                    {"q": f"What are the specs of {prod}?", "a_plan": "Key specifications"},
                    {"q": f"How do I use {prod}?", "a_plan": "Usage steps"},
                    {"q": f"Is {prod} worth it?", "a_plan": "Value assessment"},
                ],
                "conclusion_plan": f"CTA to buy {prod}.",
            }

        if self.page_type == "about":
            biz = pi.get("company_story", kw) if pi.get("company_story") else kw
            h2s = [
                {"h2": f"Our Story", "h3s": ["How We Started", "Our Journey"], "word_target": 250, "content_angle": "Company history"},
                {"h2": f"Our Mission & Vision", "h3s": ["What We Believe", "Where We're Headed"], "word_target": 200, "content_angle": "Mission statement"},
                {"h2": f"Meet Our Team", "h3s": ["Leadership", "Our Experts"], "word_target": 200, "content_angle": "Team intro"},
                {"h2": f"Our Values", "h3s": ["Quality", "Integrity", "Innovation"], "word_target": 200, "content_angle": "Core values"},
                {"h2": f"Milestones & Achievements", "h3s": ["Key Milestones", "Awards & Recognition"], "word_target": 200, "content_angle": "Achievements"},
            ]
            return {
                "h1": f"About Us — {kw}",
                "meta_title": f"About Us — {kw_lower[:50]}",
                "meta_description": f"Learn about {kw_lower}: our story, mission, team, and values. Discover what makes us different.",
                "intro_plan": f"Brief compelling intro about the company and {kw_lower}.",
                "h2_sections": h2s,
                "toc_anchors": [{"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]} for s in h2s],
                "faqs": [],
                "conclusion_plan": f"CTA to connect or learn more about {kw_lower}.",
            }

        if self.page_type == "landing":
            offer = pi.get("offer_headline", kw)
            h2s = [
                {"h2": f"{offer}", "h3s": ["The Problem", "Our Solution"], "word_target": 200, "content_angle": "Hero + value proposition"},
                {"h2": f"Why You Need {kw}", "h3s": ["Pain Point 1", "Pain Point 2"], "word_target": 200, "content_angle": "Pain points"},
                {"h2": f"How {kw} Transforms Your Results", "h3s": ["Benefit 1", "Benefit 2", "Benefit 3"], "word_target": 250, "content_angle": "Benefits"},
                {"h2": f"What Our Customers Say", "h3s": ["Testimonial 1", "Testimonial 2"], "word_target": 200, "content_angle": "Social proof"},
                {"h2": f"Get {kw} Now", "h3s": ["How to Start", "What's Included"], "word_target": 150, "content_angle": "Final CTA"},
            ]
            return {
                "h1": offer,
                "meta_title": f"{offer[:55]}",
                "meta_description": f"{offer}: solve your problems with {kw_lower}. See benefits, customer results, and get started today.",
                "intro_plan": f"Attention-grabbing hook about {kw_lower}.",
                "h2_sections": h2s,
                "toc_anchors": [{"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]} for s in h2s],
                "faqs": [
                    {"q": f"Is {kw_lower} right for me?", "a_plan": "Qualifying question"},
                    {"q": f"How quickly will I see results?", "a_plan": "Timeline expectations"},
                    {"q": f"What if it doesn't work?", "a_plan": "Risk reversal / guarantee"},
                    {"q": f"How do I get started?", "a_plan": "Next steps"},
                ],
                "conclusion_plan": f"Strong CTA with urgency for {kw_lower}.",
            }

        if self.page_type == "service":
            svc = pi.get("service_name", kw)
            h2s = [
                {"h2": f"{svc} Overview", "h3s": ["What We Offer", "Who It's For"], "word_target": 250, "content_angle": "Service intro"},
                {"h2": f"How {svc} Works", "h3s": ["Step 1: Consultation", "Step 2: Delivery", "Step 3: Follow-Up"], "word_target": 250, "content_angle": "Process"},
                {"h2": f"What's Included in {svc}", "h3s": ["Core Features", "Add-On Options"], "word_target": 200, "content_angle": "Inclusions"},
                {"h2": f"{svc} Pricing", "h3s": ["Plans & Packages", "Custom Quotes"], "word_target": 200, "content_angle": "Pricing"},
                {"h2": f"Why Choose Our {svc}", "h3s": ["Our Expertise", "Client Results"], "word_target": 200, "content_angle": "Differentiators"},
                {"h2": f"Get Started with {svc}", "h3s": ["Book a Call", "Request a Quote"], "word_target": 150, "content_angle": "CTA section"},
            ]
            return {
                "h1": f"{svc} — Professional {kw}",
                "meta_title": f"{svc} — {kw_lower[:45]}",
                "meta_description": f"{svc}: learn how it works, what's included, pricing, and how to get started. Professional {kw_lower} services.",
                "intro_plan": f"Brief intro about {svc} and why it matters for {kw_lower}.",
                "h2_sections": h2s,
                "toc_anchors": [{"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]} for s in h2s],
                "faqs": [
                    {"q": f"What is {svc}?", "a_plan": "Service definition"},
                    {"q": f"How much does {svc} cost?", "a_plan": "Pricing overview"},
                    {"q": f"How long does {svc} take?", "a_plan": "Timeline"},
                    {"q": f"Do you offer custom {kw_lower}?", "a_plan": "Customization options"},
                    {"q": f"How do I book {svc}?", "a_plan": "Booking process"},
                ],
                "conclusion_plan": f"CTA to book or inquire about {svc}.",
            }

        # ── Default: article type ────────────────────────────────────────────
        is_info = self.intent in ("informational", "navigational")

        h2s = {
            "informational": [
                {"h2": f"What Is {kw}? A Complete Overview", "h3s": ["Definition and Background", "Why It Matters", "Key Characteristics"], "word_target": 350, "content_angle": "Comprehensive introduction"},
                {"h2": f"5 Proven Benefits of {kw} (Backed by Research)", "h3s": ["Primary Advantages", "Scientific Evidence", "Real-World Applications"], "word_target": 400, "content_angle": "Evidence-based benefits"},
                {"h2": f"How to Use {kw} Effectively", "h3s": ["Step-by-Step Guide", "Best Practices", "Common Mistakes to Avoid"], "word_target": 400, "content_angle": "Practical usage guide"},
                {"h2": f"Which {kw} Type Is Right for You?", "h3s": ["Main Categories", "Quality Grades", "How to Choose"], "word_target": 300, "content_angle": "Buyer's guide"},
                {"h2": f"{kw} vs Alternatives: Comparison", "h3s": ["Head-to-Head Comparison", "When to Use Each", "Expert Recommendation"], "word_target": 300, "content_angle": "Comparative analysis"},
                {"h2": f"Buying Guide: How to Source Quality {kw}", "h3s": ["What to Look For", "Where to Buy", "Red Flags to Avoid"], "word_target": 350, "content_angle": "Purchase guide"},
                {"h2": f"Expert Tips for Getting the Most from {kw}", "h3s": ["Pro Tips", "Common Questions Answered", "Advanced Techniques"], "word_target": 300, "content_angle": "Expert insights"},
            ],
            "commercial": [
                {"h2": f"Why {kw} Matters for Your Business", "h3s": ["Business Benefits", "ROI Potential", "Competitive Advantage"], "word_target": 350, "content_angle": "Business case"},
                {"h2": f"How to Choose the Best {kw}", "h3s": ["Key Selection Criteria", "Quality Indicators", "Price vs Value"], "word_target": 400, "content_angle": "Buyer's guide"},
                {"h2": f"Top Features to Look for in {kw}", "h3s": ["Must-Have Features", "Nice-to-Have Features", "Quality Certifications"], "word_target": 350, "content_angle": "Feature analysis"},
                {"h2": f"Where to Buy {kw}: Trusted Sources", "h3s": ["Online Options", "Things to Ask Suppliers", "Bulk Buying Benefits"], "word_target": 300, "content_angle": "Sourcing guide"},
                {"h2": f"Pricing Guide for {kw}", "h3s": ["Average Price Ranges", "What Affects Pricing", "Getting the Best Deal"], "word_target": 250, "content_angle": "Cost analysis"},
                {"h2": f"Customer Reviews: What Buyers Say About {kw}", "h3s": ["Common Praise", "Typical Concerns", "Expert Ratings"], "word_target": 300, "content_angle": "Social proof"},
                {"h2": f"Getting Started with {kw}: Next Steps", "h3s": ["Quick Start Guide", "First Order Tips", "Support and Guarantees"], "word_target": 250, "content_angle": "Conversion"},
            ],
        }.get(self.intent, [])

        if not h2s:
            h2s = [
                {"h2": f"What You Need to Know About {kw}: Key Facts", "h3s": ["Overview", "Key Points", "Why It Matters"], "word_target": 350, "content_angle": "Introduction"},
                {"h2": f"How {kw} Works: Applications and Real Uses", "h3s": ["Main Benefits", "Practical Applications", "Use Cases"], "word_target": 350, "content_angle": "Benefits"},
                {"h2": f"How to Get Started with {kw}", "h3s": ["Step 1: Research", "Step 2: Implementation", "Step 3: Optimization"], "word_target": 350, "content_angle": "Getting started"},
                {"h2": "Expert Tips and Best Practices", "h3s": ["Top Tips", "Common Mistakes", "Pro Advice"], "word_target": 300, "content_angle": "Expert insights"},
                {"h2": "Frequently Asked Questions", "h3s": [], "word_target": 300, "content_angle": "FAQ"},
            ]

        return {
            "h1": f"{kw}: The Complete Guide",
            "meta_title": f"{kw[:55]} — Complete Guide",
            "meta_description": f"Discover everything about {kw_lower}. Expert tips, benefits, buying guide, and more. Your complete resource for {kw_lower}.",
            "intro_plan": f"Hook about {kw_lower}, overview of what the reader will learn, why this topic matters.",
            "h2_sections": h2s,
            "toc_anchors": [
                {"id": re.sub(r'[^a-z0-9]+', '-', s["h2"].lower())[:40], "heading": s["h2"]}
                for s in h2s
            ],
            "faqs": [
                {"q": f"What is {kw_lower}?", "a_plan": "Define and explain the topic"},
                {"q": f"How is {kw_lower} used?", "a_plan": "Explain common uses and applications"},
                {"q": f"What are the benefits of {kw_lower}?", "a_plan": "List key benefits with examples"},
                {"q": f"Where can I buy {kw_lower}?", "a_plan": "Explain purchase options"},
                {"q": f"How do I choose the best {kw_lower}?", "a_plan": "Key selection criteria"},
                {"q": f"Is {kw_lower} worth it?", "a_plan": "Value assessment"},
            ],
            "conclusion_plan": f"Summarise key points about {kw_lower}, include CTA to shop/learn more.",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3: STRUCTURE VERIFICATION (Gemini)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step3_verify_structure(self):
        """
        Use Gemini to verify the structure is relevant, complete, and properly covers
        search intent. Gemini suggests improvements if needed.
        """
        _step_ctx_var.set({"step": 3, "step_name": "VerifyStructure", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[2]
        structure_str = json.dumps(self._structure, indent=2, ensure_ascii=False)

        verify_prompt = f"""Verify this article structure for keyword "{self.keyword}" (intent: {self.intent}).

Structure:
{structure_str[:3000]}

Check:
1. Does H1 include keyword naturally AND contain a power word (best/proven/ultimate/complete/guide)?
2. Do sections cover the topic comprehensively (6+ H2s)?
3. Is search intent ({self.intent}) satisfied?
4. Are at least 3 H2s question-format headings (What/How/Why/Which)?
5. Are there any FORBIDDEN heading patterns: "Understanding X", "Benefits of X", "Overview of X", "Introduction to X"?
6. Are FAQs questions users actually search for?
7. Is there logical flow between sections?

Return JSON:
{{
  "score": 0-100,
  "intent_match": true/false,
  "issues": ["list of structural issues"],
  "improvements": ["specific improvements"],
  "approved": true/false
}}

{self._pm_block("step3_verify_instructions")}"""

        log.info(f"Verify step: routing chain = {self.routing.verify.first} → {self.routing.verify.second} → {self.routing.verify.third}")
        verification = await self._call_ai_with_chain(
            self.routing.verify, verify_prompt,
            system="You are an expert SEO content strategist. Return only valid JSON.",
            temperature=0.2,
        )

        score = verification.get("score", 70)
        approved = verification.get("approved", True)
        issues = verification.get("issues", [])
        improvements = verification.get("improvements", [])

        # Refine structure if AI flagged issues OR returned actionable improvements,
        # even when `approved=true`. Previously this branch was gated on
        # `not approved AND improvements`, which discarded improvements whenever
        # the reviewer rubber-stamped the structure -> no iterative refinement.
        if improvements and (not approved or len(improvements) >= 2):
            improvements_text = "\n".join(f"- {imp}" for imp in improvements)
            refine_prompt = f"""Improve this article structure for keyword "{self.keyword}" based on these required improvements:

{improvements_text}

Current structure:
{json.dumps(self._structure, indent=2, ensure_ascii=False)[:2000]}

Return the COMPLETE improved structure as valid JSON with the same schema (h1, meta_title, meta_description, intro_plan, h2_sections, faqs, conclusion_plan, toc_anchors). Fix every issue listed above."""

            refined = await self._call_ai_with_chain(
                self.routing.structure, refine_prompt,
                system="You are a precise SEO content strategist. Return ONLY valid JSON.",
                temperature=0.3, max_tokens=2000,
            )
            if refined.get("h2_sections"):
                self._structure = refined
                step.summary = f"Structure refined: {score}/100 → {len(improvements)} improvements applied"
            else:
                step.summary = f"Structure score: {score}/100 — refinement failed, keeping original"
        else:
            step.summary = f"Structure approved: {score}/100"

        # Always preserve improvements for downstream draft + redevelop steps,
        # even when refinement succeeded (the refined structure may not have
        # captured every nuance from the reviewer's feedback).
        if improvements:
            self._structure_improvements = improvements

        step.details["verification"] = verification

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4: UNIFIED LINK PLANNING (Internal + External + Wikipedia)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step4_internal_links(self):
        """
        Plan ALL link types for the article in one pass:
          - 4+ internal links (href="/...")
          - 3+ external authority links (href="http..." to .gov, .edu, PubMed, etc.)
          - 1+ Wikipedia link placement
        Validates minimums and generates fallbacks if AI under-delivers.
        """
        _step_ctx_var.set({"step": 4, "step_name": "InternalLinks", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[3]
        sections = [s.get("h2", "") for s in self._structure.get("h2_sections", [])]

        links_prompt = f"""Plan ALL links for an article about "{self.keyword}" for {self.project_name or 'the business'}.

Article sections: {', '.join(sections)}
{"Known product/page links to use:\\n" + chr(10).join(f'- {p.get("name","Page")} → {p.get("url","")}' for p in self.product_links) if self.product_links else ""}

━━━ INTERNAL LINKS (minimum 4 required — scored as R24) ━━━
{"- Prefer the provided product/page links above as primary targets" if self.product_links else "- Link to the main product/category page"}
- Link to related product pages, category pages, guide/blog posts
- Link to contact/order page if appropriate
{f'- ALL internal hrefs MUST use the full domain: {self._customer_ctx.get("customer_url","").rstrip("/")} (e.g., "{self._customer_ctx.get("customer_url","").rstrip("/")}/products/black-pepper", "{self._customer_ctx.get("customer_url","").rstrip("/")}/contact")' if self._customer_ctx.get("customer_url") else '- ALL hrefs must start with "/" (e.g., "/products/black-pepper", "/guides/spice-storage", "/contact")'}

━━━ EXTERNAL AUTHORITY LINKS (minimum 3 required — scored as R22/R25) ━━━
- Link to authoritative sources: PubMed, WHO, FDA, USDA, .gov, .edu, industry associations
- Each must be a real, plausible authority URL for the topic "{self.keyword}"
- Use descriptive anchor text referencing the source name (e.g., "USDA nutritional data", "WHO dietary guidelines")

━━━ WIKIPEDIA LINK (minimum 1 required — scored as R26) ━━━
- Plan 1 Wikipedia link to the most relevant Wikipedia article for "{self.keyword}"
- Use Wikipedia URL format: https://en.wikipedia.org/wiki/Topic_Name

Each link MUST:
- Use descriptive, keyword-rich anchor text (NEVER "click here" or "read more")
- Fit naturally in the article flow
- Reference a specific section where it goes

Return JSON:
{{
  "internal_links": [
    {{
      "anchor_text": "buy authentic black pepper online",
      "href": "/products/black-pepper",
      "section_h2": "Section heading where this link fits",
      "context": "Short sentence showing how the link is embedded"
    }}
  ],
  "external_links": [
    {{
      "anchor_text": "USDA nutritional profile for black pepper",
      "href": "https://fdc.nal.usda.gov/fdc-app.html",
      "section_h2": "Section heading where this link fits",
      "context": "Short sentence showing link context"
    }}
  ],
  "wikipedia_links": [
    {{
      "anchor_text": "Black pepper (Wikipedia)",
      "href": "https://en.wikipedia.org/wiki/Black_pepper",
      "section_h2": "Section heading where this link fits"
    }}
  ]
}}

{self._pm_block("step4_link_planning")}"""

        log.info(f"Links step: routing chain = {self.routing.links.first} → {self.routing.links.second} → {self.routing.links.third}")
        plan = await self._call_ai_with_chain(
            self.routing.links, links_prompt,
            system="You are an expert SEO strategist specialising in link building for content. Return ONLY valid JSON.",
            temperature=0.3, max_tokens=1500,
        )

        # ── Extract link lists with backward-compat for old "links" key ──────
        self._internal_links = plan.get("internal_links", []) or plan.get("links", [])
        self._external_links = plan.get("external_links", [])
        wiki_planned = plan.get("wikipedia_links", [])

        # ── Validate minimums & generate fallbacks ───────────────────────────
        kw_slug = re.sub(r"[^a-z0-9]+", "-", self.keyword.lower()).strip("-")
        # Wikipedia article titles: first word capitalized, rest lowercase, spaces→underscores
        # e.g. "black pepper" → "Black_pepper", not "Black_Pepper"
        _wiki_words = self.keyword.strip().split()
        kw_title = ("_".join([_wiki_words[0].capitalize()] + [w.lower() for w in _wiki_words[1:]])) if _wiki_words else self.keyword

        # Internal links: need 4+
        if len(self._internal_links) < 4:
            _cbase = (self._customer_ctx.get("customer_url") or "").rstrip("/")
            fallback_internals = [
                {"anchor_text": f"explore {self.keyword} products", "href": f"{_cbase}/products/{kw_slug}", "section_h2": sections[0] if sections else "", "context": ""},
                {"anchor_text": f"complete guide to {self.keyword}", "href": f"{_cbase}/guides/{kw_slug}", "section_h2": sections[1] if len(sections) > 1 else "", "context": ""},
                {"anchor_text": f"buy {self.keyword} online", "href": f"{_cbase}/shop/{kw_slug}", "section_h2": sections[-2] if len(sections) > 2 else "", "context": ""},
                {"anchor_text": "contact us for more information", "href": f"{_cbase}/contact", "section_h2": sections[-1] if sections else "", "context": ""},
                {"anchor_text": f"browse all {self.keyword.split()[-1] if self.keyword.split() else 'products'} options", "href": f"{_cbase}/category/{kw_slug}", "section_h2": sections[2] if len(sections) > 2 else "", "context": ""},
            ]
            existing_hrefs = {lk.get("href", "") for lk in self._internal_links}
            for fb in fallback_internals:
                if len(self._internal_links) >= 5:
                    break
                if fb["href"] not in existing_hrefs:
                    self._internal_links.append(fb)
                    existing_hrefs.add(fb["href"])
            log.info(f"Links step: padded internal links to {len(self._internal_links)} (fallback)")

        # External links: need 3+
        if len(self._external_links) < 3:
            kw_encoded = urllib.parse.quote_plus(self.keyword)
            fallback_externals = [
                {"anchor_text": f"{self.keyword} research (PubMed)", "href": f"https://pubmed.ncbi.nlm.nih.gov/?term={kw_encoded}", "section_h2": sections[1] if len(sections) > 1 else "", "context": ""},
                {"anchor_text": f"{self.keyword} information (WHO)", "href": f"https://www.who.int/news-room/fact-sheets", "section_h2": sections[2] if len(sections) > 2 else "", "context": ""},
                {"anchor_text": f"{self.keyword} data (USDA)", "href": f"https://fdc.nal.usda.gov/", "section_h2": sections[0] if sections else "", "context": ""},
                {"anchor_text": f"health benefits research (NIH)", "href": f"https://www.ncbi.nlm.nih.gov/pmc/?term={kw_encoded}", "section_h2": sections[3] if len(sections) > 3 else "", "context": ""},
            ]
            existing_hrefs = {lk.get("href", "") for lk in self._external_links}
            for fb in fallback_externals:
                if len(self._external_links) >= 4:
                    break
                if fb["href"] not in existing_hrefs:
                    self._external_links.append(fb)
                    existing_hrefs.add(fb["href"])
            log.info(f"Links step: padded external links to {len(self._external_links)} (fallback)")

        # Wikipedia links: need 1+ — will also be enriched in Step 5
        if not wiki_planned:
            wiki_planned = [{"anchor_text": f"{self.keyword} (Wikipedia)", "href": f"https://en.wikipedia.org/wiki/{kw_title}", "section_h2": sections[0] if sections else ""}]
            log.info("Links step: generated fallback Wikipedia link")

        # Store authority URLs for post-draft injection use
        self._authority_urls = [lk.get("href", "") for lk in self._external_links if lk.get("href")]

        # Store wiki links planned for Step 5 to enrich
        self._wiki_links = wiki_planned

        int_count = len(self._internal_links)
        ext_count = len(self._external_links)
        wiki_count = len(wiki_planned)
        step.summary = f"{int_count} internal + {ext_count} external + {wiki_count} Wikipedia links planned"
        step.details["links"] = self._internal_links
        step.details["external_links"] = self._external_links
        step.details["wikipedia_links"] = wiki_planned

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5: WIKIPEDIA & AUTHORITY REFERENCES
    # ─────────────────────────────────────────────────────────────────────────

    async def _step5_wikipedia(self):
        """
        Deep research from Wikipedia + web sources.
        Uses Wikipedia full-text search API (not just URL lookup) to find the
        best matching articles, then fetches full article content and extracts
        facts, statistics, historical data, and definitions.
        Also runs web research via DuckDuckGo for additional authority data.
        All research is stored in self._research_data for use in S6 drafting.
        Guarantees self._reference_links is NEVER empty.
        """
        _step_ctx_var.set({"step": 5, "step_name": "Wikipedia", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[4]
        kw = self.keyword.strip()
        words = kw.split()

        wiki_articles = []   # {title, url} for reference links
        all_facts = []       # {fact, source, type}
        all_stats = []       # {stat, source}
        all_sections_text = []  # full article extracts for context
        wiki_sources = []    # {title, url, type}

        # ── 1. Wikipedia Search API — proper full-text search ────────────────
        self._add_log("info", "S5 Searching Wikipedia for topic articles", 5)

        # Check relevance: if results don't contain any core keyword words,
        # the full SEO keyword confused Wikipedia. Try simplified variants.
        _seo_noise = {"best", "top", "buy", "online", "cheap", "free", "review",
                       "guide", "how", "what", "why", "benefits", "uses", "tips",
                       "organic", "natural", "premium", "quality", "authentic",
                       "near", "for", "with", "and", "the", "from", "price",
                       "bulk", "wholesale", "order", "shop", "store", "delivery"}
        # Geographic/location modifiers — shouldn't be treated as core topic words
        _geo_noise = {"india", "indian", "usa", "uk", "europe", "australia", "canada",
                      "america", "american", "china", "chinese", "japan", "japanese",
                      "african", "asian", "european", "kerala", "tamil", "mumbai",
                      "delhi", "bangalore", "london", "york", "california"}
        topic_words = [w for w in words if w.lower() not in _seo_noise
                       and w.lower() not in _geo_noise and len(w) > 2]
        kw_core_words = set(w.lower() for w in topic_words) if topic_words else set(w.lower() for w in words if len(w) > 3)

        # ── Skip Wikipedia if keyword is purely commercial (no real topic) ───
        # e.g. "best organic wholesale price" → all words are SEO/commercial modifiers
        # Wikipedia has nothing useful for shopping-intent queries
        _skip_wiki = len(topic_words) == 0
        if _skip_wiki:
            self._add_log("info", "S5 Keyword is purely commercial — skipping Wikipedia, using web research only", 5)
            search_results = []
        else:
            search_results = await self._wikipedia_search_api(kw, limit=3)

        def _is_relevant(title: str) -> bool:
            """Check if a Wikipedia title is relevant to the keyword's core topic.
            Requires the SUBJECT word(s) to match, not just geographic modifiers."""
            title_lower = title.lower()
            title_words = set(title_lower.split())
            overlap = kw_core_words & title_words
            if not overlap:
                return False
            # Single-word overlap must be a core subject word, not a common word
            _too_generic = {"list", "history", "index", "category", "people",
                            "culture", "economy", "geography", "outline"}
            if len(overlap) == 1 and len(kw_core_words) > 1:
                w = next(iter(overlap))
                if w in _too_generic or len(w) <= 3:
                    return False
                if len(title_words) <= 1 and len(kw_core_words) > 1:
                    return False
            # Reject titles that are clearly about a different topic (food/dish/recipe names
            # that merely mention a spice/ingredient). The title should be ABOUT our subject.
            _off_topic_markers = {"recipe", "dish", "cuisine", "cooking", "dessert",
                                  "ice cream", "cake", "bread", "curry", "soup",
                                  "virus", "disease", "pest", "infection"}
            primary_topic = max(kw_core_words, key=len) if kw_core_words else ""
            for marker in _off_topic_markers:
                if marker in title_lower and primary_topic not in title_lower.replace(marker, "").split():
                    # Title contains off-topic marker but primary topic only appears
                    # as part of that marker phrase — likely irrelevant
                    pass
            # Hard filter: title must contain the longest/primary topic word
            if primary_topic and primary_topic not in title_lower:
                return False
            return True

        relevant_results = [r for r in search_results if _is_relevant(r["title"])]
        if not _skip_wiki and not relevant_results and len(words) > 1:
            # Full keyword missed — build smarter search variants from topic words
            variants = []
            if len(topic_words) >= 2:
                variants.append(" ".join(topic_words))          # all topic words
                variants.append(" ".join(topic_words[:2]))      # first 2 topic words
            if topic_words:
                variants.append(topic_words[0])                 # single most-topic word
            # Also try last 2 original words as fallback
            if len(words) > 2:
                variants.append(" ".join(words[-2:]))
            for variant in variants:
                extra = await self._wikipedia_search_api(variant, limit=3)
                relevant_extra = [r for r in extra if _is_relevant(r["title"])]
                if relevant_extra:
                    search_results = relevant_extra + search_results
                    break
            else:
                # None of the variants produced relevant results — use best short variant
                if extra:
                    search_results = extra + search_results

        # Also try shorter variants if we got fewer than 2 results
        if not _skip_wiki and len(search_results) < 2 and len(words) > 2:
            extra = await self._wikipedia_search_api(" ".join(words[-2:]), limit=2)
            seen_ids = {r["pageid"] for r in search_results}
            for r in extra:
                if r["pageid"] not in seen_ids:
                    search_results.append(r)

        # Deduplicate by pageid, keep order
        seen_pids = set()
        deduped = []
        for r in search_results:
            if r["pageid"] not in seen_pids:
                seen_pids.add(r["pageid"])
                deduped.append(r)
        search_results = deduped

        # Final relevance gate — only fetch articles that pass _is_relevant()
        if not _skip_wiki:
            search_results = [r for r in search_results if _is_relevant(r["title"])]

        # ── 2. Fetch full content for top Wikipedia articles ─────────────────
        for sr in search_results[:3]:
            title = sr["title"]
            self._add_log("info", f"S5 Fetching Wikipedia: {title}", 5)
            wiki_data = await self._wikipedia_full_extract(title)
            if wiki_data and wiki_data.get("extract"):
                extract = wiki_data["extract"]
                page_url = wiki_data.get("url", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}")

                wiki_articles.append({"title": title, "url": page_url})
                wiki_sources.append({"title": title, "url": page_url, "type": "wikipedia"})

                # Store section text (first 2000 chars for drafting context)
                all_sections_text.append(f"=== {title} ===\n{extract[:2000]}")

                # Extract facts and statistics from the full text
                facts, stats = self._extract_facts_and_stats(extract, source=title)
                all_facts.extend(facts)
                all_stats.extend(stats)

                # Backward compat: primary wiki text
                if not self._wiki_text:
                    self._wiki_text = extract[:800]

        # ── 3. H2-based Wikipedia research ───────────────────────────────────
        if not _skip_wiki:
            h2s = self._structure.get("h2_sections", [])
            seen_titles = {a["title"].lower() for a in wiki_articles}
            for h2 in h2s[:3]:
                h2_text = h2.get("h2", "")
                if not h2_text:
                    continue
                h2_results = await self._wikipedia_search_api(f"{kw} {h2_text}", limit=1)
                for sr in h2_results:
                    if sr["title"].lower() not in seen_titles:
                        wiki_data = await self._wikipedia_full_extract(sr["title"])
                        if wiki_data and wiki_data.get("extract"):
                            page_url = wiki_data.get("url", "")
                            wiki_articles.append({"title": sr["title"], "url": page_url})
                            wiki_sources.append({"title": sr["title"], "url": page_url, "type": "wikipedia"})
                            facts, stats = self._extract_facts_and_stats(wiki_data["extract"][:1500], source=sr["title"])
                            all_facts.extend(facts)
                            all_stats.extend(stats)
                            all_sections_text.append(f"=== {sr['title']} ===\n{wiki_data['extract'][:1000]}")
                            seen_titles.add(sr["title"].lower())
                        break  # 1 extra per H2

        # ── 4. Web research for additional facts & data ──────────────────────
        self._add_log("info", "S5 Web research: searching for facts & data", 5)
        web_facts, web_sources = await self._web_research_facts(kw)
        all_facts.extend(web_facts)
        wiki_sources.extend(web_sources)

        # ── 5. PubMed authority references ───────────────────────────────────
        authority_refs = []
        if len(wiki_articles) < 2 or len(self._external_links) < 3:
            pubmed_refs = await self._pubmed_search(kw)
            authority_refs.extend(pubmed_refs)

        # ── 6. Fallback if Wikipedia completely failed ───────────────────────
        if not wiki_articles:
            candidates = [kw]
            if len(words) > 2:
                candidates.append(" ".join(words[-2:]))
                candidates.append(words[-1])
            for candidate in reversed(candidates):
                wiki_encoded = urllib.parse.quote(candidate.replace(" ", "_").title())
                fallback_url = f"https://en.wikipedia.org/wiki/{wiki_encoded}"
                wiki_articles.append({"title": candidate.title(), "url": fallback_url})
                log.info(f"Wikipedia step: using fallback constructed link for '{candidate}'")
                break

        # ── 7. Merge wiki links from Step 4 ──────────────────────────────────
        existing_urls = {a["url"] for a in wiki_articles}
        for wl in self._wiki_links:
            if wl.get("href") and wl["href"] not in existing_urls:
                wiki_articles.append({"title": wl.get("anchor_text", kw.title()), "url": wl["href"]})
                existing_urls.add(wl["href"])

        # ── 8. Add PubMed/authority refs to external links ───────────────────
        if authority_refs:
            existing_ext = {lk.get("href", "") for lk in self._external_links}
            for ref in authority_refs:
                if ref["url"] not in existing_ext and len(self._external_links) < 5:
                    self._external_links.append({
                        "anchor_text": ref["title"],
                        "href": ref["url"],
                        "section_h2": "",
                        "context": "",
                    })
                    self._authority_urls.append(ref["url"])

        # ── 9. Deduplicate facts and stats ───────────────────────────────────
        seen_facts = set()
        unique_facts = []
        for f in all_facts:
            fkey = f["fact"].lower().strip()[:60]
            if fkey not in seen_facts:
                seen_facts.add(fkey)
                unique_facts.append(f)

        seen_stats = set()
        unique_stats = []
        for s in all_stats:
            skey = s["stat"].lower().strip()[:60]
            if skey not in seen_stats:
                seen_stats.add(skey)
                unique_stats.append(s)

        # ── 10. Store research data for drafting ─────────────────────────────
        self._research_data = {
            "wiki_facts": unique_facts[:20],
            "wiki_stats": unique_stats[:15],
            "wiki_sections": "\n\n".join(all_sections_text)[:5000],
            "sources": wiki_sources[:10],
            "web_facts": web_facts[:10],
        }

        self._reference_links = wiki_articles
        n_facts = len(unique_facts)
        n_stats = len(unique_stats)
        n_sources = len(wiki_sources)
        step.summary = f"Found {len(wiki_articles)} Wikipedia + {len(authority_refs)} authority refs · {n_facts} facts · {n_stats} stats"
        step.details["references"] = wiki_articles
        step.details["authority_refs"] = authority_refs
        step.details["wiki_excerpt"] = self._wiki_text[:500] if self._wiki_text else ""
        step.details["facts_count"] = n_facts
        step.details["stats_count"] = n_stats
        step.details["sources_count"] = n_sources
        self._add_log("info", f"S5 Research complete: {n_facts} facts, {n_stats} stats from {n_sources} sources", 5)

    async def _pubmed_search(self, query: str) -> list:
        """Search PubMed for relevant references. Returns list of {title, url}."""
        def _sync_pubmed():
            results = []
            try:
                encoded = urllib.parse.quote_plus(query)
                search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={encoded}&retmax=3&retmode=json"
                resp = requests.get(search_url, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    pmids = data.get("esearchresult", {}).get("idlist", [])
                    for pmid in pmids[:3]:
                        results.append({
                            "title": f"{query} research (PubMed {pmid})",
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        })
            except Exception as e:
                log.debug(f"PubMed search failed for '{query}': {e}")
            return results

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_pubmed)
        except Exception:
            return []

    async def _wikipedia_search_api(self, query: str, limit: int = 3) -> List[Dict]:
        """Search Wikipedia using the MediaWiki full-text search API.
        Returns list of {title, pageid, snippet} — much more accurate than URL lookup."""
        def _sync_search():
            encoded = urllib.parse.quote_plus(query)
            url = (f"https://en.wikipedia.org/w/api.php?action=query&list=search"
                   f"&srsearch={encoded}&srlimit={limit}&format=json")
            headers = {"User-Agent": "ANNASEOBot/1.0 (SEO content research; contact@annaseo.app)"}
            resp = requests.get(url, timeout=10, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("query", {}).get("search", [])
                return [
                    {"title": r["title"], "pageid": r["pageid"],
                     "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", ""))}
                    for r in results
                ]
            return []
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_search)
        except Exception as e:
            log.debug(f"Wikipedia search API failed for '{query}': {e}")
            return []

    async def _wikipedia_full_extract(self, title: str) -> Optional[Dict]:
        """Fetch full article text for a Wikipedia page using action=parse.
        Returns {title, extract (plain text), url, pageid}. Extracts paragraphs
        via BeautifulSoup for clean, space-separated text."""
        def _sync_extract():
            encoded = urllib.parse.quote_plus(title)
            # action=parse gives full HTML of article body
            parse_url = (f"https://en.wikipedia.org/w/api.php?action=parse&page={encoded}"
                         f"&prop=text&format=json")
            # Also get page URL via action=query
            info_url = (f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded}"
                        f"&prop=info&inprop=url&format=json")
            headers = {"User-Agent": "ANNASEOBot/1.0 (SEO content research; contact@annaseo.app)"}

            # Fetch full article HTML
            resp = requests.get(parse_url, timeout=15, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            html = data.get("parse", {}).get("text", {}).get("*", "")
            pageid = data.get("parse", {}).get("pageid", 0)
            if not html:
                return None

            # Parse HTML and extract clean paragraphs
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["sup", "table", "style", "script"]):
                tag.decompose()
            for span in soup.select(".mw-editsection, .reference, .noprint"):
                span.decompose()

            paragraphs = []
            for p in soup.find_all("p"):
                text = p.get_text(" ", strip=True)
                if len(text) > 30:
                    text = re.sub(r"\[\d+\]", "", text)
                    text = re.sub(r"\[citation needed\]", "", text, flags=re.I)
                    text = re.sub(r"\s+", " ", text).strip()
                    paragraphs.append(text)

            extract = "\n".join(paragraphs)

            # Get page URL
            page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            try:
                resp2 = requests.get(info_url, timeout=5, headers=headers)
                if resp2.status_code == 200:
                    pages = resp2.json().get("query", {}).get("pages", {})
                    for pid, pg in pages.items():
                        if int(pid) > 0:
                            page_url = pg.get("fullurl", page_url)
                            pageid = int(pid)
            except Exception:
                pass

            return {
                "title": title,
                "extract": extract,
                "url": page_url,
                "pageid": pageid,
            } if extract else None

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_extract)
        except Exception as e:
            log.debug(f"Wikipedia full extract failed for '{title}': {e}")
            return None

    def _extract_facts_and_stats(self, text: str, source: str = "") -> tuple:
        """Extract facts and statistics from text using pattern matching.
        Returns (facts_list, stats_list) where each is [{fact/stat, source, type}]."""
        facts = []
        stats = []
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20 or len(sent) > 300:
                continue

            # Statistics: sentences containing numbers with units/context
            has_number = bool(re.search(
                r'\b\d[\d,.]*\s*(%|percent|million|billion|trillion|thousand|'
                r'kg|lb|mg|g|km|miles|meters|metres|feet|years|months|days|hours|'
                r'tonnes|tons|USD|dollars|\$|€|£|hectares|acres|litres|liters|'
                r'calories|kcal|kJ|MW|GW|ppm|sq)', sent, re.I))
            has_year = bool(re.search(r'\b(1[5-9]\d{2}|20[0-2]\d)\b', sent))
            has_comparison = bool(re.search(
                r'\b(largest|smallest|most|least|highest|lowest|first|oldest|newest|'
                r'top|leading|major|significant|world.s|globally|worldwide)\b', sent, re.I))

            if has_number:
                stats.append({"stat": sent, "source": source})
            elif has_year and len(sent) > 30:
                facts.append({"fact": sent, "source": source, "type": "historical"})
            elif has_comparison:
                facts.append({"fact": sent, "source": source, "type": "comparative"})
            elif any(w in sent.lower() for w in (
                "known as", "defined as", "refers to", "is a ", "are a ",
                "was a ", "were a ", "discovered", "invented", "originated",
                "native to", "found in", "produced in", "grown in",
                "used for", "used in", "made from", "derived from",
                "consists of", "contains ", "composed of",
            )):
                facts.append({"fact": sent, "source": source, "type": "definitional"})

        return facts[:15], stats[:10]

    async def _web_research_facts(self, keyword: str) -> tuple:
        """Search web for additional facts about keyword.
        Returns (facts_list, sources_list). Prioritises authority domains."""
        facts = []
        sources = []

        try:
            urls = await self._ddg_search(f"{keyword} facts statistics data", n=5)

            # Prioritise authority/informational domains
            authority_domains = ('.org', '.edu', '.gov', 'wikipedia', 'britannica',
                                 'statista', 'ncbi', 'pubmed', 'nih.gov', 'who.int',
                                 'fao.org', 'worldbank', 'un.org')
            auth_urls = [u for u in urls if any(d in u.lower() for d in authority_domains)]
            other_urls = [u for u in urls if u not in auth_urls]
            ordered_urls = auth_urls + other_urls

            # Skip pages already crawled in S1
            s1_urls = {p.url for p in self._crawled_pages}

            crawled_count = 0
            for url in ordered_urls:
                if crawled_count >= 3 or url in s1_urls:
                    continue
                page = await self._crawl_page(url)
                if page:
                    sources.append({"title": page.title[:100], "url": url, "type": "web"})
                    for para in page.paragraphs[:8]:
                        pf, ps = self._extract_facts_and_stats(para, source=page.title[:60])
                        facts.extend(pf)
                        facts.extend([{"fact": s["stat"], "source": s["source"], "type": "statistic"} for s in ps])
                    crawled_count += 1
                    await asyncio.sleep(0.5)  # polite crawl
        except Exception as e:
            log.warning(f"Web research failed: {e}")

        return facts[:10], sources

    def _research_context_block(self, section_h2: str = "") -> str:
        """Build a rich research context block for drafting prompts.
        If section_h2 is provided, prioritises facts relevant to that section."""
        if not self._research_data:
            return f"\nWikipedia context: {self._wiki_text[:300]}" if self._wiki_text else ""

        parts = []

        # Key facts — prioritise section-relevant ones
        all_facts = self._research_data.get("wiki_facts", []) + self._research_data.get("web_facts", [])
        if section_h2 and all_facts:
            h2_words = set(w.lower() for w in section_h2.split() if len(w) > 3)
            relevant = [f for f in all_facts if h2_words & set(f["fact"].lower().split())]
            other = [f for f in all_facts if f not in relevant]
            ordered = relevant[:5] + other[:5]
        else:
            ordered = all_facts[:8]

        if ordered:
            parts.append("RESEARCH FACTS (use these in your content for authority — cite the source):")
            for f in ordered:
                parts.append(f"  - {f['fact'][:250]} [{f.get('source', 'research')}]")

        # Statistics
        stats = self._research_data.get("wiki_stats", [])
        if stats:
            parts.append("\nSTATISTICS & DATA (embed specific numbers for credibility):")
            for s in stats[:8]:
                parts.append(f"  - {s['stat'][:250]} [{s.get('source', 'research')}]")

        # Wikipedia background context
        wiki_text = self._research_data.get("wiki_sections", "")
        if wiki_text:
            parts.append(f"\nWIKIPEDIA BACKGROUND (use for accuracy — do NOT copy verbatim):\n{wiki_text[:1000]}")

        # Sources for attribution
        src = self._research_data.get("sources", [])
        if src:
            parts.append("\nSOURCES (attribute using 'according to', 'research shows', etc.):")
            for s in src[:5]:
                parts.append(f"  - {s['title']} — {s['url']}")

        return "\n".join(parts) if parts else ""

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6: CONTENT DRAFTING (Groq)
    # ─────────────────────────────────────────────────────────────────────────

    # Per-section-type writing requirements injected at prompt time so the
    # model produces signals naturally, rather than us bolting them on after
    # generation. Eliminates most cosmetic post-process injections.
    _SECTION_TYPE_REQUIREMENTS = {
        "definition": (
            "SECTION TYPE: definition\n"
            "- Open with a clear definitional sentence: '{keyword} is a ...' or '{keyword} refers to ...'\n"
            "- Explain what it is, why it matters, and who uses it\n"
            "- Include a real-world scenario that illustrates the definition\n"
            "- Add 1 implicit question opener: 'You might wonder...', 'What many buyers don't realise...'"
        ),
        "benefits": (
            "SECTION TYPE: benefits\n"
            "- For each benefit, tie it to a REAL situation or outcome, not a feature list\n"
            "- Use scenario framing: 'For buyers who need X...', 'In situations where...'\n"
            "- Include 1 subtle qualifier: 'In most cases', 'Typically', 'Depending on your needs'\n"
            "- Close with one concrete, verifiable observation grounded in a cited source or industry-standard fact (avoid first-person testing claims)."
        ),
        "how_to": (
            "SECTION TYPE: how_to\n"
            "- Use numbered steps. Each step must have a realistic gotcha or nuance\n"
            "- Include 1 urgency/mistake signal: 'A common mistake here is...', 'Most people skip this step...'\n"
            "- Add 1 evidence-based observation tied to a specific cited source, manufacturer spec, or public dataset — NOT fabricated first-person claims.\n"
            "- Avoid robotic transitions between steps"
        ),
        "comparison": (
            "SECTION TYPE: comparison\n"
            "- Take a CLEAR POSITION. Don't say 'it depends' without immediately explaining WHY\n"
            "- Include at least one real trade-off (cost vs quality, speed vs accuracy, etc.)\n"
            "- Use balanced view: 'The advantage is X, but the trade-off is Y'\n"
            "- Include a decision helper: 'Choose option A if... choose option B if...'\n"
            "- Add 1 trust signal: verified data, named source, or tested result"
        ),
        "buyers_guide": (
            "SECTION TYPE: buyers_guide\n"
            "- Cover exactly 3 decision criteria the reader must evaluate before buying\n"
            "- For each criterion, state what to look for AND what to avoid\n"
            "- Include 1 urgency signal: 'Don't overlook this...', 'A common mistake buyers make...'\n"
            "- End with a sentence that helps the reader self-qualify: 'This is ideal for... but not suited for...'"
        ),
        "pros_cons": (
            "SECTION TYPE: pros_cons\n"
            "- Write a genuine list: 3-4 specific pros and 2-3 real cons\n"
            "- Each pro/con must be specific, not generic ('saves 2 hours per week' > 'saves time')\n"
            "- Cons must be honest and realistic — not watered-down\n"
            "- Tone: for consumer/buyer keywords, use conversational language ('you'll save time', 'ideal for home use'). For B2B/wholesale keywords, use professional language ('suitable for commercial operations', 'meets industry standards').\n"
            "- Add 1 hedging qualifier to the cons section: 'For most buyers, this is acceptable because...'"
        ),
        "use_cases": (
            "SECTION TYPE: use_cases\n"
            "- Describe 2-3 specific real-world scenarios where this is applied\n"
            "- Each use case must have a named context: 'For small-scale retailers...', 'In commercial kitchens...'\n"
            "- Add 1 implicit question: 'Which use case fits you? Here's how to decide...'"
        ),
        "trust": (
            "SECTION TYPE: trust\n"
            "- Reference specific certifications, standards, or testing processes\n"
            "- Use verified language: 'independently tested', 'ISO-certified', 'third-party verified'\n"
            "- Avoid vague 'trusted by thousands' claims — be specific about what is verified and how\n"
            "- Add 1 conversational question: 'Why does this matter? Because...'"
        ),
        "expert_tips": (
            "SECTION TYPE: expert_tips\n"
            "- Each tip must be NON-OBVIOUS — not the generic '5 tips' article\n"
            "- Include 1 evidence-based insight citing industry data or named sources (e.g. 'According to industry data...', 'What the research misses...')\n"
            "- Include 1 hedging qualifier: 'This works in most cases, though...'\n"
            "- Add 1 urgency signal: 'The detail most people overlook is...'"
        ),
        "faq": (
            "SECTION TYPE: faq\n"
            "- Each answer must be 40-60 words and DIRECTLY answer the question in the first sentence\n"
            "- Format each Q as an <h2> or <h3>, each A as a <p>\n"
            "- Include '{keyword}' naturally in each answer\n"
            "- Add 1 snippet-ready phrase per answer: 'The best {keyword} is...', 'To {keyword}...', '{keyword} works by...'"
        ),
    }

    async def _step6_draft(self):
        """
        Section-based article generation for reliability.
        Instead of one massive 8000-token call that causes timeouts and 429s,
        splits into: intro (800 tok) -> section batches (1200 tok each, 2-3 H2s
        per batch) -> FAQ + conclusion (1000 tok). Smaller calls fail less
        often and recover faster from rate limits.
        """
        _step_ctx_var.set({"step": 6, "step_name": "Draft", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[5]

        structure = self._structure
        h2_sections = structure.get("h2_sections", [])

        # ── Build shared context (compact version — not the full 33-rule spec) ──
        pt_ctx = self._page_type_context()
        pt_label = self._page_type_label()
        research_themes = self.state.steps[0].details.get("analysis", {}).get("themes", [])
        key_facts = self.state.steps[0].details.get("analysis", {}).get("key_facts", [])
        research_angles = self.state.steps[0].details.get("analysis", {}).get("angles", [])
        research_gaps = self.state.steps[0].details.get("analysis", {}).get("gaps", [])
        research_block = self._research_context_block()
        customer_ctx = self._customer_context_block()

        # Compute adaptive keyword mention target based on keyword word count
        kw_word_count = len((self.keyword or "").split())
        # Scale inversely: 1-word KW → 3-5 per section; 4+ word KW → 1-2 total per section
        if kw_word_count >= 4:
            kw_usage_guide = "use naturally 1-2 times total per section (not per paragraph)"
        elif kw_word_count == 3:
            kw_usage_guide = "use naturally 2-3 times per section"
        else:
            kw_usage_guide = "use naturally 2-4 times per section"

        # Phase D: render intent-plan constraint block (empty string if missing)
        try:
            from engines.intent_planner import render_intent_block
            _intent_block = render_intent_block(self._intent_data.get("plan") or {})
        except Exception:
            _intent_block = ""
        _intent_block_section = (_intent_block + "\n\n") if _intent_block else ""

        # Compact rules block shared across all section prompts
        rules_compact = f"""{_intent_block_section}KEYWORD: "{self.keyword}" — {kw_usage_guide}. Overall density target: 1.0-1.5%.
Semantic Variations: {', '.join(self._semantic_variations[:5]) if self._semantic_variations else 'use synonyms'}
{"Entities to mention: " + ', '.join(self._target_entities[:8]) if self._target_entities else ""}

── READABILITY (Flesch 60-70) ──
Sentence length: Avg 15-20w. Mix short (8-12w) + medium (18-25w). Break >30w sentences. Active voice >80%. Transitions between paragraphs (However, Moreover, Additionally). Max 3 sentences/paragraph. Max 80w/paragraph.

── SENTENCE VARIETY (20+ Openers) ──
Limit "The" to <20%. Questions 10%+ ("How do...?", "What makes...?"). Imperatives (Do, Try, Consider). Transitional (However, Moreover, Therefore). Subordinate (While, Although, Because). Adverbs (Typically, Generally). Coordinating sparingly (And, But, So). Never 3+ consecutive same starters.

── DATA CREDIBILITY (5+ Sourced Stats) ──
Cite SPECIFIC named sources: "According to FDA (2024)...", "Harvard study (2023) found...", "Grand View Research reports (2024)..." Every percentage MUST have attribution. NEVER invent sources. If no source, use ranges ("approximately 20-30%") or state facts directly.

── AUTHORITY & E-E-A-T ──
Show expertise via specifics: cultivar/variety names, grade thresholds, processing steps, real measurements with units. Cite third-party sources (Spices Board, USDA, ISO standards) by name. NEVER use "we tested", "in our experience", "we found", "hands-on", "after putting to the test", "in our kitchen", "we actually sent" — fabricated first-person experience destroys trust.

── STORYTELLING & VOICE (2+ Each) ──
Narrative: customer scenarios in third-person ("a buyer who needs X will find Y"), before/after framing tied to cited evidence, analogies. Opinion signals (neutral framing): "the strongest option for X is Y", "avoid X when Y", contrarian views supported by sources. Use contractions (don't, isn't). Ask 3+ rhetorical questions ("Why does this matter?"). Nuance: "on the other hand", "the catch is", "that said". DO NOT fabricate first-person testing ("we tested", "our team", "hands-on", "in our kitchen").

── BUYER GUIDANCE ──
Include: "how to choose", "what to look for", "best for", "pros and cons". Buyer decisions: "recommended for", "ideal for", "not recommended for". Practical scenarios (2+): "for example, if you need..."

── CONTENT DEPTH ──
Cover what/why/how/when angles. Mix beginner ("basics", "getting started") + advanced ("professional", "in-depth") content. Use "for example", "in practice", "use case" for concrete scenarios.

── FORBIDDEN ──
Words: delve, multifaceted, landscape, tapestry, nuanced, robust, myriad, paradigm, foster, holistic, pivotal, streamline, cutting-edge, plethora, underscore. Phrases: "let's explore", "when it comes to", "in today's world", "let's dive in", "furthermore/moreover/additionally" chains.

── TEMPLATE SENTENCE PATTERNS TO NEVER GENERATE ──
DO NOT write any of these SEO template patterns (they appear identically across thousands of AI articles and destroy uniqueness):
❌ "This factor directly influences [keyword] performance."
❌ "Buyers evaluating [keyword] should weigh this carefully."
❌ "For [keyword], this distinction matters more than most realise."
❌ "In practice, [keyword] outcomes depend heavily on [variable]."
❌ "Without addressing this, [keyword] results will be inconsistent."
❌ "This is where [keyword] quality becomes measurable."
❌ "The best [keyword] consistently scores well on this criterion."
❌ "Experienced [keyword] buyers check this before anything else."
❌ "Our experience shows that [generic claim about product/service]."
❌ "We found it adds [benefit] to [use-case]."
❌ "When we analyzed [data/feedback], we discovered [insight]."
If you need to use the keyword in a sentence, write UNIQUE phrasing specific to the actual content.

── ANTI-STUFFING ──
Do NOT repeat exact keyword "{self.keyword}" in every paragraph. Use in H2s, intro, conclusion. In body: pronouns ("it", "they", "this") or short references.

── ANTI-DUPLICATION (CRITICAL) ──
- The DEFINITION of "{self.keyword}" appears EXACTLY ONCE — in the introduction. Do NOT redefine it in any other section. Subsequent sections assume the reader knows what it is.
- Each H2 covers a DISTINCT angle. Never produce two H2s on the same topic (e.g. do not write "Whole vs Ground" twice, do not write "Regional Varieties" and "Regional Blends" as separate sections).
- If the structure plan accidentally lists overlapping H2s, MERGE them under one heading rather than repeating content.
- Do NOT recap content from earlier sections. Each section adds NEW information.

── COMPLETE SENTENCES ──
Every sentence must end with a complete thought. NEVER end mid-clause (e.g. "India is responsible for." or "The key factor includes."). If you cannot complete a fact with concrete data, omit the sentence entirely.

{customer_ctx}
OUTPUT: Clean semantic HTML only. <h2 id="anchor">, <h3>, <p>, <ul><li>, <ol><li>, <table>, <strong>, <a>. No markdown, no code fences."""

        # ── Helper: find links assigned to specific sections ──
        def _links_for_sections(section_h2s):
            h2_set = {h.lower() for h in section_h2s}
            int_links = [lk for lk in self._internal_links if lk.get("section_h2", "").lower() in h2_set]
            ext_links = [lk for lk in self._external_links if lk.get("section_h2", "").lower() in h2_set]
            ref_links = self._reference_links  # always available
            parts = []
            if int_links:
                parts.append("INTERNAL LINKS to embed:\n" + "\n".join(
                    f'  <a href="{lk["href"]}">{lk["anchor_text"]}</a>{" — " + lk["context"] if lk.get("context") else ""}' for lk in int_links))
            if ext_links:
                parts.append("EXTERNAL LINKS to embed:\n" + "\n".join(
                    f'  <a href="{lk["href"]}" target="_blank" rel="noopener">{lk["anchor_text"]}</a>{" — " + lk["context"] if lk.get("context") else ""}' for lk in ext_links))
            return "\n".join(parts)

        # ── PART 1: Introduction + TOC ───────────────────────────────────
        _toc_raw = structure.get("toc_anchors", [])
        toc_anchors = (_toc_raw if isinstance(_toc_raw, list) else [_toc_raw] if _toc_raw else [])[:8]
        intro_prompt = f"""Write the INTRODUCTION for a comprehensive SEO {pt_label} about "{self.keyword}".

{_intent_block_section}TITLE (H1): {structure.get("h1", self.keyword.title())}
Intent: {self._intent_data.get('primary_intent', self.intent)}
Business: {self.project_name or "the business"}
{"Target Audience: " + self.target_audience if self.target_audience else ""}
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
Introduction plan: {structure.get("intro_plan", "Hook + overview of what reader learns")}

Key themes: {', '.join(research_themes[:5])}
Key facts: {', '.join(key_facts[:3]) if key_facts else "Provide relevant data"}

{research_block}

REQUIREMENTS:
- Start with a hook sentence containing "{self.keyword}" in the first 10 words
- First paragraph MUST be ≥40 words and start with "{self.keyword.split()[0]}"
- DEFINITION: Within the first 150 words, include a clear definition: "{self.keyword} is a ..." or "{self.keyword} refers to ...". This is a scored requirement. The definition appears HERE ONLY — do not restate it in any later section.
- READABILITY: Sentence avg 15-20 words (mix 8-12w short + 18-25w medium). Flesch target: 60-70. Active voice >80%.
- SENTENCE VARIETY: Start sentences differently. Use 5+ opener types: questions ("What is..."), imperatives ("Consider..."), transitions ("However..."), subordinate ("While..."), adverbs ("Typically..."). Limit "The" to <20%.
- Include a TL;DR / Key Takeaways box after intro (use <div class="key-takeaway">)
- SOFT CTA: After TL;DR box, add 1 sentence: "Discover the benefits of {self.keyword} for [benefit]. Learn more below."
- After intro + CTA, add a TOC nav block: <nav><ul> with links to these anchors: {json.dumps(toc_anchors)}
- Total: 180-280 words (including soft CTA)

{rules_compact}"""

        log.info(f"Draft step: routing chain = {self.routing.draft.first} → {self.routing.draft.second} → {self.routing.draft.third}")
        self._add_log("info", "S6 Generating intro + TOC", 6)
        intro_html = await self._call_ai_raw_with_chain(
            self.routing.draft, intro_prompt, temperature=0.6, max_tokens=800
        )
        if not intro_html:
            # Build a research-aware fallback intro instead of generic filler
            _fb_themes = self.state.steps[0].details.get("analysis", {}).get("themes", []) if self.state.steps[0].details else []
            _fb_facts = self.state.steps[0].details.get("analysis", {}).get("key_facts", []) if self.state.steps[0].details else []
            _fb_theme = _fb_themes[0] if _fb_themes else "quality, sourcing, and practical selection criteria"
            _fb_fact = f' {_fb_facts[0]}.' if _fb_facts else ''
            intro_html = (
                f'<p>{self.keyword.title()} refers to {_fb_theme.lower()}, '
                f'and understanding the key differences can significantly impact your results.{_fb_fact}</p>\n'
                f'<p>This guide covers what matters most when evaluating {self.keyword} — '
                f'from critical specifications to practical buying considerations.</p>'
            )

        # ── PART 2: Body sections (batches of 2-3) ─────────────────────────
        section_parts = []
        batch_size = 3 if len(h2_sections) <= 6 else 2
        batches = [h2_sections[i:i+batch_size] for i in range(0, len(h2_sections), batch_size)]
        cross_batch_summary: list[str] = []  # accumulates per-batch memory for subsequent prompts

        for batch_idx, batch in enumerate(batches):
            section_names = [s['h2'] for s in batch]
            sections_spec = ""
            for s in batch:
                h3_list = "\n    - " + "\n    - ".join(s.get("h3s", [])) if s.get("h3s") else ""
                # Inject S2 content_angle and authority_note so the drafter uses them
                angle_line = f"\n    Angle: {s['content_angle']}" if s.get("content_angle") else ""
                authority_line = f"\n    Authority: {s['authority_note']}" if s.get("authority_note") else ""
                sections_spec += f'\n  <h2 id="{s.get("anchor", "")}"> {s["h2"]} </h2> (~{s.get("word_target", 300)} words){angle_line}{authority_line}{h3_list}'

            links_ctx = _links_for_sections(section_names)

            # Section-specific research context
            section_research = self._research_context_block(section_h2=section_names[0] if section_names else "")

            # Determine if this batch should include the comparison table
            table_note = ""
            if batch_idx == 0:
                table_note = "\nINCLUDE: One <table> with <thead>/<tbody> for comparison/data (3+ rows × 3+ columns)."
            list_note = "\nINCLUDE: At least 1 <ul> list and 1 <ol> list in these sections." if batch_idx <= 1 else ""

            # Type-specific writing requirements for each section in this batch
            type_rules_parts = []
            for s in batch:
                sec_type = (s.get("type") or "").lower()
                rule = self._SECTION_TYPE_REQUIREMENTS.get(sec_type)
                if rule:
                    type_rules_parts.append(rule.replace("{keyword}", self.keyword))
            type_rules_block = ("\nSECTION-TYPE WRITING REQUIREMENTS:\n" + "\n\n".join(type_rules_parts)) if type_rules_parts else ""

            # Cross-batch memory: prevent repeating points from prior batches
            memory_block = ""
            if cross_batch_summary:
                prev_items = cross_batch_summary  # full history to avoid repeats
                memory_block = "\nPREVIOUSLY COVERED (do NOT repeat these points or arguments):\n" + "\n".join(f"  - {m}" for m in prev_items)

            # S1 research differentiation context for body sections
            angles_block = ""
            if research_angles:
                angles_block = "DIFFERENTIATION ANGLES (weave these into the content):\n" + "\n".join(f"  - {a}" for a in research_angles[:3])
            gaps_block = ""
            if research_gaps:
                gaps_block = "CONTENT GAPS to fill (competitors miss these):\n" + "\n".join(f"  - {g}" for g in research_gaps[:3])

            batch_prompt = f"""Write these sections for an SEO {pt_label} about "{self.keyword}".

SECTIONS TO WRITE:{sections_spec}
{table_note}{list_note}
{type_rules_block}
{memory_block}

{"Supporting keywords to include: " + ', '.join(self.supporting_keywords[:8]) if self.supporting_keywords else ""}

{angles_block}
{gaps_block}

{section_research}

{links_ctx}

{("STRUCTURE REVIEWER NOTES (apply when writing):\n" + chr(10).join(f"  - {imp}" for imp in self._structure_improvements[:6])) if getattr(self, "_structure_improvements", None) else ""}

INSIGHT: For each section, include one NON-OBVIOUS insight — what do most articles miss about this topic? What's the practical real-world implication that someone with hands-on experience would know?

DATA SOURCING (Required: 3+ sourced statistics in these sections):
- Format: "According to [FDA/USDA/NIH/Harvard/etc.] (2023-2024), [statistic]..."
- Use government (FDA, USDA, NIH, CDC), academic (PubMed, universities), or industry sources (Grand View Research, IBISWorld)
- NEVER state percentages or precise numbers without attribution
- If no source available, use ranges: "approximately 20-30%" or state facts directly

STORYTELLING (Required: 1+ narrative element per section):
- Use evidence-based framing tied to cited sources, manufacturer specs, or public datasets. NEVER fabricate first-person testing or experience claims.
- Include specific scenarios: "For instance, if you're buying for [use case]..."
- Add brief customer examples (1-2 sentences)
- Use analogies for complex concepts

OPINION SIGNALS (Required: 1+ per section, NEUTRAL framing only):
- Take clear stance without fake first-person: "The strongest option is...", "Avoid X when Y", "For most buyers, prefer X"
- DO NOT write "we tested", "in our experience", "our team", "hands-on" — fabricated authority claims will be rejected by reviewers
- State contrarian views when supported by a cited source: "Contrary to popular belief, [source] shows..."
- Be specific: NOT "many benefits", YES "improved shelf life of 6-12 months"

{rules_compact}

Write ONLY these sections. Start directly with the first <h2>. No intro, no conclusion."""

            self._add_log("info", f"S6 Generating sections batch {batch_idx+1}/{len(batches)}: {', '.join(s['h2'][:30] for s in batch)}", 6)
            batch_html = await self._call_ai_raw_with_chain(
                self.routing.draft, batch_prompt, temperature=0.6, max_tokens=1200
            )
            if batch_html:
                section_parts.append(batch_html)
                # Record a compact summary for cross-batch memory — strip HTML first
                _batch_text = re.sub(r"<[^>]+>", " ", batch_html).strip()
                _batch_first_sentence = _batch_text.split(".")[0].strip()[:120]
                cross_batch_summary.append(f"{', '.join(section_names)}: {_batch_first_sentence}")
            else:
                # Research-aware fallback for this batch
                _fb_themes = self.state.steps[0].details.get("analysis", {}).get("themes", []) if self.state.steps[0].details else []
                for s in batch:
                    _sec_theme = _fb_themes[batch_idx % len(_fb_themes)] if _fb_themes else s['h2'].lower()
                    section_parts.append(
                        f'<h2 id="{s.get("anchor","")}">{s["h2"]}</h2>\n'
                        f'<p>When evaluating {self.keyword} in the context of {s["h2"].lower()}, '
                        f'the most important factor is {_sec_theme.lower()}. '
                        f'Buyers should compare at least three options before making a decision.</p>'
                    )

        # ── PART 3: FAQ + Conclusion ───────────────────────────────────────
        _faqs_raw = structure.get("faqs", [])
        faqs = (_faqs_raw if isinstance(_faqs_raw, list) else [_faqs_raw] if _faqs_raw else [])[:6]
        faq_questions = [f.get("q") or f.get("question") or f.get("text", "") for f in faqs if f.get("q") or f.get("question") or f.get("text")]
        conclusion_plan = structure.get("conclusion_plan", "Summarise + CTA")

        ref_links_text = "\n".join(
            f'  <a href="{r["url"]}" target="_blank" rel="noopener">{r["title"]} (Wikipedia)</a>'
            for r in self._reference_links
        )

        faq_prompt = f"""Write the FAQ SECTION and CONCLUSION for an SEO {pt_label} about "{self.keyword}".

FAQ SECTION:
- Start with: <h2 id="faq">Frequently Asked Questions About {self.keyword.title()}</h2>
- Then write EACH question as its own <h2> with a question mark, immediately followed by a <p> answer
- Format: <h2>Question text here?</h2><p>Answer text 40-60 words...</p>
- Include "{self.keyword}" in each answer
- Each answer paragraph must be 40-60 words, direct and complete
- Questions:
{chr(10).join(f"  - {q}" for q in faq_questions)}

CONCLUSION:
- Plan: {conclusion_plan}
- STRONG ACTION CTA (REQUIRED - scored): Final paragraph MUST include one of these verbs: buy, shop, order, contact, get started, compare, try
- CTA format: "[Action verb] {self.keyword} today and [specific benefit]. [Urgency phrase]."
- Examples: "Shop premium {self.keyword} today and enjoy 30% longer freshness. Don't settle for inferior quality."
- Include "{self.keyword}" in conclusion
- Add urgency: "Start today", "Don't wait", "Limited availability", "Act now"
- Add benefit: "...and enjoy [specific measurable benefit]"
- 100-150 words with CLEAR action-oriented final sentence

{f"WIKIPEDIA REFERENCES to embed:{chr(10)}{ref_links_text}" if ref_links_text else ""}

{self._research_context_block(section_h2="FAQ")}

{rules_compact}

Write ONLY the FAQ section and conclusion. Start with the FAQ <h2>."""

        self._add_log("info", "S6 Generating FAQ + conclusion", 6)
        faq_html = await self._call_ai_raw_with_chain(
            self.routing.draft, faq_prompt, temperature=0.6, max_tokens=1000
        )
        if not faq_html:
            # Build FAQ with keyword-specific, non-generic fallback answers
            _fb_themes = self.state.steps[0].details.get("analysis", {}).get("themes", []) if self.state.steps[0].details else []
            _fb_theme = _fb_themes[0] if _fb_themes else "specifications and sourcing"
            faq_html = f'<h2 id="faq">Frequently Asked Questions About {self.keyword.title()}</h2>'
            _faq_templates = [
                f'The answer depends primarily on {_fb_theme.lower()} and your intended application. Compare certified options from at least two suppliers before deciding.',
                f'{self.keyword.title()} varies based on grade, origin, and processing method. Verify supplier certifications and request samples to assess quality firsthand.',
                f'Most buyers of {self.keyword} prioritize consistency and documented sourcing. Start with small trial orders and scale after verifying performance.',
                f'For {self.keyword}, the key factors are origin verification, batch consistency, and compliance with industry standards. Independent lab testing offers the most reliable assurance.',
            ]
            for qi, q in enumerate(faq_questions[:4]):
                faq_html += (
                    f'\n<h3>{q}</h3>\n'
                    f'<p>{_faq_templates[qi % len(_faq_templates)]}</p>'
                )

        # ── Assemble full draft ───────────────────────────────────────────
        draft = intro_html + "\n\n" + "\n\n".join(section_parts) + "\n\n" + faq_html

        # Clean any code fences that leaked through
        draft = re.sub(r"```html\n?", "", draft)
        draft = re.sub(r"```\n?", "", draft).strip()

        if not draft or len(draft) < 200:
            log.warning("Draft: section-based generation produced insufficient output — falling back to Ollama section writer")
            try:
                draft = await self._ollama_section_writer(ollama_url=_live_ollama_url())
            except Exception as e:
                log.warning(f"Section writer also failed: {e}")
                draft = ""

        if not draft or len(draft) < 200:
            log.warning("All AI providers failed — using minimal structural placeholder draft")
            draft = self._minimal_draft_from_structure()

        self.state.draft_html = draft
        self.state.final_html = draft  # start with draft
        self.state.title = structure.get("h1", self.keyword.title())
        self.state.meta_title = structure.get("meta_title", self.keyword[:60])
        self.state.meta_desc = structure.get("meta_description", "")[:160]
        self.state.word_count = len(re.sub(r"<[^>]+>", " ", draft).split())
        step.summary = f"Draft written: {self.state.word_count} words"

        # ── Post-draft auto-injection: programmatically fix mechanical rules ──
        self.state.draft_html = self._post_draft_inject(self.state.draft_html)

        # ── AI Watermark scrub: remove AI fluff patterns (R35) ──
        self.state.draft_html = self._scrub_ai_patterns(self.state.draft_html)

        # ── Readability Enforcer: guarantee Flesch 60-70 (R18) ──
        self.state.draft_html = await self._enforce_readability(self.state.draft_html)

        # ── Content Intelligence post-processing (R34-R46) ──
        self.state.draft_html = self._intelligence_post_process(self.state.draft_html)

        # Editorial intelligence is a non-critical enhancement — never fail Step 6 over it
        try:
            await self._step_editorial_intelligence()
        except Exception as _ei_err:
            log.warning(f"Editorial intelligence skipped (non-fatal): {_ei_err}")
            if not hasattr(self.state, "editorial_instructions"):
                self.state.editorial_instructions = []

        # ── Integrity scan: detect mid-word corruption (trust killer) ──
        try:
            self.state.draft_html = self._check_content_integrity(self.state.draft_html)
        except Exception as _int_err:
            log.warning(f"Integrity scan skipped (non-fatal): {_int_err}")

        # ── Phase B: per-section scoring (read-only foundation for Phase C) ──
        self._score_all_sections(self.state.draft_html)

        # ── Phase C: targeted regen of weak sections (feature-flagged) ──
        try:
            self.state.draft_html = await self._run_targeted_regen(self.state.draft_html)
        except Exception as _regen_err:
            log.warning(f"Targeted regen skipped (non-fatal): {_regen_err}")

        self.state.final_html = self.state.draft_html

    # ─────────────────────────────────────────────────────────────────────────

    async def _step_editorial_intelligence(self):
        """
        Runs the EditorialIntelligenceEngine on the drafted sections to prevent 
        repetition, enforce narrative flow, and check global keyword density.
        Appends rewrite/restructure instructions for the recovery/redevelop step.
        """
        _step_ctx_var.set({"step": 6.5, "step_name": "Editorial Intelligence", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        
        if not hasattr(self.state, "editorial_instructions"):
            self.state.editorial_instructions = []

        # Defensive: ensure required attrs exist (handles older deployments / recovery re-instantiations)
        if not hasattr(self, "_blueprint"):
            self._blueprint = None
        if not hasattr(self, "content_state"):
            try:
                from core.routing_schema import ContentState
                self.content_state = ContentState()
            except Exception:
                log.warning("Editorial intelligence skipped: content_state unavailable")
                return

        log.info("Running EditorialIntelligenceEngine to build post-draft instructions")
        
        # Initialize Engine
        engine = EditorialIntelligenceEngine(
            title=self.state.title,
            keyword=self.keyword,
            intent=self.intent,
            content_state=self.content_state
        )

        full_html = self.state.draft_html or ""
        blueprint = getattr(self, "_blueprint", None)
        sections = getattr(blueprint, "sections", []) if blueprint else []

        # 1 — Per-section repetition scan (anecdotes / examples)
        repetition_instructions = engine.scan_all_sections_for_repetition(full_html)
        self.state.editorial_instructions.extend(repetition_instructions)

        # 2 — Global keyword density check
        density_instructions = engine.global_keyword_density_check(full_html)
        self.state.editorial_instructions.extend(density_instructions)

        # 3 — Intent fulfilment check
        intent_instructions = engine.intent_delivery_check(sections)
        self.state.editorial_instructions.extend(intent_instructions)
        
        if self.state.editorial_instructions:
            log.info(f"Editorial Intelligence added {len(self.state.editorial_instructions)} instructions")
        else:
            log.info("Editorial Intelligence passed with no additional instructions")

    # ─────────────────────────────────────────────────────────────────────────
    # POST-DRAFT AUTO-INJECTION (programmatic — runs after Step 6 draft)
    # ─────────────────────────────────────────────────────────────────────────

    def _post_draft_inject(self, html: str) -> str:
        """
        Programmatically inject missing links and authority signals into draft HTML.
        Targets R20 (authority signals), R24 (internal links), R25 (external links),
        R26 (Wikipedia). This is deterministic — no AI call needed.
        Returns the patched HTML.
        """
        if not html or len(html) < 200:
            return html

        text = re.sub(r"<[^>]+>", " ", html)
        text_lower = text.lower()

        # ── R24: Internal links (need 4+ href="/") ──────────────────────────
        internal_count = len(re.findall(r'href="/', html))
        if internal_count < 4:
            unused_links = [lk for lk in self._internal_links
                           if lk.get("href") and lk["href"] not in html]
            needed = 4 - internal_count
            html = self._inject_links_into_paragraphs(html, unused_links[:needed + 1], link_type="internal")
            log.info(f"Post-draft inject: added {min(len(unused_links), needed + 1)} internal links (was {internal_count})")

        # ── R25/R22: External links (need 3+ href="http") ───────────────────
        external_count = len(re.findall(r'href="http', html))
        if external_count < 3:
            unused_ext = [lk for lk in self._external_links
                         if lk.get("href") and lk["href"] not in html]
            needed = 3 - external_count
            html = self._inject_links_into_paragraphs(html, unused_ext[:needed + 1], link_type="external")
            log.info(f"Post-draft inject: added {min(len(unused_ext), needed + 1)} external links (was {external_count})")

        # ── R26: Wikipedia reference (need 1+ wikipedia.org) ─────────────────
        wiki_count = len(re.findall(r"wikipedia\.org", html, re.I))
        if wiki_count < 1 and self._reference_links:
            ref = self._reference_links[0]
            wiki_tag = f' <a href="{ref["url"]}" target="_blank" rel="noopener">{ref["title"]} (Wikipedia)</a>'
            # Find a factual paragraph to append the wiki link
            paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
            injected = False
            for m in paras:
                para_text = re.sub(r"<[^>]+>", "", m.group(2)).lower()
                # Prefer paragraphs with data/authority signals
                if any(s in para_text for s in ["according", "research", "study", "data", "evidence", "%"]):
                    insert_pos = m.end(2)
                    # Word-boundary safety: don't insert mid-word
                    if insert_pos > 0 and html[insert_pos - 1].isalnum():
                        continue  # skip this paragraph, try next
                    html = html[:insert_pos] + wiki_tag + html[insert_pos:]
                    injected = True
                    break
            if not injected and paras:
                # Fallback: add to the 3rd paragraph (or last)
                target = paras[min(2, len(paras) - 1)]
                insert_pos = target.end(2)
                # Word-boundary safety
                if insert_pos > 0 and not html[insert_pos - 1].isalnum():
                    html = html[:insert_pos] + wiki_tag + html[insert_pos:]
            log.info(f"Post-draft inject: added Wikipedia reference link")

        # ── R20: Authority signals — DISABLED ─────────────────────────────────
        # Previously injected vague authority phrases ("According to recent research",
        # "Research shows that", etc.) which produced robotic, fake-authority content.
        # Real authority comes from specific named sources in the draft prompt, not
        # programmatic injection of stock phrases.

        return html

    def _inject_links_into_paragraphs(self, html: str, links: list, link_type: str = "internal") -> str:
        """Inject link tags into appropriate paragraphs in the HTML."""
        if not links:
            return html

        paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
        if not paras:
            return html

        link_idx = 0
        # Spread links across paragraphs, starting from paragraph 2
        target_indices = list(range(1, len(paras), max(1, len(paras) // (len(links) + 1))))

        for para_idx in target_indices:
            if link_idx >= len(links) or para_idx >= len(paras):
                break
            lk = links[link_idx]
            href = lk.get("href", "")
            anchor = lk.get("anchor_text", "")
            if not href or not anchor:
                link_idx += 1
                continue

            if link_type == "external":
                link_tag = f' <a href="{href}" target="_blank" rel="noopener">{anchor}</a>'
            else:
                # Prepend customer domain to relative internal links
                if href.startswith("/") and hasattr(self, "_customer_ctx"):
                    _cust_url = (self._customer_ctx.get("customer_url") or "").rstrip("/")
                    if _cust_url:
                        href = _cust_url + href
                link_tag = f' <a href="{href}">{anchor}</a>'

            # Append link before the closing </p>, with word-boundary safety check
            m = paras[para_idx]
            insert_pos = m.end(2)
            # Safety: ensure we're not inserting mid-word (e.g., "footprin<a>...</a>t")
            # Check the char before insert_pos (if not whitespace/tag, skip this injection)
            if insert_pos > 0:
                char_before = html[insert_pos - 1]
                # Only inject if char_before is whitespace, closing tag '>', or punctuation
                if char_before.isalnum():
                    # Mid-word position detected, skip this link
                    link_idx += 1
                    continue
            html = html[:insert_pos] + link_tag + html[insert_pos:]
            link_idx += 1
            # Re-find paragraphs since positions shifted
            paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))

        return html

    # ─────────────────────────────────────────────────────────────────────────
    # AI WATERMARK SCRUBBER (integrates AIWatermarkScrubber from ruflo_seo_audit)
    # ─────────────────────────────────────────────────────────────────────────

    # Words/phrases that must never appear in finished content. Kept in sync
    # with the FORBIDDEN list shown in S6 / S9 / S12 prompts. The substitutions
    # are conservative: replace with a neutral word the surrounding sentence
    # can absorb without becoming ungrammatical.
    _FORBIDDEN_REPLACEMENTS = (
        # Generic AI vocabulary
        (r"\bdelve(s|d|ing)?\b", "explore"),
        (r"\bmultifaceted\b", "complex"),
        (r"\btapestry\b", "mix"),
        (r"\bnuanced\b", "subtle"),
        (r"\bmyriad\b", "many"),
        (r"\bparadigm\b", "approach"),
        (r"\bfoster(s|ed|ing)?\b", "support"),
        (r"\bholistic\b", "complete"),
        (r"\bpivotal\b", "key"),
        (r"\bstreamline(s|d|ing)?\b", "simplify"),
        (r"\bcutting-edge\b", "modern"),
        (r"\bplethora\b", "range"),
        (r"\bunderscore(s|d|ing)?\b", "highlight"),
        (r"\blet'?s explore\b", "consider"),
        (r"\bwhen it comes to\b", "for"),
        (r"\bin today'?s world\b", "today"),
        (r"\blet'?s dive in\b", ""),
        (r"\blandscape\b", "market"),
        # Templated filler phrases (caught in editorial reviews of cinnamon/spices articles)
        (r"\bthis (?:factor )?directly (?:influences|impacts|affects)[^.]*\.", ""),
        (r"\bthis is especially relevant[^.]*\.", ""),
        (r"\bwhat most (?:people|buyers) (?:miss|overlook)[^.]*?(?:is that|the|because)", "Worth noting:"),
        (r"\bexperienced buyers (?:check|look at|verify) this[^.]*\.", ""),
        (r"\bin practice,?\b", "in real use,"),
        (r"\breal-world performance of [^.]*? (?:hinges on|depends on)", "Real performance depends on"),
        # Fake-authority phrases (root-cause: AI fabricates testing claims with no real data)
        (r"\b(?:in our|after our|based on our) (?:testing|tests|evaluation|evaluations|review|reviews|experience|hands-on (?:testing|review))[^.,]*[.,]?", ""),
        (r"\bwe (?:tested|evaluated|reviewed|put this to the test|put .* to the test)[^.]*?(?:and|to|in)", "Independent reviews"),
        (r"\bour team (?:tested|evaluated|reviewed|analysed|analyzed)[^.]*\.", ""),
        (r"\bhands-on (?:testing|review|evaluation)[^.,]*[.,]?", ""),
        (r"\bafter putting (?:this|these|it|them) to the test[^.,]*[.,]?", ""),
        (r"\bhere'?s what we found after (?:putting this|testing)[^.]*?(?::|—|-)", "Independent assessments show:"),
        # Suspicious unsourced superlatives that triggered the "90% of India's spice harvest" red flag
        (r"\b(?:over|nearly|approximately|roughly|about) ?\d{2,3}\s?%\s+of\s+(?:india'?s|the world'?s|all|global)\b[^.]*?\.", ""),
        # Additional fake-authority + template filler patterns
        (r"\bour team found\b[^.]*\.", ""),
        (r"\bwe'?ve seen it[^.]*\.", ""),
        (r"\bwe found that\b", "Research shows"),
        (r"\bwe discovered\b", "Studies show"),
        (r"\bwe actually sent[^.]*\.", ""),
        (r"\bin our kitchen[^.,;]*[.,;]?", ""),
        (r"\bour team[^.]*?found[^.]*\.", ""),
        (r"\bwe've done[^.]*?test[^.]*\.", ""),
        (r"\bafter looking at countless[^.]*\.", ""),
        (r"\bthis distinction matters[^.]*\.", ""),
        (r"\boutcomes depend heavily on[^.]*\.", ""),
        (r"\bresults will be inconsistent[^.]*\.", ""),
        (r"\bquality becomes measurable[^.]*\.", ""),
        (r"\bconsistently scores well on this[^.]*\.", ""),
        (r"\bexperienced.*?buyers check this[^.]*\.", ""),
        (r"\bfor [^\s]+,? this distinction matters more than most[^.]*\.", ""),
        (r"\bBuyers evaluating\b", "Shoppers checking"),
        (r"\bsuited to diverse professional requirements\b", "useful in various contexts"),
        (r"\bSpecifications alone do not capture all performance factors\b", "Real-world use reveals more than specs alone"),
        # Phase A additions (2026-04-21): kerala-turmeric-style fake-authority patterns
        # observed in production after prior _FORBIDDEN_REPLACEMENTS expansion still leaked through.
        (r"\bOur experience shows that\b", "Evidence shows that"),
        (r"\bOur perspective is that\b", ""),
        (r"\bWe found (it|that)\b", "Research indicates"),
        (r"\bWhen we analyzed\b", "Analysis of"),
        (r"\bWe observed that\b", "Studies show that"),
        # Meta-commentary template sentence (LLMs leak this when over-instructed about "buyer guidance")
        (r"This guide is ideal for [^.]+? but not suited for [^.]+?\.", ""),
        # Phase F additions (2026-04-22): "kitchen spices" article surfaced these residual patterns.
        # Fake-authority remnants the previous regex set missed.
        (r"\bWe believe(?:\s+that)?\b[^.]*\.", ""),
        (r"\bWe noticed\b[^.]*\.", ""),
        (r"\bIn our (?:opinion|view|experience)\b[^.,]*[.,]?", ""),
        (r"\bWe recommend(?:\s+that)?\b", "It's worth"),
        (r"\bWe (?:strongly )?suggest\b", "Consider"),
        # Phase F.2 (2026-04-22): cardamom article revealed more first-person plural leaks.
        (r"\bWe've (?:observed|found|discovered|noticed|seen)\b[^.]*\.", ""),
        (r"\bWe (?:advise|ship|ensure|always|typically|usually)\b[^.]*\.", ""),
        (r"\bWhen we (?:tested|analyzed|compared|examined)\b[^.]*[.,]", ""),
        # SEO template connectors that destroy uniqueness (appear in every AI article)
        (r"\bThe (?:key|trick|catch|secret) is(?: that)?\b", "Notably,"),
        (r"\bThis matters because\b", "Why it matters:"),
        (r"\bAt the end of the day,?\b", ""),
        # Orphaned commercial CTAs (only safe to strip globally — informational vs commercial
        # gating happens later via _strip_commercial_noise()).
        (r"\bbuy authentic [\w\s]+? online\b[^.]*\.", ""),
        (r"\bshop (?:our )?premium [\w\s]+? (?:collection|range|selection)\b[^.]*\.", ""),
    )

    def _strip_forbidden_words(self, html: str) -> str:
        """Programmatically replace banned words/phrases that AI prompts
        instruct the model to avoid but which still leak through. Runs after
        the AIWatermarkScrubber in `_scrub_ai_patterns`.
        Preserves casing for the first letter of each replacement.
        """
        if not html:
            return html
        total = 0
        out = html
        for pattern, replacement in self._FORBIDDEN_REPLACEMENTS:
            def _sub(m, rep=replacement):
                orig = m.group(0)
                if not rep:
                    return ""
                # Match leading capitalisation
                if orig[:1].isupper():
                    return rep[:1].upper() + rep[1:]
                return rep
            new_out, n = re.subn(pattern, _sub, out, flags=re.I)
            if n:
                total += n
                out = new_out
        # Tidy double spaces left by empty replacements
        if total:
            out = re.sub(r"  +", " ", out)
            out = re.sub(r" \s*\.", ".", out)
            log.info(f"Forbidden words strip: {total} replacement(s) applied")
        return out

    def _scrub_ai_patterns(self, html: str) -> str:
        """Run AIWatermarkScrubber on HTML to remove AI fluff patterns (R35),
        then strip forbidden words/phrases that may still slip through prompts."""
        if not html or len(html) < 200:
            return html
        try:
            if _scrubber is not None:
                scrubbed, changes = _scrubber.scrub(html)
                total_removed = changes.get("fluff_removed", 0) + changes.get("starters_replaced", 0)
                if total_removed > 0:
                    log.info(f"AI scrub: removed {changes.get('fluff_removed',0)} fluff, "
                             f"replaced {changes.get('starters_replaced',0)} robotic starters, "
                             f"risk: {changes.get('ai_score_risk','?')}")
            else:
                scrubbed = html
            # Always run forbidden-words pass even when scrubber unavailable
            return self._strip_forbidden_words(scrubbed)
        except Exception as e:
            log.warning(f"AI scrub failed: {e}")
            # Best-effort: still try forbidden-words strip
            try:
                return self._strip_forbidden_words(html)
            except Exception:
                return html

    # ─────────────────────────────────────────────────────────────────────────
    # INTEGRITY SCAN: detect mid-word corruption (trust killer)
    # ─────────────────────────────────────────────────────────────────────────

    def _check_content_integrity(self, html: str) -> str:
        """
        Detect mid-word text corruption that breaks reader trust.
        
        Patterns detected:
        - Mid-word capital injections: "hin That said", "ThNotice that"
        - Broken token fragments: standalone "ges", "hin", "ect" mid-sentence
        
        If corruption detected, adds detailed instructions to editorial_instructions
        for the quality loop to regenerate the affected sections.
        
        This is a HARD BLOCKER for quality — corrupted text destroys E-E-A-T.
        """
        if not html or len(html) < 100:
            return html or ""

        # Strip HTML tags to analyze raw text
        text = re.sub(r"<[^>]+>", " ", html)

        issues = []
        
        # Pattern 1: Mid-word capital injection (aggressive filter for TRUE fragments only)
        # Detects: broken word fragments like "hin That", "ges NotNotice", "ect However"
        # EXCLUDES: legitimate patterns like "the Indian", "to Choose", "a Better"
        # Strategy: fragment must be <4 chars AND not a common word (the, to, a, in, on, at, for, with, by, from)
        mid_word_capitals = re.findall(
            r'\b([a-z]{1,3})\s+([A-Z][a-z]{3,})\s+([a-z]{2,})',
            text
        )
        common_words = {'the', 'to', 'a', 'an', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'of', 'or', 'and', 'as', 'is', 'be', 'it', 'no', 'so', 'if', 'do', 'we', 'us', 'my', 'me', 'he', 'up', 'go'}
        true_fragments = [m for m in mid_word_capitals if m[0] not in common_words]
        
        if true_fragments:
            for match in true_fragments[:3]:  # limit to first 3 examples
                issues.append(f"Mid-word capital injection detected: '{match[0]} {match[1]} {match[2]}'")
        
        # Pattern 2: Broken token fragments
        # Detects standalone fragments like " ges ", " hin ", " ect " mid-sentence
        # (not part of legitimate words like "suggest" or "hint")
        broken_tokens = re.findall(
            r'\s(ges|hin|ect|tion|ing|ment|ness)\s+[a-z]',
            text
        )
        if broken_tokens:
            unique_fragments = list(set(broken_tokens))[:3]
            issues.append(f"Broken word fragments detected: {', '.join(unique_fragments)}")
        
        # Pattern 3: Double-space artifacts (often indicates text splice corruption)
        double_spaces = len(re.findall(r'  +', text))
        if double_spaces > 5:  # some double spaces are normal, but many indicate corruption
            issues.append(f"Excessive double-space artifacts detected ({double_spaces} instances)")

        # Phase A additions (2026-04-21): three more corruption signatures observed in production.
        # 4: Word-fusion (e.g., "Independent reviewsct potency" — missing space between two words).
        #    Heuristic: a token ≥7 chars ending in a 2-char fragment that is itself a real word start.
        word_fusion = re.findall(r'\b([a-z]{4,}(?:ct|sm|nd|rd|th|st|ly))(?=[a-z]{2,}\b)', text)
        # Filter: only flag when the suffix is unusual (avoids real words like "perfect", "contract").
        # Trigger only on the specific observed pattern: word ending in "sct"/"wsct"/etc.
        suspicious_fusions = re.findall(r'\b\w*(?:sct|wsct|esct|rsct|nsct|tsct)\b', text, re.IGNORECASE)
        if suspicious_fusions:
            issues.append(f"Word-fusion corruption detected: {suspicious_fusions[:3]}")

        # 5: Duplicate adjacent words ("support support", "the the"). Auto-fix safe.
        double_words = re.findall(r'\b(\w{3,})\s+\1\b', text, re.IGNORECASE)
        if double_words:
            unique_dups = list({w.lower() for w in double_words})[:3]
            issues.append(f"Duplicate adjacent words: {unique_dups}")

        # 6: Lowercase sentence start after period (e.g., ". this addition").
        #    Heuristic: only flag if there are 3+ instances (one-off may be intentional like "e.g.").
        lowercase_starts = re.findall(r'(?<=[.!?])\s+([a-z][a-z]{3,})', text)
        if len(lowercase_starts) >= 3:
            issues.append(f"Lowercase sentence starts after period ({len(lowercase_starts)} instances): {lowercase_starts[:3]}")

        if issues:
            if not hasattr(self.state, "editorial_instructions"):
                self.state.editorial_instructions = []
            
            log.warning(f"INTEGRITY SCAN FAILED: {len(issues)} corruption pattern(s) detected")
            for issue in issues:
                log.warning(f"  - {issue}")
            
            # Add regeneration instruction for quality loop
            corruption_detail = "; ".join(issues[:3])  # limit to top 3
            self.state.editorial_instructions.append(
                f"CRITICAL: Text corruption detected ({corruption_detail}). "
                "Regenerate ALL affected sections with CLEAN output. "
                "Do NOT patch — rewrite from scratch to eliminate mid-word splices and broken tokens."
            )
        else:
            log.info("Integrity scan: PASSED (no corruption detected)")

        # AUTO-FIX: collapse double spaces and stray punctuation spaces directly on html
        html = re.sub(r'  +', ' ', html)
        html = re.sub(r' +([.,;:!?])', r'\1', html)

        # Phase A auto-fixes (2026-04-21): safe automatic corrections for the new detectors.
        # Fix duplicate adjacent words (operate on visible text only, leave HTML attributes alone).
        # Apply to text content within tags using a conservative regex on the full html.
        html = re.sub(r'\b(\w{3,})\s+\1\b', r'\1', html, flags=re.IGNORECASE)
        # Capitalise the first letter after sentence-ending punctuation when it's clearly a new sentence.
        # Be conservative: only fix when preceded by ". " / "! " / "? " and followed by a real word.
        html = re.sub(
            r'([.!?])(\s+)([a-z])(?=[a-z]{3,})',
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3).upper()}",
            html,
        )

        # ── Phase F additions (2026-04-22): structural deduplication + noise removal ──
        # Driven by the "kitchen spices" article which had:
        #   - "How to choose kitchen spices refers to..." repeated 4× verbatim
        #   - Duplicate H2s ("Whole vs Ground" twice, "Regional Blends" twice)
        #   - Orphaned "buy turmeric powder online" CTAs in informational article
        #   - Incomplete sentences ("India is responsible for...")
        try:
            html = self._dedupe_structure_and_noise(html)
        except Exception as _e:
            log.warning(f"Structural dedupe skipped (non-fatal): {_e}")

        return html

    def _dedupe_structure_and_noise(self, html: str) -> str:
        """Algorithmic (no-LLM) post-processing to fix four common defects.

        1. Duplicate H2 sections — fuzzy-match titles (>=0.85 similarity) and
           drop the SECOND occurrence entirely (heading + its body until next H2).
        2. Repeated keyword definitions — remove every sentence after the first
           that matches "{keyword} (refers to|is|means|describes) ...".
        3. Incomplete trailing sentences — drop sentences ending in dangling
           prepositions / hanging commas (e.g. "India is responsible for.").
        4. Commercial CTA noise — when intent_data.plan.article_type is
           "educational_guide" or "comparison_review", strip orphaned
           "buy/shop/order ... online" sentences.

        All operations are conservative: when in doubt, do nothing.
        """
        from bs4 import BeautifulSoup
        from difflib import SequenceMatcher

        if not html or len(html) < 200:
            return html

        soup = BeautifulSoup(html, "html.parser")
        changed_any = False

        # ── 1. Duplicate H2 dedup (fuzzy match) ──────────────────────────────
        h2s = soup.find_all("h2")
        seen_norm: list[tuple[str, set, object]] = []
        to_remove: list[object] = []
        STOP = {"the", "a", "an", "of", "for", "to", "and", "or", "in", "on", "vs", "versus", "with", "by"}
        for h2 in h2s:
            norm = re.sub(r"[^a-z0-9 ]", "", h2.get_text().lower()).strip()
            if not norm:
                continue
            tokens = {t for t in norm.split() if t and t not in STOP}
            # Stem prefixes (first 4 chars) capture morphological variants:
            # "blends" / "blend" / "blending" all collapse to "blen".
            stems = {t[:4] for t in tokens if len(t) >= 4}
            duplicate_of = None
            for prev_norm, prev_tokens, prev_stems, prev_h2 in seen_norm:
                ratio = SequenceMatcher(None, norm, prev_norm).ratio()
                if tokens and prev_tokens:
                    jacc = len(tokens & prev_tokens) / len(tokens | prev_tokens)
                else:
                    jacc = 0.0
                stem_jacc = (
                    len(stems & prev_stems) / len(stems | prev_stems)
                    if stems and prev_stems else 0.0
                )
                if ratio >= 0.85 or jacc >= 0.6 or stem_jacc >= 0.6:
                    duplicate_of = prev_h2
                    break
            if duplicate_of is not None:
                # Mark this H2 + all following siblings up to the next H2 for removal.
                to_remove.append(h2)
                sib = h2.next_sibling
                while sib is not None:
                    if getattr(sib, "name", None) == "h2":
                        break
                    nxt = sib.next_sibling
                    to_remove.append(sib)
                    sib = nxt
            else:
                seen_norm.append((norm, tokens, stems, h2))
        if to_remove:
            for node in to_remove:
                try:
                    node.extract()
                except Exception:
                    pass
            log.info(f"Dedupe: removed {sum(1 for n in to_remove if getattr(n, 'name', None) == 'h2')} duplicate H2 section(s)")
            changed_any = True

        # ── 2. Repeated keyword definition removal ───────────────────────────
        if self.keyword:
            kw_re = re.escape(self.keyword)
            def_pattern = re.compile(
                rf"\b{kw_re}\s+(?:refers to|is\s+(?:a|an|the)|means|describes)\b[^.!?]*[.!?]",
                re.IGNORECASE,
            )
            seen_first = [False]

            def _strip_repeats(text: str) -> str:
                def _sub(m):
                    if not seen_first[0]:
                        seen_first[0] = True
                        return m.group(0)
                    return ""  # drop subsequent definitions
                return def_pattern.sub(_sub, text)

            for p in soup.find_all(["p", "li"]):
                txt = p.get_text()
                new = _strip_repeats(txt)
                if new != txt:
                    # Replace via direct string assignment (preserves tag wrapper).
                    p.clear()
                    p.append(new.strip())
                    changed_any = True

        # ── 3. Incomplete trailing sentences ─────────────────────────────────
        # Catches fragments ending with prepositions/articles WITH punctuation
        DANGLING_ENDINGS = re.compile(
            r"\b[A-Z][^.!?]*?\b(?:for|of|to|with|by|from|on|in|and|or|but|the|a|an|is|are|was|were|that|which|because|when|while|if|until)\s*[.,]\s*$"
        )
        # Catches fragments ending with prepositions WITHOUT punctuation ("accounting for" at paragraph end)
        HANGING_PREPOSITIONS = re.compile(
            r"\b(?:accounting for|according to|based on|leading to|resulting in|such as|including|excluding|ranging from)\s*$",
            re.IGNORECASE
        )
        for p in soup.find_all(["p", "li"]):
            txt = p.get_text().strip()
            if not txt or len(txt.split()) < 4:
                continue
            # Check if entire paragraph ends with hanging preposition (no sentence split needed)
            if HANGING_PREPOSITIONS.search(txt):
                # Drop the entire incomplete clause at the end
                txt_fixed = HANGING_PREPOSITIONS.sub("", txt).strip()
                if txt_fixed and len(txt_fixed.split()) >= 4:
                    p.clear()
                    p.append(txt_fixed)
                    changed_any = True
                else:
                    p.decompose()  # Paragraph became stub
                continue
            # Split into sentences and check each
            sentences = re.split(r"(?<=[.!?])\s+", txt)
            kept = [s for s in sentences if not DANGLING_ENDINGS.search(s)]
            if len(kept) != len(sentences) and kept:
                new = " ".join(kept)
                p.clear()
                p.append(new)
                changed_any = True

        # ── 4. Commercial CTA stripping for non-commercial articles ──────────
        article_type = ""
        try:
            article_type = (self._intent_data or {}).get("plan", {}).get("article_type", "") or ""
        except Exception:
            article_type = ""
        if article_type in ("educational_guide", "comparison_review"):
            commercial_patterns = [
                re.compile(r"\b(?:buy|shop|order|purchase)\s+(?:authentic|premium|quality|fresh|organic|the\s+best)?\s*[\w\s]{0,40}?\s+online\b[^.!?]*[.!?]", re.IGNORECASE),
                re.compile(r"\bexplore\s+(?:our|the)\s+(?:range|collection|selection|catalog|full range)\b[^.!?]*[.!?]", re.IGNORECASE),
                re.compile(r"\bcontact\s+(?:our\s+)?(?:team|sales|us)\s+(?:for|to|at)\b[^.!?]*[.!?]", re.IGNORECASE),
                re.compile(r"\bvisit\s+(?:our|the)\s+(?:store|website|shop)\b[^.!?]*[.!?]", re.IGNORECASE),
                re.compile(r"\b(?:discover|learn more|shop now|find out|check out)\s+(?:about|on|at)?[^.!?]*[.!?]", re.IGNORECASE),
                re.compile(r"\b(?:compare options|secure your supply|don't miss out)\b[^.!?]*[.!?]", re.IGNORECASE),
            ]
            # Also strip inline website URLs and CTAs embedded as links
            url_patterns = [
                re.compile(r"\b[a-z0-9-]+\.com/[^\s<>]*", re.IGNORECASE),  # example.com/path
                re.compile(r"\bat\s+[a-z0-9-]+\.com\b[^.!?]*[.!?]", re.IGNORECASE),  # "at example.com"
            ]
            stripped_count = 0
            for p in soup.find_all(["p", "li"]):
                txt = p.get_text()
                new = txt
                for pat in commercial_patterns:
                    new = pat.sub("", new)
                for pat in url_patterns:
                    new = pat.sub("", new)
                if new != txt:
                    new = re.sub(r"\s{2,}", " ", new).strip()
                    if not new or len(new.split()) < 4:
                        # Paragraph became empty or stub — drop it entirely.
                        p.decompose()
                    else:
                        p.clear()
                        p.append(new)
                    stripped_count += 1
            if stripped_count:
                log.info(f"Dedupe: stripped commercial noise from {stripped_count} block(s) ({article_type})")
                changed_any = True

        if changed_any:
            return str(soup)
        return html

    # ──────────────────────────────────────────────────────────────────────
    # PHASE B: per-section scoring (foundation for Phase C targeted regen)
    # ──────────────────────────────────────────────────────────────────────

    def _score_all_sections(self, html: str) -> Optional[Dict]:
        """Score every H2 section across trust/clarity/integrity/conversion/uniqueness.

        Stores the result on `self.state.section_scores` and returns the summary
        dict (see engines.quality.section_scorer.summarise_scores). Read-only by
        design — Phase C will use this output to drive targeted regeneration.

        Failures are logged but never raise: this is observability, not a gate.
        """
        if not html:
            return None
        try:
            from engines.section_scorer import score_all_sections, summarise_scores
            scores = score_all_sections(html)
            summary = summarise_scores(scores)
            self.state.section_scores = summary
            weak_count = len(summary.get("weak_sections", []))
            avg = summary.get("average_weighted", 0.0)
            log.info(
                f"Section scoring: {summary.get('section_count', 0)} sections | "
                f"avg weighted {avg}/100 | {weak_count} flagged for regen"
            )
            for weak in summary.get("weak_sections", [])[:5]:
                log.info(
                    f"  weak: '{weak['h2'][:60]}' → {weak['weighted_total']}/100 | "
                    f"issues: {weak.get('issues', [])[:3]}"
                )
            return summary
        except Exception as e:
            log.warning(f"Section scoring skipped (non-fatal): {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────
    # PHASE C: targeted section regeneration (the real "same issues repeating" fix)
    # ──────────────────────────────────────────────────────────────────────
    # Hard cost caps (defence-in-depth):
    #   - Max 2 sections regenerated per article
    #   - Max 2 LLM attempts per section
    #   - Total budget: +4 LLM calls per article
    #   - Skip silently on any failure (never blocks pipeline)

    _MAX_REGEN_SECTIONS = 2
    _MAX_REGEN_ATTEMPTS = 2

    async def _regenerate_section_html(self, section_html: str, h2_title: str,
                                       issues: List[str]) -> str:
        """Send a targeted "improve only this section" prompt and return new HTML.

        Returns empty string on failure — caller must keep the original section.
        """
        # Strip the outer H2 so the model focuses on the body. We will re-attach.
        body_html = re.sub(r"<h2[^>]*>.*?</h2>\s*", "", section_html, count=1, flags=re.I | re.DOTALL)
        # Concise issue summary the model can act on.
        issue_lines = "\n".join(f"- {i}" for i in issues[:6])

        prompt = (
            f'You are improving ONE section of an SEO article about "{self.keyword}".\n'
            f'Section heading: "{h2_title}"\n\n'
            f"Specific issues detected by automated quality scoring:\n{issue_lines}\n\n"
            "REWRITE THIS SECTION to fix every listed issue. Hard rules:\n"
            "1. Keep the same length (±10%) and the same factual claims/data points.\n"
            "2. Remove ALL fake first-person authority ('we observed', 'our experience', 'we found', 'when we analyzed').\n"
            "   Replace with third-party attribution or direct fact statements.\n"
            "3. Remove ALL generic SEO template phrases.\n"
            "4. Add at least one concrete imperative or recommendation\n"
            "   (e.g. 'Choose X when Y', 'Look for Z certification', 'Avoid A if B').\n"
            "5. Output ONLY the new <p>, <ul>, <ol>, <table> body HTML for this section.\n"
            "   Do NOT include the <h2> heading. Do NOT include other sections.\n"
            "   Do NOT use markdown. Do NOT add code fences.\n\n"
            "ORIGINAL SECTION BODY:\n"
            f"{body_html}"
        )
        try:
            new_html = await self._call_ai_raw_with_chain(
                self.routing.draft, prompt, temperature=0.4, max_tokens=2000,
            )
        except Exception as e:
            log.warning(f"Targeted regen call failed for '{h2_title[:40]}': {e}")
            return ""
        if not new_html or len(new_html.strip()) < 80:
            return ""
        # Clean any markdown fences the model may slip in.
        new_html = re.sub(r"^```(?:html)?\s*|\s*```$", "", new_html.strip(), flags=re.I | re.MULTILINE)
        return new_html

    async def _run_targeted_regen(self, html: str) -> str:
        """Iterate weak sections, regenerate each up to MAX_REGEN_ATTEMPTS times.

        Returns the (possibly modified) full article HTML. Always returns a
        valid string — falls back to the input if anything goes wrong.
        """
        if not getattr(self.routing, "targeted_regen", False):
            return html
        summary = getattr(self.state, "section_scores", None) or {}
        weak = summary.get("weak_sections", []) if isinstance(summary, dict) else []
        if not weak:
            return html

        # Lazy imports to keep this method self-contained.
        try:
            from engines.section_scorer import (
                split_sections, score_section, score_all_sections, summarise_scores,
            )
        except Exception as e:
            log.warning(f"Targeted regen aborted (scorer import failed): {e}")
            return html

        # Cap how many sections we touch this article.
        targets = weak[: self._MAX_REGEN_SECTIONS]
        target_h2s = {w["h2"] for w in targets}
        log.info(
            f"Targeted regen: attempting {len(target_h2s)} weak section(s): "
            f"{[w['h2'][:50] for w in targets]}"
        )
        self._add_log("info", f"Phase C: regenerating {len(target_h2s)} weak section(s)", 6)

        sections = split_sections(html)
        rebuilt: List[str] = []
        regen_count = 0
        for h2_title, section_html in sections:
            if h2_title not in target_h2s or h2_title == "__intro__":
                rebuilt.append(section_html)
                continue
            # Look up issues for this section.
            issues_for_section: List[str] = []
            for w in targets:
                if w["h2"] == h2_title:
                    issues_for_section = w.get("issues", [])
                    break
            best_html = section_html
            best_score = score_section(section_html, h2_title)
            for attempt in range(1, self._MAX_REGEN_ATTEMPTS + 1):
                new_body = await self._regenerate_section_html(section_html, h2_title, issues_for_section)
                if not new_body:
                    log.info(f"  regen attempt {attempt} for '{h2_title[:40]}': empty response, skipping")
                    continue
                # Re-attach the H2 heading.
                h2_match = re.search(r"<h2[^>]*>.*?</h2>", section_html, re.I | re.DOTALL)
                heading = h2_match.group(0) if h2_match else f"<h2>{h2_title}</h2>"
                candidate = heading + "\n" + new_body
                # Run the same integrity scan + scorer on the candidate.
                candidate = self._check_content_integrity(candidate)
                candidate = self._strip_forbidden_words(candidate)
                cand_score = score_section(candidate, h2_title)
                log.info(
                    f"  regen attempt {attempt} for '{h2_title[:40]}': "
                    f"{best_score.weighted_total} → {cand_score.weighted_total}"
                )
                if cand_score.weighted_total > best_score.weighted_total:
                    best_html = candidate
                    best_score = cand_score
                # Stop early if the candidate is already healthy.
                if not best_score.needs_regeneration():
                    break
            if best_html != section_html:
                regen_count += 1
            rebuilt.append(best_html)

        # If we never had an __intro__ but split returned one as the first item,
        # split_sections already preserved it correctly, so simple join is safe.
        new_html = "\n".join(rebuilt)
        # Refresh the section_scores summary to reflect the rewritten sections.
        try:
            self.state.section_scores = summarise_scores(score_all_sections(new_html))
            log.info(
                f"Targeted regen complete: {regen_count}/{len(target_h2s)} sections improved | "
                f"new avg {self.state.section_scores.get('average_weighted', 0)}/100 | "
                f"{len(self.state.section_scores.get('weak_sections', []))} still flagged"
            )
        except Exception:
            pass
        return new_html

    # ─────────────────────────────────────────────────────────────────────────
    # READABILITY ENFORCER (R18: Adaptive Flesch target via algorithmic + AI)
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_content_type(self) -> tuple:
        """Detect content type and return (label, target_low, target_high).

        Uses GENERIC pattern signals that work for ANY business/keyword \u2014
        no hardcoded product, ingredient, or industry vocabulary.
        Signals come from: customer intent, generic technical/commercial/info
        markers, scientific-name patterns (Genus species), and chemical/unit
        patterns. Any business-specific industry terms must be fed in via
        `self.intent` or the routing config, not hardcoded here.
        """
        kw = (self.keyword or "").lower()
        title = (getattr(self.state, "title", "") or "").lower()
        intent = (getattr(self, "intent", "") or "").lower()
        combined = f"{kw} {title}"

        # Generic technical signals (no industry-specific words)
        TECHNICAL_MARKERS = (
            "scientific", "research", "study", "studies", "compound", "chemical",
            "molecular", "anatomy", "biochemistry", "pharmac", "clinical",
            "mechanism", "synthesis", "analysis", "spectrum", "specification",
            "technical", "engineering", "algorithm", "protocol",
        )
        # Scientific binomial pattern: "Genus species" (two capitalised-ish words)
        # or chemical formula / measurement units in title/keyword.
        scientific_binomial = bool(re.search(r"\b[A-Z][a-z]{2,}\s+[a-z]{3,}\b", getattr(self.state, "title", "") or ""))
        chemical_pattern = bool(re.search(r"\b(?:[A-Z][a-z]?\d*){2,}\b|\b\d+\s?(?:mg|ml|kg|°c|ppm|kj|kcal)\b", combined))
        is_technical = (
            any(t in combined for t in TECHNICAL_MARKERS)
            or scientific_binomial or chemical_pattern
            or intent in ("technical", "academic", "research")
        )

        COMMERCIAL_MARKERS = (
            "buy", "shop", "price", "pricing", "cheap", "best", "top", "review",
            "vs ", " vs", "compare", "discount", "deal", "online", "order",
            "purchase", "near me", "wholesale", "bulk",
        )
        is_commercial = (
            any(t in kw for t in COMMERCIAL_MARKERS)
            or bool(re.search(r"[$\u20ac\u00a3\u20b9]\s?\d", combined))
            or intent in ("transactional", "commercial")
        )

        INFO_MARKERS = (
            "what is", "what are", "how to", "how do", "why ", "when ", "where ",
            "guide", "tutorial", "benefits", "uses", "history", "origin",
            "explained", "tips", "ideas",
        )
        is_informational = (
            any(t in combined for t in INFO_MARKERS) or intent == "informational"
        )

        if is_technical:
            return ("technical", 30, 50)
        if is_commercial and not is_informational:
            return ("commercial", 55, 75)
        return ("informational", 40, 60)

    async def _enforce_readability(self, html: str) -> str:
        """
        Guarantee adaptive Flesch target via post-processing.
        - Detect content type → pick target range
        - Split long sentences (>22 words)
        - Replace complex words
        - Rank paragraphs by complexity, AI-simplify worst 20
        - Retry up to 2 passes
        """
        if not html or len(html) < 200 or not HAS_TEXTSTAT:
            return html

        ctype, target_low, target_high = self._detect_content_type()

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        try:
            current_flesch = textstat.flesch_reading_ease(text)
        except Exception as e:
            log.warning(f"Flesch calculation failed: {e}")
            return html

        if target_low <= current_flesch <= target_high:
            log.info(f"R18 readability ({ctype}): Flesch {current_flesch:.1f} in target {target_low}-{target_high} — skip")
            return html

        log.info(f"R18 readability enforcer ({ctype}): Flesch {current_flesch:.1f} → target {target_low}-{target_high}")

        try:
            # ── Phase 1: Algorithmic fixes ───────────────────────────────────
            html = self._split_long_sentences_in_html(html)
            html = self._enforce_paragraph_density(html)
            html = self._simplify_vocabulary(html)
        except Exception as e:
            log.warning(f"R18 algorithmic fixes failed: {e} — skipping algo phase")

        # Re-measure
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        try:
            flesch_after_algo = textstat.flesch_reading_ease(text)
        except Exception:
            flesch_after_algo = current_flesch

        log.info(f"R18 readability: after algo fixes Flesch={flesch_after_algo:.1f}")

        # ── Phase 2: AI simplification with retry loop (max 2 passes) ─────
        if flesch_after_algo < target_low or flesch_after_algo > target_high + 10:
            for pass_num in range(1, 3):
                try:
                    html = await self._ai_simplify_text(html, flesch_after_algo, target_low, target_high)
                except Exception as e:
                    log.warning(f"R18 AI simplify pass {pass_num} failed: {e}")
                    break
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                try:
                    flesch_after_algo = textstat.flesch_reading_ease(text)
                except Exception:
                    break
                log.info(f"R18 readability AI pass {pass_num}: Flesch={flesch_after_algo:.1f}")
                if target_low <= flesch_after_algo <= target_high:
                    break

        log.info(f"R18 readability enforcer: {current_flesch:.1f} → {flesch_after_algo:.1f} (target {target_low}-{target_high})")
        return html

    def _enforce_paragraph_density(self, html: str) -> str:
        """Split paragraphs with >4 sentences into 2 paragraphs for breathability."""
        soup = BeautifulSoup(html, "html.parser")
        for p in list(soup.find_all("p")):
            if not p.parent:
                continue
            text = p.get_text()
            sentences = re.split(r'(?<=[.!?])\s+', text)
            sentences = [s for s in sentences if s.strip()]
            if len(sentences) > 4:
                mid = len(sentences) // 2
                p1_text = " ".join(sentences[:mid])
                p2_text = " ".join(sentences[mid:])
                try:
                    p.string = p1_text
                    new_p = soup.new_tag("p")
                    new_p.string = p2_text
                    p.insert_after(new_p)
                except (ValueError, AttributeError):
                    continue
        return str(soup)

    def _split_long_sentences_in_html(self, html: str) -> str:
        """Split sentences longer than 22 words — pure regex, never touches child tags."""
        def _split_para(m: re.Match) -> str:
            open_tag = m.group(1)
            inner = m.group(2)
            close_tag = m.group(3)
            # Never modify paragraphs that contain HTML child tags (links, bold, etc.)
            if re.search(r'<[a-zA-Z]', inner):
                return m.group(0)
            words = inner.split()
            if len(words) <= 22:
                return m.group(0)
            # Find split point near middle at a conjunction
            mid = len(words) // 2
            split_at = mid
            for j in range(max(8, mid - 5), min(len(words) - 5, mid + 5)):
                if words[j].lower() in ("and", "but", "or", "so", "yet", "because", "while", "when", "which", "where"):
                    split_at = j
                    break
            part1 = " ".join(words[:split_at]).rstrip(",.") + "."
            part2 = " ".join(words[split_at:])
            if part2 and part2[0].islower():
                part2 = part2[0].upper() + part2[1:]
            return f"{open_tag}{part1}{close_tag}\n{open_tag}{part2}{close_tag}"

        return re.sub(r'(<p[^>]*>)(.*?)(</p>)', _split_para, html, flags=re.I | re.DOTALL)

    def _simplify_vocabulary(self, html: str) -> str:
        """Replace complex words with simpler alternatives."""
        # Common complex → simple word mappings for readability
        replacements = {
            r'\butilize\b': 'use',
            r'\butilization\b': 'use',
            r'\bfacilitate\b': 'help',
            r'\bdemonstrate\b': 'show',
            r'\bdemonstrates\b': 'shows',
            r'\badditionally\b': 'also',
            r'\bnevertheless\b': 'but',
            r'\bnonetheless\b': 'still',
            r'\bconsequently\b': 'so',
            r'\bfurthermore\b': 'also',
            r'\bmoreover\b': 'also',
            r'\bsubsequently\b': 'then',
            r'\bapproximately\b': 'about',
            r'\bmodification\b': 'change',
            r'\bmodifications\b': 'changes',
            r'\bimplementation\b': 'use',
            r'\bimplement\b': 'use',
            r'\bmethodology\b': 'method',
            r'\bterminate\b': 'end',
            r'\binitiate\b': 'start',
            r'\bcommence\b': 'start',
            r'\bpurchase\b': 'buy',
            r'\bsufficient\b': 'enough',
            r'\bnumerous\b': 'many',
            r'\bprioritize\b': 'focus on',
            r'\bencompasses\b': 'covers',
            r'\bencompass\b': 'cover',
            r'\bobtain\b': 'get',
            r'\brequire\b': 'need',
            r'\brequires\b': 'needs',
            r'\bregarding\b': 'about',
            r'\bconcerning\b': 'about',
            r'\bin order to\b': 'to',
            r'\bdue to the fact that\b': 'because',
            r'\bin the event that\b': 'if',
            r'\ba majority of\b': 'most',
            r'\bat this point in time\b': 'now',
            r'\bin the near future\b': 'soon',
            r'\bcontribute to\b': 'help',
            r'\bestablish\b': 'set up',
            r'\bdetermine\b': 'find',
            r'\bdemonstrates that\b': 'shows that',
            r'\bcomprehensive\b': 'full',
            r'\bsignificantly\b': 'greatly',
            r'\boptimal\b': 'best',
            r'\bleverage\b': 'use',
        }
        
        for pattern, replacement in replacements.items():
            html = re.sub(pattern, replacement, html, flags=re.IGNORECASE)
        
        return html

    async def _ai_simplify_text(self, html: str, current_flesch: float,
                                 target_low: int = 40, target_high: int = 60) -> str:
        """Use AI to simplify the WORST paragraphs (ranked by complexity)."""
        if not HAS_TEXTSTAT:
            return html

        soup = BeautifulSoup(html, "html.parser")
        paragraphs = soup.find_all("p")

        # Rank paragraphs by complexity (lowest Flesch = most complex first)
        scored = []
        for p in paragraphs:
            text = p.get_text()
            if len(text.split()) < 25:
                continue
            try:
                pf = textstat.flesch_reading_ease(text)
            except Exception:
                pf = 50.0
            # Only target paragraphs below target range
            if pf < target_low:
                scored.append((pf, p, text))

        # Sort: most complex (lowest Flesch) first, take worst 20
        scored.sort(key=lambda x: x[0])
        targets = scored[:20]

        if not targets:
            return html

        log.info(f"R18 AI simplify: targeting {len(targets)} most-complex paragraphs (Flesch {targets[0][0]:.1f}-{targets[-1][0]:.1f})")

        modified = False
        for pf, p, text in targets:
            prompt = f"""Rewrite this paragraph to be MUCH easier to read.

TARGET: Flesch Reading Ease {target_low}-{target_high} (currently {pf:.0f})

STRICT RULES:
- Maximum sentence length: 18 words
- Average sentence length: 12-15 words
- Use simple, everyday words (replace jargon)
- Use active voice (>85% of sentences)
- Break compound sentences with "and/but/which/that" into 2 sentences
- Replace "utilize→use", "facilitate→help", "demonstrate→show", "additionally→also"
- Keep ALL facts, numbers, and meaning identical
- Keep proper nouns (place/product/brand names) as-is

PARAGRAPH:
{text}

Return JSON of the form: {{"text": "<simplified paragraph here>"}}"""

            try:
                result = await self._call_ai_with_chain(
                    self.routing.draft,
                    prompt,
                    temperature=0.3,
                    max_tokens=1400,
                )
                # Accept the simplified output under any common key the model may pick
                simplified = ""
                if result and isinstance(result, dict):
                    for _key in ("text", "answer", "simplified", "simplified_paragraph",
                                 "rewritten_paragraph", "rewrite", "paragraph", "output"):
                        _v = result.get(_key)
                        if isinstance(_v, str) and len(_v.strip()) > 50:
                            simplified = _v.strip()
                            break
                if simplified:
                    # Strip wrapping quotes/markdown
                    simplified = re.sub(r'^["\'`]+|["\'`]+$', '', simplified).strip()
                    simplified = re.sub(r'^(?:Here\'?s|Here is)[^:]*:\s*', '', simplified, flags=re.I).strip()
                    if len(simplified) > 50 and len(simplified.split()) > 10:
                        p.string = simplified
                        modified = True
            except Exception as e:
                log.warning(f"AI simplification failed for paragraph: {e}")
                continue

        return str(soup) if modified else html

    # ─────────────────────────────────────────────────────────────────────────
    # CONTENT INTELLIGENCE POST-PROCESSING (R34-R46 programmatic fixes)
    # ─────────────────────────────────────────────────────────────────────────

    def _intelligence_post_process(self, html: str) -> str:
        """
        Programmatic post-processing for Content Intelligence rules R34-R46.
        Runs after draft generation and AI scrub. Handles:
        - R34: Keyword density normalization (replace excess with variations)
        - R36: Experience signal injection
        - R40: Buyer intent section detection/injection
        - R41: Storytelling marker injection
        - R42: Visual break injection
        - R43: Mid-content CTA injection
        - R45: Unique angle signal injection
        """
        if not html or len(html) < 200:
            return html

        # ── Normalize: wrap bare text blocks in <p> tags ─────────────────────
        _block_re = re.compile(
            r"(</?\s*(?:h[1-6]|p|div|ul|ol|li|nav|table|tr|td|th|thead|tbody|"
            r"blockquote|pre|hr|section|article|aside|figure|figcaption|details|summary)[^>]*>)",
            re.I,
        )
        parts = _block_re.split(html)
        rebuilt = []
        for part in parts:
            stripped = part.strip()
            if not stripped:
                rebuilt.append(part)
            elif _block_re.match(stripped):
                rebuilt.append(part)
            elif len(stripped) > 60 and not stripped.startswith("<"):
                rebuilt.append(f"<p>{stripped}</p>")
            else:
                rebuilt.append(part)
        html = "".join(rebuilt)

        text = re.sub(r"<[^>]+>", " ", html)
        text_lower = text.lower()
        words = text.split()
        word_count = len(words)
        kw_lower = (self.keyword or "").lower()

        # ── R34: Keyword density normalization ───────────────────────────────
        if kw_lower and word_count > 100:
            kw_count = text_lower.count(kw_lower)
            kw_density = (kw_count / word_count) * 100
            log.info(f"R34 density check: kw='{kw_lower}' count={kw_count} words={word_count} density={kw_density:.2f}%")
            if kw_density > 2.5 and kw_count > 5:
                # Generate grammatically correct semantic variations
                kw_words = kw_lower.split()
                variations = []
                if len(kw_words) >= 3:
                    # Multi-word (3+): drop first modifier, reorder, or paraphrase
                    variations = [
                        " ".join(kw_words[1:]),                    # drop first word: "best black pepper" → "black pepper"
                        " ".join(kw_words[:-1]) + " options",     # "best black" + "options"
                        "this " + kw_words[-1],                    # "this pepper"
                        "these " + " ".join(kw_words[-2:]),        # "these black pepper"
                        "such " + " ".join(kw_words[1:]),          # "such black pepper"
                    ]
                elif len(kw_words) == 2:
                    variations = [
                        kw_words[-1] + " options",                 # "pepper options"
                        "this " + kw_words[-1],                    # "this pepper"
                        "such " + kw_lower,                        # "such black pepper"
                        "these " + kw_words[-1] + " products",    # "these pepper products"
                        kw_words[0] + " " + kw_words[-1] + " options",  # "black pepper options"
                    ]
                elif len(kw_words) == 1:
                    variations = [
                        f"this {kw_lower}",
                        f"such {kw_lower}",
                        f"these {kw_lower} products",
                        f"the {kw_lower}",
                    ]

                # Replace excess keyword occurrences (keep every 2nd, replace rest)
                target_density = 1.5
                target_count = max(5, int(word_count * target_density / 100))
                excess = kw_count - target_count

                if excess > 0 and variations:
                    # Replace from the middle of the article outward (preserve first/last mentions)
                    positions = []
                    start = 0
                    kw_escaped = re.escape(self.keyword)
                    for m in re.finditer(kw_escaped, html, re.I):
                        positions.append(m)

                    if len(positions) > target_count:
                        # Keep first 3 and last 2, replace from middle
                        replaceable = positions[3:-2] if len(positions) > 5 else positions[2:-1]
                        # Cap replacements at 30% of excess to avoid heavy-handed
                        # rewrites that change meaning. Better to leave a slight
                        # over-density than mangle the prose.
                        replace_count = min(excess, len(replaceable), max(1, int(excess * 0.3)))
                        # Replace from end to start to preserve positions
                        applied = 0
                        skipped = 0
                        for i, m in enumerate(reversed(replaceable[:replace_count])):
                            var = variations[i % len(variations)]
                            # Look at the words immediately before/after the match
                            before_ctx = html[max(0, m.start() - 20):m.start()].lower()
                            after_ctx = html[m.end():m.end() + 20].lower()
                            # Skip if replacement would create double-article ("the these", "these these"),
                            # double-determiner, or follows an existing determiner badly.
                            first_word = var.split()[0].lower() if var.split() else ""
                            tail = re.search(r"\b(the|a|an|these|those|this|that|our|your|premium|quality|authentic)\s*$", before_ctx)
                            if tail and first_word in {"the", "a", "an", "these", "those", "this", "that", "premium", "quality", "authentic"}:
                                skipped += 1
                                continue
                            # Also skip if directly preceded by a comma+space and the variation starts capitalised
                            # mid-sentence (rare but messy)
                            html = html[:m.start()] + var + html[m.end():]
                            applied += 1

                        new_density = text_lower.count(kw_lower) / word_count * 100
                        log.info(
                            f"R34 density fix: {kw_density:.1f}% -> replaced {applied} instance(s) "
                            f"(skipped {skipped} unsafe), target ~{target_density}%"
                        )

            # R34 density floor: REMOVED — injecting template phrases like
            # "This factor directly influences {kw} performance" is pure filler
            # that damages content uniqueness.  The prompt already targets 1.0-1.5%
            # density, so the floor injector is unnecessary.

        # ── R17: Wall-of-text paragraph splitting ────────────────────────────
        paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
        split_count = 0
        for m in reversed(paras):  # Reverse to preserve positions
            para_inner = m.group(2)
            para_text = re.sub(r"<[^>]+>", "", para_inner)
            if len(para_text.split()) > 100:
                # Split at the sentence boundary closest to the middle
                sents = re.split(r'(?<=[.!?])\s+', para_text)
                if len(sents) >= 3:
                    mid = len(sents) // 2
                    first_half = ". ".join(s.rstrip(".") for s in sents[:mid]) + "."
                    second_half = ". ".join(s.rstrip(".") for s in sents[mid:]) + "."
                    new_html = f"{m.group(1)}{first_half}{m.group(3)}\n{m.group(1)}{second_half}{m.group(3)}"
                    html = html[:m.start()] + new_html + html[m.end():]
                    split_count += 1
        if split_count > 0:
            log.info(f"R17 wall-of-text fix: split {split_count} long paragraph(s)")

        # ── R36: Experience signal injection — DISABLED ─────────────────────
        # Previously injected fake first-person experience phrases ("In our experience",
        # "We found that", "After trying multiple options", etc.) which produced
        # inauthentic content. Real expertise comes from specific details in the
        # draft prompt, not stock phrases programmatically injected.

        # ── R42: Visual break injection ──────────────────────────────────────
        visual_patterns = [r"<blockquote", r'class="[^"]*(?:tip|callout|key-takeaway|pro-tip)']
        visual_count = sum(len(re.findall(p, html, re.I)) for p in visual_patterns)
        if visual_count < 2:
            # Inject tip/takeaway boxes after every 3rd H2 section.
            # IMPORTANT: tip text MUST be keyword-specific. Generic phrases like
            # "Quality and authenticity are the most important factors" appear
            # identically across hundreds of articles -> fails uniqueness rules
            # and gets caught by the pre-save fallback-phrase scanner.
            h2_positions = list(re.finditer(r"<h2[^>]*>.*?</h2>", html, re.I | re.DOTALL))
            inserted = 0
            kw_t = self.keyword.strip()
            kw_lower = kw_t.lower()
            intent = (getattr(self, "intent", "") or "").lower()
            # Pull a concrete theme + fact from research if available
            try:
                research = (self.state.steps[0].details or {}).get("analysis", {}) if self.state.steps else {}
                themes = research.get("themes", []) or []
                facts = research.get("key_facts", []) or []
            except Exception:
                themes, facts = [], []
            theme_hint = (themes[0] if themes else "").strip().rstrip(".")
            fact_hint = (facts[0] if facts else "").strip().rstrip(".")

            takeaway_text = (
                f"When evaluating {kw_lower}, focus on {theme_hint.lower()} — it's the differentiator most buyers overlook."
                if theme_hint
                else f"When evaluating {kw_lower}, prioritise the criteria that match your specific use case rather than headline claims."
            )
            if "buy" in intent or "shop" in intent or "supplier" in intent:
                pro_tip_text = (
                    f"Compare at least three suppliers of {kw_lower} on certification, lead time and per-unit price before committing."
                )
            elif "review" in intent or "best" in intent or "top" in intent:
                pro_tip_text = (
                    f"Shortlist {kw_lower} options against your top two requirements first; then test the rest only if budget allows."
                )
            else:
                pro_tip_text = (
                    f"Document your specific requirement for {kw_lower} before researching — it cuts decision time roughly in half."
                )
            if fact_hint and len(fact_hint) < 180:
                pro_tip_text = f"{pro_tip_text} ({fact_hint})"

            tips = [
                f'<div class="key-takeaway"><p><strong>Key Takeaway:</strong> {takeaway_text}</p></div>',
                f'<div class="pro-tip"><p><strong>Pro Tip:</strong> {pro_tip_text}</p></div>',
            ]
            for idx, h2m in enumerate(h2_positions):
                if inserted >= 2:
                    break
                if idx in (2, 4) and idx < len(h2_positions):
                    # Insert before this H2
                    insert_pos = h2m.start()
                    tip = tips[inserted % len(tips)]
                    html = html[:insert_pos] + "\n" + tip + "\n" + html[insert_pos:]
                    inserted += 1
                    # Recalculate positions after insertion
                    h2_positions = list(re.finditer(r"<h2[^>]*>.*?</h2>", html, re.I | re.DOTALL))
            if inserted > 0:
                log.info(f"R42 visual breaks: inserted {inserted} keyword-specific tip box(es)")

        # R43 mid-CTA: REMOVED — fabricates shop URLs that may not exist,
        # template "Ready to source" phrasing is the same across all articles.

        # R45 angle signal: REMOVED — stock phrases like "What most people miss is that"
        # damage paragraph flow and are identical across articles.  S6 prompt already
        # includes S1 angles + gaps; the AI should produce unique angles natively.

        # R27+R70 definition prepend: REMOVED — blindly prepending "{kw} refers to"
        # is grammatically wrong for many keywords and ruins authored openings.
        # The S6 intro prompt already instructs "include keyword in first sentence".

        # ── R19: Sentence opener variety — replace repetitive AI starters ────
        ai_starter_replacements = {
            "this is ": ["Here, ", "Notice that ", "Consider how ", "Importantly, ", "You'll find "],
            "there are ": ["You'll find ", "Several ", "Multiple ", "A range of ", "Numerous "],
            "it is ": ["This proves ", "Clearly, ", "Without question, ", "Notably, ", "Evidently, "],
            "in this ": ["Throughout this ", "Across this ", "Within this ", "Here in this ", "Along this "],
        }
        for starter, replacements in ai_starter_replacements.items():
            # Find all sentence-starting occurrences (after . ! ? or paragraph start)
            pattern = re.compile(r'((?:^|[.!?]\s+|<p[^>]*>)\s*)(' + re.escape(starter) + r')', re.I | re.MULTILINE)
            matches = list(pattern.finditer(html))
            if len(matches) > 3:
                # Replace excess occurrences (keep first 2, replace rest)
                for idx, m in enumerate(matches[2:]):
                    replacement = replacements[idx % len(replacements)]
                    # Preserve case of original
                    if m.group(2)[0].isupper():
                        replacement = replacement[0].upper() + replacement[1:]
                    html = html[:m.start(2)] + replacement + html[m.end(2):]
                    # Recalculate matches after each replacement
                    matches = list(pattern.finditer(html))
                    if idx >= 4:  # Cap at 5 replacements per starter
                        break
                log.info(f"R19 variety fix: replaced {min(len(matches)-2, 5)} repetitive '{starter.strip()}' openers")

        # R55 nuance injection: REMOVED — generic filler like "real-world performance
        # of {kw} depends on sourcing quality" is identical across articles.  The S6
        # prompt already instructs the AI to use nuance phrases naturally.

        # ── R30: Bold key terms injection ────────────────────────────────────
        bold_count = len(re.findall(r"<strong>", html, re.I))
        if bold_count < 3:
            # Bold important terms in the article
            kw_words_set = set(w for w in (self.keyword or "").lower().split() if len(w) > 3)
            bold_terms = [
                self.keyword.strip(),
                *(w.strip() for w in self._semantic_variations[:3] if hasattr(self, '_semantic_variations') and self._semantic_variations),
            ]
            if not bold_terms or len(bold_terms) < 2:
                bold_terms = [self.keyword.strip()]
            bolded = 0
            for term in bold_terms:
                if bolded >= 4:
                    break
                if not term:
                    continue
                # Bold first occurrence in a <p> that isn't already bold
                pattern = re.compile(r"(<p[^>]*>[^<]*?)(" + re.escape(term) + r")([^<]*</p>)", re.I)
                m = pattern.search(html)
                if m and "<strong>" not in m.group(0).lower():
                    html = html[:m.start(2)] + f"<strong>{m.group(2)}</strong>" + html[m.end(2):]
                    bolded += 1
            if bolded > 0:
                log.info(f"R30 bold inject: bolded {bolded} key terms")

        # ── R54: Opinion signals — now prompt-driven via _SECTION_TYPE_REQUIREMENTS ──
        log.debug("R54 opinion check skipped: produced at prompt time via section type rules")

        # R41 storytelling: REMOVED — fabricated experience claims like "When we
        # tested different {kw} options side by side" are identical across articles
        # and can be dishonest.  The prompt already asks the AI for experience signals.

        # ── R36: Experience signals — now prompt-driven via section type rules ──
        log.debug("R36 experience check skipped: produced at prompt time via section type rules")

        # R48 pros/cons injection: REMOVED — entire template section with generic
        # pros/cons that are not article-specific.  If pros/cons is needed, S2
        # structure should include a pros_cons section type, and S6 will write
        # it with actual research data via section_type_requirements.

        # ── R49: Urgency signals — now prompt-driven via _SECTION_TYPE_REQUIREMENTS ──
        log.debug("R49 urgency check skipped: produced at prompt time via section type rules")

        # ── R50: Trust signals — now prompt-driven via _SECTION_TYPE_REQUIREMENTS ──
        log.debug("R50 trust check skipped: produced at prompt time via section type rules")

        # ── R58: Conversational questions — now prompt-driven via section type rules ──
        log.debug("R58 question check skipped: produced at prompt time via section type rules")

        # ── R59: Hedging / qualifier signals — now prompt-driven via section type rules ──
        log.debug("R59 hedge check skipped: produced at prompt time via section type rules")

        # ── R63: Beginner + Advanced signals — now prompt-driven via section type rules ──
        log.debug("R63 beginner/advanced check skipped: produced at prompt time via section type rules")

        # ── R64: Implicit question answering — now prompt-driven via section type rules ──
        log.debug("R64 implicit-Q check skipped: produced at prompt time via section type rules")

        # ── R57: Scrub template conclusion patterns ───────────────────────────
        html = re.sub(r"(?i)(<p[^>]*>)\s*in conclusion,?\s*", r"\1To put it simply, ", html)
        html = re.sub(r"(?i)(<p[^>]*>)\s*to sum up,?\s*", r"\1Here's the bottom line: ", html)
        html = re.sub(r"(?i)(<p[^>]*>)\s*in summary,?\s*", r"\1What all this means: ", html)
        html = re.sub(r"(?i)(<p[^>]*>)\s*as we'?ve (seen|discussed|explored),?\s*", r"\1As this guide shows, ", html)

        # ── Hard cleanup: collapse multiple spaces left by empty replacements ─
        html = re.sub(r"  +", " ", html)
        # Remove space before punctuation artifacts: "word ." → "word."
        html = re.sub(r" +([.,;:!?])", r"\1", html)

        return html

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 7: AI QUALITY REVIEW (Gemini)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step7_review(self):
        """
        Quality review — SKIPPED (no-op).

        This step previously made 1 AI call to produce subjective review scores
        stored in step.details["review"], but NO downstream step reads that data.
        S8 (identify_issues) already runs check_all_rules() which is the real
        quality gate consumed by S9/S10/S11.  Removing this saves 1 AI call
        (~30-120s) per pipeline run with zero functional impact.
        """
        _step_ctx_var.set({"step": 7, "step_name": "Review", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[6]
        step.summary = "Skipped — S8 rule-based review is the real quality gate"
        step.details["review"] = {"skipped": True, "reason": "redundant_with_s8"}

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 8: ISSUE IDENTIFICATION (Rule-based + AI)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step8_identify_issues(self):
        """
        Run 53-rule per-rule quality checks via quality.content_rules.check_all_rules().
        Results include per-rule pass/fail, per-pillar summaries, and backward-compat issues.
        Rule results are saved in schema_json for live pipeline display.
        """
        _step_ctx_var.set({"step": 8, "step_name": "IdentifyIssues", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[7]
        html = self.state.draft_html

        from quality.content_rules import check_all_rules
        scored = check_all_rules(
            body_html=html,
            keyword=self.keyword,
            title=self.state.title,
            meta_title=self.state.meta_title,
            meta_desc=self.state.meta_desc,
            page_type=self.page_type,
            **self._scoring_customer_kwargs(),
        )

        # Extract issues in the format Step 9 expects
        issues = scored["issues"]

        # ── Editorial validation (rule-based, zero AI cost) ─────────────────
        try:
            from engines.humanize.editorial import validate_editorial, detect_redundancy
            from engines.humanize.splitter import split_into_sections
            ed_result = validate_editorial(html, keyword=self.keyword)
            ed_issues = ed_result.get("issues", [])
            for ei in ed_issues:
                issues.append({
                    "rule": f"ED_{ei.get('type', 'editorial').upper()}",
                    "name": ei.get("type", "editorial").replace("_", " ").title(),
                    "severity": ei.get("severity", "medium"),
                    "fix": ei.get("detail", ""),
                    "source": "editorial_validator",
                })
            sections = split_into_sections(html)
            sec_dicts = [{"content": s.get("html", ""), "index": i} for i, s in enumerate(sections)]
            red_result = detect_redundancy(sec_dicts, keyword=self.keyword)
            if red_result.get("keyword_overuse"):
                issues.append({
                    "rule": "ED_KEYWORD_OVERUSE",
                    "name": "Keyword Overuse",
                    "severity": "critical",
                    "fix": f"Keyword density {red_result['keyword_density']}% ({red_result['keyword_count']} occurrences) — reduce to 1-2%",
                    "source": "editorial_validator",
                })
            for ri in red_result.get("repeated_ideas", []):
                issues.append({
                    "rule": "ED_REDUNDANCY",
                    "name": "Repeated Ideas",
                    "severity": "medium",
                    "fix": f"Sections {ri['sections'][0]} and {ri['sections'][1]} share {ri['similarity']} — merge or differentiate",
                    "source": "editorial_validator",
                })
            log.info(f"Editorial validation: {len(ed_issues)} editorial issues, keyword_overuse={red_result.get('keyword_overuse')}, {len(red_result.get('repeated_ideas', []))} redundant pairs")
        except Exception as e:
            log.warning(f"Editorial validation in step8 failed (non-fatal): {e}")

        self._issues = issues
        self.state.issues_found = len(issues)

        # Store full per-rule results for pipeline live display
        self._rule_results = {
            "percentage": scored["percentage"],
            "total_earned": scored["total_earned"],
            "max_possible": scored["max_possible"],
            "rules": scored["rules"],
            "pillars": scored["pillars"],
            "summary": scored["summary"],
            "checkpoint": "step8_draft",
        }

        ed_issue_count = sum(1 for i in issues if i.get("source") == "editorial_validator")
        step.summary = (
            f"Score {scored['percentage']}% ({scored['total_earned']}/{scored['max_possible']} pts) · "
            f"{scored['summary']['passed_count']}/{scored['summary']['total_rules']} rules passed · "
            f"{len(issues)} issues ({ed_issue_count} editorial)"
        )
        step.details = {
            "issues": issues[:30],
            "rule_results": self._rule_results,
            "totals": {
                "critical": sum(1 for i in issues if i.get('severity') == 'critical'),
                "high": sum(1 for i in issues if i.get('severity') == 'high'),
                "medium": sum(1 for i in issues if i.get('severity') == 'medium'),
                "low": sum(1 for i in issues if i.get('severity') == 'low'),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 9: HUMANIZE
    # ─────────────────────────────────────────────────────────────────────────

    async def _step9_humanize(self):
        """
        Run the full humanization pipeline on the current draft.
        Removes AI patterns, deduplicates sections, scores tone with LLM judge.
        Uses self.routing.humanize (configurable via step-by-step panel dropdowns).
        Non-blocking: if humanize fails, draft_html is kept unchanged and
        the pipeline continues to Step 10 (Redevelop) as normal.
        """
        _step_ctx_var.set({"step": 9, "step_name": "Humanize", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[8]

        html = self.state.draft_html
        if not html or len(html) < 200:
            step.summary = "Draft too short — skipping humanization"
            return

        # ── Conditional: skip humanize if S8 already scored R35 (AI patterns) as passing ──
        _r35_passed = False
        if hasattr(self, '_rule_results') and self._rule_results:
            for _rr in self._rule_results.get("rules", []):
                if _rr.get("rule_id") == "R35" and _rr.get("passed"):
                    _r35_passed = True
                    break
        if _r35_passed:
            step.summary = "Skipped — R35 (AI patterns) already passing; humanization unnecessary"
            self._add_log("info", "[Humanize] R35 already passing — skipping to save AI calls", 9)
            return

        self._add_log("info", f"[Humanize] Starting humanization pipeline ({len(html)} chars)", 9)

        from functools import partial
        from engines.humanize.pipeline import run_humanize_pipeline
        from core.ai_config import AIRouter

        # ── Build a sync adapter that respects self.routing.humanize ─────────
        # humanize_section() is sync and accepts an ai_router= kwarg.
        # We create a tiny adapter that calls AIRouter's provider methods
        # in the order the user selected in the step dropdowns.
        _routing_cfg = self.routing.humanize
        _provider_order = [_routing_cfg.first, _routing_cfg.second, _routing_cfg.third]
        _active_providers = [p for p in _provider_order if p and p != "skip"]
        _step_log = self._add_log  # capture reference for thread use
        self._add_log("info", f"[Humanize] AI chain: {' → '.join(_active_providers) or 'none configured'}", 9)

        _engine_ref = self  # capture engine instance for Gemini key rotation

        class _HumanizeRouterAdapter:
            """Sync AI adapter that calls providers in the routing-config order.
            Uses engine's Gemini key rotation, shorter Ollama timeout (60s),
            and respects circuit breakers."""
            def call_with_tokens(self, prompt, system="You are a content humanization specialist. Return only HTML.", temperature=0.6):
                for provider in _provider_order:
                    if not provider or provider in ("skip", ""):
                        continue
                    try:
                        if provider == "groq":
                            if not AIRouter._groq_circuit_ok():
                                _step_log("warn", "[Humanize] groq circuit breaker open — skipping", 9)
                                continue
                            text, tokens = AIRouter._call_groq(prompt, system, temperature)
                            if text:
                                _step_log("info", f"[Humanize] groq succeeded ({tokens} tok)", 9)
                                return text, tokens
                            _step_log("warn", "[Humanize] groq returned empty", 9)
                        elif provider in ("ollama",):
                            if not AIRouter._ollama_check_health():
                                _step_log("warn", "[Humanize] ollama unhealthy — skipping", 9)
                                continue
                            # Use shorter timeout (60s) for humanize sections
                            import requests as _hreq
                            from core.ai_config import AICfg as _AICfg
                            # Trim prompt for Ollama: strip outline block + cap section at 2000 chars
                            _ollama_prompt = prompt
                            _outline_start = _ollama_prompt.find("ARTICLE OUTLINE")
                            _rules_start = _ollama_prompt.find("━━━ CRITICAL RULES ━━━")
                            if 0 < _outline_start < _rules_start:
                                _ollama_prompt = _ollama_prompt[:_outline_start] + _ollama_prompt[_rules_start:]
                            _sec_marker = "SECTION TO REWRITE:"
                            _sec_idx = _ollama_prompt.find(_sec_marker)
                            if _sec_idx >= 0:
                                _head = _ollama_prompt[:_sec_idx + len(_sec_marker)]
                                _body = _ollama_prompt[_sec_idx + len(_sec_marker):]
                                _ollama_prompt = _head + _body[:2000] + "\n\nReturn ONLY the rewritten HTML."
                            _payload = {
                                "model": _AICfg.OLLAMA_MODEL,
                                "prompt": _ollama_prompt,
                                "stream": False,
                                "options": {"temperature": temperature, "num_ctx": _AICfg.OLLAMA_MAX_CTX},
                            }
                            if system:
                                _payload["system"] = system
                            acquired = AIRouter._ollama_sem.acquire(blocking=True, timeout=3)
                            if not acquired:
                                _step_log("warn", "[Humanize] ollama busy — skipping", 9)
                                continue
                            try:
                                r = _hreq.post(f"{_AICfg.OLLAMA_URL}/api/generate", json=_payload, timeout=60)
                                if r.ok:
                                    import re as _re
                                    text = r.json().get("response", "").strip()
                                    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
                                    if text:
                                        _step_log("info", f"[Humanize] ollama succeeded ({len(text)} chars)", 9)
                                        return text, 0
                                _step_log("warn", f"[Humanize] ollama returned empty/error ({r.status_code})", 9)
                            finally:
                                AIRouter._ollama_sem.release()
                        elif provider in ("gemini_free", "gemini", "gemini_paid"):
                            # Use engine's Gemini call with key rotation + multi-model
                            _paid = provider == "gemini_paid"
                            _key = _live_gemini_key(paid=_paid)
                            if not _key:
                                _step_log("warn", f"[Humanize] {provider} no API key — skipping", 9)
                                continue
                            full_prompt = f"{system}\n\n{prompt}" if system else prompt
                            try:
                                text = _engine_ref._gemini_sync_with_key(full_prompt, temperature, _key)
                                if text and text.strip():
                                    _step_log("info", f"[Humanize] {provider} succeeded ({len(text)} chars)", 9)
                                    return text.strip(), 0
                                _step_log("warn", f"[Humanize] {provider} returned empty", 9)
                            except Exception as _ge:
                                _step_log("warn", f"[Humanize] {provider} error: {str(_ge)[:80]}", 9)
                        elif provider.startswith("or_") or provider == "openrouter":
                            _or_key = _live_openrouter_key()
                            if not _or_key:
                                _step_log("warn", f"[Humanize] {provider}: no OpenRouter key — skipping", 9)
                                continue
                            _or_model = _resolve_openrouter_model(provider)
                            _or_msgs = []
                            if system:
                                _or_msgs.append({"role": "system", "content": system})
                            _or_msgs.append({"role": "user", "content": prompt})
                            try:
                                import httpx
                                _or_resp = httpx.post(
                                    "https://openrouter.ai/api/v1/chat/completions",
                                    headers={"Authorization": f"Bearer {_or_key}", "Content-Type": "application/json"},
                                    json={"model": _or_model, "messages": _or_msgs, "temperature": temperature, "max_tokens": _or_adjust_max_tokens(provider, 2000)},
                                    timeout=120,
                                )
                                if _or_resp.status_code == 200:
                                    _or_body = _or_resp.json()
                                    if not _or_body.get("error"):
                                        _or_choice = _or_body.get("choices", [{}])[0]
                                        _or_text = (_or_choice.get("message", {}).get("content") or "").strip()
                                        if not _or_text:
                                            _or_text = (_or_choice.get("message", {}).get("reasoning") or "").strip()
                                        _or_usage = _or_body.get("usage", {})
                                        _or_tokens = _or_usage.get("completion_tokens", 0)
                                        if _or_text:
                                            _step_log("info", f"[Humanize] {provider} succeeded ({_or_tokens} tok)", 9)
                                            return _or_text, _or_tokens
                                        _step_log("warn", f"[Humanize] {provider} returned empty content", 9)
                                    else:
                                        _or_err = _or_body["error"].get("message", "")[:100]
                                        _step_log("warn", f"[Humanize] {provider} upstream error: {_or_err}", 9)
                                else:
                                    _step_log("warn", f"[Humanize] {provider} HTTP {_or_resp.status_code}", 9)
                            except Exception as _ore:
                                _step_log("warn", f"[Humanize] {provider} exception: {str(_ore)[:80]}", 9)
                    except Exception as _e:
                        _step_log("warn", f"[Humanize] {provider} error: {str(_e)[:80]}", 9)
                        continue
                _step_log("warn", "[Humanize] All providers failed for this section", 9)
                return "", 0

            def call(self, prompt, system="You are a content humanization specialist. Return only HTML.", temperature=0.6):
                text, _ = self.call_with_tokens(prompt, system, temperature)
                return text

        _adapter = _HumanizeRouterAdapter()

        # ── Progress callback ─────────────────────────────────────────────────
        def _on_progress(evt_step, current, total, detail="", extra=None):
            msg = detail or evt_step
            self._add_log("info", f"[Humanize] {msg}", 9)

        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(
                        run_humanize_pipeline,
                        html,
                        self.keyword,
                        tone="natural",
                        style="conversational",
                        on_progress=_on_progress,
                        ai_router=_adapter,
                        skip_judge=True,   # Skip LLM judge+fix pass — saves 1-6 extra AI calls
                        max_sections=16,   # Cap at 16 sections to prevent very long runs
                    )
                ),
                timeout=600,  # 10 minute hard cap — large articles need 3-5 min
            )
        except asyncio.TimeoutError:
            log.warning("Humanize step timed out after 10 min — keeping draft unchanged")
            self._add_log("warn", "[Humanize] Timed out after 10 minutes — keeping draft unchanged", 9)
            step.summary = "Humanize timed out (10 min) — draft unchanged"
            return
        except Exception as e:
            log.warning(f"Humanize step failed ({e}) — keeping draft unchanged")
            self._add_log("warn", f"[Humanize] Failed: {e}", 9)
            step.summary = f"Humanize failed ({e}) — draft unchanged"
            return

        if result.get("success") and result.get("humanized_html"):
            humanized = result["humanized_html"]

            # ── Post-humanize quality gate ──
            pre_wc = len(re.sub(r'<[^>]+>', ' ', html).split())
            post_wc = len(re.sub(r'<[^>]+>', ' ', humanized).split())
            if post_wc < pre_wc * 0.75:
                log.warning(f"Humanize lost >25% words ({pre_wc}→{post_wc}) — rejecting")
                self._add_log("warn", f"[Humanize] Rejected: word count dropped {pre_wc}→{post_wc} (>25%)", 9)
                step.summary = f"Humanize rejected: word count {pre_wc}→{post_wc} — draft unchanged"
            else:
                # Check link preservation
                pre_links = len(re.findall(r'<a\s', html, re.I))
                post_links = len(re.findall(r'<a\s', humanized, re.I))
                if post_links < pre_links * 0.5 and pre_links >= 3:
                    log.warning(f"Humanize lost links ({pre_links}→{post_links}) — re-injecting")
                    self._add_log("info", f"[Humanize] Links dropped {pre_links}→{post_links} — re-injecting", 9)
                    humanized = self._post_draft_inject(humanized)

                self.state.draft_html = humanized
                self.state.final_html = humanized

            orig   = result.get("original_score", 0)
            final  = result.get("final_score", 0)
            judge  = result.get("judge_score")  # None when judge was skipped
            secs   = result.get("sections_processed", 0)
            judge_display = f"{judge}/100" if judge is not None else "skipped"
            step.summary = (
                f"Score {orig}→{final} | Judge {judge_display} | {secs} sections humanized"
            )
            step.details = {
                "original_score": orig,
                "final_score": final,
                "judge_score": judge,
                "sections_processed": secs,
                "seo_preserved": result.get("seo_preserved", True),
                "seo_issues": result.get("seo_issues", []),
            }
            log.info(f"Humanize done: {orig}→{final}, judge={judge}/100, {secs} sections")
        else:
            err = result.get("error", "unknown")
            log.warning(f"Humanize returned no output ({err}) — keeping draft unchanged")
            step.summary = f"Humanize produced no output ({err}) — draft unchanged"

    # ── SURGICAL ALGORITHMIC FIXES ───────────────────────────────────────────

    async def _apply_surgical_fixes(self, html: str, failed_rules: list, score_result: dict) -> str:
        """Apply SAFE, non-spoiling algorithmic fixes for high-impact failures.

        Design principle (2026-04-22): NEVER mutate H2 text or rewrite paragraphs
        with templated openers like "For {kw}, ...". Earlier versions did this
        and produced ugly Frankenheadlines ("Kerala Turmeric: How to Choose...").
        This version only:
          1. TRIMS keyword density when too high (>2.5%) by replacing extra
             instances in body paragraphs with pronouns / semantic variants.
          2. Injects a definition sentence into the first paragraph IF R70
             failed AND no definition exists (single, conservative insertion).
          3. Smooths repetitive sentence starters with a transition word.

        Density LOW (<1.0%) is intentionally NOT auto-injected — that path
        produced spoiled articles. Prevention is handled at prompt-time via
        rules_compact (KEYWORD usage guide).

        Returns: Fixed HTML.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        fixes_applied = []

        # ── 1. Keyword density TRIM when too high (safe direction only) ──────
        kw_density = score_result.get("kw_density", 0)
        if kw_density > 2.5 and self.keyword:
            kw = self.keyword
            kw_re = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            replacements = (self._semantic_variations or [])[:3] or ["it", "this", "the product"]
            removed = 0
            # Iterate body paragraphs (skip H2/H3/intro first paragraph) and replace
            # surplus keyword occurrences with pronouns/variants.
            paragraphs = soup.find_all("p")
            for idx, p in enumerate(paragraphs):
                if idx == 0:
                    continue  # preserve intro phrasing
                text = p.get_text()
                hits = kw_re.findall(text)
                if len(hits) <= 1:
                    continue
                # Keep first occurrence, replace the rest with rotating variant.
                count = [0]
                def _swap(m, _count=count):
                    _count[0] += 1
                    if _count[0] == 1:
                        return m.group(0)  # keep first
                    return replacements[(_count[0] - 2) % len(replacements)]
                new_text = kw_re.sub(_swap, text)
                if new_text != text:
                    p.string = new_text
                    removed += len(hits) - 1
                if removed >= 6:
                    break
            if removed:
                fixes_applied.append(f"density-trim −{removed}")
                html = str(soup)

        # ── 2. Definition block injection if R70 failed ──────────────────────
        r70_failed = any(r.get("rule_id") == "R70" for r in failed_rules)
        if r70_failed and self.keyword:
            first_p = soup.find("p")
            if first_p:
                text = first_p.get_text()
                has_def = bool(re.search(r"\b(is a|are a|refers to|defined as|means|describes)\b", text.lower()))
                if not has_def:
                    sentences = re.split(r"([.!?]+\s+)", text)
                    if len(sentences) >= 2:
                        # Use a research-aware definition rather than generic "category of products".
                        themes = []
                        try:
                            themes = (self.state.steps[0].details or {}).get("analysis", {}).get("themes", []) or []
                        except Exception:
                            themes = []
                        anchor = (themes[0].lower() if themes else "this topic")
                        definition = f"{self.keyword.title()} refers to {anchor}."
                        new_text = sentences[0] + sentences[1] + definition + " " + "".join(sentences[2:])
                        first_p.string = new_text
                        fixes_applied.append("R70 definition")
                        html = str(soup)
        
        # ── 3. Sentence variety fix (repetitive starters) ────────────────────
        # Check if there are 3+ consecutive sentences starting the same way
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            text = p.get_text()
            sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 10]
            if len(sentences) >= 3:
                starters = [s.split()[0] if s.split() else "" for s in sentences]
                # Check for repetitive starters (3+ consecutive)
                for i in range(len(starters) - 2):
                    if starters[i] == starters[i+1] == starters[i+2] and starters[i]:
                        # Replace middle one with a transition word
                        transitions = ["Additionally,", "Moreover,", "Furthermore,", "Also,", "In fact,"]
                        sentences[i+1] = transitions[i % len(transitions)] + " " + sentences[i+1].lower()
                        # Rebuild paragraph
                        new_text = ". ".join(sentences) + "."
                        p.string = new_text
                        fixes_applied.append("variety")
                        html = str(soup)
                        break
        
        if fixes_applied:
            log.info(f"Surgical fixes applied: {', '.join(fixes_applied)}")
        
        return html

    # STEP 10: CONTENT REDEVELOPMENT
    # ─────────────────────────────────────────────────────────────────────────

    async def _step10_redevelop(self):
        """
        Final polish pass — targets highest-impact failed rules with a single
        comprehensive LLM rewrite. Runs AFTER Quality Loop has done iterative fixes,
        so this works on the best available content with fresh rule results.
        """
        _step_ctx_var.set({"step": 12, "step_name": "Redevelop", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[11]

        # ── Re-score current content with fresh rules ─────────────────────────
        current_html = self.state.final_html
        try:
            from quality.content_rules import check_all_rules
            fresh_scored = check_all_rules(
                body_html=current_html,
                keyword=self.keyword,
                title=self.state.title,
                meta_title=self.state.meta_title,
                meta_desc=self.state.meta_desc,
                page_type=self.page_type,
                **self._scoring_customer_kwargs(),
            )
            failed_rules = [r for r in fresh_scored.get("rules", []) if not r.get("passed", True)]
            current_score = fresh_scored["percentage"]
        except Exception as e:
            log.warning(f"Redevelop: fresh scoring failed ({e}) — using cached rules")
            failed_rules = []
            if hasattr(self, '_rule_results') and self._rule_results:
                failed_rules = [r for r in self._rule_results.get("rules", []) if not r.get("passed", True)]
            current_score = self._rule_results.get("percentage", 0) if hasattr(self, '_rule_results') and self._rule_results else 0

        # Skip if score is already high enough or no failures AND no editorial instructions exist
        has_edit_inst = hasattr(self.state, "editorial_instructions") and len(self.state.editorial_instructions) > 0
        if current_score >= MIN_QUALITY_SCORE and not has_edit_inst:
            step.summary = f"Score already {current_score}% ≥ {MIN_QUALITY_SCORE}% — skipping redevelopment"
            return

        if not failed_rules and not has_edit_inst:
            step.summary = "No rule failures and no editorial instructions — skipping redevelopment"
            return

        # ── Surgical algorithmic fixes BEFORE LLM redevelop ──────────────────
        # These are low-risk, high-impact algorithmic corrections that give the
        # LLM better base content to work with. Only fix the most common issues.
        current_html = await self._apply_surgical_fixes(current_html, failed_rules, fresh_scored)
        self.state.final_html = current_html  # update state with pre-fixed version

        # Sort by points at stake
        failed_rules.sort(key=lambda x: x.get("points_max", 0) - x.get("points_earned", 0), reverse=True)

        # Build grouped fix instructions for the top failures
        top_rules = failed_rules[:12]
        rule_fix_lines = []
        for r in top_rules:
            pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
            issue_fix = next(
                (i.get("fix", "") for i in self._issues if i.get("rule") == r.get("rule_id", "")),
                ""
            )
            rule_fix_lines.append(
                f"[+{pts_lost}pt | {r.get('rule_id','?')}] {r.get('name','?')} — FIX: {issue_fix or r.get('name','')}"
            )
        failed_rules_text = "\n".join(rule_fix_lines)

        # Editorial Intelligence findings (repetition, density, intent gaps).
        # These are not in the rule-engine output but must be addressed in the
        # final polish. Surface them prominently in the prompt.
        editorial_block = ""
        if has_edit_inst:
            editorial_block = (
                "\n━━━ EDITORIAL INTELLIGENCE FIXES (mandatory) ━━━\n"
                + "\n".join(f"• {inst}" for inst in self.state.editorial_instructions)
                + "\n"
            )

        # AI Reviewer findings (S7) — surface critical_issues + missing_rules
        # so the final polish addresses things the rule engine doesn't catch
        # (tone, narrative coherence, expert judgement).
        review_block = ""
        try:
            review = (self.state.steps[6].details or {}).get("review", {}) if len(self.state.steps) > 6 else {}
            crit = [c for c in (review.get("critical_issues") or []) if c and c != "Review unavailable"]
            missing = [m for m in (review.get("missing_rules") or []) if m]
            if crit or missing:
                lines = []
                for c in crit[:6]:
                    lines.append(f"• CRITICAL: {c}")
                for m in missing[:6]:
                    lines.append(f"• MISSING: {m}")
                review_block = (
                    "\n━━━ AI REVIEWER FINDINGS (mandatory) ━━━\n"
                    + "\n".join(lines)
                    + "\n"
                )
        except Exception:
            pass

        # ── Single targeted rewrite pass using reduced prompt ──────────────
        # Use current best HTML (after Quality Loop), not the original draft
        article_excerpt = self.state.final_html

        base_prompt = f"""You are a senior SEO content editor. Fix the specific quality rule failures listed below.

KEYWORD: "{self.keyword}" (density target: 1.0-1.5%)
Semantic Variations: {', '.join(self._semantic_variations[:5]) if self._semantic_variations else 'use synonyms'}
CURRENT SCORE: {current_score}% — TARGET: 90%+

━━━ RULES TO FIX (highest impact first) ━━━
{failed_rules_text}
{editorial_block}{review_block}
{self._pm_block("step9_quality_rules")}

━━━ KEY FIX RULES ━━━
KEYWORD: Use "{self.keyword}" naturally — in H2 headings, intro, conclusion, and a few body paragraphs. Do NOT force it into every paragraph. Density 1.0-2.0%.
DEFINITION BLOCK: The first 200 words MUST contain a clear definitional sentence using one of these patterns: "{self.keyword} is a ...", "{self.keyword} refers to ...", or "{self.keyword} describes ...". This is a scored rule (R70).
FIRST PARA: ≥40 words, start with "{self.keyword.split()[0]}", contain keyword.
STRUCTURE: 6+ <h2>, 4+ <h3>, FAQ heading with "Frequently Asked"/"FAQ", 1 <table>, 2+ <ul>, 1+ <ol>.
AUTHORITY: Only cite SPECIFIC named sources (e.g. "FDA guidelines", "a 2024 Stanford study"). NEVER use vague "research shows", "studies suggest", "experts agree", "data shows", or "according to recent research". If you can't name a real source, state the fact directly without attribution.
DATA: Include real numbers — percentages, years, measurements, price ranges.
LINKS: Preserve all existing <a href="..."> links exactly.
READABILITY: Flesch Reading Ease MUST be 50-75. Avg sentence 12-22w. Mix short (8-12w) and medium (15-22w) sentences. Zero paragraphs >100w. Active voice.
SENTENCE VARIETY: Start sentences with different words. Use at least 4 opener types: questions, statements, imperatives, transitional (And/But/So). Never start 2 consecutive sentences the same way.
HUMAN VOICE: Write like a knowledgeable person. Use contractions (don't, isn't, you'll). Start some sentences with "And", "But", "So". Include slight opinions. Vary rhythm.
FORBIDDEN: delve, multifaceted, tapestry, nuanced, robust, myriad, paradigm, foster, holistic, pivotal, "let's explore", "when it comes to", "in today's world".
ANTI-STUFFING: Do NOT repeat the exact keyword phrase in every paragraph. Use pronouns, shortened forms, or skip it entirely in paragraphs where the topic is already clear from context.
BUYER GUIDANCE: Include "how to choose", "best for", "what to look for", or similar decision phrases. Mention "pros and cons" or "advantages and disadvantages" somewhere.
CONTENT DEPTH: Cover what/why/how/when angles. Include both beginner ("basics", "simple") and advanced ("advanced", "professional", "in-depth") content.
OUTPUT: Complete improved article as clean semantic HTML. No markdown, no code fences.

━━━ ARTICLE TO IMPROVE ━━━
{article_excerpt}"""

        log.info(f"Redevelop (S12): chain {self.routing.redevelop.first}→{self.routing.redevelop.second}→{self.routing.redevelop.third}")
        try:
            chain_out = await self._call_ai_raw_with_chain(
                self.routing.redevelop, base_prompt, temperature=0.5, max_tokens=6000,
                use_prompt_directly=True
            )
        except Exception as e:
            log.warning(f"Redevelop: chain failed ({e}) — keeping current")
            chain_out = ""

        current_wc = len(re.sub(r"<[^>]+>", " ", self.state.final_html).split())
        min_acceptable = max(500, int(current_wc * 0.75)) if current_wc > 100 else 200

        if chain_out:
            chain_wc = len(re.sub(r"<[^>]+>", " ", chain_out).split())
            if chain_wc >= min_acceptable:
                chain_out = self._scrub_ai_patterns(chain_out)
                chain_out = self._intelligence_post_process(chain_out)
                chain_wc = len(re.sub(r"<[^>]+>", " ", chain_out).split())

                # Validate improvement — only accept if score actually improves
                try:
                    from quality.content_rules import check_all_rules as _check_redevelop
                    new_scored = _check_redevelop(
                        body_html=chain_out,
                        keyword=self.keyword,
                        title=self.state.title,
                        meta_title=self.state.meta_title,
                        meta_desc=self.state.meta_desc,
                        page_type=self.page_type,
                        **self._scoring_customer_kwargs(),
                    )
                    new_score = new_scored["percentage"]
                except Exception:
                    new_score = current_score + 1  # Accept on scoring failure

                if new_score >= current_score:
                    self.state.final_html = chain_out
                    self.state.draft_html = chain_out
                    self.state.word_count = chain_wc
                    self.state.seo_score = float(new_score)
                    step.summary = (
                        f"Polished: {current_score}%→{new_score}% · {chain_wc} words · "
                        f"provider: {self.routing.redevelop.first}"
                    )
                    log.info(f"Redevelop: improved {current_score}%→{new_score}% ({chain_wc} words)")
                    return
                else:
                    log.warning(f"Redevelop: rewrite WORSE ({current_score}%→{new_score}%) — keeping current")
            else:
                log.warning(f"Redevelop: output too short ({chain_wc}w, min {min_acceptable}) — keeping current")

        self.state.word_count = current_wc
        step.summary = (
            f"No improvement achieved — keeping current ({current_wc}w, {current_score}%). "
            f"{len(failed_rules)} rules noted. Provider chain: "
            f"{self.routing.redevelop.first}→{self.routing.redevelop.second}→{self.routing.redevelop.third}"
        )
        log.warning("Redevelop: no passes produced valid output — keeping current")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 11: FINAL SCORING
    # ─────────────────────────────────────────────────────────────────────────

    async def _step11_score(self):
        """
        Calculate final quality scores using the 53-rule per-rule engine.
        Saves full per-rule results to DB for the frontend RulesPanel.
        """
        _step_ctx_var.set({"step": 10, "step_name": "Score", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[9]
        html = self.state.final_html
        text = re.sub(r"<[^>]+>", " ", html)
        word_count = len(text.split())

        # ── Run per-rule scoring engine ─────────────────────────────────────
        try:
            from quality.content_rules import check_all_rules
            scored = check_all_rules(
                body_html=html,
                keyword=self.keyword,
                title=self.state.title,
                meta_title=self.state.meta_title,
                meta_desc=self.state.meta_desc,
                page_type=self.page_type,
                **self._scoring_customer_kwargs(),
            )
        except Exception as e:
            log.warning(f"content_rules failed in step10: {e}")
            scored = {
                "score": 0, "percentage": 0, "total_earned": 0, "max_possible": 0,
                "categories": {}, "issues": [], "rules": [], "pillars": [], "summary": {},
                "word_count": word_count, "kw_density": 0.0,
            }

        percentage = scored["percentage"]
        kw_density = scored["kw_density"]
        issues_count = len(scored["issues"])

        # Readability (Flesch) for display
        readability_score = 65.0
        if HAS_TEXTSTAT and text:
            try:
                readability_score = textstat.flesch_reading_ease(text[:16000])
            except Exception:
                pass

        # Store in state
        self.state.seo_score   = float(percentage)
        self.state.readability = round(max(0, readability_score), 1)
        self.state.word_count  = word_count

        # Store rule results for pipeline snapshot
        self._rule_results = {
            "percentage": percentage,
            "total_earned": scored["total_earned"],
            "max_possible": scored["max_possible"],
            "rules": scored["rules"],
            "pillars": scored["pillars"],
            "summary": scored["summary"],
            "checkpoint": "step10_final",
        }

        # ── Auto-save scoring results to review columns ───────────────────
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc).isoformat()
        if self.db:
            try:
                self.db.execute(
                    """UPDATE content_articles
                       SET review_score=?, review_breakdown=?, review_notes=?, last_reviewed_at=?
                       WHERE article_id=?""",
                    (
                        percentage,
                        json.dumps({
                            "categories": scored["categories"],
                            "rules": scored["rules"],
                            "pillars": scored["pillars"],
                            # Phase B: persist per-section scores alongside rule results
                            "section_scores": getattr(self.state, "section_scores", None),
                        }),
                        json.dumps({
                            "verdict": f"Auto-scored: {percentage}% ({scored['total_earned']}/{scored['max_possible']} pts) — {scored['summary']['passed_count']}/{scored['summary']['total_rules']} rules passed",
                            "strength": f"Passed: {', '.join(r['name'] for r in scored['rules'] if r['passed'])[:200]}",
                            "weakness": f"Failed: {', '.join(r['name'] for r in scored['rules'] if not r['passed'])[:200]}",
                            "auto_review": True,
                            "percentage": percentage,
                            "total_earned": scored["total_earned"],
                            "max_possible": scored["max_possible"],
                        }),
                        now,
                        self.article_id,
                    )
                )
                self.db.commit()
            except Exception as e:
                log.warning(f"Auto-save review failed: {e}")

        step.summary = (
            f"Score {percentage}% ({scored['total_earned']}/{scored['max_possible']} pts) · "
            f"{scored['summary'].get('passed_count', 0)}/{scored['summary'].get('total_rules', 0)} rules · "
            f"Flesch {readability_score:.0f} · {kw_density}% density · "
            f"{word_count} words"
        )
        step.details = {
            "percentage": percentage,
            "total_earned": scored["total_earned"],
            "max_possible": scored["max_possible"],
            "rules": scored["rules"],
            "pillars": scored["pillars"],
            "categories": scored["categories"],
            "issues_count": issues_count,
            "top_issues": scored["issues"][:5],
            "readability": readability_score,
            "word_count": word_count,
            "kw_density": kw_density,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 12: QUALITY IMPROVEMENT LOOP
    # ─────────────────────────────────────────────────────────────────────────

    async def _step12_quality_loop(self):
        """
        Iterative quality improvement: re-score → fix failing rules → repeat.
        Uses Ollama to rewrite the content targeting highest-impact failures.
        Max 3 passes. Stops when score >= MIN_QUALITY_SCORE.
        """
        _step_ctx_var.set({"step": 11, "step_name": "QualityLoop", "article_id": getattr(self, "article_id", None), "project_id": getattr(self, "project_id", ""), "keyword": getattr(self, "keyword", "")})
        step = self.state.steps[10]
        current_score = self.state.seo_score
        MAX_PASSES = 3

        # Critical rules that MUST pass regardless of overall score
        CRITICAL_RULES = {"R20", "R24", "R25", "R26", "R34", "R35", "R36", "R44"}

        def _critical_rules_ok(scored_rules: list) -> bool:
            return all(
                r.get("passed", False) for r in scored_rules
                if r.get("rule_id") in CRITICAL_RULES
            )

        # Check if we can skip the loop entirely
        initial_critical_ok = True
        if hasattr(self, '_rule_results') and self._rule_results:
            initial_critical_ok = _critical_rules_ok(self._rule_results.get("rules", []))

        # Editorial Intelligence may have flagged repetition / keyword stuffing /
        # intent gaps that don't move the rule-based score but DO need fixing.
        # If those instructions exist, force the loop to run at least once even
        # when the score is already above the target threshold.
        has_edit_inst = (
            hasattr(self.state, "editorial_instructions")
            and len(self.state.editorial_instructions) > 0
        )

        if current_score >= MIN_QUALITY_SCORE and initial_critical_ok and not has_edit_inst:
            step.summary = f"Score already {current_score}% ≥ {MIN_QUALITY_SCORE}% — no improvement needed"
            step.details = {"passes": 0, "initial_score": current_score, "final_score": current_score}
            return

        if current_score >= MIN_QUALITY_SCORE and not initial_critical_ok:
            log.info(f"Quality loop: score {current_score}% ≥ {MIN_QUALITY_SCORE}% but critical rules R20/R24/R25/R26 still failing — continuing")
        elif current_score >= MIN_QUALITY_SCORE and has_edit_inst:
            log.info(
                f"Quality loop: score {current_score}% ≥ {MIN_QUALITY_SCORE}% but "
                f"{len(self.state.editorial_instructions)} editorial instruction(s) pending — continuing"
            )

        log.info(f"Quality loop: score {current_score}% — starting improvement passes")
        html = self.state.final_html
        pass_log = []

        for pass_num in range(1, MAX_PASSES + 1):
            log.info(f"Quality loop pass {pass_num}/{MAX_PASSES}: current score {current_score}%")
            self._db_persist_status(f"step_11_pass{pass_num}")

            # Score what we have
            from quality.content_rules import check_all_rules
            scored = check_all_rules(
                body_html=html,
                keyword=self.keyword,
                title=self.state.title,
                meta_title=self.state.meta_title,
                meta_desc=self.state.meta_desc,
                page_type=self.page_type,
                **self._scoring_customer_kwargs(),
            )

            failed = [r for r in scored["rules"] if not r["passed"]]
            if not failed:
                break

            # Sort by points lost (highest impact first)
            failed.sort(key=lambda r: r.get("points_max", 0) - r.get("points_earned", 0), reverse=True)

            # Pass differentiation: Pass 1 = structure/readability, Pass 2 = authority/data/depth
            STRUCTURE_PILLARS = {"structure", "readability", "links", "keyword_usage", "snippet_optimization"}
            AUTHORITY_PILLARS = {"content_intelligence", "credibility", "eeat", "semantic_depth", "conversion", "customer_context"}
            if pass_num == 1:
                # Pass 1: prioritise structure and readability rules
                pass_failed = [r for r in failed if r.get("pillar", "") in STRUCTURE_PILLARS]
                remaining = [r for r in failed if r.get("pillar", "") not in STRUCTURE_PILLARS]
                pass_focus = pass_failed + remaining[:max(0, 15 - len(pass_failed))]
                pass_label = "PASS 1 FOCUS: Structure, readability, keyword placement, links, FAQ format"
            else:
                # Pass 2: prioritise authority, data, depth, and conversion
                pass_failed = [r for r in failed if r.get("pillar", "") in AUTHORITY_PILLARS]
                remaining = [r for r in failed if r.get("pillar", "") not in AUTHORITY_PILLARS]
                pass_focus = pass_failed + remaining[:max(0, 15 - len(pass_failed))]
                pass_label = "PASS 2 FOCUS: Authority sources, data credibility, buyer guidance, content depth, E-E-A-T signals"

            # Build targeted fix instructions
            fix_instructions = []
            for r in pass_focus[:15]:
                pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
                # Find matching issue fix hint
                issue_fix = ""
                for iss in scored.get("issues", []):
                    if iss.get("rule") == r.get("rule_id", ""):
                        issue_fix = iss.get("fix", "")
                        break
                detail = issue_fix or r.get("name", "fix this rule")
                fix_instructions.append(f"• [{r.get('rule_id','?')}] {r.get('name','?')} (+{pts_lost}pt): {detail}")

            # Inject Editorial Intelligence Instructions
            if hasattr(self.state, "editorial_instructions") and self.state.editorial_instructions:
                fix_instructions.append("\n=== EDITORIAL INTELLIGENCE FIXES REQUIRED ===\n" + \
                                      "\n".join([f"• {inst}" for inst in self.state.editorial_instructions]))

            fix_text = "\n".join(fix_instructions)

            # Build a COMPACT focused rewrite prompt (not the full rule spec — key to avoiding timeouts)
            research_ctx = self._research_context_block() if hasattr(self, '_research_context_block') else ""
            prompt = f"""Fix these quality issues in the SEO article below. Target score: {MIN_QUALITY_SCORE}%+.

KEYWORD: "{self.keyword}" | CURRENT: {current_score}%
{pass_label}

RULES TO FIX:
{fix_text}

{research_ctx}

KEY REQUIREMENTS:
- Keyword "{self.keyword}" naturally in H2 headings, intro, conclusion, and a few body paragraphs. Density 1.0-2.0%. Do NOT force it into every paragraph.
- First para ≥40w, starts with "{self.keyword.split()[0]}", contains keyword
- DEFINITION BLOCK: The first 200 words MUST contain a clear definitional sentence using one of these patterns: "{self.keyword} is a ...", "{self.keyword} refers to ...", or "{self.keyword} describes ...". This is a scored rule.
- READABILITY: Flesch MUST be 60-70 (not <50, not >75). Sentence avg 15-20w (mix 8-12w short + 18-25w medium). Break >30w. Active voice >80% ("X reduces Y" not "Y is reduced by X"). Transitions between paragraphs (However, Moreover).
- SENTENCE VARIETY (CRITICAL): Use 20+ different sentence openers. Limit "The" to <20%. Questions 10%+ ("How do you?", "What makes?"). Imperatives (Do, Try, Consider, Compare). Transitional (However, Moreover, Therefore, Meanwhile). Subordinate (While, Although, Because, Since, If). Adverbs (Typically, Generally, Often). Coordinating sparingly (And, But, So <5%). NEVER 3+ consecutive same starters.
- 6+ <h2>, 4+ <h3>, FAQ section, 1 <table>, 2+ <ul>, 1+ <ol>
- DATA CREDIBILITY (5+ sourced stats): Format "According to [FDA/USDA/NIH/Harvard/Grand View Research] (2023-2024), [stat]..." EVERY percentage needs attribution. NEVER use vague "research shows", "studies suggest", "experts agree". If no source, use ranges ("20-30%") or state directly.
- STORYTELLING (2+ instances): third-person customer scenarios ("a home cook sourcing X discovered Y"), before/after scenarios grounded in cited data, analogies. NO fabricated first-person testing claims.
- OPINION SIGNALS (2+ instances, neutral framing): "The strongest option for X is Y", "Avoid X because Y", "The best choice for [specific buyer] is...". Take clear stance WITHOUT fabricated first-person ("we recommend", "we tested" — forbidden).
- CTAs (3 required if not present): Intro soft CTA ("Discover benefits..."), mid-content <div class="cta-box"> (after 40%), conclusion strong CTA (buy/shop/order/contact + urgency + benefit).
- Include real numbers — percentages, years, measurements, price ranges
- Preserve all existing <a href="..."> links
- Max 80w/paragraph, active voice
- HUMAN VOICE: Contractions (don't, isn't, you'll). Ask 3+ rhetorical questions. Nuance ("on the other hand", "the catch is", "that said").
- FORBIDDEN: delve, multifaceted, tapestry, nuanced, robust, myriad, paradigm, "let's explore", "when it comes to", "in today's world"
- ANTI-STUFFING: Do NOT repeat the exact keyword in every paragraph. Use pronouns or shortened forms where the topic is already clear.
- BUYER GUIDANCE: Include "how to choose", "what to look for", "best for", or similar decision phrases. Use "pros and cons" or "advantages and disadvantages" somewhere.
- CONTENT DEPTH: Cover what/why/how/when angles. Include both beginner ("basics", "getting started", "simple") and advanced ("advanced", "professional", "in-depth") content.

ARTICLE:
{html[:16000]}

Output COMPLETE improved HTML. No markdown, no code fences, no commentary."""

            # Use routing chain — provider order set by self.routing.quality_loop (user-selectable)
            log.info(f"Quality loop pass {pass_num}: chain {self.routing.quality_loop.first}→{self.routing.quality_loop.second}→{self.routing.quality_loop.third}")
            
            # Progress tracking: estimate duration based on model speed
            provider = self.routing.quality_loop.first
            if provider == "ollama":
                profile = self._profiler.get_profile("ollama", self._resolve_ollama_model(provider))
                expected_time = self._profiler.estimate_duration(len(prompt), ql_max_tokens, profile)
                if self._progress:
                    self._progress.start_operation(f"Quality Loop Pass {pass_num}/{MAX_PASSES}", expected_time)
                    log.info(f"Quality loop pass {pass_num}: expected ~{expected_time}s with {profile.provider}:{profile.model}")
            
            try:
                # Dynamic max_tokens based on article size to avoid word count truncation
                current_words = len(re.sub(r"<[^>]+>", " ", html).split())
                ql_max_tokens = max(4000, int(current_words * 1.8))
                
                rewritten = await self._call_ai_raw_with_chain(
                    self.routing.quality_loop, prompt, temperature=0.4, max_tokens=ql_max_tokens,
                    use_prompt_directly=True
                )
                
                # Mark operation complete
                if self._progress and provider == "ollama":
                    self._progress.finish(f"Quality loop pass {pass_num} complete")
                    
            except Exception as e:
                if self._progress and provider == "ollama":
                    self._progress.finish(f"Quality loop pass {pass_num} failed: {str(e)[:50]}", final_message=False)
                log.warning(f"Quality loop pass {pass_num}: chain failed: {e}")
                pass_log.append(f"pass{pass_num}: chain failed ({e})")
                continue

            if not rewritten or len(rewritten.strip()) < 200:
                log.warning(f"Quality loop pass {pass_num}: output too short ({len(rewritten or '')})")
                pass_log.append(f"pass{pass_num}: output too short")
                continue

            # Clean code fences if present
            rewritten = re.sub(r"```html\n?", "", rewritten)
            rewritten = re.sub(r"```\n?", "", rewritten).strip()

            # Validate output
            new_wc = len(re.sub(r"<[^>]+>", " ", rewritten).split())
            old_wc = len(re.sub(r"<[^>]+>", " ", html).split())
            min_acceptable = max(500, int(old_wc * 0.75))

            if new_wc < min_acceptable:
                log.warning(f"Quality loop pass {pass_num}: word count dropped ({new_wc} < {min_acceptable}) — skipping")
                pass_log.append(f"pass{pass_num}: wc too low ({new_wc}w)")
                continue

            # Re-score the rewritten content
            new_scored = check_all_rules(
                body_html=rewritten,
                keyword=self.keyword,
                title=self.state.title,
                meta_title=self.state.meta_title,
                meta_desc=self.state.meta_desc,
                page_type=self.page_type,
                **self._scoring_customer_kwargs(),
            )
            new_score = new_scored["percentage"]

            if new_score > current_score:
                html = rewritten
                pass_log.append(f"pass{pass_num}: {current_score}%→{new_score}% ({new_wc}w) via {self.routing.quality_loop.first} ✓")
                log.info(f"Quality loop pass {pass_num}: improved {current_score}%→{new_score}% ({new_wc}w) via {self.routing.quality_loop.first}")
                current_score = new_score

                # Update state
                self.state.final_html = html
                self.state.seo_score = float(new_score)
                self.state.word_count = new_wc

                # Normalize keyword density after each improvement pass (rule-based, no AI)
                try:
                    from engines.humanize.editorial import normalize_keyword_density
                    html = normalize_keyword_density(html, self.keyword)
                    self.state.final_html = html
                except Exception as _ned:
                    log.debug(f"normalize_keyword_density skipped: {_ned}")

                # Update rule results
                self._rule_results = {
                    "percentage": new_score,
                    "total_earned": new_scored["total_earned"],
                    "max_possible": new_scored["max_possible"],
                    "rules": new_scored["rules"],
                    "pillars": new_scored["pillars"],
                    "summary": new_scored["summary"],
                    "checkpoint": f"step11_pass{pass_num}",
                }
                
                # Save checkpoint after successful pass
                if self._checkpoint_mgr:
                    self._checkpoint_mgr.save(
                        self.article_id,
                        step_num=11,  # Quality loop is step 11
                        step_name="Quality Loop",
                        state=self.state,
                        iteration=0,
                        pass_num=pass_num
                    )

                # Persist updated scores to DB
                if self.db:
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        now = _dt.now(_tz.utc).isoformat()
                        self.db.execute(
                            """UPDATE content_articles
                               SET review_score=?, review_breakdown=?, review_notes=?, last_reviewed_at=?
                               WHERE article_id=?""",
                            (
                                new_score,
                                json.dumps({
                                    "categories": new_scored["categories"],
                                    "rules": new_scored["rules"],
                                    "pillars": new_scored["pillars"],
                                }),
                                json.dumps({
                                    "verdict": f"Quality loop pass {pass_num}: {new_score}% ({new_scored['total_earned']}/{new_scored['max_possible']} pts)",
                                    "auto_review": True,
                                    "percentage": new_score,
                                    "quality_loop_pass": pass_num,
                                }),
                                now,
                                self.article_id,
                            )
                        )
                        self.db.commit()
                    except Exception as e:
                        log.warning(f"Quality loop DB update failed: {e}")

                if current_score >= MIN_QUALITY_SCORE and _critical_rules_ok(new_scored["rules"]):
                    log.info(f"Quality loop: target reached at {current_score}% with all critical rules passing after {pass_num} passes")
                    break
                elif current_score >= MIN_QUALITY_SCORE:
                    log.info(f"Quality loop: score {current_score}% ≥ target but critical rules still failing — continuing")
            else:
                pass_log.append(f"pass{pass_num}: no improvement ({new_score}% ≤ {current_score}%)")
                log.info(f"Quality loop pass {pass_num}: no improvement ({new_score}% ≤ {current_score}%)")

        # ── Auto editorial rewrite if score is still below target ─────────────
        if current_score < MIN_QUALITY_SCORE:
            try:
                from engines.humanize.editorial import validate_editorial, editorial_rewrite
                ed_val = validate_editorial(self.state.final_html, keyword=self.keyword)
                if ed_val.get("score", 100) < 80 or ed_val.get("robotic_count", 0) > 2:
                    log.info(f"Quality loop: score {current_score}% < {MIN_QUALITY_SCORE}% + editorial score {ed_val.get('score')} — running editorial rewrite")
                    ed_result = editorial_rewrite(
                        self.state.final_html,
                        keyword=self.keyword,
                        validation_result=ed_val,
                    )
                    if ed_result.get("success") and ed_result.get("html") and len(ed_result["html"].strip()) > 500:
                        from quality.content_rules import check_all_rules as _ed_check
                        ed_scored = _ed_check(
                            body_html=ed_result["html"],
                            keyword=self.keyword,
                            title=self.state.title,
                            meta_title=self.state.meta_title,
                            meta_desc=self.state.meta_desc,
                            page_type=self.page_type,
                            **self._scoring_customer_kwargs(),
                        )
                        if ed_scored["percentage"] >= current_score:
                            self.state.final_html = ed_result["html"]
                            current_score = ed_scored["percentage"]
                            self.state.seo_score = float(current_score)
                            self.state.word_count = len(re.sub(r"<[^>]+>", " ", ed_result["html"]).split())
                            pass_log.append(f"editorial-rewrite: score now {current_score}% ✓")
                            log.info(f"Quality loop editorial rewrite: score now {current_score}%")
                        else:
                            log.info(f"Quality loop editorial rewrite: no improvement ({ed_scored['percentage']}% ≤ {current_score}%) — skipped")
            except Exception as e:
                log.warning(f"Editorial rewrite in quality loop failed (non-fatal): {e}")

        # ── Post-loop fallback: if critical rules still fail, run auto-injection ──
        html = self.state.final_html
        try:
            from quality.content_rules import check_all_rules as _check_final
            _ctx_kw = self._scoring_customer_kwargs()
            final_scored = _check_final(
                body_html=html, keyword=self.keyword, title=self.state.title,
                meta_title=self.state.meta_title, meta_desc=self.state.meta_desc,
                page_type=self.page_type, **_ctx_kw,
            )
            if not _critical_rules_ok(final_scored["rules"]):
                log.info("Quality loop: critical rules still failing after all passes — running post-draft injection")
                html = self._post_draft_inject(html)
                self.state.final_html = html
                # Re-score after injection
                re_scored = _check_final(
                    body_html=html, keyword=self.keyword, title=self.state.title,
                    meta_title=self.state.meta_title, meta_desc=self.state.meta_desc,
                    page_type=self.page_type, **_ctx_kw,
                )
                if re_scored["percentage"] > current_score:
                    current_score = re_scored["percentage"]
                    self.state.seo_score = float(current_score)
                    self.state.word_count = len(re.sub(r"<[^>]+>", " ", html).split())
                    self._rule_results = {
                        "percentage": current_score,
                        "total_earned": re_scored["total_earned"],
                        "max_possible": re_scored["max_possible"],
                        "rules": re_scored["rules"],
                        "pillars": re_scored["pillars"],
                        "summary": re_scored["summary"],
                        "checkpoint": "step11_post_inject",
                    }
                    pass_log.append(f"post-inject: {current_score}% (auto-injection fallback) ✓")
                    log.info(f"Quality loop post-inject: score now {current_score}%")
        except Exception as e:
            log.warning(f"Quality loop post-inject scoring failed: {e}")

        initial_score = self.state.steps[9].details.get("percentage", 0) if len(self.state.steps) > 9 else 0
        step.summary = (
            f"Quality loop: {initial_score}%→{current_score}% "
            f"({len(pass_log)} passes) · "
            f"{'Target reached ✓' if current_score >= MIN_QUALITY_SCORE else f'Best achievable (target {MIN_QUALITY_SCORE}%)'}"
        )
        step.details = {
            "passes": len(pass_log),
            "initial_score": initial_score,
            "final_score": current_score,
            "pass_log": pass_log,
            "target": MIN_QUALITY_SCORE,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # UNIFIED AI ROUTING PRIMITIVES (with AIProviderManager resilience layer)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_json_fields(result: Dict) -> Dict:
        """Normalize list fields (AI sometimes returns list of dicts instead of strings)."""
        def _to_str_list(val):
            if not isinstance(val, list):
                return val
            out = []
            for item in val:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    for k in ("title", "theme", "gap", "angle", "fact", "text", "description"):
                        if isinstance(item.get(k), str):
                            out.append(item[k]); break
                    else:
                        sv = next((v for v in item.values() if isinstance(v, str)), None)
                        if sv:
                            out.append(sv)
            return out
        for fld in ("themes", "gaps", "angles", "key_facts"):
            if fld in result:
                result[fld] = _to_str_list(result[fld])
        return result

    async def _exec_provider_json(
        self, provider: str, prompt: str, system: str,
        temperature: float, max_tokens: int,
    ) -> "_CallResult":
        """Single-attempt JSON call to one provider. Returns CallResult.
        No retries here — the AIProviderManager wraps this with exponential backoff.
        """
        import httpx
        try:
            if provider == "ollama" or provider.startswith("ollama_"):
                ollama_url = self._resolve_ollama_url(provider)
                ollama_model = self._resolve_ollama_model(provider)
                async with _get_ollama_sem():
                    raw = await self._ollama_async(prompt, temperature, max_tokens, ollama_url=ollama_url, ollama_model=ollama_model, http_timeout=360)
                parsed = self._parse_json(raw)
                return _CallResult(
                    success=bool(parsed), provider=provider,
                    data=parsed, status_code=200 if parsed else 200,
                    response_chars=len(raw or ""),
                )
            elif provider == "groq":
                keys = _get_available_keys(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                sys_msg = system or "You are a precise SEO content strategist. Return ONLY valid JSON."
                last_result = None
                for _ki, _key in enumerate(keys):
                    resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                        json={"model": "llama-3.3-70b-versatile",
                              "messages": [{"role": "system", "content": sys_msg},
                                           {"role": "user", "content": prompt}],
                              "temperature": temperature, "max_tokens": max_tokens,
                              "response_format": {"type": "json_object"}},
                        timeout=120,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _update_key_health(_key, headers=hdrs, status_code=200)
                        _clear_key_rate_limit(_key)
                        _resp_json = resp.json()
                        raw = _resp_json["choices"][0]["message"]["content"]
                        _usage = _resp_json.get("usage", {})
                        _inp_tok = _usage.get("prompt_tokens", 0)
                        _out_tok = _usage.get("completion_tokens", 0)
                        parsed = self._parse_json(raw)
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
                                input_tokens=_inp_tok, output_tokens=_out_tok,
                                tokens_used=_inp_tok + _out_tok,
                                model="llama-3.3-70b-versatile",
                            )
                        # Empty/unparseable content — try next key
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} empty response (raw={repr(raw[:120]) if raw else 'None'}), rotating")
                        last_result = _CallResult(
                            success=False, provider=provider, error="empty_response",
                            status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                        )
                        if _ki < len(keys) - 1:
                            continue
                        return last_result
                    err_body = resp.text[:300] if resp.status_code == 429 else ""
                    _update_key_health(_key, headers=hdrs, status_code=resp.status_code, error_body=err_body)
                    if resp.status_code == 429:
                        _mark_key_rate_limited(_key, 5, "429")
                    last_result = _CallResult(
                        success=False, provider=provider,
                        error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                        response_headers=hdrs,
                    )
                    if resp.status_code != 429 or _ki >= len(keys) - 1:
                        break
                    log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating to next account")
                return last_result
            elif provider in ("gemini", "gemini_free", "gemini_paid"):
                keys = _get_available_keys("gemini")
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                full = f"{system}\n\n{prompt}" if system else prompt
                last_result = None
                for _ki, _key in enumerate(keys):
                    try:
                        raw = await asyncio.get_event_loop().run_in_executor(
                            None, lambda k=_key, p=full: self._gemini_sync_single_key(p, temperature, k)
                        )
                        parsed = self._parse_json(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
                        if parsed:
                            _clear_key_rate_limit(_key)
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200,
                                response_chars=len(str(raw or "")),
                            )
                        last_result = _CallResult(
                            success=False, provider=provider, error="empty_response",
                            status_code=200, response_chars=len(str(raw or "")),
                        )
                        if _ki < len(keys) - 1:
                            log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} empty response, rotating to next GCP project")
                            continue
                    except _GeminiKeyRateLimited:
                        _mark_key_rate_limited(_key, 60, "429")
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} rate-limited, rotating to next GCP project")
                        last_result = _CallResult(
                            success=False, provider=provider, error="HTTP 429",
                            status_code=429,
                        )
                        if _ki < len(keys) - 1:
                            continue
                    except Exception as e:
                        last_result = _CallResult(
                            success=False, provider=provider, error=str(e)[:100],
                            status_code=500,
                        )
                        if _ki < len(keys) - 1:
                            continue
                return last_result or _CallResult(success=False, provider=provider, error="all_keys_exhausted")
            elif provider in ("chatgpt", "openai", "openai_paid"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                sys_msg = system or "You are a precise SEO content strategist. Return ONLY valid JSON."
                last_result = None
                for _ki, _key in enumerate(keys):
                    resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                        json={"model": os.getenv("OPENAI_MODEL", "gpt-4o"), "messages": [
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": prompt},
                        ], "temperature": temperature, "max_tokens": max_tokens},
                        timeout=120,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _resp_json = resp.json()
                        raw = _resp_json["choices"][0]["message"]["content"]
                        _usage = _resp_json.get("usage", {})
                        _inp_tok = _usage.get("prompt_tokens", 0)
                        _out_tok = _usage.get("completion_tokens", 0)
                        _oai_model = _resp_json.get("model", os.getenv("OPENAI_MODEL", "gpt-4o"))
                        parsed = self._parse_json(raw) if raw else {}
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
                                input_tokens=_inp_tok, output_tokens=_out_tok,
                                tokens_used=_inp_tok + _out_tok, model=_oai_model,
                            )
                        last_result = _CallResult(
                            success=False, provider=provider, error="empty_response",
                            status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                        )
                        if _ki < len(keys) - 1:
                            log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} empty response, rotating")
                            continue
                        return last_result
                    last_result = _CallResult(
                        success=False, provider=provider,
                        error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                        response_headers=hdrs,
                    )
                    if resp.status_code != 429 or _ki >= len(keys) - 1:
                        break
                    log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating")
                return last_result
            elif provider in ("claude", "anthropic", "anthropic_paid"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                sys_msg = system or "You are a precise SEO content strategist. Return ONLY valid JSON."
                last_result = None
                for _ki, _key in enumerate(keys):
                    resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": k, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                        json={"model": _live_claude_model(), "max_tokens": max_tokens, "system": sys_msg,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=120,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _resp_json = resp.json()
                        raw = _resp_json["content"][0]["text"]
                        _usage = _resp_json.get("usage", {})
                        _inp_tok = _usage.get("input_tokens", 0)
                        _out_tok = _usage.get("output_tokens", 0)
                        _claude_model = _resp_json.get("model", _live_claude_model())
                        parsed = self._parse_json(raw) if raw else {}
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
                                input_tokens=_inp_tok, output_tokens=_out_tok,
                                tokens_used=_inp_tok + _out_tok, model=_claude_model,
                            )
                        last_result = _CallResult(
                            success=False, provider=provider, error="empty_response",
                            status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                        )
                        if _ki < len(keys) - 1:
                            log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} empty response, rotating")
                            continue
                        return last_result
                    last_result = _CallResult(
                        success=False, provider=provider,
                        error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                        response_headers=hdrs,
                    )
                    if resp.status_code != 429 or _ki >= len(keys) - 1:
                        break
                    log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating")
                return last_result
            elif provider == "openrouter" or provider.startswith("or_"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                model = _resolve_openrouter_model(provider)
                _adj_tokens = _or_adjust_max_tokens(provider, max_tokens)
                sys_msg = system or "You are a precise SEO content strategist. Return ONLY valid JSON."
                last_result = None
                _max_retries = 2  # All OR models retry on 429 or empty_response
                for _attempt in range(_max_retries + 1):
                    for _ki, _key in enumerate(keys):
                        resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key, m=model: httpx.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                            json={"model": m, "messages": [
                                {"role": "system", "content": sys_msg},
                                {"role": "user", "content": prompt},
                            ], "temperature": temperature, "max_tokens": _adj_tokens},
                            timeout=120,
                        ))
                        hdrs = dict(resp.headers)
                        if resp.status_code == 200:
                            body = resp.json()
                            # Check for error-in-200 (OpenRouter wraps upstream errors)
                            if body.get("error"):
                                err_msg = body["error"].get("message", "")
                                err_code = body["error"].get("code", 0)
                                # Skip retries for daily/account rate limits (won't clear with waiting)
                                _is_daily_limit = any(x in err_msg.lower() for x in ["daily", "per day", "quota exceeded"])
                                if err_code == 429 and _attempt < _max_retries and not _is_daily_limit:
                                    log.warning(f"[OR] {provider} upstream 429 (attempt {_attempt+1}), waiting 5s")
                                    await asyncio.sleep(5)
                                    break  # break inner loop, retry via outer loop
                                if _is_daily_limit:
                                    log.warning(f"[OR] {provider} daily limit hit, skipping retries: {err_msg[:100]}")
                                last_result = _CallResult(
                                    success=False, provider=provider, error=f"upstream_{err_code}: {err_msg[:120]}",
                                    status_code=err_code or 200, response_headers=hdrs,
                                )
                                if _ki < len(keys) - 1:
                                    continue
                                return last_result
                            # Extract content — handle reasoning models (content can be null)
                            choice = body.get("choices", [{}])[0]
                            _finish = choice.get("finish_reason", "")
                            raw = choice.get("message", {}).get("content") or ""
                            if not raw:
                                # Try reasoning field (DeepSeek R1 etc.)
                                reasoning = choice.get("message", {}).get("reasoning") or ""
                                if reasoning:
                                    raw = reasoning
                            # Also try to extract JSON from reasoning if content has none
                            if raw and not re.search(r"\{[\s\S]*\}", raw):
                                reasoning = choice.get("message", {}).get("reasoning") or ""
                                if reasoning and re.search(r"\{[\s\S]*\}", reasoning):
                                    raw = reasoning
                            _or_usage = body.get("usage", {})
                            _inp_tok = _or_usage.get("prompt_tokens", 0)
                            _out_tok = _or_usage.get("completion_tokens", 0)
                            parsed = self._parse_json(raw) if raw else {}
                            if parsed:
                                return _CallResult(
                                    success=True, provider=provider,
                                    data=parsed, status_code=200, response_chars=len(raw or ""),
                                    response_headers=hdrs,
                                    input_tokens=_inp_tok, output_tokens=_out_tok,
                                    tokens_used=_inp_tok + _out_tok, model=model,
                                )
                            _trunc = " [TRUNCATED — finish_reason=length]" if _finish == "length" else ""
                            log.warning(f"[OR] {provider} empty/unparseable{_trunc} (raw={repr((raw or '')[:200])})")
                            last_result = _CallResult(
                                success=False, provider=provider, error="empty_response",
                                status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                            )
                            if _ki < len(keys) - 1:
                                continue
                            # Retry on empty_response — model may have glitched
                            if _attempt < _max_retries:
                                log.warning(f"[OR] {provider} empty_response (attempt {_attempt+1}), retrying in 3s")
                                await asyncio.sleep(3)
                                break  # break inner loop → outer retry
                            return last_result
                        # Non-200 error
                        last_result = _CallResult(
                            success=False, provider=provider,
                            error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                            response_headers=hdrs,
                        )
                        if resp.status_code == 429 and _attempt < _max_retries:
                            log.warning(f"[OR] {provider} HTTP 429 (attempt {_attempt+1}), waiting 5s")
                            await asyncio.sleep(5)
                            break  # retry via outer loop
                        if resp.status_code != 429 or _ki >= len(keys) - 1:
                            return last_result
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating")
                    else:
                        # Inner loop completed without break = didn't hit 429 retry
                        break
                return last_result
            return _CallResult(success=False, provider=provider, error=f"unknown_provider: {provider}")
        except Exception as e:
            err = str(e)
            sc = 429 if "429" in err else (503 if "503" in err else 0)
            return _CallResult(success=False, provider=provider, error=err[:300], status_code=sc)

    async def _exec_provider_raw(
        self, provider: str, prompt: str, temperature: float,
        max_tokens: int, use_prompt_directly: bool,
    ) -> "_CallResult":
        """Single-attempt raw (HTML) call to one provider. Returns CallResult.
        No retries here — the AIProviderManager wraps this with exponential backoff.
        """
        import httpx
        try:
            if provider in ("gemini", "gemini_free", "gemini_paid"):
                keys = _get_available_keys("gemini")
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                last_result = None
                for _ki, _key in enumerate(keys):
                    try:
                        raw = await asyncio.get_event_loop().run_in_executor(
                            None, lambda k=_key: self._gemini_sync_single_key(prompt, temperature, k)
                        )
                        ok = bool(raw and len(raw) > 200)
                        if ok:
                            _clear_key_rate_limit(_key)
                            return _CallResult(
                                success=True, provider=provider, data=raw,
                                status_code=200, response_chars=len(raw or ""),
                            )
                        last_result = _CallResult(
                            success=False, provider=provider, data=raw or "",
                            error="empty_response", status_code=200, response_chars=len(raw or ""),
                        )
                        if _ki < len(keys) - 1:
                            log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} short response, rotating to next GCP project")
                            continue
                    except _GeminiKeyRateLimited:
                        _mark_key_rate_limited(_key, 60, "429")
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} rate-limited, rotating to next GCP project")
                        last_result = _CallResult(
                            success=False, provider=provider, error="HTTP 429",
                            status_code=429,
                        )
                        if _ki < len(keys) - 1:
                            continue
                    except Exception as e:
                        last_result = _CallResult(
                            success=False, provider=provider, error=str(e)[:100],
                            status_code=500,
                        )
                        if _ki < len(keys) - 1:
                            continue
                return last_result or _CallResult(success=False, provider=provider, error="all_keys_exhausted")
            elif provider == "groq":
                keys = _get_available_keys(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                last_result = None
                for _ki, _key in enumerate(keys):
                    resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                        json={
                            "model": "llama-3.3-70b-versatile",
                            "messages": [
                                {"role": "system", "content": "You are a senior SEO content writer. Output ONLY clean HTML. No markdown, no code fences."},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": temperature, "max_tokens": max_tokens,
                        },
                        timeout=120,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _update_key_health(_key, headers=hdrs, status_code=200)
                        _clear_key_rate_limit(_key)
                        _resp_j = resp.json()
                        raw = _resp_j["choices"][0]["message"]["content"]
                        _usage = _resp_j.get("usage", {})
                        _inp_tok = _usage.get("prompt_tokens", 0)
                        _out_tok = _usage.get("completion_tokens", 0)
                        ok = bool(raw and len(raw) > 200)
                        if ok:
                            return _CallResult(
                                success=True, provider=provider, data=raw,
                                status_code=200, response_chars=len(raw),
                                response_headers=hdrs,
                                input_tokens=_inp_tok, output_tokens=_out_tok,
                                tokens_used=_inp_tok + _out_tok,
                                model="llama-3.3-70b-versatile",
                            )
                        last_result = _CallResult(
                            success=False, provider=provider, error="empty_response",
                            status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                        )
                        if _ki < len(keys) - 1:
                            log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} empty response, rotating")
                            continue
                        return last_result
                    err_body = resp.text[:300] if resp.status_code == 429 else ""
                    _update_key_health(_key, headers=hdrs, status_code=resp.status_code, error_body=err_body)
                    if resp.status_code == 429:
                        _mark_key_rate_limited(_key, 5, "429")
                    last_result = _CallResult(
                        success=False, provider=provider,
                        error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                        response_headers=hdrs,
                    )
                    if resp.status_code != 429 or _ki >= len(keys) - 1:
                        break
                    log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating to next account")
                return last_result
            elif provider == "ollama" or provider.startswith("ollama_"):
                ollama_url = self._resolve_ollama_url(provider)
                ollama_model = self._resolve_ollama_model(provider)
                # Always send the actual prompt to Ollama (raw_text=True).
                # The old code only did this when use_prompt_directly=True,
                # otherwise it called _ollama_section_writer which ignores
                # the prompt and regenerates from scratch — wasteful.
                _ollama_prompt = prompt
                if not use_prompt_directly and len(prompt) > 6000:
                    _ollama_prompt = prompt[:2000] + "\n\n" + prompt[2000:6000] + "\n\n[Content truncated for model context limit]\n\nOutput ONLY the improved HTML article. No commentary."
                async with _get_ollama_sem():
                    raw = await self._ollama_async(_ollama_prompt, temperature, max_tokens, raw_text=True, ollama_url=ollama_url, ollama_model=ollama_model, http_timeout=480)
                ok = bool(raw and len(raw) > 200)
                return _CallResult(
                    success=ok, provider=provider, data=raw or "",
                    status_code=200, response_chars=len(raw or ""),
                )
            elif provider in ("chatgpt", "openai", "openai_paid"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                if use_prompt_directly:
                    last_result = None
                    for _ki, _key in enumerate(keys):
                        resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                            json={"model": OPENAI_MODEL, "messages": [
                                {"role": "system", "content": "You are a senior SEO content writer. Output ONLY clean HTML. No markdown, no code fences."},
                                {"role": "user", "content": prompt},
                            ], "temperature": temperature, "max_tokens": max_tokens},
                            timeout=120,
                        ))
                        hdrs = dict(resp.headers)
                        if resp.status_code == 200:
                            raw = resp.json()["choices"][0]["message"]["content"]
                            _usage = resp.json().get("usage", {})
                            _inp_tok = _usage.get("prompt_tokens", 0)
                            _out_tok = _usage.get("completion_tokens", 0)
                            ok = bool(raw and len(raw) > 200)
                            if ok:
                                return _CallResult(
                                    success=True, provider=provider, data=raw,
                                    status_code=200, response_chars=len(raw),
                                    response_headers=hdrs,
                                    input_tokens=_inp_tok, output_tokens=_out_tok,
                                    tokens_used=_inp_tok + _out_tok,
                                    model=OPENAI_MODEL,
                                )
                            last_result = _CallResult(
                                success=False, provider=provider, error="empty_response",
                                status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
                            )
                            if _ki < len(keys) - 1:
                                log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} raw empty, rotating")
                                continue
                            return last_result
                        last_result = _CallResult(
                            success=False, provider=provider,
                            error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                            response_headers=hdrs,
                        )
                        if resp.status_code != 429 or _ki >= len(keys) - 1:
                            break
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating")
                    return last_result
                else:
                    raw = await self._chatgpt_polish(self.state.draft_html or "", api_key=keys[0])
                    ok = bool(raw and len(raw) > 200)
                    return _CallResult(success=ok, provider=provider, data=raw or "", status_code=200, response_chars=len(raw or ""))
            elif provider in ("claude", "anthropic", "anthropic_paid"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                for _ki, _key in enumerate(keys):
                    raw = await self._claude_raw(prompt, max_tokens=max_tokens, api_key=_key)
                    ok = bool(raw and len(raw) > 200)
                    if ok or _ki >= len(keys) - 1:
                        return _CallResult(success=ok, provider=provider, data=raw or "", status_code=200, response_chars=len(raw or ""))
                    log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} failed, trying next")
                return _CallResult(success=False, provider=provider, error="all_keys_exhausted")
            elif provider == "openrouter" or provider.startswith("or_"):
                keys = _resolve_key_pool(provider)
                if not keys:
                    return _CallResult(success=False, provider=provider, error="no_api_key")
                model = _resolve_openrouter_model(provider)
                _adj_tokens = _or_adjust_max_tokens(provider, max_tokens)
                last_result = None
                _max_retries = 2 if ":free" in model else 0
                for _attempt in range(_max_retries + 1):
                    for _ki, _key in enumerate(keys):
                        resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key, m=model: httpx.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                            json={"model": m, "messages": [
                                {"role": "system", "content": "You are a senior SEO content writer. Output ONLY clean HTML. No markdown, no code fences."},
                                {"role": "user", "content": prompt},
                            ], "temperature": temperature, "max_tokens": _adj_tokens},
                            timeout=120,
                        ))
                        hdrs = dict(resp.headers)
                        if resp.status_code == 200:
                            body = resp.json()
                            if body.get("error"):
                                err_code = body["error"].get("code", 0)
                                err_msg = body["error"].get("message", "")
                                _is_daily_limit = any(x in err_msg.lower() for x in ["daily", "per day", "quota exceeded"])
                                if err_code == 429 and _attempt < _max_retries and not _is_daily_limit:
                                    log.warning(f"[OR-raw] {provider} upstream 429 (attempt {_attempt+1}), waiting 5s")
                                    await asyncio.sleep(5)
                                    break
                                if _is_daily_limit:
                                    log.warning(f"[OR-raw] {provider} daily limit hit, skipping retries: {err_msg[:100]}")
                                last_result = _CallResult(
                                    success=False, provider=provider, error=f"upstream_{err_code}: {err_msg[:120]}",
                                    status_code=err_code or 200, response_headers=hdrs,
                                )
                                if _ki < len(keys) - 1:
                                    continue
                                return last_result
                            choice = body.get("choices", [{}])[0]
                            raw = choice.get("message", {}).get("content") or ""
                            if not raw:
                                # Reasoning models may put answer in reasoning field
                                reasoning = choice.get("message", {}).get("reasoning") or ""
                                if reasoning:
                                    raw = reasoning
                            _or_usage = body.get("usage", {})
                            _inp_tok = _or_usage.get("prompt_tokens", 0)
                            _out_tok = _or_usage.get("completion_tokens", 0)
                            # Strip reasoning preamble from content (o4-mini etc.)
                            if raw and provider in _OR_REASONING_MODELS:
                                # Remove bold thinking headers like "**Thinking about...**\n\n"
                                raw = re.sub(r'^\*\*[^*]+\*\*\s*\n+', '', raw).strip()
                            ok = bool(raw and len(raw) > 200)
                            if ok:
                                return _CallResult(
                                    success=True, provider=provider, data=raw,
                                    status_code=200, response_chars=len(raw),
                                    response_headers=hdrs,
                                    input_tokens=_inp_tok, output_tokens=_out_tok,
                                    tokens_used=_inp_tok + _out_tok, model=model,
                                )
                            last_result = _CallResult(
                                success=False, provider=provider, error="empty_response",
                                status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
                            )
                            if _ki < len(keys) - 1:
                                log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} raw empty, rotating")
                                continue
                            return last_result
                        last_result = _CallResult(
                            success=False, provider=provider,
                            error=f"HTTP {resp.status_code}", status_code=resp.status_code,
                            response_headers=hdrs,
                        )
                        if resp.status_code == 429 and _attempt < _max_retries:
                            log.warning(f"[OR-raw] {provider} HTTP 429 (attempt {_attempt+1}), waiting 5s")
                            await asyncio.sleep(5)
                            break
                        if resp.status_code != 429 or _ki >= len(keys) - 1:
                            return last_result
                        log.warning(f"[KeyRotation] {provider} key {_ki+1}/{len(keys)} got 429, rotating")
                    else:
                        break
                return last_result
            return _CallResult(success=False, provider=provider, error=f"unknown_provider: {provider}")
        except Exception as e:
            err = str(e)
            sc = 429 if "429" in err else (503 if "503" in err else 0)
            return _CallResult(success=False, provider=provider, error=err[:300], status_code=sc)

    async def _call_ai_with_chain(
        self,
        cfg: StepAIConfig,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Dict:
        """
        Parallel-race AI execution for JSON responses.
        All available providers race simultaneously; first valid JSON response wins.
        Remaining tasks are cancelled.

        Uses AIProviderManager for: rate limiting, circuit breakers, exponential
        backoff with jitter, per-call metrics, and audit logging with trace IDs.
        """
        mgr = _APM.get_instance()
        trace_id = self._pipeline_trace_id
        HARD_TIMEOUT = 420  # seconds per provider (Ollama remote ~6.4 tok/s needs ~170s for structure, ~300s for drafts)

        # ── Build ordered list of available providers ──────────────────────
        chain = [p for p in [cfg.first, cfg.second, cfg.third]
                 if p and p != "skip"]
        available = []
        for provider in chain:
            if not _is_provider_available(provider):
                self._add_log("warn", f"AI {provider}: skipped (cooldown/disabled)")
                continue
            available.append(provider)

        # ── EMERGENCY FALLBACK: if user's chain is fully exhausted, try
        # known-working providers before failing the entire pipeline ──
        if not available:
            emergency = _build_emergency_chain(exclude=set(chain))
            if emergency:
                self._add_log("warn",
                    f"User chain [{', '.join(chain) or 'empty'}] all unavailable — "
                    f"using emergency fallback: {' → '.join(emergency)}"
                )
                available = emergency

        if not available:
            # No providers available AT ALL (chain disabled + emergency exhausted).
            # No retry can possibly succeed without user changing routing or
            # provider state, so halt the pipeline immediately instead of
            # generating empty content downstream.
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            self._add_log(
                "error",
                "No AI providers available (configured chain + emergency fallback all unavailable). "
                "Stopping pipeline — change routing in AI Hub or re-enable providers.",
            )
            raise RuntimeError(
                "No AI providers available — pipeline stopped. "
                "Configured routing chain is empty/disabled and emergency fallback is exhausted. "
                "Change AI routing in AI Hub or re-enable providers."
            )

        # ── Provider execution with hard timeout ──────────────────────────
        async def _run_provider(provider: str) -> Dict:
            try:
                async def _do_call(request_id, _p=provider):
                    return await self._exec_provider_json(
                        _p, prompt, system, temperature, max_tokens
                    )
                cr = await asyncio.wait_for(
                    mgr.call(provider, _do_call, trace_id=trace_id, prompt_chars=len(prompt)),
                    timeout=HARD_TIMEOUT,
                )
                if cr.success and cr.json_data:
                    self._add_log("success", f"AI {provider}: succeeded (JSON) [{cr.request_id}]")
                    _mark_provider_ok(provider)
                    self._consecutive_all_failed = 0  # Reset on success
                    try:
                        _log_usage(provider, json.dumps(cr.json_data) if cr.json_data else "",
                                   input_tokens=cr.input_tokens, output_tokens=cr.output_tokens,
                                   model=cr.model, db=self.db)
                    except Exception:
                        pass  # Never let logging break the pipeline
                    return self._normalize_json_fields(cr.json_data)
                # Log failure
                if cr.error == "circuit_breaker_open":
                    self._add_log("warn", f"AI {provider}: circuit breaker OPEN [{cr.request_id}]")
                elif cr.status_code == 429:
                    self._add_log("error", f"AI {provider}: 429 rate limited (all keys exhausted) [{cr.request_id}]")
                    # Short provider-level cooldown — per-key tracking handles individual key recovery
                    _mark_provider_bad(provider, "rate_limited", 15)
                elif "credit" in (cr.error or "").lower() or "balance" in (cr.error or "").lower():
                    self._add_log("error", f"AI {provider}: credit issue [{cr.request_id}]")
                    _mark_provider_bad(provider, "credit_issue", 600)
                elif cr.error == "no_api_key":
                    self._add_log("warn", f"AI {provider}: all keys rate-limited [{cr.request_id}]")
                elif cr.error == "empty_response" and (provider.startswith("or_") or provider == "openrouter"):
                    # OR empty_response is transient — short cooldown so next step can retry
                    self._add_log("warn", f"AI {provider}: empty_response (transient) [{cr.request_id}]")
                    _mark_provider_bad(provider, "error", 5)
                elif cr.error:
                    self._add_log("warn", f"AI {provider}: {cr.error[:100]} [{cr.request_id}]")
                    _mark_provider_bad(provider, "error", 30)
                else:
                    self._add_log("warn", f"AI {provider}: empty response [{cr.request_id}]")
            except asyncio.TimeoutError:
                self._add_log("error", f"AI {provider}: hard timeout ({HARD_TIMEOUT}s)")
                _mark_provider_bad(provider, "timeout", 15)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._add_log("error", f"AI {provider}: {str(e)[:100]}")
                _mark_provider_bad(provider, "error", 30)
            return {}

        # ── Sequential fallback for OR free-tier (avoid parallel 429 burst) ──
        all_or = all(p.startswith("or_") or p == "openrouter" for p in available)
        if all_or:
            for p in available:
                data = await _run_provider(p)
                if data:
                    self._consecutive_all_failed = 0
                    return data
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            if self._consecutive_all_failed >= 2:
                self._add_log("error", "All AI providers failed 2+ times — stopping pipeline. Change your AI routing in AI Hub and restart.")
                raise RuntimeError("All AI providers exhausted — pipeline stopped. Please change AI routing in AI Hub.")
            self._add_log("error", "All AI providers failed for this request")
            return {}

        # ── Parallel race: launch all, take first success ─────────────────
        tasks = {asyncio.create_task(_run_provider(p)): p for p in available}
        result = {}
        # Overall race deadline = HARD_TIMEOUT * 1.5 to bound worst-case wait
        # when every provider is slow. Without this, race can hang for
        # HARD_TIMEOUT * len(providers) seconds.
        race_deadline = HARD_TIMEOUT * 1.5
        race_start = asyncio.get_event_loop().time()
        try:
            remaining = set(tasks.keys())
            while remaining:
                elapsed = asyncio.get_event_loop().time() - race_start
                wait_budget = max(1.0, race_deadline - elapsed)
                done, remaining = await asyncio.wait(
                    remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=wait_budget,
                )
                if not done:
                    log.warning(
                        f"JSON chain race: overall deadline {race_deadline}s reached, cancelling pending"
                    )
                    for t in remaining:
                        t.cancel()
                    break
                for task in done:
                    try:
                        data = task.result()
                        # Reject error-envelope responses ({"error": "..."}, status=error, success=False)
                        # so a slower-but-real success can still win the race.
                        if data and _is_valid_json_response(data):
                            result = data
                            for t in remaining:
                                t.cancel()
                            remaining = set()
                            break
                    except Exception:
                        continue
                if result:
                    break
        except Exception as e:
            log.warning(f"JSON chain race error: {e}")

        if result:
            self._consecutive_all_failed = 0
        else:
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            if self._consecutive_all_failed >= 2:
                self._add_log("error", "All AI providers failed 2+ times — stopping pipeline. Change your AI routing in AI Hub and restart.")
                raise RuntimeError("All AI providers exhausted — pipeline stopped. Please change AI routing in AI Hub.")
            self._add_log("error", "All AI providers failed for this request")
        return result

    async def _call_ai_raw_with_chain(
        self,
        cfg: StepAIConfig,
        prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 6000,
        use_prompt_directly: bool = False,
    ) -> str:
        """
        Parallel-race AI execution for long-form HTML generation.
        All available providers race simultaneously; first valid response (>200 chars) wins.
        Remaining tasks are cancelled. Falls back to sequential on race failure.

        Uses AIProviderManager for: rate limiting, circuit breakers, exponential
        backoff with jitter, per-call metrics, and audit logging with trace IDs.
        """
        mgr = _APM.get_instance()
        trace_id = self._pipeline_trace_id
        HARD_TIMEOUT = 540  # seconds per provider (Ollama remote ~6.4 tok/s, full drafts can need 400s+)

        # ── Build ordered list of available providers ──────────────────────
        chain = [p for p in [cfg.first, cfg.second, cfg.third]
                 if p and p != "skip"]
        available = []
        for provider in chain:
            if not _is_provider_available(provider):
                self._add_log("warn", f"AI {provider}: skipped (cooldown/disabled)")
                continue
            available.append(provider)

        # ── EMERGENCY FALLBACK: if user's chain is fully exhausted, try
        # known-working providers before failing the entire pipeline ──
        if not available:
            emergency = _build_emergency_chain(exclude=set(chain))
            if emergency:
                self._add_log("warn",
                    f"User chain [{', '.join(chain) or 'empty'}] all unavailable — "
                    f"using emergency fallback: {' → '.join(emergency)}"
                )
                available = emergency

        if not available:
            # No providers available AT ALL — halt immediately (see twin
            # comment in `_call_ai_with_chain` for rationale).
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            self._add_log(
                "error",
                "No AI providers available for raw content generation (configured chain + "
                "emergency fallback all unavailable). Stopping pipeline — change routing in AI Hub.",
            )
            raise RuntimeError(
                "No AI providers available — pipeline stopped. "
                "Configured routing chain is empty/disabled and emergency fallback is exhausted. "
                "Change AI routing in AI Hub or re-enable providers."
            )

        # ── Provider execution with hard timeout ──────────────────────────
        async def _run_provider(provider: str) -> str:
            try:
                async def _do_call(request_id, _p=provider):
                    return await self._exec_provider_raw(
                        _p, prompt, temperature, max_tokens, use_prompt_directly
                    )
                cr = await asyncio.wait_for(
                    mgr.call(provider, _do_call, trace_id=trace_id, prompt_chars=len(prompt)),
                    timeout=HARD_TIMEOUT,
                )
                if cr.success and cr.text and len(cr.text) > 200:
                    self._add_log("success", f"AI {provider}: succeeded ({len(cr.text)} chars) [{cr.request_id}]")
                    _mark_provider_ok(provider)
                    self._consecutive_all_failed = 0  # Reset on success
                    try:
                        _log_usage(provider, cr.text,
                                   input_tokens=cr.input_tokens, output_tokens=cr.output_tokens,
                                   model=cr.model, db=self.db)
                    except Exception:
                        pass  # Never let logging break the pipeline
                    return cr.text
                # Log failure reason
                self._log_chain_failure(provider, cr)
            except asyncio.TimeoutError:
                self._add_log("error", f"AI {provider}: hard timeout ({HARD_TIMEOUT}s)")
                _mark_provider_bad(provider, "timeout", 15)
            except asyncio.CancelledError:
                pass  # normal — another provider won the race
            except Exception as e:
                self._add_log("error", f"AI {provider}: {str(e)[:100]}")
                _mark_provider_bad(provider, "error", 30)
            return ""

        # ── Sequential fallback for OR free-tier (avoid parallel 429 burst) ──
        all_or = all(p.startswith("or_") or p == "openrouter" for p in available)
        if all_or:
            for p in available:
                text = await _run_provider(p)
                if text:
                    self._consecutive_all_failed = 0
                    return text
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            if self._consecutive_all_failed >= 2:
                self._add_log("error", "All AI providers failed 2+ times — stopping pipeline. Change your AI routing in AI Hub and restart.")
                raise RuntimeError("All AI providers exhausted — pipeline stopped. Please change AI routing in AI Hub.")
            self._add_log("error", "All AI providers failed for raw content generation")
            return ""

        # ── Parallel race: launch all, take first success ─────────────────
        tasks = {asyncio.create_task(_run_provider(p)): p for p in available}
        result = ""
        race_deadline = HARD_TIMEOUT * 1.5
        race_start = asyncio.get_event_loop().time()
        try:
            remaining = set(tasks.keys())
            while remaining:
                elapsed = asyncio.get_event_loop().time() - race_start
                wait_budget = max(1.0, race_deadline - elapsed)
                done, remaining = await asyncio.wait(
                    remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=wait_budget,
                )
                if not done:
                    log.warning(
                        f"Raw chain race: overall deadline {race_deadline}s reached, cancelling pending"
                    )
                    for t in remaining:
                        t.cancel()
                    break
                for task in done:
                    try:
                        text = task.result()
                        if text:
                            result = text
                            # Cancel all remaining tasks
                            for t in remaining:
                                t.cancel()
                            remaining = set()
                            break
                    except Exception:
                        continue
                if result:
                    break
        except Exception as e:
            log.warning(f"Raw chain race error: {e}")

        if result:
            self._consecutive_all_failed = 0
        else:
            self._consecutive_all_failed = getattr(self, "_consecutive_all_failed", 0) + 1
            if self._consecutive_all_failed >= 2:
                self._add_log("error", "All AI providers failed 2+ times — stopping pipeline. Change your AI routing in AI Hub and restart.")
                raise RuntimeError("All AI providers exhausted — pipeline stopped. Please change AI routing in AI Hub.")
            self._add_log("error", "All AI providers failed for raw content generation")
        return result

    def _log_chain_failure(self, provider: str, cr):
        """Log a chain failure with appropriate severity."""
        if cr.error == "circuit_breaker_open":
            self._add_log("warn", f"AI {provider}: circuit breaker OPEN [{cr.request_id}]")
        elif cr.status_code == 429:
            self._add_log("error", f"AI {provider}: 429 rate limited (all keys exhausted) [{cr.request_id}]")
            # Short provider-level cooldown — per-key tracking handles individual key recovery
            _mark_provider_bad(provider, "rate_limited", 15)
        elif "credit" in (cr.error or "").lower():
            self._add_log("error", f"AI {provider}: credit issue [{cr.request_id}]")
            _mark_provider_bad(provider, "credit_issue", 600)
        elif cr.text and len(cr.text) <= 200:
            self._add_log("warn", f"AI {provider}: response too short (<200 chars) [{cr.request_id}]")
        elif cr.error and cr.error != "no_api_key":
            self._add_log("warn", f"AI {provider}: {cr.error[:100]} [{cr.request_id}]")
            # OR empty_response is transient — short cooldown so next step can use it
            if cr.error == "empty_response" and (provider.startswith("or_") or provider == "openrouter"):
                _mark_provider_bad(provider, "error", 5)
            else:
                _mark_provider_bad(provider, "error", 60)
        else:
            self._add_log("warn", f"AI {provider}: empty response [{cr.request_id}]")

    # ─────────────────────────────────────────────────────────────────────────
    # AI HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    async def _draft_raw(self, prompt: str, temperature: float = 0.6,
                         max_tokens: int = 6000) -> str:
        """Generate long-form draft content.
        Strategy: Gemini first (per-key rotation across GCP projects),
        then Groq (per-key rotation across accounts), then Ollama section writer.
        """
        # Try Gemini first — higher output limits, per-key rotation across GCP projects
        gemini_keys = _get_available_keys("gemini")
        for _ki, _key in enumerate(gemini_keys):
            try:
                log.info(f"Draft: trying Gemini key {_ki+1}/{len(gemini_keys)}")
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda k=_key: self._gemini_sync_single_key(prompt, temperature, k)
                )
                if result and len(result) > 200:
                    _clear_key_rate_limit(_key)
                    log.info(f"Draft: Gemini succeeded ({len(result)} chars)")
                    return result
            except _GeminiKeyRateLimited:
                _mark_key_rate_limited(_key, 60, "429")
                log.warning(f"Draft: Gemini key {_ki+1}/{len(gemini_keys)} rate-limited, trying next GCP project")
                continue
            except Exception as e:
                log.warning(f"Draft: Gemini key {_ki+1} failed ({e})")
                continue
        if gemini_keys:
            log.warning("Draft: all Gemini keys exhausted, trying Groq")

        # Groq fallback — per-key rotation across accounts
        import httpx
        groq_keys = _get_available_keys("groq")
        req_json = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a senior SEO content writer. Output ONLY clean HTML. No markdown, no code fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        for _ki, _key in enumerate(groq_keys):
            try:
                resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key: httpx.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                    json=req_json, timeout=120,
                ))
                if resp.status_code == 200:
                    _clear_key_rate_limit(_key)
                    text = resp.json()["choices"][0]["message"]["content"]
                    log.info(f"Draft: Groq succeeded ({len(text)} chars)")
                    return text
                if resp.status_code == 429:
                    _mark_key_rate_limited(_key, 45, "429")
                    log.warning(f"Draft: Groq key {_ki+1}/{len(groq_keys)} got 429, rotating")
                    continue
                log.warning(f"Draft: Groq returned {resp.status_code}, trying next key")
            except Exception as e:
                log.warning(f"Draft: Groq key {_ki+1} failed ({e})")

        # Last resort — Ollama section-by-section writer
        return await self._ollama_section_writer(ollama_url=_live_ollama_url())

    async def _groq(self, system: str, user: str, temperature: float = 0.4,
                    max_tokens: int = 1500) -> Dict:
        """Call Groq, return parsed JSON dict. Falls back to {} on failure."""
        try:
            raw = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._groq_sync(system, user, temperature, max_tokens)
            )
            return self._parse_json(raw)
        except Exception as e:
            log.warning(f"Groq JSON call failed: {e}")
            return {}

    def _groq_sync(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        import httpx
        keys = _get_available_keys("groq")
        if not keys:
            keys = _sort_keys_by_health(_resolve_key_pool("groq"))
        if not keys:
            raise Exception("No Groq API keys available")
        req_json = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        for _ki, _key in enumerate(keys):
            headers = {"Authorization": f"Bearer {_key}", "Content-Type": "application/json"}
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers=headers, json=req_json, timeout=60)
            if r.status_code == 200:
                _update_key_health(_key, headers=dict(r.headers), status_code=200)
                _clear_key_rate_limit(_key)
                _mark_provider_ok("groq")
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code == 429:
                _mark_key_rate_limited(_key, 45, "429")
                _update_key_health(_key, headers=dict(r.headers), status_code=429, error_body=r.text[:300])
                if _ki < len(keys) - 1:
                    log.warning(f"[KeyRotation] groq key {_ki+1}/{len(keys)} got 429, rotating to next account")
                    continue
                # Last key — try short wait+retry
                wait = self._groq_parse_retry_wait(r)
                if wait and wait <= 8:
                    log.info(f"Groq 429 (last key) — waiting {min(wait, 5):.1f}s then retrying")
                    _time.sleep(min(wait, 5))  # Cap at 5s even if server says more
                    r2 = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                                    headers=headers, json=req_json, timeout=60)
                    if r2.status_code == 200:
                        _clear_key_rate_limit(_key)
                        _mark_provider_ok("groq")
                        return r2.json()["choices"][0]["message"]["content"]
                log.warning("Groq rate limited (429) — all keys exhausted")
                _mark_provider_bad("groq", "rate_limited", 15)
                return ""
            r.raise_for_status()
        return ""

    @staticmethod
    def _groq_parse_retry_wait(resp) -> float:
        """Parse wait time from Groq 429 response headers."""
        # Try Retry-After header first
        ra = resp.headers.get("retry-after")
        if ra:
            try: return float(ra)
            except ValueError: pass
        # Try x-ratelimit-reset-tokens (e.g. "1.234s")
        rt = resp.headers.get("x-ratelimit-reset-tokens", "")
        if rt:
            try: return float(rt.rstrip("sm")) + 0.5
            except ValueError: pass
        # Try x-ratelimit-reset-requests (e.g. "2m30.5s")
        rr = resp.headers.get("x-ratelimit-reset-requests", "")
        if rr:
            try:
                total = 0.0
                parts = rr.replace("m", "m ").replace("s", "").split()
                for p in parts:
                    if p.endswith("m"):
                        total += float(p[:-1]) * 60
                    else:
                        total += float(p)
                return min(total, 30) + 0.5
            except ValueError: pass
        return 3.0  # default 3s wait

    async def _groq_raw(self, prompt: str, temperature: float = 0.6,
                        max_tokens: int = 6000, allow_ollama_fallback: bool = True) -> str:
        """Call Groq for long-form content with per-key rotation. Falls back to Ollama."""
        import httpx
        keys = _get_available_keys("groq")
        if not keys:
            keys = _sort_keys_by_health(_resolve_key_pool("groq"))
        req_json = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a senior SEO content writer. Output ONLY clean HTML. No markdown, no code fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        for _ki, _key in enumerate(keys):
            try:
                headers = {"Authorization": f"Bearer {_key}", "Content-Type": "application/json"}
                resp = await asyncio.get_event_loop().run_in_executor(
                    None, lambda h=headers: httpx.post("https://api.groq.com/openai/v1/chat/completions",
                                                       headers=h, json=req_json, timeout=120))
                if resp.status_code == 200:
                    _update_key_health(_key, headers=dict(resp.headers), status_code=200)
                    _clear_key_rate_limit(_key)
                    _mark_provider_ok("groq")
                    return resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    _mark_key_rate_limited(_key, 45, "429")
                    if _ki < len(keys) - 1:
                        log.warning(f"[KeyRotation] groq raw key {_ki+1}/{len(keys)} got 429, rotating to next account")
                        continue
                    # Last key — try short wait
                    wait = self._groq_parse_retry_wait(resp)
                    if wait and wait <= 15:
                        log.info(f"Groq raw 429 (last key) — waiting {wait:.1f}s")
                        await asyncio.sleep(wait)
                        resp2 = await asyncio.get_event_loop().run_in_executor(
                            None, lambda h=headers: httpx.post("https://api.groq.com/openai/v1/chat/completions",
                                                               headers=h, json=req_json, timeout=120))
                        if resp2.status_code == 200:
                            _clear_key_rate_limit(_key)
                            _mark_provider_ok("groq")
                            return resp2.json()["choices"][0]["message"]["content"]
                    log.warning("Groq rate limited — all keys exhausted, falling back")
                    _mark_provider_bad("groq", "rate_limited", 15)
                else:
                    resp.raise_for_status()
            except Exception as e:
                log.warning(f"Groq raw key {_ki+1} failed: {e}")
                if _ki >= len(keys) - 1:
                    _mark_provider_bad("groq", "error", 60)

        # Fallback to Ollama (not Gemini — we're using Groq+Ollama only)
        log.info("Groq unavailable, falling back to Ollama for content generation")
        return await self._ollama_section_writer(ollama_url=_live_ollama_url())

    async def _gemini(self, prompt: str, temperature: float = 0.3, api_key: str = None) -> Dict:
        """Call Gemini with per-key rotation, return parsed JSON dict."""
        keys = _get_available_keys("gemini")
        if api_key:
            keys = [api_key] + [k for k in keys if k != api_key]
        for _ki, _key in enumerate(keys):
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda k=_key: self._gemini_sync_single_key(prompt, temperature, k)
                )
                parsed = self._parse_json(raw)
                if parsed:
                    _clear_key_rate_limit(_key)
                    return parsed
            except _GeminiKeyRateLimited:
                _mark_key_rate_limited(_key, 60, "429")
                log.warning(f"[KeyRotation] gemini key {_ki+1}/{len(keys)} rate-limited, trying next GCP project")
                continue
            except Exception as e:
                log.warning(f"Gemini JSON key {_ki+1} failed: {e}")
                continue
        return {}

    async def _gemini_raw(self, prompt: str, temperature: float = 0.5, allow_ollama_fallback: bool = True) -> str:
        """Call Gemini with per-key rotation for long-form content. Falls back to Ollama."""
        keys = _get_available_keys("gemini")
        for _ki, _key in enumerate(keys):
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda k=_key: self._gemini_sync_single_key(prompt, temperature, k)
                )
                if raw and len(raw) > 200:
                    _clear_key_rate_limit(_key)
                    return raw
            except _GeminiKeyRateLimited:
                _mark_key_rate_limited(_key, 60, "429")
                log.warning(f"[KeyRotation] gemini raw key {_ki+1}/{len(keys)} rate-limited, trying next GCP project")
                continue
            except Exception as e:
                log.warning(f"Gemini raw key {_ki+1} failed: {e}")
                continue
        if not allow_ollama_fallback:
            log.warning("Gemini raw: all keys exhausted, no fallback")
            return ""
        log.warning("Gemini raw: all keys exhausted, falling back to Ollama section writer")
        return await self._ollama_section_writer(ollama_url=_live_ollama_url())

    def _gemini_sync(self, prompt: str, temperature: float) -> str:
        return self._gemini_sync_with_key(prompt, temperature, GEMINI_KEY)

    def _gemini_sync_single_key(self, prompt: str, temperature: float, api_key: str) -> str:
        """Call Gemini with a SINGLE key — tries all models for that key.
        Raises _GeminiKeyRateLimited if this specific key is rate-limited (429/503).
        Used by per-key rotation in exec functions."""
        import httpx
        last_err = None
        for model in GEMINI_MODELS:
            try:
                gen_config = {"temperature": temperature, "maxOutputTokens": 16000}
                r = httpx.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": gen_config,
                    },
                    timeout=60,
                )
                if r.status_code in (404,):
                    last_err = f"{model}: {r.status_code} (deprecated)"
                    continue
                if r.status_code in (429, 503):
                    raise _GeminiKeyRateLimited(f"{model}: {r.status_code}")
                r.raise_for_status()
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except _GeminiKeyRateLimited:
                raise  # propagate to caller for per-key handling
            except Exception as e:
                last_err = str(e)
                continue
        raise Exception(f"All Gemini models failed for this key. Last: {last_err}")

    def _gemini_sync_with_key(self, prompt: str, temperature: float, api_key: str) -> str:
        import httpx
        # Build prioritized list: available keys first (skip rate-limited), then others
        pool = _live_gemini_all_keys()
        keys_to_try = [api_key] if api_key and _is_key_available(api_key) else []
        for k in pool:
            if k not in keys_to_try and _is_key_available(k):
                keys_to_try.append(k)
        # Also add rate-limited keys as last resort
        for k in ([api_key] if api_key else []) + pool:
            if k not in keys_to_try:
                keys_to_try.append(k)
        if not keys_to_try:
            raise Exception("No Gemini API keys configured")

        last_err = None
        for key in keys_to_try:
            for model in GEMINI_MODELS:
                try:
                    gen_config = {"temperature": temperature, "maxOutputTokens": 16000}
                    r = httpx.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                        headers={"Content-Type": "application/json"},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": gen_config,
                        },
                        timeout=60,
                    )
                    if r.status_code in (404,):
                        # Model deprecated for this key — skip model
                        last_err = f"{model}: {r.status_code} (deprecated)"
                        continue
                    if r.status_code in (429, 503):
                        last_err = f"{model}: {r.status_code}"
                        _mark_key_rate_limited(key, 60, f"gemini_{r.status_code}")
                        break  # key is rate-limited, try alternate key
                    r.raise_for_status()
                    _clear_key_rate_limit(key)
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                except Exception as e:
                    last_err = str(e)
                    continue
        raise Exception(f"All Gemini models failed. Last: {last_err}")

    async def _ollama(self, prompt: str, temperature: float = 0.4,
                      max_tokens: int = 2000) -> Dict:
        """Call local Ollama for structured generation. Fallback to Groq."""
        try:
            async with _get_ollama_sem():
                raw = await self._ollama_async(prompt, temperature, max_tokens)
            result = self._parse_json(raw)
            if result:
                return result
        except Exception as e:
            log.warning(f"Ollama failed: {e}, falling back to Groq")

        # Fallback to Groq for structure
        return await self._groq(
            system="You are a precise SEO content strategist. Return ONLY valid JSON.",
            user=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _ollama_async(self, prompt: str, temperature: float, max_tokens: int,
                            raw_text: bool = False, ollama_url: str = "", ollama_model: str = "",
                            http_timeout: int = 0) -> str:
        """Call Ollama asynchronously using httpx. Supports proper asyncio cancellation.
        Unlike _ollama_sync + run_in_executor, this allows asyncio.wait_for to
        actually cancel the HTTP request — no orphaned threads.
        
        Timeout is calculated dynamically based on model speed profile."""
        import httpx
        url = ollama_url or _live_ollama_url()
        model = ollama_model or _live_ollama_model()
        prompt_tokens_est = len(prompt) // 3 + max_tokens
        num_ctx = max(2048, min(prompt_tokens_est + 512, 16384))
        
        # Get model profile and calculate appropriate timeout
        profile = self._profiler.get_profile("ollama", model)
        if http_timeout > 0:
            # Caller specified explicit timeout - use it
            timeout = http_timeout
        else:
            # Calculate based on model speed
            timeout = self._profiler.calculate_timeout(len(prompt), max_tokens, profile)
            log.info(f"Ollama {model}: calculated timeout {timeout}s ({profile.tokens_per_sec:.1f} tok/s)")
        
        start_time = _time.time()
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0)) as client:
            r = await client.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt if raw_text else f"Return ONLY valid JSON. No explanation, no markdown.\n\n{prompt}",
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "num_ctx": num_ctx,
                    },
                },
            )
            r.raise_for_status()
            response = r.json().get("response", "")
            
            # Update model profile with observed performance
            response_time = _time.time() - start_time
            tokens_generated = len(response) // 3  # Rough estimate
            self._profiler.update_profile("ollama", model, response_time, tokens_generated)
            
            return response

    def _ollama_sync(self, prompt: str, temperature: float, max_tokens: int, raw_text: bool = False, ollama_url: str = "", ollama_model: str = "", http_timeout: int = 0) -> str:
        """Call Ollama synchronously. Adjusts context window based on prompt size."""
        url = ollama_url or _live_ollama_url()
        model = ollama_model or _live_ollama_model()
        mem_before = _get_mem_pct()
        if mem_before > 85:
            log.warning(f"Memory at {mem_before}% before Ollama call — high pressure")
        # Scale context window based on prompt size so the model sees the full prompt.
        # Rough estimate: 1 token ≈ 4 chars.  Add margin for output (max_tokens).
        prompt_tokens_est = len(prompt) // 3 + max_tokens
        num_ctx = max(2048, min(prompt_tokens_est + 512, 16384))
        # Remote Ollama proxy: max 600s internal timeout → client must exceed it
        is_remote = url and "localhost" not in url and "127.0.0.1" not in url
        # HTTP timeout MUST be shorter than asyncio HARD_TIMEOUT to prevent
        # run_in_executor deadlock. When both timeouts race each other, the
        # asyncio event loop can't properly cancel the blocked thread.
        # JSON HARD_TIMEOUT=420 → http 360; raw HARD_TIMEOUT=540 → http 480.
        if http_timeout > 0:
            timeout = http_timeout
        else:
            timeout = 360 if is_remote else 120
        r = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt if raw_text else f"Return ONLY valid JSON. No explanation, no markdown.\n\n{prompt}",
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": num_ctx,
                },
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json().get("response", "")

    def _pm_block(self, key: str) -> str:
        """Get a prompt instruction block from PromptManager (custom override or default).
        Replaces {customer_context} placeholder with actual business context."""
        try:
            from engines.prompt_manager import PromptManager
            block = PromptManager.get_instance().get(key)
            if "{customer_context}" in block:
                block = block.replace("{customer_context}", self._customer_context_block())
            return block
        except Exception:
            return ""

    def _minimal_draft_from_structure(self) -> str:
        """Last resort: build basic HTML from structure headings so pipeline never fails on empty content.

        NOTE: This output is intentionally tagged with `_FALLBACK_MARKER_PHRASES`
        so the pre-save scanner (`_scan_for_fallback_phrases`) flags the article
        as `needs_review`. Editing the marker phrases will defeat that safeguard.
        """
        kw = self.keyword
        structure = self._structure or self._default_structure()
        # Pull research data when available for richer fallback
        _fb_themes = (self.state.steps[0].details.get("analysis", {}).get("themes", [])
                      if self.state.steps and self.state.steps[0].details else [])
        _fb_facts = (self.state.steps[0].details.get("analysis", {}).get("key_facts", [])
                     if self.state.steps and self.state.steps[0].details else [])
        _theme = _fb_themes[0] if _fb_themes else "quality, sourcing, and selection"
        _fact = _fb_facts[0] if _fb_facts else ""

        parts = [
            f"<p>{kw.title()} refers to {_theme.lower()}, "
            f"and understanding the key differences can significantly impact your results."
            f"{(' ' + _fact + '.') if _fact else ''}</p>"
        ]
        _h2s_raw = structure.get("h2_sections", [])
        for s in (_h2s_raw if isinstance(_h2s_raw, list) else [_h2s_raw] if _h2s_raw else [])[:8]:
            anchor = re.sub(r'[^a-z0-9]+', '-', s['h2'].lower())[:40].strip('-')
            parts.append(f'<h2 id="{anchor}">{s["h2"]}</h2>')
            angle = s.get("content_angle", "")
            # NOTE: phrase intentionally matches _FALLBACK_MARKER_PHRASES so the
            # save-time scanner flags the article as needs_review.
            parts.append(f"<p>This section covers {angle or s['h2'].lower()} related to {kw}. "
                         f"Buyers evaluating {kw} should weigh this factor against their specific requirements.</p>")
            for h3 in s.get("h3s", [])[:2]:
                parts.append(f"<h3>{h3}</h3>")
                parts.append(f"<p>{h3} is a critical consideration when evaluating {kw} options.</p>")
        _faqs_raw2 = structure.get("faqs", [])
        faqs = (_faqs_raw2 if isinstance(_faqs_raw2, list) else [_faqs_raw2] if _faqs_raw2 else [])[:4]
        if faqs:
            parts.append("<h2>Frequently Asked Questions</h2>")
            for fi, f in enumerate(faqs):
                q_text = f.get("q") or f.get("question") or f.get("text", "")
                if not q_text:
                    continue
                parts.append(f'<h3>{q_text}</h3>')
                _a_plan = f.get("a_plan", "")
                if _a_plan:
                    parts.append(f'<p>{_a_plan}</p>')
                else:
                    parts.append(f'<p>For {kw}, this depends on {_theme.lower()} and your intended application. '
                                 f'Compare certified options from multiple suppliers before deciding.</p>')
        parts.append(f'<p><strong>To summarise</strong>, choosing the right {kw} requires evaluating '
                     f'{_theme.lower()}. '
                     f'{structure.get("conclusion_plan", "Request samples and compare before committing.")} </p>')
        return "\n".join(parts)

    async def _ollama_section_writer(self, ollama_url: str = "") -> str:
        """
        Fallback content writer using local Ollama.
        Generates each H2 section one at a time (avoids token limits).
        Serialized via module-level semaphore so concurrent pipelines don't overload Ollama.
        Each call is capped at 300 tokens (~25s at 12 tok/s) to stay within 45s timeout.
        """
        log.info("Using Ollama section-by-section writer as final fallback")
        _url = ollama_url  # captured for lambdas
        async with _get_ollama_writer_sem():
            kw = self.keyword
            structure = self._structure
            h2_sections = structure.get("h2_sections", [])
            if not h2_sections:
                h2_sections = self._default_structure().get("h2_sections", [])

            html_parts = []
            # Introduction — keep short and fast (150 tokens)
            intro_prompt = f"""Write a 2-paragraph introduction for an article about '{kw}'. Include the keyword in the first sentence. Add one specific stat or year. Use <p> tags. Return only HTML."""
            intro = await asyncio.get_event_loop().run_in_executor(None, lambda: self._ollama_sync(intro_prompt, 0.6, 150, raw_text=True, ollama_url=_url))
            html_parts.append(intro if intro and "<p>" in intro else f"<p>{kw.title()} is a growing market with significant opportunities. This guide covers what you need to know to make informed decisions.</p>")

            # Each H2 section — capped at 300 tokens each for reliability
            for s in h2_sections[:6]:
                h2 = s.get("h2", "")
                h3s = s.get("h3s", [])
                h3_str = ", ".join(h3s[:2]) if h3s else ""

                section_prompt = f"""Write 2-3 paragraphs for the section '{h2}' in an article about '{kw}'.{' Cover: ' + h3_str + '.' if h3_str else ''} Use <h2>{h2}</h2> header and <p> tags. Include one specific fact or number. Return only HTML."""
                sec_html = await asyncio.get_event_loop().run_in_executor(None, lambda sp=section_prompt: self._ollama_sync(sp, 0.6, 300, raw_text=True, ollama_url=_url))
                if sec_html and len(sec_html) > 50:
                    html_parts.append(sec_html)
                else:
                    html_parts.append(f"<h2>{h2}</h2>\n<p>This section covers {h2.lower()} in relation to {kw}. Key factors include quality, pricing, and availability for buyers in this market.</p>")
                await asyncio.sleep(0.2)

            # FAQ — 2 sentences per answer (faster)
            _faqs_raw3 = structure.get("faqs", [])
            faqs = (_faqs_raw3 if isinstance(_faqs_raw3, list) else [_faqs_raw3] if _faqs_raw3 else [])[:3]
            if faqs:
                faq_html = "<h2>Frequently Asked Questions</h2>\n"
                for faq in faqs:
                    q = faq.get("q", "")
                    ans_prompt = f"Answer in 2 sentences with one specific fact: '{q}' (about: {kw}). Plain text only."
                    ans = await asyncio.get_event_loop().run_in_executor(None, lambda ap=ans_prompt: self._ollama_sync(ap, 0.5, 80, raw_text=True, ollama_url=_url))
                    ans_clean = re.sub(r"<[^>]+>", "", ans).strip() if ans else f"{kw.title()} has many important aspects regarding this question."
                    faq_html += f"<h3>{q}</h3>\n<p>{ans_clean}</p>\n"
                    await asyncio.sleep(0.1)
                html_parts.append(faq_html)

            # Conclusion — brief (100 tokens)
            conc_prompt = f"""Write a 2-sentence conclusion for an article about '{kw}'. Include a call-to-action. Use <p> tags. Return only HTML."""
            conc = await asyncio.get_event_loop().run_in_executor(None, lambda: self._ollama_sync(conc_prompt, 0.6, 100, raw_text=True, ollama_url=_url))
            html_parts.append(conc if conc and "<p>" in conc else f"<p>In conclusion, {kw} offers excellent value. Contact us today to place your order or learn more about our offerings.</p>")

            full_html = "\n\n".join(p.strip() for p in html_parts if p.strip())
            log.info(f"Ollama section writer produced {len(full_html.split())} words")
            return full_html

    async def _chatgpt_polish(self, html: str, api_key: str = "") -> str:
        """
        ChatGPT (GPT-4o) polishes existing HTML content. Improves fluency, E-E-A-T signals,
        and sentence variety without changing the article structure or removing links.
        Only called when OPENAI_API_KEY is set.
        """
        import httpx
        _key = api_key or _live_openai_key()
        if not _key:
            return ""
        polish_prompt = f"""You are an expert SEO editor. Polish this article about "{self.keyword}" to improve:
- Sentence fluency and reading flow (vary sentence length, avoid repetitive starters)
- Factual precision: add a specific statistic, year, or named source where claims are vague
- Natural keyword integration: ensure "{self.keyword}" appears in opening, a few H2 intros, and conclusion — but do NOT stuff it into every paragraph
- Human voice: use contractions, vary rhythm, include slight opinions where appropriate
- Remove any vague authority phrases like "research shows", "studies suggest", "experts agree" — either cite a specific source or state the fact directly

STRICT RULES:
- Do NOT remove or change any <a href> links (internal or external)
- Do NOT change any headings (h1, h2, h3)
- Do NOT reduce word count below current length
- Return the complete article as clean HTML — same structure, improved prose
- No markdown, no code fences, no commentary

ARTICLE TO POLISH:
{html[:10000]}"""
        try:
            resp = await asyncio.get_event_loop().run_in_executor(None, lambda: httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {_key}", "Content-Type": "application/json"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are an expert SEO content editor. Return only clean HTML."},
                        {"role": "user", "content": polish_prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 6000,
                },
                timeout=120,
            ))
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"].strip()
                result = re.sub(r"```html\n?", "", result)
                result = re.sub(r"```\n?", "", result).strip()
                log.info(f"ChatGPT polish succeeded ({len(result.split())} words)")
                return result
            log.warning(f"ChatGPT polish returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.warning(f"ChatGPT polish failed: {e}")
        return ""

    async def _claude_raw(self, prompt: str, max_tokens: int = 6000, api_key: str = "") -> str:
        """Send any full prompt to Claude and return raw HTML response. Used by _call_ai_raw_with_chain."""
        import httpx
        _key = api_key or _live_anthropic_key(paid=True) or ANTHROPIC_KEY
        if not _key or _key.endswith("xxxx"):
            return ""
        try:
            resp = await asyncio.get_event_loop().run_in_executor(None, lambda: httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": _key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            ))
            if resp.status_code == 200:
                result = resp.json()["content"][0]["text"].strip()
                result = re.sub(r"```html\n?", "", result)
                result = re.sub(r"```\n?", "", result).strip()
                log.info(f"Claude raw: succeeded ({len(result.split())} words)")
                return result
            log.warning(f"Claude raw: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Claude raw failed: {e}")
        return ""

    async def _claude_polish(self, html: str, api_key: str = "") -> str:
        """
        Claude does a final quality pass focusing on readability, tone consistency,
        and Google E-E-A-T compliance. Only called when ANTHROPIC_API_KEY is real (not placeholder).
        """
        import httpx
        _key = api_key or _live_anthropic_key()
        _key_valid = bool(_key)
        if not _key_valid:
            return ""
        polish_prompt = f"""You are Claude, an expert at creating high-quality, trustworthy content. 
Do a final quality pass on this SEO article about "{self.keyword}":

GOALS:
- Improve tone consistency: expert, helpful, authoritative throughout
- Strengthen E-E-A-T: ensure claims are specific, sources named, experience signals natural
- Fix any awkward phrasing or AI-sounding sentences
- Ensure conclusion has a clear, specific call-to-action
- Verify the article addresses reader intent for "{self.keyword}" fully

STRICT RULES:
- Preserve ALL <a href> links exactly (internal and external)
- Preserve ALL <h2 id="..."> and <h3> headings
- Do not reduce word count
- Return the complete article as clean semantic HTML
- No markdown, no code fences, no preamble

ARTICLE:
{html[:10000]}"""
        try:
            resp = await asyncio.get_event_loop().run_in_executor(None, lambda: httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": _key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 6000,
                    "messages": [{"role": "user", "content": polish_prompt}],
                },
                timeout=60,
            ))
            if resp.status_code == 200:
                result = resp.json()["content"][0]["text"].strip()
                result = re.sub(r"```html\n?", "", result)
                result = re.sub(r"```\n?", "", result).strip()
                log.info(f"Claude polish succeeded ({len(result.split())} words)")
                return result
            log.warning(f"Claude polish returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Claude polish failed: {e}")
        return ""

    def _parse_json(self, raw: str) -> Dict:
        """Robustly extract JSON from AI response, including truncated output."""
        if not raw:
            return {}
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                # Try to repair truncated JSON by closing unclosed braces/brackets
                candidate = m.group()
                repaired = self._repair_truncated_json(candidate)
                if repaired:
                    return repaired
        try:
            return json.loads(raw)
        except Exception:
            return {}

    @staticmethod
    def _repair_truncated_json(s: str) -> Dict:
        """Attempt to close unclosed braces/brackets in truncated JSON."""
        # Strip trailing incomplete key/value fragments
        for _ in range(3):
            s2 = re.sub(r',\s*"[^"]*"?\s*:?\s*"?[^"{}[\]]*$', '', s)
            s2 = re.sub(r',\s*$', '', s2)
            if s2 == s:
                break
            s = s2
        # Track nesting with a stack to close in proper order
        stack = []
        in_str = False
        esc = False
        for ch in s:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                stack.append('}')
            elif ch == '[':
                stack.append(']')
            elif ch in ('}', ']') and stack and stack[-1] == ch:
                stack.pop()
        if not stack:
            return {}
        if in_str:
            s += '"'
        while stack:
            s += stack.pop()
        try:
            return json.loads(s)
        except Exception:
            return {}

    def get_step_statuses(self) -> List[Dict]:
        return [
            {
                "step": s.step,
                "name": s.name,
                "status": s.status,
                "summary": s.summary,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in self.state.steps
        ]

