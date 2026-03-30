import math


def compute_weight(success_rate: float, sample_size: int) -> float:
    # success_rate in [0,1], sample_size integer
    base = max(0.0, min(success_rate, 1.0))
    volume_boost = min(sample_size / 50.0, 1.0)
    return base * (0.5 + 0.5 * volume_boost)


def update_memory(db, pattern_type: str, pattern_value: str, roi: float):
    row = db.execute(
        "SELECT * FROM strategy_memory WHERE pattern_type=? AND pattern_value=?",
        (pattern_type, pattern_value),
    ).fetchone()

    if row:
        total_count = row["total_count"] + 1
        avg_roi = (row["avg_roi"] * row["total_count"] + roi) / total_count
        # incremental variance (online approx using Welford is more accurate, but this is fine for now)
        variance = row["variance"]
        # we can use exponential smoothing for variance with limited data
        variance = ((variance * (total_count - 1)) + (roi - avg_roi) ** 2) / total_count
        success_rate = (row["success_count"] + (1 if roi > 0 else 0)) / total_count
        weight = compute_weight(success_rate, total_count)

        db.execute(
            """
            UPDATE strategy_memory
            SET avg_roi=?, variance=?, success_count=?, total_count=?, weight=?, last_updated=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (avg_roi, variance, row["success_count"] + (1 if roi > 0 else 0), total_count, weight, row["id"]),
        )
    else:
        success = 1 if roi > 0 else 0
        success_rate = success
        weight = compute_weight(success_rate, 1)
        db.execute(
            """
            INSERT INTO strategy_memory
            (pattern_type, pattern_value, avg_roi, variance, success_count, total_count, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pattern_type, pattern_value, roi, 0.0, success, 1, weight),
        )

    db.commit()


def get_top_patterns(db, limit: int = 10):
    rows = db.execute(
        """
        SELECT pattern_type, pattern_value, avg_roi, variance, success_count, total_count, weight
        FROM strategy_memory
        WHERE total_count >= 3
        ORDER BY weight DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
