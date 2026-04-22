"""
Execution Engine — runs the DAG level-by-level.

Resolves dependencies → checks gates → executes runners → stores outputs.
Supports parallel execution within a level, retry on failure, and feedback loops.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Callable

from services.phase_registry import REGISTRY, DepMode, PhaseSpec, get_phase
from services.dag_resolver import resolve, get_phase_order
from services.session_graph import SessionGraph

log = logging.getLogger("kw2.dag")

MAX_FEEDBACK_ITERATIONS = 2


class PhaseError(Exception):
    """Raised when a phase fails after exhausting retries."""
    def __init__(self, phase_id: str, message: str):
        self.phase_id = phase_id
        super().__init__(f"Phase {phase_id}: {message}")


class HumanGateWaiting(Exception):
    """Raised when execution pauses at a human gate."""
    def __init__(self, phase_id: str):
        self.phase_id = phase_id
        super().__init__(f"Waiting for human approval: {phase_id}")


# ── Single phase execution ──────────────────────────────────────────────────

async def run_phase(
    sg: SessionGraph,
    phase_id: str,
    *,
    context: dict | None = None,
) -> dict:
    """Execute a single phase.

    1. Check dependency completion
    2. Resolve inputs from completed deps
    3. Merge any feedback signals
    4. Call the runner
    5. Store output + mark done
    6. Trigger feedback evaluation if applicable

    Returns the phase output dict.
    """
    spec = get_phase(phase_id)
    if spec is None:
        raise PhaseError(phase_id, "not found in registry")

    if spec.is_human_gate:
        sg.set_status(phase_id, "waiting")
        raise HumanGateWaiting(phase_id)

    # Check deps
    phases_for_mode = {
        pid for pid, s in REGISTRY.items() if sg.mode in s.modes
    }
    deps = [d for d in spec.dependencies if d in phases_for_mode]
    if spec.dep_mode == DepMode.ALL:
        for d in deps:
            if not sg.is_done(d):
                raise PhaseError(phase_id, f"dependency {d} not completed")
    elif spec.dep_mode == DepMode.ANY:
        if deps and not any(sg.is_done(d) for d in deps):
            raise PhaseError(phase_id, "no dependencies completed (ANY mode)")

    # Resolve inputs
    inputs = sg.resolve_inputs(deps)

    # Merge feedback signals
    fb_signals = sg.get_feedback(phase_id)
    if fb_signals:
        inputs["_feedback"] = fb_signals

    # Merge extra context
    if context:
        inputs["_context"] = context

    sg.set_status(phase_id, "running")

    # Execute with retry
    runner = spec.runner
    if runner is None:
        raise PhaseError(phase_id, "no runner wired")

    last_error = None
    attempts = spec.max_retries if spec.retryable else 1
    for attempt in range(1, attempts + 1):
        try:
            if asyncio.iscoroutinefunction(runner):
                output = await runner(sg.session_id, inputs)
            else:
                output = runner(sg.session_id, inputs)
            break
        except Exception as exc:
            last_error = exc
            log.warning(
                "Phase %s attempt %d/%d failed: %s",
                phase_id, attempt, attempts, exc,
            )
            if attempt == attempts:
                sg.set_status(phase_id, "failed")
                raise PhaseError(
                    phase_id,
                    f"failed after {attempts} attempts: {last_error}",
                ) from exc

    if not isinstance(output, dict):
        output = {"result": output}

    sg.store_output(phase_id, output)
    sg.set_status(phase_id, "done")
    sg.clear_feedback(phase_id)

    return output


# ── Feedback evaluation ─────────────────────────────────────────────────────

def evaluate_feedback(
    sg: SessionGraph,
    source_phase: str,
    target_phase: str,
    rejection_threshold: float = 0.60,
) -> bool:
    """Check if a feedback loop should fire.

    Returns True if the target phase should re-run.
    Called after the source phase completes (e.g. validate → generate).
    """
    output = sg.get_output(source_phase)
    if not output:
        return False

    # Look for rejection_report or rejection_rate
    report = output.get("rejection_report", {})
    rate = report.get("rejection_rate", 0)

    # Also check raw count
    if not rate:
        total = report.get("total", 0)
        rejected = report.get("rejected", 0)
        rate = (rejected / total) if total > 0 else 0

    # Check iteration count
    fb_history = sg.get_feedback(target_phase)
    iteration = len(fb_history) + 1

    if rate >= rejection_threshold and iteration <= MAX_FEEDBACK_ITERATIONS:
        sg.send_feedback(
            target_phase=target_phase,
            source_phase=source_phase,
            data={
                "reason": "high_rejection_rate",
                "rejection_rate": rate,
                "iteration": iteration,
                "constraints": report.get("top_rejection_reasons", []),
            },
        )
        sg.set_status(target_phase, "feedback")
        log.info(
            "Feedback loop %s→%s triggered (rejection %.0f%%, iteration %d)",
            source_phase, target_phase, rate * 100, iteration,
        )
        return True

    return False


# ── Full pipeline execution ─────────────────────────────────────────────────

async def execute_pipeline(
    sg: SessionGraph,
    mode: str,
    *,
    on_phase_start: Callable | None = None,
    on_phase_done: Callable | None = None,
    context: dict | None = None,
) -> SessionGraph:
    """Execute the full DAG pipeline level-by-level.

    - Parallel-eligible phases within a level are run concurrently.
    - Human gates pause execution and return the graph.
    - Feedback loops re-run the target phase up to MAX_FEEDBACK_ITERATIONS.

    Callbacks *on_phase_start(phase_id)* and *on_phase_done(phase_id, output)*
    can be used for SSE streaming or progress tracking.
    """
    levels = resolve(mode)

    for level in levels:
        # Skip already-done phases (resume support)
        remaining = [pid for pid in level if not sg.is_done(pid)]
        if not remaining:
            continue

        # Check if all phases in this level are parallel-eligible
        all_parallel = len(remaining) > 1 and all(
            REGISTRY.get(pid, PhaseSpec(id="")).parallel for pid in remaining
        )

        if all_parallel:
            await _run_parallel(sg, remaining, on_phase_start, on_phase_done, context)
        else:
            for pid in remaining:
                await _run_single(sg, pid, on_phase_start, on_phase_done, context)

        # After each level, evaluate feedback loops
        for pid in level:
            spec = get_phase(pid)
            if spec and spec.feedback_to:
                for target in spec.feedback_to:
                    should_rerun = evaluate_feedback(sg, pid, target)
                    if should_rerun:
                        await _run_single(sg, target, on_phase_start, on_phase_done, context)
                        # Re-run the source phase too (e.g. validate after generate re-run)
                        sg.set_status(pid, "idle")
                        await _run_single(sg, pid, on_phase_start, on_phase_done, context)

    return sg


async def _run_single(
    sg: SessionGraph,
    phase_id: str,
    on_start: Callable | None,
    on_done: Callable | None,
    context: dict | None,
) -> None:
    """Run a single phase with callbacks."""
    try:
        if on_start:
            on_start(phase_id)
        output = await run_phase(sg, phase_id, context=context)
        if on_done:
            on_done(phase_id, output)
    except HumanGateWaiting:
        if on_done:
            on_done(phase_id, {"status": "waiting"})
        raise
    except PhaseError:
        raise


async def _run_parallel(
    sg: SessionGraph,
    phase_ids: list[str],
    on_start: Callable | None,
    on_done: Callable | None,
    context: dict | None,
) -> None:
    """Run multiple phases concurrently."""
    async def _task(pid: str):
        await _run_single(sg, pid, on_start, on_done, context)

    results = await asyncio.gather(
        *[_task(pid) for pid in phase_ids],
        return_exceptions=True,
    )

    # Check for gate pauses
    for r in results:
        if isinstance(r, HumanGateWaiting):
            raise r
        if isinstance(r, Exception):
            raise r
