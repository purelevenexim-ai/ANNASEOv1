import json

from services.db_utils import row_to_dict


def update_meta_learning(db, features: dict, roi: float):
    if not features:
        return

    key = json.dumps(features, sort_keys=True)
    row = db.execute("SELECT * FROM meta_learning WHERE feature_json = ?", (key,)).fetchone()
    success = 1 if roi > 0 else 0

    if row:
        current = row_to_dict(row)
        samples = current.get("samples", 0) + 1
        avg_roi = current.get("avg_roi", 0.0)
        new_avg = (avg_roi * (samples - 1) + roi) / samples
        db.execute(
            "UPDATE meta_learning SET avg_roi=?, samples=?, updated_at=CURRENT_TIMESTAMP WHERE feature_json=?",
            (new_avg, samples, key),
        )
    else:
        db.execute(
            "INSERT INTO meta_learning(feature_json, avg_roi, samples, updated_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)",
            (key, roi),
        )
    db.commit()


def compute_meta_score(db, features: dict):
    if not features:
        return 0.5

    key = json.dumps(features, sort_keys=True)
    row = db.execute("SELECT * FROM meta_learning WHERE feature_json = ?", (key,)).fetchone()
    if not row:
        return 0.5

    row = row_to_dict(row)
    if row.get("samples", 0) < 3:
        return 0.5

    return float(row.get("avg_roi", 0.5))
