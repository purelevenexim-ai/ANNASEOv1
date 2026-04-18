"""
================================================================================
ANNASEO — CENTRAL AI CONFIGURATION
================================================================================
Single source of truth for all AI provider settings.

Priority order (configured here):
  1. Groq (primary — fast, free tier)
  2. Ollama/DeepSeek (secondary — local, offline-capable)
  3. Gemini (tertiary — when available)
  4. Claude (quality gates only — pay-per-use)

All engines import from here. To change a model or key, edit .env only.
================================================================================
"""

from __future__ import annotations
import os
import json
import logging
import re
import threading
import time
from typing import Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("annaseo.ai_config")


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER SETTINGS — loaded from .env
# ─────────────────────────────────────────────────────────────────────────────

class AICfg:
    """Central AI configuration — reads from environment."""

    # ── Primary: Groq ─────────────────────────────────────────────────────────
    GROQ_KEY        = os.getenv("GROQ_API_KEY", "")
    GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # ── Secondary: Ollama proxy (remote CPU server) ────────────────────────────
    # Remote proxy: max 1 concurrent request, 600s internal timeout.
    # Client timeout must exceed server timeout → use 620s.
    OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
    OLLAMA_TIMEOUT  = 620  # seconds — must exceed server's 600s internal timeout
    OLLAMA_MAX_CTX  = 4096 # context for humanize prompts; verify proxy /health before raising further
    OLLAMA_HEALTH_TTL = 60 # seconds to cache health check result

    # ── Tertiary: Gemini ──────────────────────────────────────────────────────
    GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "")
    GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

    # ── Quality gate: Claude ──────────────────────────────────────────────────
    CLAUDE_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    CLAUDE_MAX_TOKENS = 1000

    # ── Rate limits (free tiers) ───────────────────────────────────
    # Groq free:  30 RPM, 6000 TPM  →  safe = 3s between calls
    # Gemini free: ~10 RPM           →  safe = 8s between calls
    # Ollama: no limit, bounded by CPU speed
    GROQ_RATE_LIMIT = 5.0   # seconds between Groq calls (free tier: 30 RPM)
    GEMINI_RATE_LIMIT = 8.0 # seconds between Gemini calls
    AI_RATE_LIMIT   = 2.0   # minimum gap between ANY AI call

    @classmethod
    def reload(cls):
        """Reload all values from environment (useful after settings update)."""
        load_dotenv(override=True)
        cls.GROQ_KEY     = os.getenv("GROQ_API_KEY", "")
        cls.GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        cls.OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")
        cls.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
        cls.GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")
        cls.CLAUDE_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
        cls.CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        log.info("[AICfg] Reloaded AI configuration from environment")

    @classmethod
    def status(cls) -> dict:
        """Return the current provider status for settings UI."""
        return {
            "groq":   {"configured": bool(cls.GROQ_KEY),  "model": cls.GROQ_MODEL},
            "ollama": {"configured": bool(cls.OLLAMA_URL), "model": cls.OLLAMA_MODEL, "url": cls.OLLAMA_URL},
            "gemini": {"configured": bool(cls.GEMINI_KEY), "model": "gemini-flash-latest"},
            "claude": {"configured": bool(cls.CLAUDE_KEY), "model": cls.CLAUDE_MODEL},
        }


# ─────────────────────────────────────────────────────────────────────────────
# CENTRAL AI ROUTER
# ─────────────────────────────────────────────────────────────────────────────

