"""
audit/trace/tracer.py
=====================
Stage-level trace logging for the kw2 pipeline.

Attach a StageTracer to a pipeline run. After each stage, call
tracer.log(...) to record input/output sizes, timing, and errors.

The trace is then embedded in the pipeline result under result["_trace"],
which the audit runner uses for observability.

Usage:
    tracer = StageTracer(run_id="abc123")
    tracer.log("crawl", input_data=url, output_data=pages)
    tracer.log("entity_extraction", input_data=pages, output_data=entities)
    ...
    result["_trace"] = tracer.get_traces()
"""
from __future__ import annotations
import time
import traceback
from typing import Any


class StageTracer:
    """Lightweight per-stage trace recorder."""

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self._traces: list[dict[str, Any]] = []
        self._stage_start: dict[str, float] = {}

    def start(self, stage: str) -> None:
        """Mark stage start (optional — log() handles timing automatically)."""
        self._stage_start[stage] = time.time()

    def log(
        self,
        stage: str,
        input_data: Any = None,
        output_data: Any = None,
        error: Exception | None = None,
        token_usage: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a completed stage."""
        now = time.time()
        start = self._stage_start.pop(stage, now)
        elapsed = round(now - start, 3)

        entry: dict[str, Any] = {
            "stage": stage,
            "timestamp": now,
            "elapsed_s": elapsed,
            "input_size": _measure(input_data),
            "output_size": _measure(output_data),
            "ok": error is None,
        }

        if error is not None:
            entry["error"] = f"{type(error).__name__}: {error}"
            entry["traceback"] = traceback.format_exc()[-500:]

        if token_usage:
            entry["token_usage"] = token_usage

        if metadata:
            entry.update(metadata)

        self._traces.append(entry)

    def get_traces(self) -> list[dict[str, Any]]:
        return list(self._traces)

    def summary(self) -> dict[str, Any]:
        """High-level summary of the trace."""
        total_elapsed = sum(t.get("elapsed_s", 0) for t in self._traces)
        failed_stages = [t["stage"] for t in self._traces if not t.get("ok")]
        stage_timings = {t["stage"]: t.get("elapsed_s", 0) for t in self._traces}
        return {
            "run_id": self.run_id,
            "stages": len(self._traces),
            "total_elapsed_s": round(total_elapsed, 2),
            "failed_stages": failed_stages,
            "stage_timings": stage_timings,
            "slowest_stage": max(stage_timings, key=stage_timings.get) if stage_timings else None,
        }


def _measure(obj: Any) -> int:
    """Return a size proxy (bytes for strings, length for lists, else 0)."""
    if obj is None:
        return 0
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, (list, dict)):
        try:
            import json
            return len(json.dumps(obj, ensure_ascii=False))
        except Exception:
            return len(str(obj))
    return len(str(obj))
