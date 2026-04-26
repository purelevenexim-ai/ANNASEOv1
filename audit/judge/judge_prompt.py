"""
audit/judge/judge_prompt.py
============================
Prompt templates for the LLM-as-Judge module.

The judge is Mistral 7B via the remote Ollama proxy.
It scores each pipeline output on 5 axes and returns strict JSON.
"""

JUDGE_SYSTEM = (
    "You are a strict AI quality auditor for an SEO keyword intelligence system. "
    "You evaluate pipeline outputs with no bias. "
    "You MUST return ONLY valid JSON — no markdown, no explanation."
)

JUDGE_USER = """You are auditing the output of an SEO keyword intelligence pipeline.

=== BUSINESS INPUT ===
{input_summary}

=== PIPELINE OUTPUT ===
Keywords ({kw_count} total, sample of 20):
{kw_sample}

Business Profile:
{profile_summary}

Clusters ({cluster_count}):
{cluster_summary}

=== EVALUATION TASK ===
Score each dimension from 0 to 10:

1. relevance      — Are the keywords actually relevant to this business?
2. consistency    — Is the output internally consistent (no contradictions)?
3. completeness   — Are all key product categories and intents covered?
4. hallucination  — How free from invented/nonsense content? (10=none, 0=severe)
5. business_value — Would a real business owner find this useful and actionable?

Return ONLY this JSON (integers for scores):
{{
  "relevance": 0,
  "consistency": 0,
  "completeness": 0,
  "hallucination": 0,
  "business_value": 0,
  "final_score": 0.0,
  "strengths": ["..."],
  "issues": ["..."]
}}

Rules:
- final_score = weighted average: relevance*0.25 + consistency*0.20 + completeness*0.15 + hallucination*0.20 + business_value*0.20
- Be strict. A score of 7+ means production-ready. 5-7 = needs work. <5 = broken.
- Base your judgment ONLY on the provided data, not on what you think SEO should be."""