class AIRouter:
    """
    Central AI router for all AnnaSEO engines.

    Priority: Groq → Ollama/DeepSeek → Gemini
    On ANY error (rate limit, quota, timeout, parse failure):
      - Log clearly with provider name
      - Move to next provider immediately (no retry)
      - If all fail, return empty string and log warning

    Usage:
        text = AIRouter.call("your prompt")
        text, tokens = AIRouter.call_with_tokens("your prompt")
    """

    _last_call_time: float = 0.0

    @classmethod
    def _rate_limit(cls):
        elapsed = time.time() - cls._last_call_time
        if elapsed < AICfg.AI_RATE_LIMIT:
            time.sleep(AICfg.AI_RATE_LIMIT - elapsed)
        cls._last_call_time = time.time()

    _last_groq_time: float = 0.0
    _last_gemini_time: float = 0.0

    # ── Circuit breaker state (I28) ──────────────────────────────────────
    _groq_429_count: int = 0
    _groq_429_window_start: float = 0.0
    _groq_circuit_open_until: float = 0.0
    _GROQ_CB_THRESHOLD = 2        # 429s within window to trip
    _GROQ_CB_WINDOW = 60.0        # seconds — rolling window
    _GROQ_CB_COOLDOWN = 30.0      # seconds to skip Groq after trip (kept short for sustained workloads)

    @classmethod
    def _groq_circuit_ok(cls) -> bool:
        """Return False if the Groq circuit breaker is open."""
        now = time.time()
        if now < cls._groq_circuit_open_until:
            return False
        # Reset window if expired
        if now - cls._groq_429_window_start > cls._GROQ_CB_WINDOW:
            cls._groq_429_count = 0
            cls._groq_429_window_start = now
        return True

    @classmethod
    def _groq_record_429(cls):
        """Record a 429 hit and trip the breaker if threshold exceeded."""
        now = time.time()
        if now - cls._groq_429_window_start > cls._GROQ_CB_WINDOW:
            cls._groq_429_count = 0
            cls._groq_429_window_start = now
        cls._groq_429_count += 1
        if cls._groq_429_count >= cls._GROQ_CB_THRESHOLD:
            cls._groq_circuit_open_until = now + cls._GROQ_CB_COOLDOWN
            log.warning("[AIRouter] Groq circuit breaker OPEN — %d 429s in %.0fs, "
                        "skipping Groq for %.0fs",
                        cls._groq_429_count, cls._GROQ_CB_WINDOW, cls._GROQ_CB_COOLDOWN)
            cls._groq_429_count = 0

    @classmethod
    def call(cls, prompt: str, system: str = "You are an expert SEO analyst.",
             temperature: float = 0.2) -> str:
        """Call AI with fallback chain. Returns text or empty string — never raises."""
        text, _ = cls.call_with_tokens(prompt, system, temperature)
        return text

    @classmethod
    def call_with_tokens(cls, prompt: str, system: str = "You are an expert SEO analyst.",
                         temperature: float = 0.2) -> Tuple[str, int]:
        """Call AI with fallback chain. Returns (text, tokens)."""
        cls._rate_limit()

        # 1. Try Groq (primary) — with circuit breaker + per-provider rate limit
        if AICfg.GROQ_KEY and cls._groq_circuit_ok():
            groq_elapsed = time.time() - cls._last_groq_time
            if groq_elapsed < AICfg.GROQ_RATE_LIMIT:
                time.sleep(AICfg.GROQ_RATE_LIMIT - groq_elapsed)
            text, tokens = cls._call_groq(prompt, system, temperature)
            cls._last_groq_time = time.time()
            if text:
                return text, tokens

        # 2. Try Ollama/DeepSeek (secondary)
        text = cls._call_ollama(prompt, system, temperature)
        if text:
            return text, 0

        # 3. Try Gemini (tertiary) — with per-provider rate limit
        if AICfg.GEMINI_KEY:
            gemini_elapsed = time.time() - cls._last_gemini_time
            if gemini_elapsed < AICfg.GEMINI_RATE_LIMIT:
                time.sleep(AICfg.GEMINI_RATE_LIMIT - gemini_elapsed)
            text = cls._call_gemini(prompt, temperature)
            cls._last_gemini_time = time.time()
            if text:
                return text, 0

        # All failed
        log.warning("[AIRouter] All AI providers failed — proceeding without AI")
        return "", 0

    # Groq retry config
    _GROQ_MAX_RETRIES = 2
    _GROQ_BACKOFF = [5, 15]  # seconds per attempt — capped, never use retry-after header value
    _GROQ_RETRYABLE = {429, 502, 503, 504}

    @classmethod
    def _call_groq(cls, prompt: str, system: str, temperature: float) -> Tuple[str, int]:
        """Call Groq with retry on rate-limit/transient errors. Returns (text, tokens) or ("", 0)."""
        import requests as _req
        max_chars = 16000
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars] + "\n\n[Content truncated for token limit]"

        for attempt in range(1, cls._GROQ_MAX_RETRIES + 1):
            try:
                r = _req.post(AICfg.GROQ_URL, headers={
                    "Authorization": f"Bearer {AICfg.GROQ_KEY}",
                    "Content-Type": "application/json",
                }, json={
                    "model": AICfg.GROQ_MODEL,
                    "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 4096,
                }, timeout=30)

                if r.status_code == 413:
                    log.warning("[AIRouter] Groq 413: payload too large — skipping")
                    return "", 0

                if r.status_code in cls._GROQ_RETRYABLE:
                    if r.status_code == 429:
                        cls._groq_record_429()
                        # 429 = rate-limited — no retry, fall through to Ollama immediately
                        err_msg = ""
                        try:
                            err_msg = r.json().get("error", {}).get("message", "")[:120]
                        except Exception:
                            pass
                        log.warning(f"[AIRouter] Groq 429 — rate limited, falling back to Ollama immediately. {err_msg}")
                        return "", 0
                    # Other retryable errors (502/503/504) — brief retry
                    wait = cls._GROQ_BACKOFF[attempt - 1]
                    if attempt < cls._GROQ_MAX_RETRIES:
                        log.warning(f"[AIRouter] Groq {r.status_code} (attempt {attempt}/{cls._GROQ_MAX_RETRIES}) — retrying in {wait}s")
                        time.sleep(wait)
                        continue
                    log.warning(f"[AIRouter] Groq {r.status_code} max retries exhausted — skipping to next provider")
                    return "", 0

                if not r.ok:
                    log.warning(f"[AIRouter] Groq error {r.status_code}: {r.text[:200]} — skipping to next provider")
                    return "", 0

                data = r.json()
                text = data["choices"][0]["message"]["content"].strip()
                tokens = data.get("usage", {}).get("total_tokens", 0)
                return text, tokens

            except Exception as e:
                if attempt < cls._GROQ_MAX_RETRIES:
                    wait = cls._GROQ_BACKOFF[attempt - 1]
                    log.warning(f"[AIRouter] Groq failed (attempt {attempt}/{cls._GROQ_MAX_RETRIES}): {e} — retrying in {wait}s")
                    time.sleep(wait)
                    continue
                log.warning(f"[AIRouter] Groq failed (attempt {attempt}/{cls._GROQ_MAX_RETRIES}): {e} — skipping to next provider")
                return "", 0

        return "", 0

    # ── Ollama concurrency guard — proxy allows max 1 simultaneous request ──────
    _ollama_sem: threading.Semaphore = threading.Semaphore(1)

    # ── Ollama health cache — avoid hammering /health before every call ──────────
    _ollama_health_cache: dict = {"ok": True, "ts": 0.0, "cooldown_until": 0.0}

    @classmethod
    def _ollama_check_health(cls) -> bool:
        """
        Check the Ollama proxy /health endpoint.
        Returns True if safe to send a generation request.
        Caches result for OLLAMA_HEALTH_TTL seconds to avoid repeated polling.
        """
        import requests as _req
        now = time.time()
        # Still in cooldown from a previous circuit-breaker trip?
        if now < cls._ollama_health_cache["cooldown_until"]:
            remaining = int(cls._ollama_health_cache["cooldown_until"] - now)
            log.info(f"[AIRouter] Ollama in cooldown — {remaining}s remaining")
            return False
        # Use cached result if fresh
        if now - cls._ollama_health_cache["ts"] < AICfg.OLLAMA_HEALTH_TTL:
            return cls._ollama_health_cache["ok"]
        # Fetch fresh health data
        try:
            r = _req.get(
                f"{AICfg.OLLAMA_URL}/health",
                timeout=5,
            )
            if not r.ok:
                cls._ollama_health_cache.update({"ok": False, "ts": now})
                return False
            data = r.json()
            status = data.get("status", "ok")
            cb = data.get("circuit_breaker", {})
            cb_open = cb.get("open", False)
            cb_cooldown = cb.get("cooldown_remaining_sec", 0)
            if cb_open:
                cls._ollama_health_cache["cooldown_until"] = now + cb_cooldown + 2
                log.warning(f"[AIRouter] Ollama circuit breaker open — waiting {cb_cooldown}s")
                cls._ollama_health_cache.update({"ok": False, "ts": now})
                return False
            if status == "degraded":
                log.warning("[AIRouter] Ollama server memory degraded — skipping")
                cls._ollama_health_cache.update({"ok": False, "ts": now})
                return False
            cls._ollama_health_cache.update({"ok": True, "ts": now})
            return True
        except Exception as e:
            # /health not available — this is raw Ollama (no proxy), proceed
            log.debug(f"[AIRouter] Ollama /health not available ({e}) — assuming ok")
            cls._ollama_health_cache.update({"ok": True, "ts": now})
            return True

    @classmethod
    def _call_ollama(cls, prompt: str, system: str, temperature: float) -> str:
        """
        Call Ollama generate endpoint.

        Best practices implemented:
        - Health check before sending (circuit breaker + degraded status)
        - Global semaphore: only 1 request at a time (proxy limit)
        - 620s timeout (exceeds proxy's 600s internal timeout)
        - stream=False always (proxy requirement)
        - num_ctx set via AICfg.OLLAMA_MAX_CTX (verify proxy memory if raising above 4096)
        - system sent as separate field, not concatenated into prompt
        - Handles 503 (circuit breaker) and 504 (timeout) with backoff
        - Strips <think>...</think> reasoning blocks from response

        Returns text or "" on any error.
        """
        import requests as _req

        # 1. Health check (non-blocking, cached)
        if not cls._ollama_check_health():
            log.warning("[AIRouter] Ollama health check failed — skipping to next provider")
            return ""

        # 2. Acquire semaphore — ensures only 1 concurrent Ollama request
        acquired = cls._ollama_sem.acquire(blocking=True, timeout=5)
        if not acquired:
            log.warning("[AIRouter] Ollama semaphore not acquired — skipping to next provider")
            return ""

        try:
            payload: dict = {
                "model": AICfg.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": AICfg.OLLAMA_MAX_CTX,
                },
            }
            if system:
                payload["system"] = system

            r = _req.post(
                f"{AICfg.OLLAMA_URL}/api/generate",
                json=payload,
                timeout=AICfg.OLLAMA_TIMEOUT,
            )

            if r.status_code == 503:
                err = {}
                try:
                    err = r.json()
                except Exception:
                    pass
                cb_open = err.get("detail", {}).get("circuit_breaker_open", False) if isinstance(err.get("detail"), dict) else False
                if cb_open:
                    # Trip the health cache so next call skips immediately
                    cls._ollama_health_cache.update({"ok": False, "ts": time.time(), "cooldown_until": time.time() + 120})
                log.warning(f"[AIRouter] Ollama 503 — {err} — skipping to next provider")
                return ""

            if r.status_code == 504:
                log.warning("[AIRouter] Ollama 504 generation timeout — prompt may be too long")
                return ""

            if not r.ok:
                log.warning(f"[AIRouter] Ollama error {r.status_code} — skipping to next provider")
                return ""

            data = r.json()
            text = data.get("response", "").strip()
            # Invalidate health cache on success (mark server as healthy)
            cls._ollama_health_cache.update({"ok": True, "ts": time.time()})
            return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        except _req.exceptions.Timeout:
            log.warning(f"[AIRouter] Ollama request timed out after {AICfg.OLLAMA_TIMEOUT}s — skipping to next provider")
            return ""
        except Exception as e:
            log.warning(f"[AIRouter] Ollama failed: {e} — skipping to next provider")
            return ""
        finally:
            cls._ollama_sem.release()

    # Track Gemini quota exhaustion for session (daily limit)
    _gemini_quota_exhausted: bool = False

    @classmethod
    def _call_gemini(cls, prompt: str, temperature: float) -> str:
        """Call Gemini. No retry on 429 (daily quota). Returns text or "" on error."""
        import requests as _req
        if cls._gemini_quota_exhausted:
            log.info("[AIRouter] Gemini quota previously exhausted — skipping")
            return ""
        try:
            r = _req.post(f"{AICfg.GEMINI_URL}?key={AICfg.GEMINI_KEY}", json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
            }, timeout=30)
            if r.status_code == 429:
                cls._gemini_quota_exhausted = True
                log.warning("[AIRouter] Gemini quota exhausted (daily limit) — will not retry this session")
                return ""
            if not r.ok:
                log.warning(f"[AIRouter] Gemini error {r.status_code} — skipping to next provider")
                return ""
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"[AIRouter] Gemini failed: {e} — skipping to next provider")
            return ""

    @classmethod
    def extract_json(cls, text: str):
        """Extract JSON from AI response text. Returns dict/list or None."""
        if not text:
            return None
        # First try markdown code blocks (most reliable signal)
        for pattern in [r"```json\s*([\s\S]+?)```", r"```\s*([\s\S]+?)```"]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                candidate = m.group(1).strip()
                try:
                    return json.loads(candidate)
                except Exception:
                    continue
        # Try parsing the whole text directly (AI returned raw JSON)
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except Exception:
                pass
        # Greedy match for outermost JSON object (handles trailing text after JSON)
        m = re.search(r"\{[\s\S]*\}", text, re.DOTALL)
        if m:
            candidate = m.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                pass
        # Greedy match for outermost JSON array
        m = re.search(r"\[[\s\S]*\]", text, re.DOTALL)
        if m:
            candidate = m.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                pass
        return None
