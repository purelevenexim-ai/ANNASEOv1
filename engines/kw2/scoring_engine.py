"""
kw2 Scoring Engine — Phase 7.

Scores every non-duplicate question using a 5-weight formula.
Weights are stored per session in kw2_scoring_config and are user-configurable.

Formula:
  FINAL_SCORE = (
    business_fit    × w1  +
    intent_value    × w2  +
    demand_potential × w3 +
    competition_ease × w4 +
    uniqueness       × w5
  )
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from engines.kw2 import db

log = logging.getLogger("kw2.scoring_engine")

DEFAULT_WEIGHTS = {
    "business_fit":     0.30,
    "intent_value":     0.20,
    "demand_potential": 0.20,
    "competition_ease": 0.15,
    "uniqueness":       0.15,
}

# Intent value mapping
INTENT_VALUES = {
    "transactional": 1.0,
    "commercial":    0.8,
    "informational": 0.6,
    "navigational":  0.4,
}

# Funnel stage bonus
FUNNEL_BONUS = {
    "BOFU": 0.15,
    "MOFU": 0.05,
    "TOFU": 0.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class ScoringEngine:
    """Phase 7: Score questions using weighted formula."""

    def run(
        self,
        session_id: str,
        project_id: str,
        custom_weights: dict | None = None,
    ) -> dict:
        """
        Score all non-duplicate questions for a session.
        Uses weights from kw2_scoring_config (or defaults if not set).
        Profile-aware: boosts questions that match target locations,
        product catalog items, audience terms, or cultural context.
        """
        weights = self._load_weights(session_id)
        if custom_weights:
            weights.update(custom_weights)

        # Validate weights sum ≈ 1.0 (normalize if not)
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        # Load profile for context-aware scoring
        profile = db.load_business_profile(project_id) or {}
        mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
        profile_ctx = self._build_profile_match_ctx(profile, mi)

        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, business_relevance, intent, funnel_stage,
                          expansion_depth, content_cluster_id
                   FROM kw2_intelligence_questions
                   WHERE session_id=? AND is_duplicate=0""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        questions = [dict(r) for r in rows]
        if not questions:
            return {"scored": 0}

        updates = []
        for q in questions:
            score, breakdown = self._score_question(q, weights, profile_ctx)
            updates.append((score, json.dumps(breakdown), q["id"], session_id))

        conn = db.get_conn()
        try:
            conn.executemany(
                "UPDATE kw2_intelligence_questions SET final_score=?, score_breakdown=? WHERE id=? AND session_id=?",
                updates,
            )
            conn.commit()
        finally:
            conn.close()

        # Also update cluster avg_score
        self._update_cluster_scores(session_id)

        log.info("[ScoringEngine] Scored %d questions", len(updates))
        return {"scored": len(updates), "weights_used": weights}

    def get_config(self, session_id: str) -> dict:
        """Get scoring weights for a session."""
        weights = self._load_weights(session_id)
        return {"weights": weights, "defaults": DEFAULT_WEIGHTS}

    def update_config(self, session_id: str, weights: dict) -> bool:
        """Save user-configured weights for a session."""
        # Validate: all 5 weight keys must be present
        required = set(DEFAULT_WEIGHTS.keys())
        provided = set(weights.keys())
        if not required.issubset(provided):
            missing = required - provided
            raise ValueError(f"Missing weight keys: {missing}")

        conn = db.get_conn()
        try:
            existing = conn.execute(
                "SELECT id, version FROM kw2_scoring_config WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if existing:
                new_version = (existing["version"] or 1) + 1
                conn.execute(
                    "UPDATE kw2_scoring_config SET weights=?, version=? WHERE session_id=?",
                    (json.dumps(weights), new_version, session_id),
                )
            else:
                conn.execute(
                    """INSERT INTO kw2_scoring_config (id, session_id, weights, version, created_at)
                       VALUES (?,?,?,1,?)""",
                    (_uid("sc_"), session_id, json.dumps(weights), _now()),
                )
            conn.commit()
        finally:
            conn.close()
        return True

    def get_ranked(
        self, session_id: str, limit: int = 200,
        intent_filter: str | None = None,
        funnel_filter: str | None = None,
    ) -> list[dict]:
        """Return questions ranked by final_score."""
        conn = db.get_conn()
        try:
            conds = ["session_id=?", "is_duplicate=0"]
            params: list = [session_id]
            if intent_filter:
                conds.append("intent=?")
                params.append(intent_filter)
            if funnel_filter:
                conds.append("funnel_stage=?")
                params.append(funnel_filter)
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM kw2_intelligence_questions WHERE {' AND '.join(conds)} "
                f"ORDER BY final_score DESC LIMIT ?",
                params,
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["question_text"] = d.get("question", "")
                d["cluster_id"] = d.get("content_cluster_id", "")
                d["module_id"] = d.get("module_code", "")
                d["audience"] = d.get("audience_segment", "")
                result.append(d)
            return result
        finally:
            conn.close()

    # ── Internal scoring ──────────────────────────────────────────────────────

    def _score_question(self, q: dict, weights: dict, profile_ctx: dict | None = None) -> tuple[float, dict]:
        # 1. Business fit (0–1) from enrichment
        #    If not yet enriched (NULL / 0), use 0.40 as neutral baseline
        #    so unenriched questions aren't zeroed out before their first enrich pass.
        raw_biz = q.get("business_relevance")
        if raw_biz is None or raw_biz == 0:
            business_fit = 0.40  # neutral baseline for un-enriched questions
        else:
            business_fit = _clamp(float(raw_biz) / 100.0)

        # 2. Intent value (0–1)
        intent = (q.get("intent") or "").lower()
        intent_val = INTENT_VALUES.get(intent, 0.5)
        # Funnel stage bonus
        funnel = (q.get("funnel_stage") or "").upper()
        intent_val = _clamp(intent_val + FUNNEL_BONUS.get(funnel, 0.0))

        # 3. Demand potential (0–1) — proxy from expansion depth & cluster membership
        has_cluster = bool(q.get("content_cluster_id"))
        is_expanded = (q.get("expansion_depth") or 0) > 0
        demand = 0.5
        if has_cluster:
            demand += 0.2
        if is_expanded:
            demand += 0.15
        demand = _clamp(demand)

        # 4. Competition ease (0–1) — default moderate; long-tail questions score higher
        question_text = ""  # text not loaded in this lightweight call
        # Expansion depth suggests longer-tail (easier competition)
        depth = q.get("expansion_depth") or 0
        competition_ease = _clamp(0.5 + depth * 0.15)

        # 5. Uniqueness (0–1) — seed questions score higher (depth=0)
        uniqueness = _clamp(1.0 - depth * 0.1)

        # 6. Profile-aware context boost (applied to business_fit)
        #    Match question text against profile fields for relevance bonus
        ctx_boost = 0.0
        if profile_ctx:
            q_text = (q.get("question") or "").lower()
            if q_text:
                # Location match: question mentions a target or business location
                for loc in profile_ctx.get("locations", []):
                    if loc in q_text:
                        ctx_boost += 0.08
                        break
                # Product match: question mentions a specific product
                for prod in profile_ctx.get("products", []):
                    if prod in q_text:
                        ctx_boost += 0.06
                        break
                # Cultural match: question references cultural context terms
                for term in profile_ctx.get("cultural", []):
                    if term in q_text:
                        ctx_boost += 0.05
                        break
                # Audience match: question matches audience segment language
                for seg in profile_ctx.get("audience", []):
                    if seg in q_text:
                        ctx_boost += 0.04
                        break
        business_fit = _clamp(business_fit + ctx_boost)

        breakdown = {
            "business_fit": round(business_fit, 3),
            "intent_value": round(intent_val, 3),
            "demand_potential": round(demand, 3),
            "competition_ease": round(competition_ease, 3),
            "uniqueness": round(uniqueness, 3),
        }

        final = (
            business_fit     * weights.get("business_fit", 0.30) +
            intent_val       * weights.get("intent_value", 0.20) +
            demand           * weights.get("demand_potential", 0.20) +
            competition_ease * weights.get("competition_ease", 0.15) +
            uniqueness       * weights.get("uniqueness", 0.15)
        )
        return round(_clamp(final) * 100, 2), breakdown

    def _load_weights(self, session_id: str) -> dict:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT weights FROM kw2_scoring_config WHERE session_id=?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return dict(DEFAULT_WEIGHTS)
        try:
            w = json.loads(row["weights"])
            # Fill in any missing keys with defaults
            return {k: w.get(k, DEFAULT_WEIGHTS[k]) for k in DEFAULT_WEIGHTS}
        except Exception:
            return dict(DEFAULT_WEIGHTS)

    @staticmethod
    def _build_profile_match_ctx(profile: dict, mi: dict) -> dict:
        """Build lowercase term sets from profile for keyword-matching during scoring."""
        ctx: dict[str, list[str]] = {"locations": [], "products": [], "cultural": [], "audience": []}
        # Combine target_locations + business_locations
        for loc in (profile.get("target_locations") or mi.get("target_locations", [])):
            t = str(loc).strip().lower()
            if t and len(t) >= 2:
                ctx["locations"].append(t)
        for loc in (profile.get("business_locations") or mi.get("business_locations", [])):
            t = str(loc).strip().lower()
            if t and len(t) >= 2 and t not in ctx["locations"]:
                ctx["locations"].append(t)
        # Product catalog items (extract short searchable terms)
        for prod in (profile.get("product_catalog") or []):
            t = str(prod).strip().lower()
            if t and len(t) >= 3:
                ctx["products"].append(t)
        # Cultural context terms
        for c in (profile.get("cultural_context") or mi.get("cultural_context", [])):
            t = str(c).strip().lower()
            if t and len(t) >= 2:
                ctx["cultural"].append(t)
        # Audience segments
        for a in (profile.get("audience") or []):
            t = str(a).strip().lower()
            if t and len(t) >= 3:
                ctx["audience"].append(t)
        return ctx

    def _update_cluster_scores(self, session_id: str) -> None:
        conn = db.get_conn()
        try:
            clusters = conn.execute(
                "SELECT id FROM kw2_content_clusters WHERE session_id=?",
                (session_id,),
            ).fetchall()
            for cl in clusters:
                cid = cl["id"]
                avg = conn.execute(
                    """SELECT AVG(final_score) as avg_s, COUNT(*) as cnt
                       FROM kw2_intelligence_questions
                       WHERE content_cluster_id=? AND session_id=? AND is_duplicate=0""",
                    (cid, session_id),
                ).fetchone()
                if avg:
                    conn.execute(
                        "UPDATE kw2_content_clusters SET avg_score=?, question_count=? WHERE id=?",
                        (
                            round(float(avg["avg_s"] or 0), 2),
                            avg["cnt"] or 0,
                            cid,
                        ),
                    )
            conn.commit()
        finally:
            conn.close()
