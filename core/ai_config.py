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

    # ── Secondary: Ollama / DeepSeek (local) ─────────────────────────────────
    OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    OLLAMA_TIMEOUT  = 60   # seconds — 3b model needs ~12s per batch on CPU

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
    GROQ_RATE_LIMIT = 3.0   # seconds between Groq calls
    GEMINI_RATE_LIMIT = 8.0 # seconds between Gemini calls
    AI_RATE_LIMIT   = 2.0   # minimum gap between ANY AI call

    @classmethod
    def reload(cls):
        """Reload all values from environment (useful after settings update)."""
        load_dotenv(override=True)
        cls.GROQ_KEY     = os.getenv("GROQ_API_KEY", "")
        cls.GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        cls.OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")
        cls.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
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

        # 1. Try Groq (primary) — with per-provider rate limit
        if AICfg.GROQ_KEY:
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

    @classmethod
    def _call_groq(cls, prompt: str, system: str, temperature: float) -> Tuple[str, int]:
        """Call Groq. Returns (text, tokens) or ("", 0) on any error."""
        import requests as _req
        # Truncate prompt if it's too long for Groq free tier (6000 TPM)
        # Rough heuristic: 1 token ≈ 4 chars; keep under ~4500 tokens prompt
        max_chars = 16000
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars] + "\n\n[Content truncated for token limit]"
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
            if r.status_code in (429, 413):
                err = r.json().get("error", {})
                log.warning(f"[AIRouter] Groq {r.status_code}: {err.get('message', 'rate/size limit')} — skipping to next provider")
                return "", 0
            if not r.ok:
                log.warning(f"[AIRouter] Groq error {r.status_code}: {r.text[:200]} — skipping to next provider")
                return "", 0
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return text, tokens
        except Exception as e:
            log.warning(f"[AIRouter] Groq failed: {e} — skipping to next provider")
            return "", 0

    @classmethod
    def _call_ollama(cls, prompt: str, system: str, temperature: float) -> str:
        """Call Ollama. Returns text or "" on any error."""
        import requests as _req
        try:
            combined = f"{system}\n\n{prompt}" if system else prompt
            r = _req.post(f"{AICfg.OLLAMA_URL}/api/generate", json={
                "model": AICfg.OLLAMA_MODEL,
                "stream": False,
                "options": {"temperature": temperature, "num_ctx": 2048},
                "prompt": combined,
            }, timeout=AICfg.OLLAMA_TIMEOUT)
            if not r.ok:
                log.warning(f"[AIRouter] Ollama error {r.status_code} — skipping to next provider")
                return ""
            data = r.json()
            text = data.get("response", "").strip()
            return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        except Exception as e:
            log.warning(f"[AIRouter] Ollama failed: {e} — skipping to next provider")
            return ""

    @classmethod
    def _call_gemini(cls, prompt: str, temperature: float) -> str:
        """Call Gemini. Returns text or "" on any error."""
        import requests as _req
        try:
            r = _req.post(f"{AICfg.GEMINI_URL}?key={AICfg.GEMINI_KEY}", json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
            }, timeout=30)
            if r.status_code == 429:
                log.warning("[AIRouter] Gemini quota exhausted — skipping to next provider")
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
        for pattern in [r"```json\s*([\s\S]+?)```", r"```\s*([\s\S]+?)```",
                        r"\{[\s\S]*?\}", r"\[[\s\S]*?\]"]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                candidate = m.group(1) if "```" in pattern else m.group(0)
                try:
                    return json.loads(candidate.strip())
                except Exception:
                    continue
        # Last-ditch: try parsing the whole text
        try:
            return json.loads(text.strip())
        except Exception:
            return None
