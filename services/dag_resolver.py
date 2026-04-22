"""
DAG Resolver — topological sort with parallel-level detection.

Given a mode (brand/expand/review), filters the phase registry to only
the relevant phases, then produces an ordered list of *levels*.
Each level is a list of phase IDs that can execute concurrently.
"""
from __future__ import annotations

import logging
from collections import deque

from services.phase_registry import REGISTRY, DepMode, PhaseSpec

log = logging.getLogger("kw2.dag")


class CycleError(Exception):
    """Raised when a cycle is detected in the phase DAG."""


class MissingDependencyError(Exception):
    """Raised when a phase depends on a phase not present in the mode."""


def resolve(mode: str) -> list[list[str]]:
    """Resolve the execution order for *mode*.

    Returns a list of levels.  Each level is a list of phase IDs that can
    execute in parallel (no inter-level dependencies).

    Raises :class:`CycleError` if a cycle is detected.
    """
    phases: dict[str, PhaseSpec] = {
        pid: spec
        for pid, spec in REGISTRY.items()
        if mode in spec.modes
    }
    valid_ids = set(phases.keys())

    # Build adjacency + in-degree
    in_degree: dict[str, int] = {pid: 0 for pid in phases}
    children: dict[str, list[str]] = {pid: [] for pid in phases}

    for pid, spec in phases.items():
        deps = _effective_deps(spec, valid_ids)
        for d in deps:
            children[d].append(pid)
            in_degree[pid] += 1

    # Kahn's algorithm → levels
    levels: list[list[str]] = []
    queue = deque(pid for pid, deg in in_degree.items() if deg == 0)
    visited = 0

    while queue:
        level = list(queue)
        levels.append(level)
        visited += len(level)
        next_q: deque[str] = deque()

        for node in level:
            for child in children[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_q.append(child)

        queue = next_q

    if visited != len(phases):
        remaining = {pid for pid, d in in_degree.items() if d > 0}
        raise CycleError(f"Cycle detected in phase DAG (stuck: {remaining})")

    return levels


def get_phase_order(mode: str) -> list[str]:
    """Flat execution order (levels flattened)."""
    return [pid for level in resolve(mode) for pid in level]


def get_parallel_groups(mode: str) -> list[dict]:
    """Return levels annotated with parallelism info.

    Each entry: ``{"level": int, "phases": [str], "parallel": bool}``
    """
    levels = resolve(mode)
    out = []
    for i, level in enumerate(levels):
        # a level is parallel if every phase in it is marked parallel
        all_parallel = len(level) > 1 and all(
            REGISTRY[pid].parallel for pid in level if pid in REGISTRY
        )
        out.append({"level": i, "phases": level, "parallel": all_parallel})
    return out


def get_dag_state(mode: str) -> dict:
    """Full DAG description for frontend consumption.

    Returns::

        {
            "mode": str,
            "levels": [ {"level": int, "phases": [...], "parallel": bool} ],
            "phases": [
                {
                    "id": str, "label": str, "icon": str,
                    "description": str, "dependencies": [...],
                    "outputs": [...], "is_human_gate": bool,
                    "parallel": bool, "retryable": bool,
                    "feedback_to": [...], "feedback_from": [...],
                    "estimated_seconds": int,
                }
            ],
            "edges": [ {"from": str, "to": str} ],
        }
    """
    levels = get_parallel_groups(mode)
    phases_in_mode = {
        pid: spec
        for pid, spec in REGISTRY.items()
        if mode in spec.modes
    }
    valid_ids = set(phases_in_mode.keys())

    phase_list = []
    edges = []
    for pid, spec in phases_in_mode.items():
        phase_list.append({
            "id": spec.id,
            "label": spec.label,
            "icon": spec.icon,
            "description": spec.description,
            "dependencies": _effective_deps(spec, valid_ids),
            "outputs": spec.outputs,
            "is_human_gate": spec.is_human_gate,
            "parallel": spec.parallel,
            "retryable": spec.retryable,
            "feedback_to": spec.feedback_to,
            "feedback_from": spec.feedback_from,
            "estimated_seconds": spec.estimated_seconds,
        })
        for dep in _effective_deps(spec, valid_ids):
            edges.append({"from": dep, "to": pid})

    return {
        "mode": mode,
        "levels": levels,
        "phases": phase_list,
        "edges": edges,
    }


# ── helpers ──────────────────────────────────────────────────────────────────

def _effective_deps(spec: PhaseSpec, valid_ids: set[str]) -> list[str]:
    """Filter dependencies to only those present in the current mode."""
    return [d for d in spec.dependencies if d in valid_ids]
