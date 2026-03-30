import json
from services.db_utils import row_to_dict
from core.decay_engine import compute_decay_factor
from core.confidence_engine import compute_confidence


def pattern_to_key(pattern: dict) -> str:
    return json.dumps(pattern, sort_keys=True)


def update_global_memory(db, pattern: dict, roi: float, context: dict = None):
    context = context or {"niche": "global", "country": "global", "intent": "all"}
    key_base = pattern_to_key(pattern)
    key = f"{key_base}|{context.get('niche','global')}|{context.get('country','global')}|{context.get('intent','all')}"

    row = db.execute("SELECT * FROM global_strategy_memory WHERE pattern_hash = ?", (key,)).fetchone()
    success = 1 if roi > 0 else 0

    if row:
        current = row_to_dict(row)
        n = current.get("total_samples", 0) + 1
        old_avg = current.get("avg_roi", 0.0)
        alpha = 0.3
        new_avg = alpha * roi + (1 - alpha) * old_avg
        new_variance = current.get("variance", 0.0)
        if n > 1:
            new_variance = ((new_variance * (n - 1)) + (roi - new_avg) ** 2) / n

        db.execute(
            "UPDATE global_strategy_memory SET total_samples=?, successes=successes+?, failures=failures+?, avg_roi=?, variance=?, niche=?, country=?, intent=?, last_seen=CURRENT_TIMESTAMP WHERE pattern_hash=?",
            (n, success, 1 - success, new_avg, new_variance, context.get("niche"), context.get("country"), context.get("intent"), key),
        )
    else:
        db.execute(
            "INSERT INTO global_strategy_memory(pattern_hash, pattern_json, total_samples, successes, failures, avg_roi, variance, niche, country, intent, last_seen, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (key, json.dumps(pattern), success, 1 - success, roi, 0.0, context.get("niche"), context.get("country"), context.get("intent"),),
        )
    db.commit()


def get_global_stats(db, pattern: dict, context: dict = None):
    context = context or {}
    key_base = pattern_to_key(pattern)
    key = f"{key_base}|{context.get('niche','global')}|{context.get('country','global')}|{context.get('intent','all')}"
    row = db.execute("SELECT * FROM global_strategy_memory WHERE pattern_hash = ?", (key,)).fetchone()
    if not row:
        return None
    return row_to_dict(row)


def compute_freshness_boost(global_data: dict):
    if not global_data:
        return 1.0
    recent_samples = min(global_data.get("total_samples", 0), 10)
    return 1.0 + (recent_samples / 20.0)


def compute_global_score(db, variant: dict, context: dict = None):
    pattern = variant.get("pattern") or {"variant": variant.get("variant")}
    global_data = get_global_stats(db, pattern, context)
    if not global_data:
        return 0.5

    total = max(int(global_data.get("total_samples", 1)), 1)
    success_rate = float(global_data.get("successes", 0)) / total

    computed_confidence = compute_confidence(
        float(global_data.get("avg_roi", 0.0)),
        float(global_data.get("variance", 1.0)),
        total,
    )
    # For global memory we don't want to suppress meaningful early signals too harshly
    if total < 5:
        fallback_conf = 0.3 + 0.14 * total  # n=1=>0.44, n=4=>0.86
        confidence = max(computed_confidence, min(fallback_conf, 0.9))
    else:
        confidence = computed_confidence

    decay = compute_decay_factor(global_data.get("last_seen"))
    boost = compute_freshness_boost(global_data)

    return max(0.0, min(1.0, success_rate * confidence * decay * boost))


def compute_context_score(db, context: dict):
    if not context:
        return 0.5
    rows = db.execute(
        "SELECT * FROM global_strategy_memory WHERE niche = ? OR country = ? OR intent = ? ORDER BY avg_roi DESC LIMIT 20",
        (context.get("niche", "global"), context.get("country", "global"), context.get("intent", "all")),
    ).fetchall()
    if not rows:
        return 0.5
    avg = sum(float(r["avg_roi"] or 0.0) for r in rows) / len(rows)
    return max(0.0, min(1.0, avg))
