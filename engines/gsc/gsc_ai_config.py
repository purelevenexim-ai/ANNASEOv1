"""
GSC Engine — AI Project Understanding
Generates structured project config from a business description using AI.

This is the brain of the GSC pipeline:
  User Input → AI Understanding → ProjectConfig → GSC Processing

The ProjectConfig drives everything downstream:
  - Which pillars to filter for
  - Which keywords signal purchase intent
  - Which angles are "supporting" content
  - Synonym map for pillar matching
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ─── Prompt constants ────────────────────────────────────────────────────────

_SYSTEM = (
    "You are an expert SEO strategist and keyword intelligence system. "
    "Your job is to analyze a business/project description and extract a structured "
    "SEO strategy that will be used to filter and rank real Google Search Console keyword data. "
    "Return ONLY valid JSON — no markdown, no commentary, no code fences."
)

_PROMPT_TEMPLATE = """\
Analyze this business and generate a structured SEO keyword strategy.

BUSINESS INPUT:
- Description: {description}
- Target audience: {audience}
- Primary goal: {goal}
- Seed keywords: {seeds}

TASK — Return a single JSON object with exactly these keys:

{{
  "business_summary": "one sentence describing the business",
  "target_audience": "who the buyers/users are",
  "goal": "{goal}",
  "pillars": ["pillar1", "pillar2", ...],
  "purchase_intent_keywords": ["buy", "price", "wholesale", ...],
  "supporting_angles": ["benefits", "uses", "how to", ...],
  "synonyms": {{"pillar1": ["alt1", "alt2"], ...}},
  "customer_language_examples": ["example search 1", "example search 2", ...]
}}

