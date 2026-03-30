import json
from datetime import datetime
from typing import Dict, List, Optional

from services.db_utils import row_to_dict


def create_experiment(db, name: str, variants: List[str], payload: Dict = None):
    payload_json = json.dumps(payload or {})
    created_at = datetime.utcnow().isoformat()
    cursor = db.execute(
        """
        INSERT INTO strategy_experiments
        (name, variants, payload_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, json.dumps(variants), payload_json, "running", created_at, created_at),
    )
    db.commit()
    experiment_id = cursor.lastrowid
    return get_experiment(db, experiment_id)


def get_experiment(db, experiment_id: int):
    row = db.execute("SELECT * FROM strategy_experiments WHERE id = ?", (experiment_id,)).fetchone()
    return dict(row) if row else None


def list_experiments(db):
    rows = db.execute("SELECT * FROM strategy_experiments ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def assign_variant(db, experiment_id: int) -> Optional[str]:
    experiment = get_experiment(db, experiment_id)
    if not experiment:
        return None

    variants = json.loads(experiment.get("variants", "[]") or "[]")
    if not variants:
        return None

    count = db.execute(
        "SELECT COUNT(1) FROM strategy_experiment_results WHERE experiment_id = ?", (experiment_id,)
    ).fetchone()[0]

    chosen = variants[count % len(variants)]

    db.execute(
        "INSERT INTO strategy_experiment_assignments (experiment_id, variant, assigned_at) VALUES (?, ?, ?)",
        (experiment_id, chosen, datetime.utcnow().isoformat()),
    )
    db.commit()

    return chosen


from core.memory_engine import update_memory, compute_weight
from core.global_memory_engine import update_global_memory
from core.context_extractor import extract_context
from core.meta_features import extract_meta_features
from core.meta_learning import update_meta_learning


def record_result(db, experiment_id: int, variant: str, job_id: str, roi: float, status: str = "completed", extra_context: dict = None, serp_data: dict = None):
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO strategy_experiment_results (experiment_id, variant, job_id, roi, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (experiment_id, variant, job_id, roi, status, now, now),
    )
    db.commit()

    # Update local pattern memory
    update_memory(db, "variant", variant, roi)

    # Update global pattern memory with context
    pattern = {"variant": variant}
    context = extract_context(pattern, extra_context or {})
    update_global_memory(db, pattern, roi, context)

    # Update meta-learning features
    meta_features = extract_meta_features(pattern, serp_data or {})
    update_meta_learning(db, meta_features, roi)

    return get_experiment(db, experiment_id)


def get_experiment_summary(db, experiment_id: int):
    rows = db.execute(
        "SELECT variant, roi FROM strategy_experiment_results WHERE experiment_id = ?",
        (experiment_id,),
    ).fetchall()

    data = {}
    for r in rows:
        variant = r["variant"]
        roi = r["roi"] or 0.0
        if variant not in data:
            data[variant] = {
                "variant": variant,
                "rois": [],
                "sample_size": 0,
                "mean_roi": 0.0,
                "variance": 0.0,
                "success_count": 0,
            }
        item = data[variant]
        item["rois"].append(roi)
        item["sample_size"] += 1
        if roi > 0:
            item["success_count"] += 1

    for item in data.values():
        n = item["sample_size"]
        if n > 0:
            item["mean_roi"] = sum(item["rois"]) / n
            if n > 1:
                m = item["mean_roi"]
                item["variance"] = sum((x - m) ** 2 for x in item["rois"]) / (n - 1)
            else:
                item["variance"] = 0.0
            item["success_rate"] = item["success_count"] / n
            item["weight"] = compute_weight(item["success_rate"], n)
        else:
            item["mean_roi"] = 0.0
            item["variance"] = 0.0
            item["success_rate"] = 0.0
            item["weight"] = 0.0

    return list(data.values())


def json_or_empty(value):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}
