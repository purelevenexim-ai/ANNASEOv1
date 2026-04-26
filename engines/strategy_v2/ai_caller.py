"""
Strategy V2 — AI caller with OpenAI primary, Gemini Flash fallback, Groq tertiary.

Uses requests (sync) — runs in ThreadPoolExecutor from pipeline.py.
"""
import json
import logging
import os
import re
import time

import requests

from core.ai_config import AICfg

log = logging.getLogger("strategy_v2.ai_caller")

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_TIMEOUT = 60  # seconds


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks (DeepSeek-R1 style)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> str:
    """Strip markdown fences and return raw JSON string."""
    text = _strip_think_tags(text).strip()
    if text.startswith("```"):
        parts = text.split("```")
        for part in parts:
            stripped = part.lstrip("json").strip()
            if stripped.startswith(("{", "[")):
                return stripped
    return text


def _call_openai(system: str, user: str, temperature: float = 0.4) -> str:
    """Call OpenAI chat completions API."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},  # enforce JSON mode
    }
    resp = requests.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_OPENAI_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, temperature: float = 0.4) -> str:
    """Call Gemini Flash via REST."""
    api_key = AICfg.GEMINI_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    url = AICfg.GEMINI_URL + f"?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2000},
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(system: str, user: str, temperature: float = 0.4) -> str:
    """Call Groq via OpenAI-compatible API."""
    api_key = AICfg.GROQ_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
    }
    resp = requests.post(
        AICfg.GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_ai_json(system: str, user_prompt: str, gemini_merged_prompt: str,
                 temperature: float = 0.4) -> dict:
    """
    Call AI with provider fallchain: OpenAI → Gemini → Groq.
    Returns parsed JSON dict/list.
    Raises RuntimeError if all providers fail.
    """
    providers_tried = []

    # 1. OpenAI
    if os.getenv("OPENAI_API_KEY", ""):
        try:
            raw = _call_openai(system, user_prompt, temperature)
            return json.loads(_extract_json(raw))
        except Exception as e:
            providers_tried.append(f"openai: {e}")
            log.warning(f"[strategy_v2] OpenAI failed: {e}")
            time.sleep(1)

    # 2. Gemini
    if AICfg.GEMINI_KEY:
        try:
            raw = _call_gemini(gemini_merged_prompt, temperature)
            return json.loads(_extract_json(raw))
        except Exception as e:
            providers_tried.append(f"gemini: {e}")
            log.warning(f"[strategy_v2] Gemini failed: {e}")
            time.sleep(1)

    # 3. Groq
    if AICfg.GROQ_KEY:
        try:
            raw = _call_groq(system, user_prompt, temperature)
            return json.loads(_extract_json(raw))
        except Exception as e:
            providers_tried.append(f"groq: {e}")
            log.warning(f"[strategy_v2] Groq failed: {e}")

    raise RuntimeError(f"All AI providers failed: {'; '.join(providers_tried)}")
