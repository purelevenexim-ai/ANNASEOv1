"""
Recovery strategy builder — constructs targeted fix prompts
from classified issues + recovery_rules.
"""
from typing import Dict, List

# Specific fix instructions for contract-failure types emitted by the validate step.
# These override the generic "Fix the <type> issue" fallback when there is no entry
# in recovery_rules["issue_actions"] for the type.
_CONTRACT_INSTRUCTIONS: Dict[str, str] = {
    "missing_pros_cons": (
        "Add a clear pros/cons block in this section. "
        "Use a <ul> for pros (at least 3 advantages/benefits with specific detail) "
        "and a <ul> for cons (at least 3 drawbacks/limitations with honest nuance). "
        "Label each list with a bold heading: <strong>Pros</strong> / <strong>Cons</strong>."
    ),
    "missing_buyer_guidance": (
        "Add explicit buyer guidance: who this product/service is best for, "
        "a concrete recommendation ('we recommend X if…'), and 'choose if' or 'ideal for' language. "
        "At least one sentence must name a specific use case or buyer profile."
    ),
    "missing_objections": (
        "Address the common reader objections in this section: "
        "is it worth the price, what are the risks or limitations, "
        "and when should a reader NOT choose this. "
        "Use a direct, honest tone — 'fair question: here's when it may not suit you'."
    ),
    "contract_failure": (
        "Fix the structural gap described above: follow the section contract requirements "
        "and ensure the section covers all required content elements completely."
    ),
}


def build_recovery_prompt(
    section_html: str,
    section_heading: str,
    classified_issues: List[Dict],
    keyword: str,
    generation_rules: Dict,
    *,
    article_context: str = "",
) -> str:
    """Build a targeted AI prompt to fix a specific section.

    Includes only the relevant fix instructions for THIS section's issues.
    Does NOT include the entire article — just the failing section.
    """
    # Build fix instruction block from classified issues.
    # For contract failures (source="contract"), use targeted instructions from
    # _CONTRACT_INSTRUCTIONS instead of the generic recovery_rules fallback.
    fix_lines = []
    for ci in classified_issues:
        issue_type = ci.get("type", "")
        if ci.get("source") == "contract" and issue_type in _CONTRACT_INSTRUCTIONS:
            instruction = _CONTRACT_INSTRUCTIONS[issue_type]
        else:
            instruction = ci.get("instruction") or _CONTRACT_INSTRUCTIONS.get(issue_type, f"Fix the {issue_type} issue")
        fix_lines.append(f"- [{ci.get('severity', '?').upper()}] {ci['detail']}\n  FIX: {instruction}")
    fixes_text = "\n".join(fix_lines)

    # Extract voice/style guidance from generation_rules (condensed)
    voice = generation_rules.get("voice", {})
    forbidden_words = generation_rules.get("forbidden_words", [])

    prompt = f"""You are a senior content editor. Fix the specific issues in this section.

SECTION HEADING: {section_heading}
KEYWORD: "{keyword}"

━━━ ISSUES TO FIX ━━━
{fixes_text}

━━━ WRITING RULES ━━━
- Tone: {voice.get('tone', 'natural, expert, clear')}
- Use contractions naturally (don't, isn't, won't)
- Vary sentence lengths — mix short (8-12w) and medium (18-22w)
- Never 3 consecutive sentences of similar length
- Cite SPECIFIC named sources (e.g., "2024 FDA guidelines") — never vague
- NEVER use: {', '.join(forbidden_words[:12])}
- Preserve ALL existing <a href="..."> links exactly
- KEEP the same heading (H2/H3) — only fix the body content
- Output must be at least as long as input — expand, don't shrink

{f'ARTICLE CONTEXT: {article_context[:500]}' if article_context else ''}

━━━ SECTION TO FIX ━━━
{section_html}

Output ONLY the fixed section HTML. No markdown, no code fences, no commentary."""

    return prompt
