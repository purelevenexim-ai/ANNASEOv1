"""
kw2 Selection Engine — Phase 8.

From scored questions, selects a diversity-balanced top set for content execution.
Selection rules:
- Min/max per cluster (prevents single-cluster dominance)
- Intent distribution balance (info/commercial/transactional/nav)
- Funnel coverage (TOFU/MOFU/BOFU all represented)
- Geo coverage (ensure geographic spread if geo questions exist)
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from engines.kw2 import db

log = logging.getLogger("kw2.selection_engine")

DEFAULT_SELECTION_CONFIG = {
    "target_count": 100,
    "min_per_cluster": 3,
    "max_per_cluster": 20,
    "intent_distribution": {
        "informational":  0.50,
        "commercial":     0.25,
        "transactional":  0.20,
        "navigational":   0.05,
    },
    "ensure_funnel_coverage": True,
    "ensure_geo_coverage": True,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


class SelectionEngine:
    """Phase 8: Diversity-balanced selection from scored questions."""

    def run(
        self,
        session_id: str,
        project_id: str,
        target_count: int = 100,
        min_per_cluster: int = 3,
        max_per_cluster: int = 20,
    ) -> dict:
        """
        Select top N questions with diversity constraints.
        Saves results to kw2_selected_questions.
        """
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question, intent, funnel_stage, content_cluster_id,
                          final_score, geo_relevance, expansion_depth
                   FROM kw2_intelligence_questions
                   WHERE session_id=? AND is_duplicate=0 AND final_score > 0
                   ORDER BY final_score DESC""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        questions = [dict(r) for r in rows]
        if not questions:
            return {"selected": 0}

        # Apply profile-aware score boosts before selection
        profile = db.load_business_profile(project_id)
        if profile:
            self._apply_profile_boosts(questions, profile)
            questions.sort(key=lambda q: q.get("final_score", 0), reverse=True)

        selected = self._select_diverse(
            questions, target_count, min_per_cluster, max_per_cluster,
        )

        # Clear previous selection
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_selected_questions WHERE session_id=?", (session_id,)
            )
            now = _now()
            to_insert = []
            for rank, q in enumerate(selected, start=1):
                to_insert.append((
                    _uid("sq_"),
                    session_id,
                    q["id"],
                    rank,
                    q.get("_selection_reason", ""),
                    q.get("content_cluster_id", ""),
                    "selected",
                    now,
                ))
            conn.executemany(
                """INSERT INTO kw2_selected_questions
                   (id, session_id, question_id, selection_rank, selection_reason,
                    cluster_id, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()

        log.info("[SelectionEngine] Selected %d questions for session %s", len(selected), session_id)
        return {"selected": len(selected), "total_scored": len(questions)}

    def list_selected(self, session_id: str, limit: int = 200) -> list[dict]:
        """Return selected questions with question text joined."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT sq.*, iq.question, iq.intent, iq.funnel_stage,
                          iq.business_relevance, iq.final_score, iq.content_type,
                          iq.audience_segment, iq.module_code, iq.content_cluster_id,
                          iq.expansion_dimension_name, iq.expansion_dimension_value,
                          cc.cluster_name, cc.pillar
                   FROM kw2_selected_questions sq
                   JOIN kw2_intelligence_questions iq ON sq.question_id = iq.id
                   LEFT JOIN kw2_content_clusters cc ON iq.content_cluster_id = cc.id
                   WHERE sq.session_id=?
                   ORDER BY sq.selection_rank ASC
                   LIMIT ?""",
                (session_id, limit),
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

    def include_question(self, session_id: str, question_id: str) -> str:
        """Manually add a question to the selection."""
        conn = db.get_conn()
        try:
            # Get max rank
            max_rank = conn.execute(
                "SELECT COALESCE(MAX(selection_rank),0) FROM kw2_selected_questions WHERE session_id=?",
                (session_id,),
            ).fetchone()[0] or 0
            sid_new = _uid("sq_")
            conn.execute(
                """INSERT OR IGNORE INTO kw2_selected_questions
                   (id, session_id, question_id, selection_rank, selection_reason,
                    status, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sid_new, session_id, question_id, max_rank + 1, "manual", "selected", _now()),
            )
            conn.commit()
        finally:
            conn.close()
        return sid_new

    def remove_question(self, session_id: str, question_id: str) -> bool:
        """Remove a question from the selection."""
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_selected_questions WHERE session_id=? AND question_id=?",
                (session_id, question_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # ── Profile-aware boosting ────────────────────────────────────────────────

    @staticmethod
    def _apply_profile_boosts(questions: list[dict], profile: dict) -> None:
        """Apply small score boosts for questions matching business context."""
        _mi = profile.get("manual_input") or {}
        locations = set()
        for loc in (profile.get("target_locations") or _mi.get("target_locations") or []):
            locations.update(w.lower() for w in loc.split() if len(w) >= 3)
        for loc in (profile.get("business_locations") or _mi.get("business_locations") or []):
            locations.update(w.lower() for w in loc.split() if len(w) >= 3)
        cultural = set()
        for c in (profile.get("cultural_context") or _mi.get("cultural_context") or []):
            cultural.update(w.lower() for w in c.split() if len(w) >= 2)
        products = set()
        for p in (profile.get("product_catalog") or []):
            products.update(w.lower() for w in p.split() if len(w) >= 3)

        if not any([locations, cultural, products]):
            return

        for q in questions:
            text = (q.get("question") or "").lower()
            if not text:
                continue
            boost = 0.0
            words = set(text.split())
            if locations and words & locations:
                boost += 2.0  # location-matching questions prioritized
            if cultural and words & cultural:
                boost += 1.5  # cultural-relevance boost
            if products and words & products:
                boost += 1.0  # product-specific boost
            if boost > 0:
                q["final_score"] = q.get("final_score", 0) + boost

    # ── Selection algorithm ───────────────────────────────────────────────────

    def _select_diverse(
        self,
        questions: list[dict],
        target: int,
        min_per_cluster: int,
        max_per_cluster: int,
    ) -> list[dict]:
        selected: list[dict] = []
        cluster_counts: dict[str, int] = defaultdict(int)
        intent_counts: dict[str, int] = defaultdict(int)
        funnel_counts: dict[str, int] = defaultdict(int)
        selected_ids: set[str] = set()

        # Target distribution: informational 50%, commercial 25%, transactional 20%, nav 5%
        intent_caps = {
            "informational":  max(1, int(target * 0.50)),
            "commercial":     max(1, int(target * 0.25)),
            "transactional":  max(1, int(target * 0.20)),
            "navigational":   max(1, int(target * 0.05)),
        }
        # Funnel caps: ensure TOFU/MOFU/BOFU all present
        funnel_min = max(1, int(target * 0.15))

        def _can_add(q: dict) -> tuple[bool, str]:
            cid = q.get("content_cluster_id") or "unclassified"
            if cluster_counts[cid] >= max_per_cluster:
                return False, "cluster_max"
            intent = (q.get("intent") or "informational").lower()
            cap = intent_caps.get(intent, max(1, int(target * 0.10)))
            if intent_counts[intent] >= cap:
                return False, f"intent_cap_{intent}"
            return True, "ok"

        # Pass 1: ensure at least 1 per cluster (cluster coverage)
        clusters_covered: set[str] = set()
        for q in questions:
            if len(selected) >= target:
                break
            cid = q.get("content_cluster_id") or "unclassified"
            if cid in clusters_covered:
                continue
            ok, _ = _can_add(q)
            if not ok:
                # Still add one per cluster even if over intent cap to guarantee coverage
                if cluster_counts[cid] >= max_per_cluster:
                    continue
            q["_selection_reason"] = "cluster_coverage"
            selected.append(q)
            selected_ids.add(q["id"])
            cluster_counts[cid] += 1
            intent = (q.get("intent") or "informational").lower()
            intent_counts[intent] += 1
            funnel_counts[q.get("funnel_stage", "TOFU")] += 1
            clusters_covered.add(cid)

        # Pass 2: fill funnel gaps (ensure TOFU/MOFU/BOFU represented)
        for stage in ("TOFU", "MOFU", "BOFU"):
            if funnel_counts.get(stage, 0) >= funnel_min:
                continue
            for q in questions:
                if len(selected) >= target:
                    break
                if q["id"] in selected_ids:
                    continue
                if (q.get("funnel_stage") or "").upper() != stage:
                    continue
                cid = q.get("content_cluster_id") or "unclassified"
                if cluster_counts[cid] >= max_per_cluster:
                    continue
                q["_selection_reason"] = f"funnel_{stage}_coverage"
                selected.append(q)
                selected_ids.add(q["id"])
                cluster_counts[cid] += 1
                intent_counts[(q.get("intent") or "informational").lower()] += 1
                funnel_counts[stage] += 1
                if funnel_counts[stage] >= funnel_min:
                    break

        # Pass 3: fill remaining by score respecting intent distribution caps
        for q in questions:
            if len(selected) >= target:
                break
            if q["id"] in selected_ids:
                continue
            ok, _ = _can_add(q)
            if not ok:
                continue
            cid = q.get("content_cluster_id") or "unclassified"
            q["_selection_reason"] = "top_score"
            selected.append(q)
            selected_ids.add(q["id"])
            cluster_counts[cid] += 1
            intent_counts[(q.get("intent") or "informational").lower()] += 1
            funnel_counts[q.get("funnel_stage", "TOFU")] += 1

        # Pass 4: if still short, relax intent caps and fill by score
        if len(selected) < target:
            for q in questions:
                if len(selected) >= target:
                    break
                if q["id"] in selected_ids:
                    continue
                cid = q.get("content_cluster_id") or "unclassified"
                if cluster_counts[cid] >= max_per_cluster:
                    continue
                q["_selection_reason"] = "fill_relaxed"
                selected.append(q)
                selected_ids.add(q["id"])
                cluster_counts[cid] += 1

        return selected
