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
    # Primary — free / very cheap, good for small tasks
    "or_qwen":          {"model": "qwen/qwen3.6-plus:free",        "label": "Qwen 3.6 Plus",          "tier": "primary",   "cost": "Free"},
    "or_qwen_next":     {"model": "qwen/qwen3-next-80b-a3b-instruct:free", "label": "Qwen3 Next 80B", "tier": "primary",   "cost": "Free"},
    "or_deepseek":      {"model": "deepseek/deepseek-v3.2",        "label": "DeepSeek V3.2",           "tier": "primary",   "cost": "$0.26/M"},
    "or_gemini_flash":  {"model": "google/gemini-2.5-flash",       "label": "Gemini 2.5 Flash",        "tier": "primary",   "cost": "$0.30/M"},
    "or_gemini_lite":   {"model": "google/gemini-2.0-flash-lite-001", "label": "Gemini 2.0 Flash Lite", "tier": "primary",   "cost": "$0.07/M"},
    "or_glm":           {"model": "z-ai/glm-5-turbo",              "label": "GLM 5 Turbo",             "tier": "primary",   "cost": "$1.20/M"},
    # Secondary — additional models available via OpenRouter
    "or_gpt4o":         {"model": "openai/gpt-4o",                 "label": "GPT-4o",                  "tier": "secondary", "cost": "$2.50/M"},
    "or_claude":        {"model": "anthropic/claude-sonnet-4",     "label": "Claude Sonnet 4",         "tier": "secondary", "cost": "$3.00/M"},
    "or_llama":         {"model": "meta-llama/llama-4-maverick",   "label": "Llama 4 Maverick",        "tier": "secondary", "cost": "$0.20/M"},
    "or_qwen_coder":    {"model": "qwen/qwen3-coder:free",         "label": "Qwen3 Coder 480B",       "tier": "secondary", "cost": "Free"},
    "or_deepseek_r1":   {"model": "deepseek/deepseek-r1-0528",    "label": "DeepSeek R1",              "tier": "secondary", "cost": "$0.45/M"},
    "openrouter":       {"model": None,                             "label": "OpenRouter (default)",    "tier": "secondary", "cost": "Varies"},
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
_OR_REASONING_MODELS = {"or_deepseek_r1", "or_glm"}

def _or_adjust_max_tokens(provider: str, max_tokens: int) -> int:
    """Boost max_tokens for reasoning models so they have budget for thinking + answer."""
    if provider in _OR_REASONING_MODELS:
        return min(max_tokens * 2, 2000)  # Conservative — avoids 402 on low-credit accounts
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

def _log_usage(provider: str, result_text: str):
    """Append usage entry; reads step context from _step_ctx_var."""
    ctx = _step_ctx_var.get()
    word_count = len(result_text.split()) if result_text else 0
    tokens_estimated = int(word_count * 1.35)
    _SESSION_USAGE.append({  # deque auto-evicts oldest when maxlen reached
        "provider": provider,
        "step": ctx.get("step", 0),
        "step_name": ctx.get("step_name", ""),
        "tokens_estimated": tokens_estimated,
        "ts": _time.time(),
        "article_id": ctx.get("article_id"),
    })

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

@dataclass
class StepAIConfig:
    """Priority chain for a single pipeline step.
    Values: ollama | groq | gemini_free | gemini_paid | gemini | chatgpt | openai_paid
            | claude | anthropic | anthropic_paid | openrouter | or_qwen | or_deepseek
            | or_gemini_flash | or_gemini_lite | or_glm | or_gpt4o | or_claude
            | or_llama | or_qwen_coder | or_deepseek_r1 | skip
    """
    first:  str = "gemini_paid"
    second: str = "groq"
    third:  str = "ollama"


