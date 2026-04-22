"""
kw2 ai_caller — per-session AI provider routing.

Wraps core.ai_config.AIRouter with provider selection support.
Every kw2 engine calls kw2_ai_call() instead of AIRouter.call() directly.
"""
import logging
import time

from core.ai_config import AIRouter, AICfg

log = logging.getLogger("kw2.ai")

# Cost per token (USD) by provider — estimates based on public pricing
_COST_TABLE = {
    "groq":   {"in": 0.0,               "out": 0.0},
    "ollama": {"in": 0.0,               "out": 0.0},
    "gemini": {"in": 0.10 / 1_000_000,  "out": 0.40 / 1_000_000},
    "claude": {"in": 3.00 / 1_000_000,  "out": 15.00 / 1_000_000},
    "auto":   {"in": 0.0,               "out": 0.0},  # usually Groq = free
}
_CHARS_PER_TOKEN = 4  # rough estimate for non-reported providers


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _calc_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    c = _COST_TABLE.get(provider, _COST_TABLE["auto"])
    return input_tokens * c["in"] + output_tokens * c["out"]


def kw2_ai_call(prompt: str, system: str = "", provider: str = "auto",
                temperature: float = 0.2,
                session_id: str = None, project_id: str = None,
                task: str = "unknown", event_cb=None, **kwargs) -> str:
    """
    Call AI with provider selection. Tracks usage to DB if session_id provided.

    provider values:
      "auto"   → full cascade (Groq → Ollama → Gemini)
      "groq"   → Groq only, fallback to cascade on failure
      "gemini" → Gemini only, fallback to cascade on failure
      "ollama" → Ollama only, fallback to cascade on failure

    event_cb: optional callable(dict) — receives real-time provider events:
      {"type": "provider_selected", "provider": "groq"}
      {"type": "rate_limited", "provider": "groq", "switching_to": "gemini"}
      {"type": "provider_switch", "from": "groq", "to": "gemini", "reason": "failed"}
    """
    def _emit(ev: dict):
        if event_cb:
            try:
                event_cb(ev)
            except Exception:
                pass

    system = system or "You are an expert SEO analyst."
    t_start = time.time()
    text = ""
    actual_provider = provider
    input_tokens = output_tokens = 0

    if provider == "auto":
        _emit({"type": "provider_selected", "provider": "groq"})
        text, input_tokens = AIRouter.call_with_tokens(prompt, system, temperature)
        if not text:
            _emit({"type": "provider_switch", "from": "groq", "to": "gemini", "reason": "failed"})
        actual_provider = "groq" if input_tokens else "auto"

    elif provider == "groq":
        _emit({"type": "provider_selected", "provider": "groq"})
        result = AIRouter._call_groq(prompt, system, temperature)
        text, input_tokens = result if isinstance(result, tuple) else (result, 0)
        if not text:
            log.warning("[kw2_ai_call] groq failed, falling back to Ollama then Gemini")
            _emit({"type": "rate_limited", "provider": "groq", "switching_to": "ollama",
                   "message": "Groq failed or rate-limited — switching to Ollama"})
            text = AIRouter._call_ollama(prompt, system, temperature) or ""
            actual_provider = "ollama"
            if not text and AICfg.GEMINI_KEY:
                _emit({"type": "provider_switch", "from": "ollama", "to": "gemini",
                       "reason": "ollama failed"})
                text = AIRouter._call_gemini(prompt, temperature) or ""
                actual_provider = "gemini"

    elif provider == "gemini":
        _emit({"type": "provider_selected", "provider": "gemini"})
        text = AIRouter._call_gemini(prompt, temperature) or ""
        if not text:
            log.warning("[kw2_ai_call] gemini failed, falling back to Ollama")
            _emit({"type": "rate_limited", "provider": "gemini", "switching_to": "ollama",
                   "message": "Gemini failed or rate-limited — switching to Ollama"})
            text = AIRouter._call_ollama(prompt, system, temperature) or ""
            actual_provider = "ollama"
        else:
            input_tokens = _estimate_tokens(prompt + system)

    elif provider == "ollama":
        _emit({"type": "provider_selected", "provider": "ollama",
               "message": "Using Ollama (local AI) — this may take 5-15 minutes"})
        text = AIRouter._call_ollama(prompt, system, temperature) or ""
        if not text:
            log.warning("[kw2_ai_call] ollama failed, falling back to Gemini")
            _emit({"type": "provider_switch", "from": "ollama", "to": "gemini",
                   "reason": "ollama failed or timed out"})
            if AICfg.GEMINI_KEY:
                text = AIRouter._call_gemini(prompt, temperature) or ""
                actual_provider = "gemini"
        else:
            input_tokens = _estimate_tokens(prompt + system)

    else:
        _emit({"type": "provider_selected", "provider": "groq"})
        text, input_tokens = AIRouter.call_with_tokens(prompt, system, temperature)
        actual_provider = "auto"

    if not text:
        _emit({"type": "providers_exhausted",
               "message": "All AI providers failed or are rate-limited. Please switch provider and retry."})

    latency_ms = int((time.time() - t_start) * 1000)
    output_tokens = _estimate_tokens(text) if text else 0
    cost = _calc_cost(actual_provider, input_tokens, output_tokens)

    # Log to DB if context provided
    if session_id and project_id:
        try:
            from engines.kw2 import db as kw2_db
            kw2_db.log_ai_usage(
                session_id=session_id, project_id=project_id,
                task=task, provider=actual_provider,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cost_usd=cost, latency_ms=latency_ms,
                prompt_chars=len(prompt), response_chars=len(text),
            )
        except Exception as e:
            log.debug(f"[kw2_ai_call] usage log failed: {e}")

    return text


def kw2_extract_json(text: str):
    """Extract JSON from AI response. Returns dict/list or None."""
    return AIRouter.extract_json(text)
