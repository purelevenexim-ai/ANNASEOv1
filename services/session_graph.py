"""
Session Graph — single source of truth for a KW2 session.

Stores phase outputs immutably (with version history), tracks statuses,
manages feedback signals between phases, and supports rollback.

Serialise with ``to_dict()`` / ``from_dict()`` for DB persistence.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone

log = logging.getLogger("kw2.dag")


class SessionGraph:
    """In-memory state container for a single KW2 session."""

    def __init__(self, session_id: str, mode: str):
        self.session_id = session_id
        self.mode = mode
        self.graph: dict[str, dict] = {}          # phase_id → output dict
        self.statuses: dict[str, str] = {}         # phase_id → status str
        self.history: list[dict] = []              # version log entries
        self.feedback: dict[str, list[dict]] = {}  # phase_id → [feedback signals]
        self.version: int = 0
        self.cost_tokens: dict[str, int] = {}      # phase_id → total tokens used

    # ── Output management ────────────────────────────────────────────────

    def store_output(self, phase_id: str, output: dict) -> None:
        """Immutable write — the previous value is preserved in history."""
        self.version += 1
        self.history.append({
            "version": self.version,
            "phase": phase_id,
            "timestamp": _now(),
            "prev_snapshot": deepcopy(self.graph.get(phase_id)),
        })
        self.graph[phase_id] = output

    def get_output(self, phase_id: str) -> dict | None:
        return self.graph.get(phase_id)

    def resolve_inputs(self, dep_ids: list[str]) -> dict[str, dict]:
        """Pull outputs from completed dependency phases."""
        inputs: dict[str, dict] = {}
        for dep in dep_ids:
            if dep in self.graph:
                inputs[dep] = self.graph[dep]
        return inputs

    # ── Status management ────────────────────────────────────────────────

    VALID_STATUSES = {"idle", "ready", "running", "done", "failed", "waiting", "feedback"}

    def set_status(self, phase_id: str, status: str) -> None:
        if status not in self.VALID_STATUSES:
            log.warning("Invalid status %s for phase %s", status, phase_id)
        self.statuses[phase_id] = status

    def get_status(self, phase_id: str) -> str:
        return self.statuses.get(phase_id, "idle")

    def is_done(self, phase_id: str) -> bool:
        return self.statuses.get(phase_id) == "done"

    # ── Feedback management ──────────────────────────────────────────────

    def send_feedback(self, target_phase: str, source_phase: str, data: dict) -> None:
        """Backward signal from *source* to *target*."""
        if target_phase not in self.feedback:
            self.feedback[target_phase] = []
        self.feedback[target_phase].append({
            "from": source_phase,
            "data": data,
            "timestamp": _now(),
        })

    def get_feedback(self, phase_id: str) -> list[dict]:
        return self.feedback.get(phase_id, [])

    def clear_feedback(self, phase_id: str) -> None:
        self.feedback.pop(phase_id, None)

    # ── Cost tracking ────────────────────────────────────────────────────

    def add_tokens(self, phase_id: str, tokens: int) -> None:
        self.cost_tokens[phase_id] = self.cost_tokens.get(phase_id, 0) + tokens

    def total_tokens(self) -> int:
        return sum(self.cost_tokens.values())

    # ── Rollback ─────────────────────────────────────────────────────────

    def rollback(self, phase_id: str, to_version: int | None = None) -> bool:
        """Restore a phase to a previous version (default: most recent prior)."""
        for entry in reversed(self.history):
            if entry["phase"] == phase_id:
                if to_version is not None and entry["version"] > to_version:
                    continue
                self.graph[phase_id] = entry["prev_snapshot"]
                self.statuses[phase_id] = "idle"
                return True
        return False

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "graph": self.graph,
            "statuses": self.statuses,
            "history": self.history,
            "feedback": self.feedback,
            "version": self.version,
            "cost_tokens": self.cost_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionGraph:
        sg = cls(
            session_id=data.get("session_id", ""),
            mode=data.get("mode", "brand"),
        )
        sg.graph = data.get("graph", {})
        sg.statuses = data.get("statuses", {})
        sg.history = data.get("history", [])
        sg.feedback = data.get("feedback", {})
        sg.version = data.get("version", 0)
        sg.cost_tokens = data.get("cost_tokens", {})
        return sg

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, raw: str) -> SessionGraph:
        return cls.from_dict(json.loads(raw))


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
