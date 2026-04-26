"""
plot_engine.py — Thompson Sampling bandit for plot selection.

Given a keyword + project context, picks the best active plot using
Thompson Sampling on bs_bandit_state success/failure counts.
Also provides helpers to record usage and update bandit state.
"""
from __future__ import annotations
import json
import random
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


def _context_key(project_id: str, intent: str) -> str:
    """Build a context key for bandit state lookup."""
    return f"{project_id}:{intent}"


def pick_plot(
    db,
    project_id: str,
    keyword: str,
    intent: str = "informational",
    product_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Use Thompson Sampling to pick one active plot for this project+intent context.
    Returns the plot dict or None if no active plots exist.
    """
    ctx_key = _context_key(project_id, intent)

    if product_id:
        plots = db.execute(
            "SELECT * FROM bs_plots WHERE project_id=? AND product_id=? AND status='active' ORDER BY priority",
            (project_id, product_id),
        ).fetchall()
    else:
        plots = db.execute(
            "SELECT * FROM bs_plots WHERE project_id=? AND status='active' ORDER BY priority",
            (project_id,),
        ).fetchall()

    if not plots:
        return None

    best_plot = None
    best_sample = -1.0

    for plot in plots:
        plot_id = plot["id"]
        row = db.execute(
            "SELECT success_count, failure_count FROM bs_bandit_state WHERE context_key=? AND plot_id=?",
            (ctx_key, plot_id),
        ).fetchone()

        alpha = float(row["success_count"]) if row else 1.0
        beta = float(row["failure_count"]) if row else 1.0

        # Thompson sample: draw from Beta(alpha, beta)
        sample = random.betavariate(max(alpha, 0.1), max(beta, 0.1))
        if sample > best_sample:
            best_sample = sample
            best_plot = dict(plot)

    return best_plot


def record_plot_usage(db, plot_id: str, article_id: str, stage: str = "intro") -> None:
    """Insert a bs_plot_usage record and increment used_count on the plot."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.execute(
            "INSERT INTO bs_plot_usage(plot_id, article_id, stage, used_at) VALUES(?,?,?,?)",
            (plot_id, article_id, stage, now),
        )
        db.execute(
            "UPDATE bs_plots SET used_count = used_count + 1, updated_at=? WHERE id=?",
            (now, plot_id),
        )
        db.commit()
    except Exception:
        pass


def update_bandit(
    db,
    project_id: str,
    plot_id: str,
    intent: str,
    success: bool,
) -> None:
    """
    Update Thompson Sampling state for a plot after content performance is known.
    success=True → increment success_count; False → increment failure_count.
    """
    ctx_key = _context_key(project_id, intent)
    now = datetime.now(timezone.utc).isoformat()
    try:
        if success:
            db.execute(
                "INSERT INTO bs_bandit_state(context_key, plot_id, success_count, failure_count, updated_at) "
                "VALUES(?,?,2,1,?) ON CONFLICT(context_key, plot_id) "
                "DO UPDATE SET success_count=success_count+1, updated_at=excluded.updated_at",
                (ctx_key, plot_id, now),
            )
        else:
            db.execute(
                "INSERT INTO bs_bandit_state(context_key, plot_id, success_count, failure_count, updated_at) "
                "VALUES(?,?,1,2,?) ON CONFLICT(context_key, plot_id) "
                "DO UPDATE SET failure_count=failure_count+1, updated_at=excluded.updated_at",
                (ctx_key, plot_id, now),
            )
        db.commit()
    except Exception:
        pass