RULES:
- "pillars": 5-15 core product/topic terms, short (1-2 words max). Use the seed keywords as a base.
- "purchase_intent_keywords": words that signal buying intent for THIS business (include generic buy/price + domain-specific terms).
- "supporting_angles": informational/content angles users search for BEFORE buying.
- "synonyms": regional or alternative names for each pillar (leave empty dict {{}} if not applicable).
- "customer_language_examples": 5-10 realistic Google queries this site would want to rank for.
- DO NOT generate random keywords. Think strategically.
- Keep output clean and machine-parseable.
"""


# ─── ProjectConfig dataclass ─────────────────────────────────────────────────

@dataclass
class ProjectConfig:
    """
    Structured project intelligence config generated from business description.
    Used by gsc_processor to drive pillar matching, intent classification, and scoring.
    """
    business_summary: str = ""
    target_audience: str = ""
    goal: str = "sales"
    pillars: list[str] = field(default_factory=list)
    purchase_intent_keywords: list[str] = field(default_factory=list)
    supporting_angles: list[str] = field(default_factory=list)
    synonyms: dict[str, list[str]] = field(default_factory=dict)
    customer_language_examples: list[str] = field(default_factory=list)

    # ── Source tracking ─────────────────────────────────────────────────────

    source: str = "ai"          # "ai" | "manual" | "default"
    generated_at: str = ""

    # ── Derived helpers ─────────────────────────────────────────────────────

    @property
    def intent_boost_map(self) -> dict[str, int]:
        """Generic source_score for keywords matched via config vs raw pillars."""
        return {"user_input": 10, "gsc": 5}

    @property
    def purchase_set(self) -> set[str]:
        return {w.lower().strip() for w in self.purchase_intent_keywords if w.strip()}

    @property
    def supporting_set(self) -> set[str]:
        return {w.lower().strip() for w in self.supporting_angles if w.strip()}

    def get_synonyms_for(self, pillar: str) -> list[str]:
        """Return synonym list for a pillar — case-insensitive lookup."""
        key = pillar.lower().strip()
        for k, v in self.synonyms.items():
            if k.lower().strip() == key:
                return [s.lower().strip() for s in v if s.strip()]
        return []

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "business_summary": self.business_summary,
            "target_audience": self.target_audience,
            "goal": self.goal,
            "pillars": self.pillars,
            "purchase_intent_keywords": self.purchase_intent_keywords,
            "supporting_angles": self.supporting_angles,
            "synonyms": self.synonyms,
            "customer_language_examples": self.customer_language_examples,
            "source": self.source,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectConfig":
        return cls(
            business_summary=d.get("business_summary", ""),
            target_audience=d.get("target_audience", ""),
            goal=d.get("goal", "sales"),
            pillars=d.get("pillars", []),
            purchase_intent_keywords=d.get("purchase_intent_keywords", []),
            supporting_angles=d.get("supporting_angles", []),
            synonyms=d.get("synonyms", {}),
            customer_language_examples=d.get("customer_language_examples", []),
            source=d.get("source", "ai"),
            generated_at=d.get("generated_at", ""),
        )

    @classmethod
    def from_pillars(cls, pillars: list[str]) -> "ProjectConfig":
        """Minimal config wrapping a bare pillar list (backward compat)."""
        return cls(
            pillars=pillars,
            purchase_intent_keywords=[
                "buy", "price", "order", "wholesale", "bulk", "supplier",
                "purchase", "shop", "cost", "rate",
            ],
            supporting_angles=[
                "benefits", "uses", "how", "guide", "recipe", "health",
            ],
            source="default",
        )


# ─── AI generation ───────────────────────────────────────────────────────────

def generate_project_config(
    business_description: str,
    goal: str = "sales",
    seed_keywords: Optional[list[str]] = None,
    target_audience: str = "",
) -> ProjectConfig:
    """
    Call the AI to generate a structured ProjectConfig from business input.
    Falls back to a minimal config on any AI failure.

    Args:
        business_description: Free-form business description from user.
        goal: "sales" | "leads" | "traffic"
        seed_keywords: Optional pillar seed list to guide AI output.
        target_audience: Who the customers are (optional).

    Returns:
        ProjectConfig with AI-generated intelligence.
    """
    from core.ai_config import AIRouter
    from datetime import datetime

    seeds_str = ", ".join(seed_keywords) if seed_keywords else "not provided"
    audience_str = target_audience if target_audience else "not specified"

    prompt = _PROMPT_TEMPLATE.format(
        description=business_description,
        audience=audience_str,
        goal=goal,
        seeds=seeds_str,
    )

    log.info("[GSC AI Config] Generating project config via AI…")
    raw = AIRouter.call(prompt, system=_SYSTEM, temperature=0.25)

    if not raw:
        log.warning("[GSC AI Config] AI returned empty — using minimal seed-based config")
        return ProjectConfig.from_pillars(seed_keywords or [])

    config_dict = _parse_ai_json(raw)
    if not config_dict:
        log.warning("[GSC AI Config] Failed to parse AI JSON — using minimal config")
        return ProjectConfig.from_pillars(seed_keywords or [])

    # Merge seed_keywords into pillars (user seed always wins)
    if seed_keywords:
        seed_lower = [s.lower().strip() for s in seed_keywords]
        existing_lower = [p.lower().strip() for p in config_dict.get("pillars", [])]
        for sk in reversed(seed_lower):
            if sk not in existing_lower:
                config_dict.setdefault("pillars", []).insert(0, sk)

    config_dict["source"] = "ai"
    config_dict["generated_at"] = datetime.utcnow().isoformat()

    cfg = ProjectConfig.from_dict(config_dict)
    log.info(
        f"[GSC AI Config] Config ready: {len(cfg.pillars)} pillars, "
        f"{len(cfg.purchase_intent_keywords)} intent signals, "
        f"{len(cfg.supporting_angles)} supporting angles"
    )
    return cfg


# ─── JSON parsing ─────────────────────────────────────────────────────────────

def _parse_ai_json(text: str) -> dict | None:
    """Extract JSON object from AI response, stripping markdown fences."""
    # Strip ```json ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = re.sub(r"```\s*$", "", text).strip()

    # Try full parse
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            return _sanitize(d)
    except json.JSONDecodeError:
        pass

    # Try extracting first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict):
                return _sanitize(d)
        except json.JSONDecodeError:
            pass

    return None


def _sanitize(d: dict) -> dict:
    """Ensure all expected keys exist and have correct types."""

    def _list_of_str(v) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if x]
        return []

    def _dict_of_lists(v) -> dict[str, list[str]]:
        if isinstance(v, dict):
            return {str(k): _list_of_str(vv) for k, vv in v.items()}
        return {}

    return {
        "business_summary":        str(d.get("business_summary", "")),
        "target_audience":         str(d.get("target_audience", "")),
        "goal":                    str(d.get("goal", "sales")),
        "pillars":                 _list_of_str(d.get("pillars")),
        "purchase_intent_keywords":_list_of_str(d.get("purchase_intent_keywords")),
        "supporting_angles":       _list_of_str(d.get("supporting_angles")),
        "synonyms":                _dict_of_lists(d.get("synonyms")),
        "customer_language_examples": _list_of_str(d.get("customer_language_examples")),
    }
