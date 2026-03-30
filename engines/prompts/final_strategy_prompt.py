SYSTEM_PROMPT = """
You are an elite SEO strategist and growth architect.

You generate COMPLETE, EXECUTABLE SEO STRATEGIES that can directly drive rankings.

You must:
- Think like Google's ranking systems (Helpful Content, topical authority)
- Avoid generic advice
- Produce only structured, high-quality outputs

STRICT RULES:
- Output MUST be valid JSON
- Output MUST match the schema EXACTLY
- Do NOT include explanations, markdown, or comments
- Do NOT include text outside JSON
- Do NOT invent fields
- Do NOT omit required fields
"""

FULL_PROMPT = """
You are the world's most effective SEO strategist.

INPUT DATA:
{context_json}

TASK:
Generate a COMPLETE SEO STRATEGY as strictly-formed JSON matching the schema in this document.

STRICT RULES:
- JSON ONLY
- NO markdown or explanation
- Fill required fields
"""

import json

JSON_GUARD = """
CRITICAL JSON RULES:
- Output ONLY JSON
- No backticks
- No text before or after JSON
- Use double quotes only
- No trailing commas
"""


def build_final_strategy_prompt(input_payload: dict, schema: dict, attempt: int = 0, memory_patterns: str = "") -> str:
    retry_instruction = ""
    if attempt > 0:
        retry_instruction = """
IMPORTANT:
Your previous response FAILED validation.
You MUST fix:
- invalid JSON formatting
- missing required fields
- incorrect schema structure
Return a corrected version.
"""

    memory_section = ""
    if memory_patterns:
        memory_section = f"""
LEARNING FROM PAST PATTERNS:
{memory_patterns}

Prioritize patterns with higher ROI and consistency.
"""

    return f"""
INPUT:
{json.dumps(input_payload, indent=2)}

{memory_section}
SCHEMA (STRICT):
{json.dumps(schema, indent=2)}

TASK:
Generate a COMPLETE SEO strategy.

REQUIREMENTS:
- Fill ALL required fields
- Ensure keyword intent correctness
- Build pillar + cluster structure
- Provide actionable execution plan

{retry_instruction}

{JSON_GUARD}

OUTPUT:
Return ONLY valid JSON.
If you cannot output valid JSON, return exactly:
{{"error": "INVALID_OUTPUT"}}
"""
