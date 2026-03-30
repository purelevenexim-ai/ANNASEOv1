from core.global_memory_engine import compute_context_score


def get_contextual_patterns(db, context: dict):
    if not context:
        return []
    return db.execute(
        "SELECT * FROM global_strategy_memory WHERE niche = ? OR country = ? OR intent = ? ORDER BY avg_roi DESC LIMIT 20",
        (context.get("niche", "global"), context.get("country", "global"), context.get("intent", "all")),
    ).fetchall()


def contextual_score(db, context: dict):
    return compute_context_score(db, context)
