"""
kw2 Feedback & Learning Engine — Phase 11.

Tracks content performance and uses it to adjust scoring weights
via a simple Bayesian update rule.

Performance data sources: manual input | GSC (future) | Analytics (future)
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from engines.kw2 import db
from engines.kw2.scoring_engine import ScoringEngine, DEFAULT_WEIGHTS

log = logging.getLogger("kw2.feedback_engine")

LEARNING_CONFIG = {
    "observation_window_days": 60,
    "min_data_points": 5,
    "learning_rate": 0.1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


class FeedbackEngine:
    """Phase 11: Record performance and adjust scoring weights."""

    def record_performance(
        self,
        session_id: str,
        content_title_id: str,
        tracked_date: str,
        google_position: float = 0.0,
        organic_clicks: int = 0,
        impressions: int = 0,
        ctr: float = 0.0,
        conversions: int = 0,
        article_id: str = "",
        data_source: str = "manual",
    ) -> str:
        """Record performance metrics for a content title."""
        pid = _uid("cp_")
        conn = db.get_conn()
        try:
            conn.execute(
                """INSERT INTO kw2_content_performance
                   (id, session_id, content_title_id, article_id, tracked_date,
                    google_position, organic_clicks, impressions, ctr,
                    conversions, data_source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, session_id, content_title_id, article_id, tracked_date,
                 google_position, organic_clicks, impressions, ctr,
                 conversions, data_source, _now()),
            )
            conn.commit()
        finally:
            conn.close()
        return pid

    def get_summary(self, session_id: str) -> dict:
        """Aggregate performance stats for a session."""
        conn = db.get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM kw2_content_performance WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            if not total:
                return {"data_points": 0, "summary": None}
            agg = conn.execute(
                """SELECT
                     AVG(google_position) as avg_position,
                     SUM(organic_clicks) as total_clicks,
                     SUM(impressions) as total_impressions,
                     AVG(ctr) as avg_ctr,
                     SUM(conversions) as total_conversions,
                     COUNT(DISTINCT content_title_id) as tracked_titles
                   FROM kw2_content_performance WHERE session_id=?""",
                (session_id,),
            ).fetchone()
            return {
                "data_points": total,
                "summary": dict(agg) if agg else None,
            }
        finally:
            conn.close()

    def apply_learnings(self, session_id: str) -> dict:
        """
        Analyse performance data and adjust scoring weights via Bayesian update.
        Requires at least min_data_points records.

        Returns new weights after adjustment.
        """
        summary = self.get_summary(session_id)
        n = summary.get("data_points", 0)
        min_n = LEARNING_CONFIG["min_data_points"]
        if n < min_n:
            return {
                "ok": False,
                "reason": f"Need at least {min_n} data points, have {n}",
                "weights": None,
            }

        # Load current weights
        scorer = ScoringEngine()
        current_weights = scorer._load_weights(session_id)

        # Simple heuristic: look at which intent types perform best
        conn = db.get_conn()
        try:
            perf_rows = conn.execute(
                """SELECT cp.ctr, cp.organic_clicks, ct.intent, ct.funnel_stage
                   FROM kw2_content_performance cp
                   JOIN kw2_content_titles ct ON cp.content_title_id = ct.id
                   WHERE cp.session_id=? AND ct.intent != ''""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        if not perf_rows:
            return {"ok": False, "reason": "No performance data linked to content titles", "weights": None}

        # Calculate avg CTR by intent
        intent_ctr: dict[str, list[float]] = {}
        for row in perf_rows:
            intent = row["intent"] or "unknown"
            ctr = float(row["ctr"] or 0.0)
            intent_ctr.setdefault(intent, []).append(ctr)

        avg_ctr_by_intent = {
            intent: sum(vals) / len(vals)
            for intent, vals in intent_ctr.items()
        }

        # If transactional has high CTR, boost intent_value weight
        lr = LEARNING_CONFIG["learning_rate"]
        new_weights = dict(current_weights)
        transactional_ctr = avg_ctr_by_intent.get("transactional", 0)
        informational_ctr = avg_ctr_by_intent.get("informational", 0)

        if transactional_ctr > informational_ctr * 1.5:
            # Transactional is significantly outperforming — boost intent_value weight
            new_weights["intent_value"] = min(0.40, new_weights["intent_value"] + lr)
            new_weights["business_fit"] = max(0.10, new_weights["business_fit"] - lr / 2)
            new_weights["uniqueness"] = max(0.05, new_weights["uniqueness"] - lr / 2)
        elif informational_ctr > transactional_ctr * 1.5:
            # Informational is outperforming — boost demand_potential
            new_weights["demand_potential"] = min(0.35, new_weights["demand_potential"] + lr)
            new_weights["intent_value"] = max(0.10, new_weights["intent_value"] - lr)

        # Normalize to sum to 1
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

        # Save updated weights
        scorer.update_config(session_id, new_weights)

        log.info(
            "[FeedbackEngine] Updated weights for session %s from %d data points",
            session_id, n,
        )
        return {
            "ok": True,
            "data_points_used": n,
            "old_weights": current_weights,
            "new_weights": new_weights,
            "intent_ctr": avg_ctr_by_intent,
        }

    def list_performance(self, session_id: str, limit: int = 100) -> list[dict]:
        """List all performance records for a session."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT cp.*, ct.title, ct.primary_keyword, ct.intent
                   FROM kw2_content_performance cp
                   LEFT JOIN kw2_content_titles ct ON cp.content_title_id = ct.id
                   WHERE cp.session_id=?
                   ORDER BY cp.tracked_date DESC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
