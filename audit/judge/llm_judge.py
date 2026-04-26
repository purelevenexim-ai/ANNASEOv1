"""
audit/judge/llm_judge.py
========================
LLM-as-Judge: uses the remote Ollama proxy (Mistral 7B) to evaluate
pipeline outputs for quality, relevance, and hallucination.

The judge runs as a SECONDARY quality gate — it does NOT replace
the rule-based validators but adds reasoning-level evaluation.

Usage:
    from audit.judge.llm_judge import run_llm_judge
    verdict = run_llm_judge(input_data={"url": "..."}, output_data=result)
    # verdict["final_score"] — 0..10, threshold 6.5 for pass
"""
from __future__ import annotations
import json
import os
import logging
import re
from typing import Any

import httpx

from audit.judge.judge_prompt import JUDGE_SYSTEM, JUDGE_USER

log = logging.getLogger("audit.judge")

# Remote Ollama proxy — same as used by the main app
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")
_JUDGE_MODEL = os.getenv("AUDIT_JUDGE_MODEL", "mistral:7b-instruct-q4_K_M")
_JUDGE_TIMEOUT = 120  # seconds — judge prompt is long
_PASS_THRESHOLD = 6.5  # out of 10


def _truncate(obj: Any, max_items: int = 20, max_chars: int = 800) -> str:
    """Safely convert to a compact string for the judge prompt."""
    if isinstance(obj, list):
        obj = obj[:max_items]
    text = json.dumps(obj, ensure_ascii=False)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _build_judge_prompt(input_data: dict, output_data: dict) -> str:
    keywords = output_data.get("keywords") or output_data.get("top_keywords") or []
    profile = output_data.get("profile") or output_data.get("business_profile") or {}
    clusters = output_data.get("clusters") or []

    kw_sample = [
        {"keyword": k.get("keyword"), "intent": k.get("intent"), "relevance": k.get("ai_relevance")}
        for k in keywords[:20]
    ]

    input_summary = _truncate(input_data, max_chars=400)
    profile_summary = _truncate({
        "universe": profile.get("universe"),
        "pillars": profile.get("pillars", []),
        "business_type": profile.get("business_type"),
    }, max_chars=400)
    cluster_summary = _truncate(
        [c.get("cluster_name") for c in clusters], max_chars=300
    )

    return JUDGE_USER.format(
        input_summary=input_summary,
        kw_count=len(keywords),
        kw_sample=_truncate(kw_sample),
        profile_summary=profile_summary,
        cluster_count=len(clusters),
        cluster_summary=cluster_summary,
    )


def _parse_judge_response(raw: str) -> dict[str, Any]:
    """Extract JSON from judge response; handle markdown fences and partial output."""
    # Strip think blocks (DeepSeek-style)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    log.warning("Judge returned non-JSON: %s", raw[:200])
    return {
        "final_score": 0.0,
        "issues": ["Judge returned invalid JSON"],
        "relevance": 0,
        "consistency": 0,
        "completeness": 0,
        "hallucination": 0,
        "business_value": 0,
    }


def run_llm_judge(
    input_data: dict,
    output_data: dict,
    model: str | None = None,
    timeout: int = _JUDGE_TIMEOUT,
) -> dict[str, Any]:
    """
    Run LLM-as-Judge evaluation.

    Returns verdict dict with:
      final_score (0..10), passed (bool), individual dimension scores, issues list
    """
    model = model or _JUDGE_MODEL
    prompt = _build_judge_prompt(input_data, output_data)
    full_prompt = f"{JUDGE_SYSTEM}\n\n{prompt}"

    try:
        resp = httpx.post(
            f"{_OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
    except Exception as exc:
        log.error("LLM judge failed: %s", exc)
        return {
            "final_score": -1.0,
            "passed": False,
            "error": str(exc),
            "issues": [f"Judge unavailable: {exc}"],
        }

    verdict = _parse_judge_response(raw)

    # Compute final_score if model didn't
    if "final_score" not in verdict or verdict["final_score"] == 0:
        scores = [
            verdict.get("relevance", 0) * 0.25,
            verdict.get("consistency", 0) * 0.20,
            verdict.get("completeness", 0) * 0.15,
            verdict.get("hallucination", 0) * 0.20,
            verdict.get("business_value", 0) * 0.20,
        ]
        verdict["final_score"] = round(sum(scores), 2)

    verdict["passed"] = verdict["final_score"] >= _PASS_THRESHOLD
    verdict["threshold"] = _PASS_THRESHOLD
    verdict["model"] = model
    return verdict
