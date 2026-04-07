"""
kw2 Phase 4a — Keyword Scoring Engine.

Computes final_score for each validated keyword using:
  - ai_relevance (from Phase 3)
  - intent_weight (from INTENT_WEIGHTS)
  - volume_signal (source-based proxy)
  - commercial_score (token matching from COMMERCIAL_BOOSTS)
  - buyer_readiness (from Phase 3)
"""
import logging

from engines.kw2.constants import COMMERCIAL_BOOSTS, INTENT_WEIGHTS
from engines.kw2 import db

log = logging.getLogger("kw2.scorer")

# Source → volume signal proxy (higher = likely more search volume)
SOURCE_VOLUME = {
    "suggest": 0.70,
    "competitor": 0.60,
    "ai_expand": 0.50,
    "rules": 0.40,
    "seeds": 0.35,
}


class KeywordScorer:
    """Phase 4a: Score validated keywords with a composite formula."""

    def score_all(self, project_id: str, session_id: str) -> dict:
        """
        Compute final_score for all validated keywords in a session.

        Returns: {scored: int, score_range: {min, max, avg}}
        """
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT id, keyword, ai_relevance, intent, buyer_readiness, source "
                "FROM kw2_validated_keywords WHERE session_id=?",
                (session_id,),
            ).fetchall()

            if not rows:
                return {"scored": 0, "score_range": {"min": 0, "max": 0, "avg": 0}}

            scores = []
            updates = []
            for row in rows:
                kw = row["keyword"].lower()
                ai_rel = row["ai_relevance"] or 0.0
                intent = row["intent"] or "unknown"
                readiness = row["buyer_readiness"] or 0.0
                source = row["source"] or ""

                # Component scores
                intent_weight = INTENT_WEIGHTS.get(intent, 0.3)
                volume_signal = SOURCE_VOLUME.get(source, 0.35)
                commercial = self._commercial_score(kw)

                final = round(
                    (ai_rel * 0.30)
                    + (intent_weight * 0.25)
                    + (volume_signal * 0.20)
                    + (commercial * 0.15)
                    + (readiness * 0.10),
                    4,
                )

                scores.append(final)
                updates.append((final, commercial, row["id"]))

            conn.executemany(
                "UPDATE kw2_validated_keywords SET final_score=?, commercial_score=? WHERE id=?",
                updates,
            )
            conn.commit()

            db.update_session(session_id, phase4_done=1)

            return {
                "scored": len(scores),
                "score_range": {
                    "min": round(min(scores), 4),
                    "max": round(max(scores), 4),
                    "avg": round(sum(scores) / len(scores), 4),
                },
            }
        finally:
            conn.close()

    def _commercial_score(self, keyword: str) -> float:
        """Compute commercial score from token matching (0.0-1.0)."""
        total = 0.0
        for token, boost in COMMERCIAL_BOOSTS.items():
            if token in keyword:
                total += boost
        return min(total / 35.0, 1.0)