@dataclass
class AIRoutingConfig:
    """Per-task AI priority chains for the full 11-step pipeline.
    
    Strategy:
    - JSON tasks (S1-S5, S8): Groq (fast) → Gemini Paid (reliable) → OR Qwen (free fallback)
    - Content gen (S6): Gemini Paid (best quality + high limits) → Groq → OR Qwen
    - Review (S7): Groq (fast JSON) → Gemini Paid → OR Qwen
    - Rewrite (S9, S11): Gemini Paid (best for long rewrites) → Groq → OR Qwen
    """
    # Steps 1-5 (research & structure) — simple JSON tasks: Groq fast, Gemini fallback
    research:     StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "or_qwen"))
    structure:    StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "or_qwen"))
    verify:       StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "skip"))
    links:        StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "or_qwen"))
    references:   StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "or_qwen"))
    # Steps 6-9 (content writing) — Gemini Paid primary (high quality + rate limits), Groq fallback
    draft:        StepAIConfig = field(default_factory=lambda: StepAIConfig("gemini_paid", "groq",        "or_qwen"))
    review:       StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "or_qwen"))
    issues:       StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "skip"))
    redevelop:    StepAIConfig = field(default_factory=lambda: StepAIConfig("gemini_paid", "groq",        "or_qwen"))
    # Steps 10-11 (scoring & loop)
    score:        StepAIConfig = field(default_factory=lambda: StepAIConfig("groq",        "gemini_paid", "skip"))
    quality_loop: StepAIConfig = field(default_factory=lambda: StepAIConfig("gemini_paid", "groq",        "or_qwen"))

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
    (9,  "Content Redevelopment"),
    (10, "Final Scoring"),
    (11, "Quality Improvement Loop"),
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
                 page_inputs: Dict = None):
        self.article_id  = article_id
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

        # Pipeline event log — captured during generation, stored in schema_json
        self._logs: List[Dict] = []

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
        self._issues: List[Dict] = []
        self._intent_data: Dict = {}
        self._target_entities: List[str] = []
        self._semantic_variations: List[str] = []

        # Unique trace ID for this pipeline run (correlates all AI calls)
        import uuid as _uuid
        self._pipeline_trace_id: str = _uuid.uuid4().hex[:16]

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
            lines.append(f"BUYER PERSONAS: {c['personas'][:300]}")
        if c.get("products"):
            lines.append(f"PRODUCTS/SERVICES: {c['products'][:300]}")
        if c.get("blocked_topics"):
            lines.append(f"BLOCKED TOPICS (never mention): {c['blocked_topics']}")
        if not lines:
            return ""
        return "\n━━━ CUSTOMER CONTEXT (use this to personalise content) ━━━\n" + "\n".join(lines) + "\n"

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
                    # Quick version check (tiny request, no model loading)
                    r = await asyncio.get_event_loop().run_in_executor(None, lambda u=url: httpx.get(
                        f"{u}/api/version",
                        timeout=5,
                    ))
                    if r.status_code == 200:
                        self._add_log("success", f"Pre-flight: {provider} ({url}) — reachable")
                        _mark_provider_ok(provider)
                    else:
                        _mark_provider_bad(provider, "unreachable", 300)
                        self._add_log("error", f"Pre-flight: {provider} ({url}) — HTTP {r.status_code}")

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
        self._cancelled = False
        steps_fns = [
            self._step1_research,
            self._step2_structure,
            self._step3_verify_structure,
            self._step4_internal_links,
            self._step5_wikipedia,
            self._step6_draft,
            self._step7_review,
            self._step8_identify_issues,
            self._step9_redevelop,
            self._step10_score,
            self._step11_quality_loop,
        ]

        # ── Pre-flight provider health check ──────────────────────────────
        # Quick ping to detect unreachable providers BEFORE wasting 120s on timeouts
        await self._preflight_provider_check()

        for idx, fn in enumerate(steps_fns):
            s = self.state.steps[idx]

            # Skip already-completed steps (for resume from step N)
            if s.step < start_step:
                if s.status != "done":
                    s.status = "done"
                    s.summary = s.summary or "skipped (resumed from later step)"
                continue

            # Check if cancelled
            if self._cancelled:
                s.status = "pending"
                s.summary = "Cancelled by user"
                self._add_log("warn", f"Step {s.step}: {s.name} — cancelled", s.step)
                continue

            # In step-by-step mode: pause BEFORE each step so user can select AI first
            if self._step_mode == "pause":
                s.status = "paused"
                self._pause_event.clear()  # block until /continue is called
                self._add_log("info", f"⏸ Ready for Step {s.step}: {s.name} — select AI then click Continue", s.step)
                self._db_persist_status(f"step_{s.step}_ready")
                try:
                    await asyncio.wait_for(self._pause_event.wait(), timeout=3600)  # 1hr max
                except asyncio.TimeoutError:
                    self._add_log("warn", "Pipeline timed out waiting — auto-resuming")
                if self._cancelled:
                    s.status = "pending"
                    s.summary = "Cancelled by user"
                    continue

            # Wait for any externally set pause (e.g. from /pause endpoint switching auto→pause)
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
                # Continue — don't let one step kill the whole article

            self._db_persist_status(f"step_{s.step}_{s.status}")
            # Inter-step delay to spread Groq token consumption across time (12K/min quota)
            # 11 steps spaced by 2s = ~22s total, allowing token budget to refill between steps
            await asyncio.sleep(2.0)  # yield + rate limit spacing

        # Save final article
        self._save_final_to_db()

        # ── Clean memory release ─────────────────────────────────────────
        # Unload Ollama model to free ~2GB, then force Python GC
        mem_before = _get_mem_pct()
        _ollama_unload_model()
        _force_gc()
        mem_after = _get_mem_pct()
        log.info(f"Pipeline done for {self.article_id}: memory {mem_before}% → {mem_after}%")

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
            6: "draft", 7: "review", 8: "issues", 9: "redevelop", 10: "score", 11: "quality_loop",
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

            steps_json = json.dumps(self._pipeline_snapshot(), ensure_ascii=False)
            self.db.execute(
                """UPDATE content_articles
                   SET title=?, body=?, meta_title=?, meta_desc=?,
                       seo_score=?, readability=?, word_count=?,
                       status='draft', schema_json=?, updated_at=?
                   WHERE article_id=?""",
                (
                    self.state.title or self.keyword.title(),
                    self.state.final_html or self.state.draft_html,
                    self.state.meta_title or self.keyword[:60],
                    self.state.meta_desc or "",
                    self.state.seo_score,
                    self.state.readability,
                    self.state.word_count,
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
            6: "draft", 7: "review", 8: "issues", 9: "redevelop", 10: "score", 11: "quality_loop",
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
            "steps": [
                {
                    "step": s.step, "name": s.name, "status": s.status, "summary": s.summary,
                    "ai_first": _ai_first(s.step),
                    "ai_routing": _ai_routing(s.step),
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
        _step_ctx_var.set({"step": 1, "step_name": "Research", "article_id": getattr(self, "article_id", None)})
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

        if crawled:
            step.summary = f"Crawled {len(crawled)} pages + {ai_label} research: {themes_n} themes · {gaps_n} gaps"
        else:
            step.summary = f"DDG unavailable — {ai_label} knowledge research: {themes_n} themes · {gaps_n} gaps"

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
            system=system, temperature=0.3, max_tokens=400,
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
        _step_ctx_var.set({"step": 2, "step_name": "Structure", "article_id": getattr(self, "article_id", None)})
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
            temperature=0.4, max_tokens=600,
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
        _step_ctx_var.set({"step": 3, "step_name": "VerifyStructure", "article_id": getattr(self, "article_id", None)})
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

        # If AI flags issues, regenerate the structure incorporating improvements
        if not approved and improvements:
            improvements_text = "\n".join(f"- {imp}" for imp in improvements)
            refine_prompt = f"""Improve this article structure for keyword "{self.keyword}" based on these required improvements:

{improvements_text}

Current structure:
{json.dumps(self._structure, indent=2, ensure_ascii=False)[:2000]}

Return the COMPLETE improved structure as valid JSON with the same schema (h1, meta_title, meta_description, intro_plan, h2_sections, faqs, conclusion_plan, toc_anchors). Fix every issue listed above."""

            refined = await self._call_ai_with_chain(
                self.routing.structure, refine_prompt,
                system="You are a precise SEO content strategist. Return ONLY valid JSON.",
                temperature=0.3, max_tokens=600,
            )
            if refined.get("h2_sections"):
                self._structure = refined
                step.summary = f"Structure refined: {score}/100 → {len(improvements)} improvements applied"
            else:
                step.summary = f"Structure score: {score}/100 — refinement failed, keeping original"
        else:
            step.summary = f"Structure approved: {score}/100"

        # Pass Gemini's improvements as context to the draft writer (Step 6)
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
        _step_ctx_var.set({"step": 4, "step_name": "InternalLinks", "article_id": getattr(self, "article_id", None)})
        step = self.state.steps[3]
        sections = [s.get("h2", "") for s in self._structure.get("h2_sections", [])]

        links_prompt = f"""Plan ALL links for an article about "{self.keyword}" for {self.project_name or 'the business'}.

Article sections: {', '.join(sections)}
{"Known product/page links to use:\\n" + chr(10).join(f'- {p.get("name","Page")} → {p.get("url","")}' for p in self.product_links) if self.product_links else ""}

━━━ INTERNAL LINKS (minimum 4 required — scored as R24) ━━━
{"- Prefer the provided product/page links above as primary targets" if self.product_links else "- Link to the main product/category page"}
- Link to related product pages, category pages, guide/blog posts
- Link to contact/order page if appropriate
- ALL hrefs must start with "/" (e.g., "/products/black-pepper", "/guides/spice-storage", "/contact")

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
            temperature=0.3, max_tokens=400,
        )

        # ── Extract link lists with backward-compat for old "links" key ──────
        self._internal_links = plan.get("internal_links", []) or plan.get("links", [])
        self._external_links = plan.get("external_links", [])
        wiki_planned = plan.get("wikipedia_links", [])

        # ── Validate minimums & generate fallbacks ───────────────────────────
        kw_slug = re.sub(r"[^a-z0-9]+", "-", self.keyword.lower()).strip("-")
        kw_title = self.keyword.replace(" ", "_").title()

        # Internal links: need 4+
        if len(self._internal_links) < 4:
            fallback_internals = [
                {"anchor_text": f"explore {self.keyword} products", "href": f"/products/{kw_slug}", "section_h2": sections[0] if sections else "", "context": ""},
                {"anchor_text": f"complete guide to {self.keyword}", "href": f"/guides/{kw_slug}", "section_h2": sections[1] if len(sections) > 1 else "", "context": ""},
                {"anchor_text": f"buy {self.keyword} online", "href": f"/shop/{kw_slug}", "section_h2": sections[-2] if len(sections) > 2 else "", "context": ""},
                {"anchor_text": "contact us for more information", "href": "/contact", "section_h2": sections[-1] if sections else "", "context": ""},
                {"anchor_text": f"browse all {self.keyword.split()[-1] if self.keyword.split() else 'products'} options", "href": f"/category/{kw_slug}", "section_h2": sections[2] if len(sections) > 2 else "", "context": ""},
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
        Search Wikipedia API for the topic. Extract relevant sections,
        and identify 3-5 reference links to embed in the article.
        Falls back to PubMed and curated authority domains if Wikipedia fails.
        Guarantees self._reference_links is NEVER empty.
        """
        _step_ctx_var.set({"step": 5, "step_name": "Wikipedia", "article_id": getattr(self, "article_id", None)})
        step = self.state.steps[4]

        wiki_articles = []

        # Build search candidates: full keyword → shorter variants → key words
        kw = self.keyword.strip()
        candidates = [kw]
        words = kw.split()
        if len(words) > 2:
            candidates.append(" ".join(words[-2:]))   # last 2 words
            candidates.append(words[-1])               # last word (usually the topic noun)
        if len(words) > 1:
            candidates.append(words[0])                # first word

        primary_text, primary_url = "", ""
        for candidate in candidates:
            primary_text, primary_url = await self._wikipedia_search(candidate)
            if primary_text:
                break

        if primary_text:
            self._wiki_text = primary_text
            wiki_articles.append({"title": kw.title(), "url": primary_url})

        # Also search for related terms from structure
        h2s = self._structure.get("h2_sections", [])
        for h2 in h2s[:3]:
            h2_text, h2_url = await self._wikipedia_search(h2.get("h2", ""))
            if h2_text and h2_url and h2_url != primary_url:
                wiki_articles.append({"title": h2.get("h2", ""), "url": h2_url})
                break  # Just 1 extra

        # ── Fallback 1: PubMed search for authority references ───────────────
        authority_refs = []
        if len(wiki_articles) < 1 or len(self._external_links) < 3:
            pubmed_refs = await self._pubmed_search(kw)
            authority_refs.extend(pubmed_refs)

        # ── Fallback 2: If Wikipedia completely failed, build a plausible link ─
        if not wiki_articles:
            # Try the most specific word from keyword for a broader Wikipedia match
            for candidate in reversed(candidates):
                wiki_encoded = urllib.parse.quote(candidate.replace(" ", "_").title())
                fallback_url = f"https://en.wikipedia.org/wiki/{wiki_encoded}"
                wiki_articles.append({"title": candidate.title(), "url": fallback_url})
                log.info(f"Wikipedia step: using fallback constructed link for '{candidate}'")
                break

        # ── Merge planned wiki links from Step 4 with found wiki articles ────
        existing_urls = {a["url"] for a in wiki_articles}
        for wl in self._wiki_links:
            if wl.get("href") and wl["href"] not in existing_urls:
                wiki_articles.append({"title": wl.get("anchor_text", kw.title()), "url": wl["href"]})
                existing_urls.add(wl["href"])

        # ── Add PubMed/authority refs to external links if needed ────────────
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

        self._reference_links = wiki_articles
        step.summary = f"Found {len(wiki_articles)} Wikipedia + {len(authority_refs)} authority references"
        step.details["references"] = wiki_articles
        step.details["authority_refs"] = authority_refs
        step.details["wiki_excerpt"] = primary_text[:500] if primary_text else ""

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

    async def _wikipedia_search(self, query: str) -> tuple:
        """Search Wikipedia for query, return (text_excerpt, url). Non-blocking."""
        wiki_headers = {
            "Accept": "application/json",
            "User-Agent": "ANNASEOBot/1.0 (SEO content research; contact@annaseo.app)",
        }
        encoded = urllib.parse.quote(query.replace(" ", "_"))
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

        def _sync_wiki():
            resp = requests.get(api_url, timeout=8, headers=wiki_headers)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "")
                page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
                if extract and page_url:
                    return extract[:600], page_url
            return "", ""

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_wiki)
        except Exception as e:
            log.debug(f"Wikipedia search failed for '{query}': {e}")
            return "", ""

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6: CONTENT DRAFTING (Groq)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step6_draft(self):
        """
        Section-based article generation for reliability.
        Instead of one massive 8000-token call that causes timeouts and 429s,
        splits into: intro → sections (batches of 2-3) → FAQ+conclusion.
        Each call uses max_tokens=2500, making providers much more reliable.
        """
        _step_ctx_var.set({"step": 6, "step_name": "Draft", "article_id": getattr(self, "article_id", None)})
        step = self.state.steps[5]

        structure = self._structure
        h2_sections = structure.get("h2_sections", [])

        # ── Build shared context (compact version — not the full 33-rule spec) ──
        pt_ctx = self._page_type_context()
        pt_label = self._page_type_label()
        research_themes = self.state.steps[0].details.get("analysis", {}).get("themes", [])
        key_facts = self.state.steps[0].details.get("analysis", {}).get("key_facts", [])
        wiki_context = f"\nWikipedia context: {self._wiki_text[:300]}" if self._wiki_text else ""
        customer_ctx = self._customer_context_block()

        # Compact rules block shared across all section prompts
        rules_compact = f"""KEYWORD: "{self.keyword}" — use naturally 2-4 times per section. Density target: 1.0-1.5%.
Semantic Variations: {', '.join(self._semantic_variations[:5]) if self._semantic_variations else 'use synonyms'}
{"Entities to mention: " + ', '.join(self._target_entities[:8]) if self._target_entities else ""}
STYLE: Active voice. Mix short (8-12w) and medium (18-22w) sentences. Max 3 sentences/paragraph. Max 80 words/paragraph.
AUTHORITY: Use "according to", "research shows", "study found", "data shows" where relevant. Include numbers/percentages.
E-E-A-T: Add "we tested", "in our experience", "we found" signals. Be specific with named entities.
FORBIDDEN: delve, crucial, multifaceted, landscape, tapestry, nuanced, robust, myriad, paradigm, foster, holistic, pivotal, streamline, cutting-edge, plethora, underscore.
AI AVOIDANCE: No "furthermore/moreover/additionally" chains. No "in today's world". No "let's dive in". Vary sentence openers.
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
                    f'  <a href="{lk["href"]}">{lk["anchor_text"]}</a>' for lk in int_links))
            if ext_links:
                parts.append("EXTERNAL LINKS to embed:\n" + "\n".join(
                    f'  <a href="{lk["href"]}" target="_blank" rel="noopener">{lk["anchor_text"]}</a>' for lk in ext_links))
            return "\n".join(parts)

        # ── PART 1: Introduction + TOC ───────────────────────────────────
        toc_anchors = structure.get("toc_anchors", [])[:8]
        intro_prompt = f"""Write the INTRODUCTION for a comprehensive SEO {pt_label} about "{self.keyword}".

TITLE (H1): {structure.get("h1", self.keyword.title())}
Intent: {self._intent_data.get('primary_intent', self.intent)}
Business: {self.project_name or "the business"}
{"Target Audience: " + self.target_audience if self.target_audience else ""}
{f'{chr(10)}{pt_ctx}{chr(10)}' if pt_ctx else ''}
Introduction plan: {structure.get("intro_plan", "Hook + overview of what reader learns")}

Key themes: {', '.join(research_themes[:5])}
Key facts: {', '.join(key_facts[:3]) if key_facts else "Provide relevant data"}
{wiki_context}

REQUIREMENTS:
- Start with a hook sentence containing "{self.keyword}" in the first 10 words
- First paragraph MUST be ≥40 words and start with "{self.keyword.split()[0]}"
- Include a TL;DR / Key Takeaways box after intro (use <div class="key-takeaway">)
- After intro, add a TOC nav block: <nav><ul> with links to these anchors: {json.dumps(toc_anchors)}
- Total: 150-250 words

{rules_compact}"""

        log.info(f"Draft step: routing chain = {self.routing.draft.first} → {self.routing.draft.second} → {self.routing.draft.third}")
        self._add_log("info", "S6 Generating intro + TOC", 6)
        intro_html = await self._call_ai_raw_with_chain(
            self.routing.draft, intro_prompt, temperature=0.6, max_tokens=800
        )
        if not intro_html:
            intro_html = f'<p>{self.keyword.title()} is a topic that deserves careful attention.</p>'

        # ── PART 2: Body sections (batches of 2-3) ─────────────────────────
        section_parts = []
        batch_size = 3 if len(h2_sections) <= 6 else 2
        batches = [h2_sections[i:i+batch_size] for i in range(0, len(h2_sections), batch_size)]

        for batch_idx, batch in enumerate(batches):
            section_names = [s['h2'] for s in batch]
            sections_spec = ""
            for s in batch:
                h3_list = "\n    - " + "\n    - ".join(s.get("h3s", [])) if s.get("h3s") else ""
                sections_spec += f'\n  <h2 id="{s.get("anchor", "")}"> {s["h2"]} </h2> (~{s.get("word_target", 300)} words){h3_list}'

            links_ctx = _links_for_sections(section_names)

            # Determine if this batch should include the comparison table
            table_note = ""
            if batch_idx == 0:
                table_note = "\nINCLUDE: One <table> with <thead>/<tbody> for comparison/data (3+ rows × 3+ columns)."
            list_note = "\nINCLUDE: At least 1 <ul> list and 1 <ol> list in these sections." if batch_idx <= 1 else ""

            batch_prompt = f"""Write these sections for an SEO {pt_label} about "{self.keyword}".

SECTIONS TO WRITE:{sections_spec}
{table_note}{list_note}

{"Supporting keywords to include: " + ', '.join(self.supporting_keywords[:8]) if self.supporting_keywords else ""}
Key facts: {', '.join(key_facts[:3]) if key_facts else "Include relevant statistics"}

{links_ctx}

{rules_compact}

Write ONLY these sections. Start directly with the first <h2>. No intro, no conclusion."""

            self._add_log("info", f"S6 Generating sections batch {batch_idx+1}/{len(batches)}: {', '.join(s['h2'][:30] for s in batch)}", 6)
            batch_html = await self._call_ai_raw_with_chain(
                self.routing.draft, batch_prompt, temperature=0.6, max_tokens=1200
            )
            if batch_html:
                section_parts.append(batch_html)
            else:
                # Minimal fallback for this batch
                for s in batch:
                    section_parts.append(f'<h2 id="{s.get("anchor","")}">{s["h2"]}</h2>\n<p>{self.keyword.title()} — this section covers {s["h2"].lower()}.</p>')

        # ── PART 3: FAQ + Conclusion ───────────────────────────────────────
        faqs = structure.get("faqs", [])[:6]
        faq_questions = [f.get("q") or f.get("question") or f.get("text", "") for f in faqs if f.get("q") or f.get("question") or f.get("text")]
        conclusion_plan = structure.get("conclusion_plan", "Summarise + CTA")

        ref_links_text = "\n".join(
            f'  <a href="{r["url"]}" target="_blank" rel="noopener">{r["title"]} (Wikipedia)</a>'
            for r in self._reference_links
        )

        faq_prompt = f"""Write the FAQ SECTION and CONCLUSION for an SEO {pt_label} about "{self.keyword}".

FAQ SECTION:
- Use heading: <h2 id="faq">Frequently Asked Questions About {self.keyword.title()}</h2>
- Answer each question with 40-60 words, direct and complete
- Include "{self.keyword}" in each answer
- Questions:
{chr(10).join(f"  - {q}" for q in faq_questions)}

CONCLUSION:
- Plan: {conclusion_plan}
- Include CTA (buy/shop/contact/learn more/discover/try)
- Include "{self.keyword}" in conclusion
- 100-150 words

{f"WIKIPEDIA REFERENCES to embed:{chr(10)}{ref_links_text}" if ref_links_text else ""}

{rules_compact}

Write ONLY the FAQ section and conclusion. Start with the FAQ <h2>."""

        self._add_log("info", "S6 Generating FAQ + conclusion", 6)
        faq_html = await self._call_ai_raw_with_chain(
            self.routing.draft, faq_prompt, temperature=0.6, max_tokens=1000
        )
        if not faq_html:
            faq_html = f'<h2 id="faq">Frequently Asked Questions About {self.keyword.title()}</h2>'
            for q in faq_questions[:4]:
                faq_html += f'\n<h3>{q}</h3>\n<p>{self.keyword.title()} — answer coming soon.</p>'

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

        # ── Content Intelligence post-processing (R34-R46) ──
        self.state.draft_html = self._intelligence_post_process(self.state.draft_html)

        self.state.final_html = self.state.draft_html

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
                    html = html[:insert_pos] + wiki_tag + html[insert_pos:]
                    injected = True
                    break
            if not injected and paras:
                # Fallback: add to the 3rd paragraph (or last)
                target = paras[min(2, len(paras) - 1)]
                insert_pos = target.end(2)
                html = html[:insert_pos] + wiki_tag + html[insert_pos:]
            log.info(f"Post-draft inject: added Wikipedia reference link")

        # ── R20: Authority signals (need 5+ exact phrases) ──────────────────
        text_after = re.sub(r"<[^>]+>", " ", html).lower()
        eeat_signals = ["according to", "research shows", "study found", "study published",
                        "experts say", "data shows", "evidence suggests", "published in",
                        "scientific", "peer-reviewed", "clinical trial"]
        eeat_hits = sum(1 for s in eeat_signals if s in text_after)
        if eeat_hits < 5:
            # Inject authority phrases into factual paragraphs
            authority_prefixes = [
                ("According to recent research, ", "according to"),
                ("Research shows that ", "research shows"),
                ("A study found that ", "study found"),
                ("Data shows that ", "data shows"),
                ("Evidence suggests that ", "evidence suggests"),
                ("Experts say that ", "experts say"),
            ]
            inject_idx = 0
            needed = 5 - eeat_hits
            # Process one paragraph at a time — re-scan after each injection
            while inject_idx < len(authority_prefixes) and needed > 0:
                paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
                injected_this_pass = False
                for m in paras:
                    para_text = re.sub(r"<[^>]+>", "", m.group(2)).lower()
                    # Skip if already has an authority signal
                    if any(s in para_text for s in eeat_signals):
                        continue
                    # Skip very short paragraphs
                    if len(para_text.split()) < 10:
                        continue
                    prefix_text, signal = authority_prefixes[inject_idx]
                    # Insert prefix at the start of paragraph content (after <p> tag)
                    content_start = m.start(2)
                    existing_content = m.group(2)
                    if existing_content and existing_content[0].isupper():
                        existing_content = existing_content[0].lower() + existing_content[1:]
                    html = html[:content_start] + prefix_text + existing_content + html[m.end(2):]
                    inject_idx += 1
                    needed -= 1
                    injected_this_pass = True
                    break  # Re-scan from start after each injection
                if not injected_this_pass:
                    break  # No suitable paragraphs left
            if inject_idx > 0:
                log.info(f"Post-draft inject: added {inject_idx} authority signal phrases (was {eeat_hits})")

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
                link_tag = f' <a href="{href}">{anchor}</a>'

            # Append link before the closing </p>
            m = paras[para_idx]
            insert_pos = m.end(2)
            html = html[:insert_pos] + link_tag + html[insert_pos:]
            link_idx += 1
            # Re-find paragraphs since positions shifted
            paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))

        return html

    # ─────────────────────────────────────────────────────────────────────────
    # AI WATERMARK SCRUBBER (integrates AIWatermarkScrubber from ruflo_seo_audit)
    # ─────────────────────────────────────────────────────────────────────────

    def _scrub_ai_patterns(self, html: str) -> str:
        """Run AIWatermarkScrubber on HTML to remove AI fluff patterns (R35)."""
        if not html or len(html) < 200 or _scrubber is None:
            return html
        try:
            scrubbed, changes = _scrubber.scrub(html)
            total_removed = changes.get("fluff_removed", 0) + changes.get("starters_replaced", 0)
            if total_removed > 0:
                log.info(f"AI scrub: removed {changes.get('fluff_removed',0)} fluff, "
                         f"replaced {changes.get('starters_replaced',0)} robotic starters, "
                         f"risk: {changes.get('ai_score_risk','?')}")
            return scrubbed
        except Exception as e:
            log.warning(f"AI scrub failed: {e}")
            return html

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

        text = re.sub(r"<[^>]+>", " ", html)
        text_lower = text.lower()
        words = text.split()
        word_count = len(words)
        kw_lower = (self.keyword or "").lower()

        # ── R34: Keyword density normalization ───────────────────────────────
        if kw_lower and word_count > 100:
            kw_count = text_lower.count(kw_lower)
            kw_density = (kw_count / word_count) * 100
            if kw_density > 2.5 and kw_count > 5:
                # Generate semantic variations
                kw_words = kw_lower.split()
                variations = []
                if len(kw_words) >= 2:
                    variations = [
                        " ".join(reversed(kw_words)),  # word order swap
                        kw_words[0] + " " + "variety" if len(kw_words) == 2 else " ".join(kw_words[:-1]),
                        "these " + kw_words[-1] if len(kw_words) >= 1 else kw_lower,
                        "premium " + " ".join(kw_words[-2:]) if len(kw_words) >= 2 else "premium " + kw_lower,
                        "quality " + " ".join(kw_words[-2:]) if len(kw_words) >= 2 else "quality " + kw_lower,
                    ]
                elif len(kw_words) == 1:
                    variations = [
                        f"these {kw_lower} products",
                        f"premium {kw_lower}",
                        f"quality {kw_lower}",
                        f"authentic {kw_lower}",
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
                        replace_count = min(excess, len(replaceable))
                        # Replace from end to start to preserve positions
                        for i, m in enumerate(reversed(replaceable[:replace_count])):
                            var = variations[i % len(variations)]
                            html = html[:m.start()] + var + html[m.end():]

                        new_density = text_lower.count(kw_lower) / word_count * 100
                        log.info(f"R34 density fix: {kw_density:.1f}% → replaced {replace_count} instances (target ~{target_density}%)")

        # ── R36: Experience signal injection ─────────────────────────────────
        text_after = re.sub(r"<[^>]+>", " ", html).lower()
        experience_signals = [
            "we tested", "we found", "in our experience", "we observed",
            "after trying", "hands-on", "first-hand", "we discovered",
            "our team", "we recommend", "we compared", "in practice",
        ]
        exp_hits = sum(1 for s in experience_signals if s in text_after)
        if exp_hits < 3:
            exp_prefixes = [
                ("In our experience, ", "in our experience"),
                ("We found that ", "we found"),
                ("After trying multiple options, ", "after trying"),
                ("Our team discovered that ", "we discovered"),
                ("From our testing, ", "we tested"),
            ]
            needed = 3 - exp_hits
            inject_idx = 0
            while inject_idx < len(exp_prefixes) and needed > 0:
                paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
                injected = False
                for m in paras:
                    para_text = re.sub(r"<[^>]+>", "", m.group(2)).lower()
                    if any(s in para_text for s in experience_signals):
                        continue
                    if len(para_text.split()) < 15:
                        continue
                    # Don't inject in first or last paragraph
                    if m.start() < 500 or m.start() > len(html) - 500:
                        continue
                    prefix_text, signal = exp_prefixes[inject_idx]
                    content_start = m.start(2)
                    existing = m.group(2)
                    if existing and existing[0].isupper():
                        existing = existing[0].lower() + existing[1:]
                    html = html[:content_start] + prefix_text + existing + html[m.end(2):]
                    inject_idx += 1
                    needed -= 1
                    injected = True
                    break
                if not injected:
                    break
            if inject_idx > 0:
                log.info(f"R36 experience inject: added {inject_idx} experience signals (was {exp_hits})")

        # ── R42: Visual break injection ──────────────────────────────────────
        visual_patterns = [r"<blockquote", r'class="[^"]*(?:tip|callout|key-takeaway|pro-tip)']
        visual_count = sum(len(re.findall(p, html, re.I)) for p in visual_patterns)
        if visual_count < 2:
            # Inject tip/takeaway boxes after every 3rd H2 section
            h2_positions = list(re.finditer(r"<h2[^>]*>.*?</h2>", html, re.I | re.DOTALL))
            inserted = 0
            tips = [
                '<div class="key-takeaway"><p><strong>Key Takeaway:</strong> Quality and authenticity are the most important factors when making your purchasing decision.</p></div>',
                '<div class="pro-tip"><p><strong>Pro Tip:</strong> Always verify sourcing certifications and compare prices across multiple trusted suppliers before buying.</p></div>',
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
                log.info(f"R42 visual breaks: inserted {inserted} tip/takeaway boxes")

        # ── R43: Mid-content CTA injection ───────────────────────────────────
        mid_cta_words = ["shop now", "explore", "browse", "check out", "view our",
                         "see our", "get your", "order now"]
        mid_start = int(len(html) * 0.2)
        mid_end = int(len(html) * 0.8)
        mid_text = html[mid_start:mid_end].lower()
        has_mid_cta = any(w in mid_text for w in mid_cta_words)
        if not has_mid_cta:
            # Insert a contextual CTA after the 3rd or 4th H2 section
            h2_positions = list(re.finditer(r"</h2>", html, re.I))
            if len(h2_positions) >= 3:
                kw_title = self.keyword.title()
                cta_html = f'\n<div class="cta-block"><p>Looking for premium {kw_title}? <a href="/shop/{self.keyword.replace(" ", "-")}">Explore our curated collection</a> for the best quality and value.</p></div>\n'
                target_h2 = h2_positions[min(3, len(h2_positions) - 1)]
                # Find next paragraph after this H2
                next_p = re.search(r"</p>", html[target_h2.end():])
                if next_p:
                    insert_pos = target_h2.end() + next_p.end()
                    html = html[:insert_pos] + cta_html + html[insert_pos:]
                    log.info("R43 mid-CTA: inserted contextual CTA in article body")

        # ── R45: Unique angle signal injection ───────────────────────────────
        text_final = re.sub(r"<[^>]+>", " ", html).lower()
        angle_signals = [
            "what most people miss", "the real truth", "unlike other guides",
            "here's the difference", "we believe", "our perspective",
        ]
        has_angle = any(s in text_final for s in angle_signals)
        if not has_angle:
            # Inject a differentiation phrase into a suitable paragraph
            paras = list(re.finditer(r"(<p[^>]*>)(.*?)(</p>)", html, re.I | re.DOTALL))
            for m in paras[3:8]:  # Try paragraphs 4-8
                para_text = re.sub(r"<[^>]+>", "", m.group(2))
                if len(para_text.split()) >= 20:
                    prefix = "What most people miss is that "
                    content_start = m.start(2)
                    existing = m.group(2)
                    if existing and existing[0].isupper():
                        existing = existing[0].lower() + existing[1:]
                    html = html[:content_start] + prefix + existing + html[m.end(2):]
                    log.info("R45 angle inject: added 'what most people miss' differentiation signal")
                    break

        return html

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 7: AI QUALITY REVIEW (Gemini)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step7_review(self):
        """
        Quality review using the parallel chain system.
        Calls _call_ai_with_chain for reliable JSON response (races providers).
        Falls back to rule-based scoring if AI review fails completely.
        """
        _step_ctx_var.set({"step": 7, "step_name": "Review", "article_id": getattr(self, "article_id", None)})
        step = self.state.steps[6]

        log.info(f"Review step: routing chain = {self.routing.review.first} → {self.routing.review.second} → {self.routing.review.third}")

        draft_preview = self.state.draft_html[:6000]

        review_prompt = f"""Review this SEO article draft for keyword "{self.keyword}" (intent: {self.intent}).

Draft preview:
{draft_preview}

{self._pm_block("step7_review_criteria")}

Return ONLY valid JSON — no explanation, no markdown:
{{
  "relevance_score": 0-100,
  "quality_score": 0-100,
  "tone": "assessment",
  "eeat_score": 0-100,
  "critical_issues": ["list if any"],
  "strengths": ["list"],
  "missing_rules": ["rule IDs or names not met"],
  "toc_present": true,
  "overall_approved": true/false
}}"""

        review_system = "You are a senior SEO content reviewer. Return ONLY valid JSON. No explanation, no markdown, no extra text."

        # ── Use the parallel chain for the review ──────────────────────────
        merged_review = await self._call_ai_with_chain(
            self.routing.review, review_prompt,
            system=review_system, temperature=0.2, max_tokens=400,
        )

        reviewer_label = "chain"

        # ── Fallback: if chain returned empty, generate rule-based review ──
        if not merged_review or not merged_review.get("quality_score"):
            log.warning("Review: AI chain returned empty — generating rule-based review from scoring data")
            # Use rule-based data from step 8 preview
            from quality.content_rules import check_all_rules
            try:
                preview_scored = check_all_rules(
                    body_html=self.state.draft_html,
                    keyword=self.keyword,
                    title=self.state.title or self.keyword,
                    meta_title=self.state.meta_title or "",
                    meta_desc=self.state.meta_desc or "",
                    page_type=self.page_type,
                    **self._scoring_customer_kwargs(),
                )
                pct = preview_scored.get("percentage", 0)
                failed_names = [r.get("name", "") for r in preview_scored.get("rules", []) if not r.get("passed")]
                merged_review = {
                    "relevance_score": min(100, pct + 15),
                    "quality_score": pct,
                    "eeat_score": min(100, pct + 5),
                    "tone": "rule-based assessment",
                    "critical_issues": failed_names[:8],
                    "strengths": [r.get("name", "") for r in preview_scored.get("rules", []) if r.get("passed")][:5],
                    "missing_rules": failed_names[:10],
                    "toc_present": any("toc" in r.get("name", "").lower() for r in preview_scored.get("rules", []) if r.get("passed")),
                    "overall_approved": pct >= 80,
                }
                reviewer_label = "rule-based-fallback"
            except Exception as e:
                log.warning(f"Review: rule-based fallback also failed: {e}")
                merged_review = {
                    "relevance_score": 50, "quality_score": 50, "eeat_score": 50,
                    "tone": "no review available", "critical_issues": ["Review unavailable"],
                    "strengths": [], "missing_rules": [], "toc_present": False,
                    "overall_approved": False,
                }
                reviewer_label = "none"

        step.summary = (
            f"Quality: {merged_review.get('quality_score', '?')}/100 · "
            f"Relevance: {merged_review.get('relevance_score', '?')}/100 · "
            f"E-E-A-T: {merged_review.get('eeat_score', '?')}/100 · "
            f"Reviewers: {reviewer_label}"
        )
        step.details["review"] = merged_review

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 8: ISSUE IDENTIFICATION (Rule-based + AI)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step8_identify_issues(self):
        """
        Run 53-rule per-rule quality checks via quality.content_rules.check_all_rules().
        Results include per-rule pass/fail, per-pillar summaries, and backward-compat issues.
        Rule results are saved in schema_json for live pipeline display.
        """
        _step_ctx_var.set({"step": 8, "step_name": "IdentifyIssues", "article_id": getattr(self, "article_id", None)})
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

        step.summary = (
            f"Score {scored['percentage']}% ({scored['total_earned']}/{scored['max_possible']} pts) · "
            f"{scored['summary']['passed_count']}/{scored['summary']['total_rules']} rules passed · "
            f"{len(issues)} issues"
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
    # STEP 9: CONTENT REDEVELOPMENT (Groq)
    # ─────────────────────────────────────────────────────────────────────────

    async def _step9_redevelop(self):
        """
        Patch-based rule-aware rewrite. Instead of rewriting the entire article at once
        (which causes timeouts), targets the top 5 highest-impact failed rules with
        focused fix prompts. Each fix call uses max_tokens=2500.
        """
        _step_ctx_var.set({"step": 9, "step_name": "Redevelop", "article_id": getattr(self, "article_id", None)})
        step = self.state.steps[8]

        # ── Collect failed rules from step 8 rule results ─────────────────────
        failed_rules = []
        if hasattr(self, '_rule_results') and self._rule_results:
            failed_rules = [r for r in self._rule_results.get("rules", []) if not r.get("passed", True)]

        if not failed_rules:
            step.summary = "No rule failures — skipping redevelopment"
            return

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

        current_score = self._rule_results.get("score", 0) if hasattr(self, '_rule_results') and self._rule_results else 0

        # ── Single targeted rewrite pass using reduced prompt ──────────────
        # Truncate article for prompt (only send first 6000 chars to keep prompt small)
        article_excerpt = self.state.draft_html[:6000]
        article_tail = self.state.draft_html[6000:]

        base_prompt = f"""You are a senior SEO content editor. Fix the specific quality rule failures listed below.

KEYWORD: "{self.keyword}" (density target: 1.0-1.5%)
Semantic Variations: {', '.join(self._semantic_variations[:5]) if self._semantic_variations else 'use synonyms'}
CURRENT SCORE: {current_score}% — TARGET: 90%+

━━━ RULES TO FIX (highest impact first) ━━━
{failed_rules_text}

{self._pm_block("step9_quality_rules")}

━━━ KEY FIX RULES ━━━
KEYWORD: Use "{self.keyword}" at least {max(15, int(self.target_wc * 0.018))} times. Must be in first sentence, H2 headings, FAQ answers.
FIRST PARA: ≥40 words, start with "{self.keyword.split()[0]}", contain keyword.
STRUCTURE: 6+ <h2>, 4+ <h3>, FAQ heading with "Frequently Asked"/"FAQ", 1 <table>, 2+ <ul>, 1+ <ol>.
AUTHORITY: 5+ phrases from: "according to", "research shows", "study found", "data shows", "evidence suggests".
DATA: 5+ numbers: percentages, years, measurements.
LINKS: 4+ internal <a href="/...">, 3+ external <a href="http...">, 1+ wikipedia.org.
READABILITY: Avg sentence 12-22w. Zero paragraphs >100w. Active voice.
FORBIDDEN: delve, crucial, multifaceted, tapestry, nuanced, robust, myriad, paradigm, foster, holistic, pivotal.
PRESERVE: All existing <a href="..."> links exactly.
OUTPUT: Complete improved article as clean semantic HTML. No markdown, no code fences.

━━━ ARTICLE TO IMPROVE ━━━
{article_excerpt}"""

        log.info(f"Redevelop: chain {self.routing.redevelop.first}→{self.routing.redevelop.second}→{self.routing.redevelop.third}")
        try:
            chain_out = await self._call_ai_raw_with_chain(
                self.routing.redevelop, base_prompt, temperature=0.5, max_tokens=4000,
                use_prompt_directly=True
            )
        except Exception as e:
            log.warning(f"Redevelop: chain failed ({e}) — keeping draft")
            chain_out = ""

        draft_wc = len(re.sub(r"<[^>]+>", " ", self.state.draft_html).split())
        min_acceptable = max(500, int(draft_wc * 0.75)) if draft_wc > 100 else 200

        if chain_out:
            # If we only sent a partial article, append the tail
            if article_tail and len(article_tail) > 200:
                chain_out = chain_out + "\n" + article_tail

            chain_wc = len(re.sub(r"<[^>]+>", " ", chain_out).split())
            if chain_wc >= min_acceptable:
                chain_out = self._scrub_ai_patterns(chain_out)
                chain_wc = len(re.sub(r"<[^>]+>", " ", chain_out).split())
                self.state.final_html = chain_out
                self.state.word_count = chain_wc
                step.summary = (
                    f"Rewriting to fix {len(top_rules)} rules · {chain_wc} words · "
                    f"provider: {self.routing.redevelop.first}"
                )
                log.info(f"Redevelop: done ({chain_wc} words)")
                return
            else:
                log.warning(f"Redevelop: output too short ({chain_wc}w, min {min_acceptable}) — keeping draft")

        self.state.word_count = draft_wc
        step.summary = (
            f"No improvement pass succeeded — keeping draft ({draft_wc}w). "
            f"{len(failed_rules)} rules noted. Provider chain: "
            f"{self.routing.redevelop.first}→{self.routing.redevelop.second}→{self.routing.redevelop.third}"
        )
        log.warning("Redevelop: no passes produced valid output — keeping draft")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 10: FINAL SCORING
    # ─────────────────────────────────────────────────────────────────────────

    async def _step10_score(self):
        """
        Calculate final quality scores using the 53-rule per-rule engine.
        Saves full per-rule results to DB for the frontend RulesPanel.
        """
        _step_ctx_var.set({"step": 10, "step_name": "Score", "article_id": getattr(self, "article_id", None)})
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
                readability_score = textstat.flesch_reading_ease(text[:8000])
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
    # STEP 11: QUALITY IMPROVEMENT LOOP
    # ─────────────────────────────────────────────────────────────────────────

    async def _step11_quality_loop(self):
        """
        Iterative quality improvement: re-score → fix failing rules → repeat.
        Uses Ollama to rewrite the content targeting highest-impact failures.
        Max 3 passes. Stops when score >= MIN_QUALITY_SCORE (75%).
        """
        _step_ctx_var.set({"step": 11, "step_name": "QualityLoop", "article_id": getattr(self, "article_id", None)})
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

        if current_score >= MIN_QUALITY_SCORE and initial_critical_ok:
            step.summary = f"Score already {current_score}% ≥ {MIN_QUALITY_SCORE}% — no improvement needed"
            step.details = {"passes": 0, "initial_score": current_score, "final_score": current_score}
            return

        if current_score >= MIN_QUALITY_SCORE and not initial_critical_ok:
            log.info(f"Quality loop: score {current_score}% ≥ {MIN_QUALITY_SCORE}% but critical rules R20/R24/R25/R26 still failing — continuing")

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

            # Build targeted fix instructions
            fix_instructions = []
            for r in failed[:15]:
                pts_lost = r.get("points_max", 0) - r.get("points_earned", 0)
                # Find matching issue fix hint
                issue_fix = ""
                for iss in scored.get("issues", []):
                    if iss.get("rule") == r.get("rule_id", ""):
                        issue_fix = iss.get("fix", "")
                        break
                detail = issue_fix or r.get("name", "fix this rule")
                fix_instructions.append(f"• [{r.get('rule_id','?')}] {r.get('name','?')} (+{pts_lost}pt): {detail}")

            fix_text = "\n".join(fix_instructions)

            # Build a COMPACT focused rewrite prompt (not the full rule spec — key to avoiding timeouts)
            prompt = f"""Fix these quality issues in the SEO article below. Target score: {MIN_QUALITY_SCORE}%+.

KEYWORD: "{self.keyword}" | CURRENT: {current_score}%

RULES TO FIX:
{fix_text}

KEY REQUIREMENTS:
- Keyword "{self.keyword}" at least {max(15, int(self.target_wc * 0.018))} times, density 1.0-1.5%
- First para ≥40w, starts with "{self.keyword.split()[0]}", contains keyword
- 6+ <h2>, 4+ <h3>, FAQ section, 1 <table>, 2+ <ul>, 1+ <ol>
- 5+ authority phrases ("according to", "research shows", "data shows")
- 5+ data points (%, years, measurements)
- 4+ internal <a href="/...">, 3+ external <a href="http...">, 1+ wikipedia.org
- Max 80w/paragraph, active voice, no AI fluff words
- FORBIDDEN: delve, crucial, multifaceted, tapestry, nuanced, robust, myriad, paradigm
- Preserve all existing links

ARTICLE:
{html[:8000]}

Output COMPLETE improved HTML. No markdown, no code fences, no commentary."""

            # Use routing chain — provider order set by self.routing.quality_loop (user-selectable)
            log.info(f"Quality loop pass {pass_num}: chain {self.routing.quality_loop.first}→{self.routing.quality_loop.second}→{self.routing.quality_loop.third}")
            try:
                rewritten = await self._call_ai_raw_with_chain(
                    self.routing.quality_loop, prompt, temperature=0.4, max_tokens=4000,
                    use_prompt_directly=True
                )
            except Exception as e:
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
                    raw = await asyncio.get_event_loop().run_in_executor(
                        None, lambda u=ollama_url, m=ollama_model: self._ollama_sync(prompt, temperature, max_tokens, ollama_url=u, ollama_model=m)
                    )
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
                        timeout=35,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _update_key_health(_key, headers=hdrs, status_code=200)
                        _clear_key_rate_limit(_key)
                        raw = resp.json()["choices"][0]["message"]["content"]
                        parsed = self._parse_json(raw)
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
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
                        _mark_key_rate_limited(_key, 45, "429")
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
                        timeout=45,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"]["content"]
                        parsed = self._parse_json(raw) if raw else {}
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
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
                        timeout=45,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        raw = resp.json()["content"][0]["text"]
                        parsed = self._parse_json(raw) if raw else {}
                        if parsed:
                            return _CallResult(
                                success=True, provider=provider,
                                data=parsed, status_code=200, response_chars=len(raw or ""),
                                response_headers=hdrs,
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
                _max_retries = 2 if ":free" in model else 0  # Free models get retries for upstream 429
                for _attempt in range(_max_retries + 1):
                    for _ki, _key in enumerate(keys):
                        resp = await asyncio.get_event_loop().run_in_executor(None, lambda k=_key, m=model: httpx.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                            json={"model": m, "messages": [
                                {"role": "system", "content": sys_msg},
                                {"role": "user", "content": prompt},
                            ], "temperature": temperature, "max_tokens": _adj_tokens},
                            timeout=45,
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
                            raw = choice.get("message", {}).get("content") or ""
                            if not raw:
                                # Try reasoning field (DeepSeek R1 etc.)
                                reasoning = choice.get("message", {}).get("reasoning") or ""
                                if reasoning:
                                    raw = reasoning
                            parsed = self._parse_json(raw) if raw else {}
                            if parsed:
                                return _CallResult(
                                    success=True, provider=provider,
                                    data=parsed, status_code=200, response_chars=len(raw or ""),
                                    response_headers=hdrs,
                                )
                            log.warning(f"[OR] {provider} empty/unparseable (raw={repr((raw or '')[:120])})")
                            last_result = _CallResult(
                                success=False, provider=provider, error="empty_response",
                                status_code=200, response_chars=len(raw or ""), response_headers=hdrs,
                            )
                            if _ki < len(keys) - 1:
                                continue
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
                        timeout=45,
                    ))
                    hdrs = dict(resp.headers)
                    if resp.status_code == 200:
                        _update_key_health(_key, headers=hdrs, status_code=200)
                        _clear_key_rate_limit(_key)
                        raw = resp.json()["choices"][0]["message"]["content"]
                        ok = bool(raw and len(raw) > 200)
                        if ok:
                            return _CallResult(
                                success=True, provider=provider, data=raw,
                                status_code=200, response_chars=len(raw),
                                response_headers=hdrs,
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
                        _mark_key_rate_limited(_key, 45, "429")
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
                if use_prompt_directly:
                    if len(prompt) > 6000:
                        trunc = prompt[:2000] + "\n\n" + prompt[2000:6000] + "\n\n[Content truncated for model context limit]\n\nOutput ONLY the improved HTML article. No commentary."
                    else:
                        trunc = prompt
                    async with _get_ollama_sem():
                        raw = await asyncio.get_event_loop().run_in_executor(
                            None, lambda p=trunc, u=ollama_url, m=ollama_model: self._ollama_sync(p, temperature, max_tokens, raw_text=True, ollama_url=u, ollama_model=m)
                        )
                else:
                    raw = await self._ollama_section_writer(ollama_url=ollama_url)
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
                            timeout=45,
                        ))
                        hdrs = dict(resp.headers)
                        if resp.status_code == 200:
                            raw = resp.json()["choices"][0]["message"]["content"]
                            ok = bool(raw and len(raw) > 200)
                            if ok:
                                return _CallResult(
                                    success=True, provider=provider, data=raw,
                                    status_code=200, response_chars=len(raw),
                                    response_headers=hdrs,
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
                            timeout=45,
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
                            ok = bool(raw and len(raw) > 200)
                            if ok:
                                return _CallResult(
                                    success=True, provider=provider, data=raw,
                                    status_code=200, response_chars=len(raw),
                                    response_headers=hdrs,
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
        HARD_TIMEOUT = 50  # seconds per provider (must exceed Ollama‑s 45s HTTP timeout)

        # ── Build ordered list of available providers ──────────────────────
        chain = [p for p in [cfg.first, cfg.second, cfg.third]
                 if p and p != "skip"]
        available = []
        for provider in chain:
            if not _is_provider_available(provider):
                self._add_log("warn", f"AI {provider}: skipped (cooldown/disabled)")
                continue
            available.append(provider)

        if not available:
            self._add_log("error", "All AI providers failed for this request")
            return {}

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
                    try:
                        _log_usage(provider, json.dumps(cr.json_data) if cr.json_data else "")
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
                elif cr.error and cr.error != "no_api_key":
                    self._add_log("warn", f"AI {provider}: {cr.error[:100]} [{cr.request_id}]")
                    _mark_provider_bad(provider, "error", 60)
                else:
                    self._add_log("warn", f"AI {provider}: empty response [{cr.request_id}]")
            except asyncio.TimeoutError:
                self._add_log("error", f"AI {provider}: hard timeout ({HARD_TIMEOUT}s)")
                _mark_provider_bad(provider, "timeout", 45)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._add_log("error", f"AI {provider}: {str(e)[:100]}")
                _mark_provider_bad(provider, "error", 60)
            return {}

        # ── Sequential fallback for OR free-tier (avoid parallel 429 burst) ──
        all_or = all(p.startswith("or_") or p == "openrouter" for p in available)
        if all_or:
            for p in available:
                data = await _run_provider(p)
                if data:
                    return data
            self._add_log("error", "All AI providers failed for this request")
            return {}

        # ── Parallel race: launch all, take first success ─────────────────
        tasks = {asyncio.create_task(_run_provider(p)): p for p in available}
        result = {}
        try:
            remaining = set(tasks.keys())
            while remaining:
                done, remaining = await asyncio.wait(remaining, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try:
                        data = task.result()
                        if data:
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

        if not result:
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
        HARD_TIMEOUT = 45  # seconds per provider

        # ── Build ordered list of available providers ──────────────────────
        chain = [p for p in [cfg.first, cfg.second, cfg.third]
                 if p and p != "skip"]
        available = []
        for provider in chain:
            if not _is_provider_available(provider):
                self._add_log("warn", f"AI {provider}: skipped (cooldown/disabled)")
                continue
            available.append(provider)

        if not available:
            self._add_log("error", "All AI providers failed for raw content generation")
            return ""

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
                    try:
                        _log_usage(provider, cr.text)
                    except Exception:
                        pass  # Never let logging break the pipeline
                    return cr.text
                # Log failure reason
                self._log_chain_failure(provider, cr)
            except asyncio.TimeoutError:
                self._add_log("error", f"AI {provider}: hard timeout ({HARD_TIMEOUT}s)")
                _mark_provider_bad(provider, "timeout", 45)
            except asyncio.CancelledError:
                pass  # normal — another provider won the race
            except Exception as e:
                self._add_log("error", f"AI {provider}: {str(e)[:100]}")
                _mark_provider_bad(provider, "error", 60)
            return ""

        # ── Sequential fallback for OR free-tier (avoid parallel 429 burst) ──
        all_or = all(p.startswith("or_") or p == "openrouter" for p in available)
        if all_or:
            for p in available:
                text = await _run_provider(p)
                if text:
                    return text
            self._add_log("error", "All AI providers failed for raw content generation")
            return ""

        # ── Parallel race: launch all, take first success ─────────────────
        tasks = {asyncio.create_task(_run_provider(p)): p for p in available}
        result = ""
        try:
            remaining = set(tasks.keys())
            while remaining:
                done, remaining = await asyncio.wait(remaining, return_when=asyncio.FIRST_COMPLETED)
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

        if not result:
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
                    json=req_json, timeout=45,
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
                if wait and wait <= 15:
                    log.info(f"Groq 429 (last key) — waiting {wait:.1f}s then retrying")
                    _time.sleep(wait)
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
                                                       headers=h, json=req_json, timeout=45))
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
                                                               headers=h, json=req_json, timeout=45))
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
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._ollama_sync(prompt, temperature, max_tokens)
                )
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

    def _ollama_sync(self, prompt: str, temperature: float, max_tokens: int, raw_text: bool = False, ollama_url: str = "", ollama_model: str = "") -> str:
        """Call Ollama synchronously. Adjusts context window based on prompt size."""
        url = ollama_url or _live_ollama_url()
        model = ollama_model or _live_ollama_model()
        mem_before = _get_mem_pct()
        if mem_before > 85:
            log.warning(f"Memory at {mem_before}% before Ollama call — high pressure")
        # Scale context window: 2048 for all calls (smaller = faster + less RAM)
        num_ctx = 2048
        # Remote Ollama on CPU needs more time (60-90s per section); local is faster
        is_remote = url and "localhost" not in url and "127.0.0.1" not in url
        timeout = 120 if is_remote else 45
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
        """Last resort: build basic HTML from structure headings so pipeline never fails on empty content."""
        kw = self.keyword
        structure = self._structure or self._default_structure()
        parts = [
            f"<p>{kw.title()}: A comprehensive guide covering everything you need to know about {kw}. "
            f"In this article, we explore key aspects, benefits, and practical guidance.</p>"
        ]
        for s in structure.get("h2_sections", [])[:8]:
            anchor = re.sub(r'[^a-z0-9]+', '-', s['h2'].lower())[:40].strip('-')
            parts.append(f'<h2 id="{anchor}">{s["h2"]}</h2>')
            angle = s.get("content_angle", "")
            parts.append(f"<p>This section covers {angle or s['h2'].lower()} related to {kw}. "
                         f"Understanding this aspect helps you make better decisions about {kw}.</p>")
            for h3 in s.get("h3s", [])[:2]:
                parts.append(f"<h3>{h3}</h3>")
                parts.append(f"<p>{h3} is an important consideration when evaluating {kw}.</p>")
        faqs = structure.get("faqs", [])[:4]
        if faqs:
            parts.append("<h2>Frequently Asked Questions</h2>")
            for f in faqs:
                q_text = f.get("q") or f.get("question") or f.get("text", "")
                if not q_text:
                    continue
                parts.append(f'<h3>{q_text}</h3>')
                parts.append(f'<p>{f.get("a_plan", f"This is an important question about {kw}.")}</p>')
        parts.append(f'<p><strong>In summary</strong>, {kw} is an important topic. '
                     f'{structure.get("conclusion_plan", "Contact us to learn more.")} </p>')
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
            faqs = structure.get("faqs", [])[:3]
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
- E-E-A-T signals: add 1-2 specific first-person insights ("In our testing...", "We found that...")
- Factual precision: add a specific statistic or year where claims are vague
- Natural keyword integration: ensure "{self.keyword}" appears in opening, each H2 intro, and conclusion

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
                timeout=45,
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
        """Robustly extract JSON from AI response."""
        if not raw:
            return {}
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(raw)
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

