"""
Strategy V2 — Prompt system.

3-layer design:
  Layer 1: SYSTEM ROLE — strict strategist persona, JSON-only output
  Layer 2: Intelligence injection — business context + keyword data
  Layer 3: Task instructions — enforced reasoning steps

Two sets: OpenAI/Claude-style (system+user) and Gemini-style (merged user).
"""

BANNED_TERMS = [
    "pricing guide", "complete guide", "top 10", "best deals",
    "ultimate guide", "everything you need", "comprehensive guide",
    "beginners guide", "step by step guide",
]

# ─────────────────────────────────────────────────────────────────────────────
# System role (shared across angle + blueprint generation)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_ROLE = """You are a senior SEO strategist and conversion-focused content architect.

CORE RULES:
- Output ONLY valid JSON. No markdown fences, no explanations.
- Never generate generic titles like "Pricing Guide", "Complete Guide", "Top 10", "Best Deals".
- Every angle must have a clear perspective: contrarian, mistake-avoidance, comparison, decision, or hidden-truth.
- Think in this order: search intent → SERP gap → unique angle → narrative hook → structure.
- Quality over quantity. 5 differentiated assets beat 25 generic topics."""


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 1 — Angle Generator
# ─────────────────────────────────────────────────────────────────────────────

def build_angle_prompt(keyword: str, intent: str, kw2_context: dict = None) -> str:
    """Build the user prompt for angle generation."""
    ctx_block = ""
    if kw2_context:
        pillars = kw2_context.get("pillars", [])
        top_questions = kw2_context.get("top_questions", [])[:5]
        competitor_gaps = kw2_context.get("competitor_gaps", [])[:3]
        if pillars:
            ctx_block += f"\nPillar context: {', '.join(pillars[:5])}"
        if top_questions:
            ctx_block += f"\nBuyer questions found: {'; '.join(top_questions)}"
        if competitor_gaps:
            ctx_block += f"\nKnown competitor gaps: {'; '.join(competitor_gaps)}"

    return f"""Generate 5-8 differentiated content angles for this keyword.

KEYWORD: {keyword}
INTENT: {intent}{ctx_block}

CURRENT SERP ASSUMPTION: Repetitive listicles, generic guides, template-driven titles.
YOUR TASK: Create angles that exploit what's MISSING in those results.

STRICT RULES:
- Each angle must have a different perspective type
- NO "pricing guide", "complete guide", "top 10", "best deals", or similar templates
- Every angle must answer: "What makes THIS worth clicking over what already ranks?"
- Minimum 8 words per angle title

ANGLE TYPES TO INCLUDE (use each at most once):
- contrarian: challenges a common belief about {keyword}
- mistake: common errors buyers/users make with {keyword}
- comparison: {keyword} vs alternatives with decision clarity
- decision_framework: how to choose/evaluate {keyword} correctly
- hidden_truth: what sellers/brands don't explain about {keyword}

OUTPUT FORMAT (JSON array, no other text):
[
  {{
    "angle": "Why Most People Choose the Wrong [keyword] (And How to Avoid It)",
    "type": "mistake",
    "perspective": "one sentence on the unique viewpoint",
    "why_it_ranks": "what content gap this fills",
    "target_reader": "who this is for"
  }}
]"""


def build_angle_prompt_gemini(keyword: str, intent: str, kw2_context: dict = None) -> str:
    """Gemini-style merged prompt (no system message separation)."""
    role_block = SYSTEM_ROLE.replace("\n", " ")
    return f"{role_block}\n\n" + build_angle_prompt(keyword, intent, kw2_context)


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 2 — Blueprint Generator
# ─────────────────────────────────────────────────────────────────────────────

def build_blueprint_prompt(keyword: str, angle_obj: dict, intent: str,
                           kw2_context: dict = None) -> str:
    """Build the user prompt for blueprint generation from a single angle."""
    angle = angle_obj.get("angle", "")
    angle_type = angle_obj.get("type", "")
    perspective = angle_obj.get("perspective", "")

    biz_block = ""
    if kw2_context:
        usp = kw2_context.get("usp", "")
        audience = kw2_context.get("audience_summary", "")
        if usp:
            biz_block += f"\nBusiness USP: {usp}"
        if audience:
            biz_block += f"\nCore audience: {audience}"

    return f"""Convert this angle into a detailed content blueprint.

KEYWORD: {keyword}
ANGLE: {angle}
ANGLE TYPE: {angle_type}
PERSPECTIVE: {perspective}
INTENT: {intent}{biz_block}

BLUEPRINT REQUIREMENTS:
1. Title — natural language, reflects the angle. NOT a template. Min 8 words.
2. Hook — emotional/curiosity hook. Must challenge a belief or reveal a gap. Max 2 sentences.
3. Sections — 5-7 sections, each with a DISTINCT purpose. NO section should repeat another's purpose.
4. Story — a short relatable real-world scenario (2-3 sentences). Placed after section 2.
5. CTA — soft, trust-based guidance toward a decision. Not salesy.

SECTION RULES:
- Each section must logically follow from the previous
- Include at least one: problem framing, comparison/breakdown, decision framework
- NO "Introduction" or "Conclusion" as section headings

OUTPUT FORMAT (strict JSON, no other text):
{{
  "title": "...",
  "angle_type": "{angle_type}",
  "hook": {{
    "text": "...",
    "goal": "challenge_belief | reveal_gap | curiosity | mistake_warning"
  }},
  "sections": [
    {{
      "id": "S1",
      "heading": "...",
      "purpose": "engage | educate | compare | trust | decision | convert",
      "instruction": "what to cover in this section",
      "must_include": ["specific element or fact type"],
      "avoid": ["repeated idea or generic filler"]
    }}
  ],
  "story": {{
    "placement": "after_S2",
    "scenario": "Short vivid real-world scenario showing the problem or discovery",
    "instruction": "keep it sensory and relatable"
  }},
  "cta": {{
    "type": "soft",
    "text": "...",
    "goal": "guide_decision | build_trust | next_step"
  }}
}}"""


def build_blueprint_prompt_gemini(keyword: str, angle_obj: dict, intent: str,
                                  kw2_context: dict = None) -> str:
    """Gemini-style merged blueprint prompt."""
    role_block = SYSTEM_ROLE.replace("\n", " ")
    return f"{role_block}\n\n" + build_blueprint_prompt(keyword, angle_obj, intent, kw2_context)


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 3 — Targeted Fix (QA score < 75)
# ─────────────────────────────────────────────────────────────────────────────

def build_fix_prompt(blueprint: dict, gaps: list) -> str:
    """Build a targeted repair prompt for a low-scoring blueprint."""
    gaps_text = "\n".join(f"- {g}" for g in gaps)
    sections_text = "\n".join(
        f"  S{i+1}: {s.get('heading','?')} ({s.get('purpose','?')})"
        for i, s in enumerate(blueprint.get("sections", []))
    )
    return f"""Improve this content blueprint to fix specific quality gaps.

CURRENT TITLE: {blueprint.get('title', '')}
CURRENT SECTIONS:
{sections_text}

QUALITY GAPS TO FIX:
{gaps_text}

RULES:
- Fix ONLY the identified gaps. Do not rewrite sections that are already good.
- If a section is too generic, refine its heading and instruction only.
- If CTA or story is missing, add them.
- Keep the same angle_type and overall topic.

OUTPUT: Return the complete improved blueprint in the same JSON format.
Return ONLY the JSON object, no other text."""
