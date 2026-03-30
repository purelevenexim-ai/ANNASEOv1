def compute_win_probability(serp_summary, gaps, analyzer):
    difficulty = serp_summary.get("avg_kd", 0.5)
    gap_score = min(1.0, len(gaps)/5.0)

    if difficulty is None:
        difficulty = 0.5

    win = max(0.0, min(1.0, 0.3 + gap_score*0.45 + (1.0 - difficulty)*0.25))
    return {
        "difficulty": round(difficulty, 3),
        "gap_score": round(gap_score, 3),
        "win_probability": round(win, 3)
    }
