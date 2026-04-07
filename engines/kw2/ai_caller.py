"""
kw2 ai_caller — per-session AI provider routing.

Wraps core.ai_config.AIRouter with provider selection support.
Every kw2 engine calls kw2_ai_call() instead of AIRouter.call() directly.
"""
import logging

from core.ai_config import AIRouter

log = logging.getLogger("kw2.ai")


def kw2_ai_call(prompt: str, system: str = "", provider: str = "auto",
                temperature: float = 0.2) -> str:
    """
    Call AI with provider selection.

    provider values:
      "auto"   → full cascade (Groq → Ollama → Gemini)
      "groq"   → Groq only, fallback to cascade on failure
      "gemini" → Gemini only, fallback to cascade on failure
      "ollama" → Ollama only, fallback to cascade on failure
    """
    system = system or "You are an expert SEO analyst."

    if provider == "auto":
        return AIRouter.call(prompt, system, temperature)

    # Direct provider call with fallback
    text = ""
    if provider == "groq":
        result = AIRouter._call_groq(prompt, system, temperature)
        text = result[0] if isinstance(result, tuple) else result
    elif provider == "gemini":
        text = AIRouter._call_gemini(prompt, temperature) or ""
    elif provider == "ollama":
        text = AIRouter._call_ollama(prompt, system, temperature) or ""

    if text:
        return text

    # Fallback to full cascade
    log.warning(f"[kw2_ai_call] {provider} failed, falling back to auto cascade")
    return AIRouter.call(prompt, system, temperature)


def kw2_extract_json(text: str):
    """Extract JSON from AI response. Returns dict/list or None."""
    return AIRouter.extract_json(text)
