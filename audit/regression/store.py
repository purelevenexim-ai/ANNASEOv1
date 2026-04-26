"""
audit/regression/store.py
==========================
Golden-output baseline storage for regression testing.

Baselines are stored as JSON files under audit/regression/baselines/.
Each case_id maps to one saved output snapshot.

Usage:
    from audit.regression.store import save_baseline, load_baseline
    save_baseline("spice_co_full_run", result)
    baseline = load_baseline("spice_co_full_run")
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any

_BASELINE_DIR = Path(__file__).parent / "baselines"


def _path(case_id: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in case_id)
    return _BASELINE_DIR / f"{safe_id}.json"


def save_baseline(case_id: str, data: dict[str, Any], overwrite: bool = False) -> Path:
    """
    Persist a golden output. Raises FileExistsError if baseline already exists
    and overwrite=False (prevents accidental overwrite of trusted baselines).
    """
    _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(case_id)
    if p.exists() and not overwrite:
        raise FileExistsError(
            f"Baseline '{case_id}' already exists at {p}. "
            "Pass overwrite=True to replace it."
        )
    payload = {
        "_meta": {
            "case_id": case_id,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "keyword_count": len(data.get("keywords") or []),
            "cluster_count": len(data.get("clusters") or []),
            "has_strategy": bool(data.get("strategy")),
        },
        **data,
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return p


def load_baseline(case_id: str) -> dict[str, Any]:
    """Load a saved baseline. Returns {} if not found (first-run safe)."""
    p = _path(case_id)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def list_baselines() -> list[str]:
    """Return all saved baseline case IDs."""
    _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    return [f.stem for f in sorted(_BASELINE_DIR.glob("*.json"))]


def delete_baseline(case_id: str) -> bool:
    """Remove a baseline. Returns True if deleted, False if not found."""
    p = _path(case_id)
    if p.exists():
        p.unlink()
        return True
    return False
