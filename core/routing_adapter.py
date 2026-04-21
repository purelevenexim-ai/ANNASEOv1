"""Adapter layer between canonical v2 routing schema and legacy backend.

Two functions:
  normalize_template()  — ANY incoming dict (legacy or v2) → canonical RoutingTemplate
  adapt_template_to_legacy() — canonical RoutingTemplate → legacy 13-field dict for _build_routing()

Key mappings:
  - All 10 canonical steps pass through directly (research, structure, verify, links,
    references, draft, recovery, humanize, quality_loop, redevelop)
  - Legacy-only fields (review, issues, score) → None in output
    so _build_routing() falls back to its defaults
"""

from typing import Dict, Any
from core.routing_schema import RoutingTemplate, StepConfig, CANONICAL_STEPS


# Legacy key → canonical key mapping (for normalization)
_LEGACY_TO_CANONICAL = {
    "research":     "research",
    "structure":    "structure",
    "verify":       "verify",
    "links":        "links",
    "references":   "references",
    "draft":        "draft",
    "recovery":     "recovery",
    "humanize":     "humanize",
    "quality_loop": "quality_loop",
    "redevelop":    "redevelop",
}

# Legacy-only fields that should NOT appear in v2 templates
_LEGACY_ONLY_FIELDS = {"review", "issues", "score"}


def normalize_template(data: Dict[str, Any]) -> RoutingTemplate:
    """Convert any routing dict (legacy 12-field, v2, or partial) into canonical RoutingTemplate.

    Handles:
      - Already v2: pass through
      - Legacy dict with quality_loop/review/issues etc: maps to v2
      - Nested under 'routing' key (custom template format): unwraps
      - Empty/None: returns empty template
      - Version > 2: raises ValueError (future schema)
    """
    if not data:
        return RoutingTemplate(name="empty", steps={})

    # Check version for future-proofing
    version = data.get("version")
    if version is not None and version > 2:
        raise ValueError(f"Unsupported routing template version: {version}. Max supported: 2")

    # Already canonical v2 with steps dict
    if version == 2 and "steps" in data:
        return RoutingTemplate(**{
            k: v for k, v in data.items()
            if k in {"version", "name", "steps", "description", "system"}
        })

    # Legacy format: routing may be top-level keys or nested under "routing"
    routing = data.get("routing", data)

    steps: Dict[str, StepConfig] = {}

    for legacy_key, canonical_key in _LEGACY_TO_CANONICAL.items():
        cfg = routing.get(legacy_key)
        if not cfg or not isinstance(cfg, dict):
            continue

        # Skip if we already have this canonical key (recovery takes priority over quality_loop)
        if canonical_key in steps:
            continue

        first  = cfg.get("first", "skip")
        second = cfg.get("second", "skip")
        third  = cfg.get("third", "skip")

        # Only include if at least one slot is usable
        if first == "skip" and second == "skip" and third == "skip":
            continue

        steps[canonical_key] = StepConfig(first=first, second=second, third=third)

    return RoutingTemplate(
        version=2,
        name=data.get("name", "migrated_template"),
        description=data.get("description", ""),
        system=data.get("system", False),
        steps=steps,
    )


def adapt_template_to_legacy(template: RoutingTemplate) -> Dict[str, Any]:
    """Convert canonical v2 RoutingTemplate → legacy routing dict for _build_routing().

    Output shape matches what _build_routing() expects:
      { "research": {"first": ..., "second": ..., "third": ...}, ... }

    Rules:
      - recovery → BOTH 'recovery' AND 'quality_loop' (both consumed by backend)
      - Missing steps → None (NOT {} — backend checks truthiness; empty dict breaks)
      - Legacy-only fields → None (so _build_routing() uses its defaults)
    """
    legacy: Dict[str, Any] = {}

    def _to_dict(sc: StepConfig) -> Dict[str, str]:
        return {"first": sc.first, "second": sc.second, "third": sc.third}

    # Direct pass-through for all 10 canonical steps
    for step_key in ("research", "structure", "verify", "links", "references", "draft",
                     "recovery", "humanize", "quality_loop", "redevelop"):
        if step_key in template.steps:
            legacy[step_key] = _to_dict(template.steps[step_key])
        else:
            legacy[step_key] = None

    # Legacy-only fields: always None — _build_routing() falls back to its defaults
    for key in ("review", "issues", "score"):
        legacy[key] = None

    return legacy
