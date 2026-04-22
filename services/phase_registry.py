"""
Phase Registry — every phase self-declares dependencies, outputs, and behavior.

The DAG engine uses this registry to resolve execution order, detect parallelism,
and enforce input/output contracts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger("kw2.dag")


class DepMode(Enum):
    ALL = "all"   # all deps must complete
    ANY = "any"   # at least one dep must complete


@dataclass
class PhaseSpec:
    id: str
    label: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    dep_mode: DepMode = DepMode.ALL
    outputs: list[str] = field(default_factory=list)
    runner: Optional[Callable] = None
    retryable: bool = True
    max_retries: int = 3
    is_human_gate: bool = False
    parallel: bool = False
    feedback_to: list[str] = field(default_factory=list)
    feedback_from: list[str] = field(default_factory=list)
    modes: list[str] = field(default_factory=list)
    estimated_seconds: int = 30
    icon: str = ""


# ── Global registry ──────────────────────────────────────────────────────────
REGISTRY: dict[str, PhaseSpec] = {}


def register_phase(spec: PhaseSpec) -> None:
    """Register a phase spec.  Duplicate IDs overwrite silently."""
    REGISTRY[spec.id] = spec


def get_phase(phase_id: str) -> PhaseSpec | None:
    return REGISTRY.get(phase_id)


def get_phases_for_mode(mode: str) -> list[PhaseSpec]:
    """Return all phases whose *modes* list includes *mode*."""
    return [s for s in REGISTRY.values() if mode in s.modes]


def list_phase_ids() -> list[str]:
    return list(REGISTRY.keys())


# ── Default KW2 phases ──────────────────────────────────────────────────────
# Each phase mirrors engines/kw2/* runner classes.
# Runner functions are late-bound (set to None here, wired via wire_runners).

_DEFAULT_PHASES: list[PhaseSpec] = [
    # ── Brand entry ──────────────────────────────────────────────────────
    PhaseSpec(
        id="analyze",
        label="Analyze",
        icon="🔬",
        description="Extract business profile from domain/URL",
        dependencies=[],
        outputs=["profile"],
        retryable=True,
        modes=["brand"],
        estimated_seconds=30,
    ),
    PhaseSpec(
        id="intel",
        label="Intel",
        icon="🕵️",
        description="Market research, competitor analysis, strategy synthesis",
        dependencies=["analyze"],
        outputs=["intel", "competitor_keywords"],
        retryable=True,
        modes=["brand"],
        estimated_seconds=45,
    ),
    PhaseSpec(
        id="business_context",
        label="Business Context",
        icon="📋",
        description="Structured business context object synthesized from profile + intel",
        dependencies=["analyze", "intel"],
        outputs=["business_context"],
        retryable=True,
        modes=["brand"],
        estimated_seconds=20,
    ),
    PhaseSpec(
        id="confirm_pillars",
        label="Confirm Pillars",
        icon="✅",
        description="Human gate — user reviews and confirms pillars before generation",
        dependencies=["business_context"],
        outputs=["confirmed_pillars"],
        is_human_gate=True,
        retryable=False,
        modes=["brand"],
        estimated_seconds=0,
    ),
    # ── Search (parallel-eligible) ───────────────────────────────────────
    PhaseSpec(
        id="search_gsc",
        label="Search (GSC)",
        icon="📡",
        description="Fetch existing Google Search Console keyword data",
        dependencies=[],
        outputs=["gsc_keywords"],
        retryable=True,
        parallel=True,
        modes=["brand", "review"],
        estimated_seconds=15,
    ),
    PhaseSpec(
        id="search_global",
        label="Search (Global)",
        icon="🌍",
        description="Global keyword discovery via suggest, SERP, AI",
        dependencies=[],
        dep_mode=DepMode.ANY,
        outputs=["global_keywords"],
        retryable=True,
        parallel=True,
        modes=["brand", "expand"],
        estimated_seconds=30,
    ),
    PhaseSpec(
        id="merge_keywords",
        label="Merge",
        icon="🔗",
        description="Deduplicate and merge all keyword sources",
        dependencies=["search_gsc", "search_global"],
        dep_mode=DepMode.ANY,
        outputs=["merged_keywords"],
        retryable=True,
        modes=["brand", "expand"],
        estimated_seconds=10,
    ),
    # ── Core pipeline ────────────────────────────────────────────────────
    PhaseSpec(
        id="generate",
        label="Generate",
        icon="⚙️",
        description="Build keyword universe with gap filling and pillar balancing",
        dependencies=["merge_keywords", "business_context"],
        dep_mode=DepMode.ALL,
        outputs=["keyword_universe"],
        retryable=True,
        modes=["brand", "expand"],
        feedback_from=["validate"],
        estimated_seconds=60,
    ),
    PhaseSpec(
        id="validate",
        label="Validate",
        icon="🛡️",
        description="AI + rule filtering, intent correction, pillar rebalancing",
        dependencies=["generate"],
        outputs=["validated_keywords", "rejection_report"],
        retryable=True,
        modes=["brand", "expand"],
        feedback_to=["generate"],
        estimated_seconds=40,
    ),
    PhaseSpec(
        id="review",
        label="Review",
        icon="👁️",
        description="Human review — approve, reject, edit keywords",
        dependencies=["validate"],
        outputs=["reviewed_keywords"],
        is_human_gate=True,
        retryable=False,
        modes=["brand", "expand"],
        estimated_seconds=0,
    ),
    PhaseSpec(
        id="score",
        label="Score",
        icon="📊",
        description="Multi-signal scoring (opportunity, business value, competition) + clustering",
        dependencies=["review"],
        outputs=["scored_keywords", "clusters"],
        retryable=True,
        modes=["brand", "expand"],
        estimated_seconds=30,
    ),
    PhaseSpec(
        id="strategy",
        label="Strategy",
        icon="🎯",
        description="Quick wins, content plan, revenue projection, competitor gaps",
        dependencies=["score", "intel"],
        dep_mode=DepMode.ALL,
        outputs=["strategy_output"],
        retryable=True,
        modes=["brand", "expand"],
        estimated_seconds=40,
    ),
    # ── Review-only mode ─────────────────────────────────────────────────
    PhaseSpec(
        id="insights",
        label="Insights",
        icon="💡",
        description="GSC data analysis — pillar authority, trends, quick wins",
        dependencies=["search_gsc"],
        outputs=["authority_report"],
        retryable=True,
        modes=["review"],
        estimated_seconds=20,
    ),
]


def _bootstrap_registry() -> None:
    """Load default phases into the global registry."""
    for spec in _DEFAULT_PHASES:
        register_phase(spec)


# Auto-bootstrap on import
_bootstrap_registry()


# ── Runner wiring (called at app startup) ────────────────────────────────────
def wire_runners(runner_map: dict[str, Callable]) -> None:
    """Attach runner callables from the engine layer.

    Example::

        wire_runners({
            "analyze": my_analyze_runner,
            "generate": my_generate_runner,
        })
    """
    for phase_id, fn in runner_map.items():
        spec = REGISTRY.get(phase_id)
        if spec:
            spec.runner = fn
        else:
            log.warning("wire_runners: unknown phase %s", phase_id)
