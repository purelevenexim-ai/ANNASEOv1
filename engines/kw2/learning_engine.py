"""
kw2 Learning Engine — Phase 12 (Real AI).

Data → Intelligence → Decisions → Strategy

Pipeline:
  1. PatternExtractor   — groups content performance by (cluster, title_type)
                          computes aggregates with statistical confidence
  2. PatternScorer      — revenue-weighted business score per pattern
  3. PatternMemory      — persists patterns to kw2_patterns table
  4. ClusterScorer      — cluster_score = revenue×0.5 + conversion×0.3 + traffic×0.2
  5. ROIEngine          — profit / cost → roi_score
  6. DecisionEngine     — scale / kill / optimize per content piece
  7. ContentMixOptimizer— dynamic intent % from pattern performance data
  8. FeedbackLoop       — runs all steps end-to-end and updates kw2_strategy_state
"""
from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from engines.kw2 import db

log = logging.getLogger("kw2.learning_engine")


# ── Utilities ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / (len(values) - 1)


# ── Title type classifier ──────────────────────────────────────────────────────

_TITLE_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("how_to",      re.compile(r"\bhow\s+to\b", re.I)),
    ("best_of",     re.compile(r"\bbest\b", re.I)),
    ("guide",       re.compile(r"\bguide\b|\bguida\b", re.I)),
    ("vs",          re.compile(r"\bvs\.?\b|\bversus\b", re.I)),
    ("review",      re.compile(r"\breview\b|\breviews\b", re.I)),
    ("top_n",       re.compile(r"\btop\s+\d+\b", re.I)),
    ("what_is",     re.compile(r"\bwhat\s+is\b|\bwhat\s+are\b", re.I)),
    ("where_to",    re.compile(r"\bwhere\s+to\b", re.I)),
    ("buy",         re.compile(r"\bbuy\b|\bshop\b|\borders?\b|\bpurchase\b", re.I)),
    ("price",       re.compile(r"\bprice\b|\bcost\b|\brate\b|\bwholesale\b", re.I)),
    ("recipe",      re.compile(r"\brecipe\b|\bcook\b|\bdish\b|\bfood\b", re.I)),
    ("benefit",     re.compile(r"\bbenefits?\b|\badvantage\b|\bhealth\b", re.I)),
]


def classify_title_type(title: str) -> str:
    """Return the title type category for a content title string."""
    if not title:
        return "other"
    for label, pattern in _TITLE_TYPE_PATTERNS:
        if pattern.search(title):
            return label
    return "other"


# ── 1. Pattern Extractor ───────────────────────────────────────────────────────

class PatternExtractor:
    """
    Extracts pattern signals from kw2_content_performance × kw2_content_titles.
    Groups by (cluster_name, title_type) and computes statistical aggregates.
    """

    def extract(self, session_id: str) -> list[dict]:
        """
        Return a list of pattern dicts, each representing one
        (cluster_name, title_type) combination with aggregated metrics.
        """
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT
                     ct.cluster_name,
                     ct.title,
                     ct.intent,
                     ct.word_count_target,
                     cp.ctr,
                     cp.google_position,
                     cp.organic_clicks,
                     cp.impressions,
                     cp.conversions,
                     cp.revenue,
                     cp.cost,
                     cp.bounce_rate,
                     cp.time_on_page_seconds
                   FROM kw2_content_performance cp
                   JOIN kw2_content_titles ct ON cp.content_title_id = ct.id
                   WHERE cp.session_id = ?""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        # Group by (cluster_name, title_type)
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            cluster = (r["cluster_name"] or "Unclustered").strip()
            title_type = classify_title_type(r["title"] or "")
            groups[(cluster, title_type)].append({
                "ctr":              float(r["ctr"] or 0.0),
                "avg_position":     float(r["google_position"] or 0.0),
                "clicks":           int(r["organic_clicks"] or 0),
                "impressions":      int(r["impressions"] or 0),
                "conversions":      int(r["conversions"] or 0),
                "revenue":          float(r["revenue"] or 0.0),
                "cost":             float(r["cost"] or 0.0),
                "bounce_rate":      float(r["bounce_rate"] or 0.0),
                "time_on_page":     int(r["time_on_page_seconds"] or 0),
                "word_count":       int(r["word_count_target"] or 0),
                "intent":           r["intent"] or "",
            })

        patterns: list[dict] = []
        for (cluster, title_type), items in groups.items():
            n = len(items)
            ctrs = [i["ctr"] for i in items]
            convs = [i["conversions"] for i in items]
            revs = [i["revenue"] for i in items]
            lengths = [i["word_count"] for i in items if i["word_count"] > 0]

            avg_ctr = _mean(ctrs)
            avg_conv = _mean(convs)
            avg_rev = _mean(revs)
            avg_cost = _mean([i["cost"] for i in items])
            avg_bounce = _mean([i["bounce_rate"] for i in items])
            avg_ttp = _mean([i["time_on_page"] for i in items])
            avg_pos = _mean([i["avg_position"] for i in items if i["avg_position"] > 0])

            # Statistical confidence: larger samples + lower CTR variance → higher confidence
            ctr_var = _variance(ctrs)
            confidence = min(1.0, n / 10.0) * (1.0 / (1.0 + ctr_var))

            # Best length (most common rounded to 500-word bands)
            best_length = 0
            if lengths:
                band_counts: dict[int, int] = defaultdict(int)
                for l in lengths:
                    band = round(l / 500) * 500
                    band_counts[band] += 1
                best_length = max(band_counts, key=band_counts.get)

            # Best intent (most common in this group)
            intent_counts: dict[str, int] = defaultdict(int)
            for i in items:
                if i["intent"]:
                    intent_counts[i["intent"]] += 1
            best_intent = max(intent_counts, key=intent_counts.get) if intent_counts else ""

            patterns.append({
                "cluster_name":       cluster,
                "title_type":         title_type,
                "sample_size":        n,
                "avg_ctr":            round(avg_ctr, 5),
                "avg_position":       round(avg_pos, 2),
                "avg_conversions":    round(avg_conv, 3),
                "avg_revenue":        round(avg_rev, 2),
                "avg_cost":           round(avg_cost, 2),
                "avg_bounce_rate":    round(avg_bounce, 4),
                "avg_time_on_page":   round(avg_ttp, 1),
                "confidence":         round(confidence, 4),
                "best_length":        best_length,
                "best_intent":        best_intent,
            })

        return patterns


# ── 2. Pattern Scorer ──────────────────────────────────────────────────────────

class PatternScorer:
    """
    Computes a single weighted business score per pattern.
    Revenue > Conversion > Traffic.
    """

    # Weights: revenue > conversion > ctr (traffic)
    CTR_W = 0.20
    CONVERSION_W = 0.40
    REVENUE_W = 0.40

    def score(self, patterns: list[dict], max_revenue: float = 0.0) -> list[dict]:
        """
        Add a 'pattern_score' (0–1) to each pattern.
        Scores are normalised so the best pattern = 1.0.
        """
        if not patterns:
            return patterns

        # Normalisation denominators
        max_ctr = max((p["avg_ctr"] for p in patterns), default=1.0) or 1.0
        max_conv = max((p["avg_conversions"] for p in patterns), default=1.0) or 1.0
        max_rev = max_revenue or max((p["avg_revenue"] for p in patterns), default=1.0) or 1.0

        scored = []
        for p in patterns:
            norm_ctr = p["avg_ctr"] / max_ctr
            norm_conv = p["avg_conversions"] / max_conv
            norm_rev = p["avg_revenue"] / max_rev
            raw = (
                norm_ctr * self.CTR_W +
                norm_conv * self.CONVERSION_W +
                norm_rev * self.REVENUE_W
            )
            p["pattern_score"] = round(raw * p["confidence"], 4)
            scored.append(p)

        return sorted(scored, key=lambda x: x["pattern_score"], reverse=True)


# ── 3. Pattern Memory ──────────────────────────────────────────────────────────

class PatternMemory:
    """
    Persists patterns to kw2_patterns.
    Provides retrieval: best patterns per cluster, best title type overall.
    """

    def update(self, session_id: str, project_id: str, patterns: list[dict]) -> int:
        """Upsert all patterns into kw2_patterns. Returns count saved."""
        if not patterns:
            return 0
        now = _now()
        conn = db.get_conn()
        saved = 0
        try:
            for p in patterns:
                existing = conn.execute(
                    "SELECT id FROM kw2_patterns WHERE session_id=? AND cluster_name=? AND title_type=?",
                    (session_id, p["cluster_name"], p["title_type"]),
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE kw2_patterns SET
                           sample_size=?, avg_ctr=?, avg_position=?, avg_conversions=?,
                           avg_revenue=?, avg_cost=?, avg_time_on_page=?, avg_bounce_rate=?,
                           confidence=?, pattern_score=?, best_length=?, best_intent=?,
                           updated_at=?
                           WHERE id=?""",
                        (
                            p["sample_size"], p["avg_ctr"], p.get("avg_position", 0),
                            p["avg_conversions"], p["avg_revenue"], p["avg_cost"],
                            p.get("avg_time_on_page", 0), p.get("avg_bounce_rate", 0),
                            p["confidence"], p.get("pattern_score", 0),
                            p["best_length"], p["best_intent"],
                            now, existing["id"],
                        ),
                    )
                else:
                    conn.execute(
                        """INSERT INTO kw2_patterns
                           (id, session_id, project_id, cluster_name, title_type,
                            sample_size, avg_ctr, avg_position, avg_conversions,
                            avg_revenue, avg_cost, avg_time_on_page, avg_bounce_rate,
                            confidence, pattern_score, best_length, best_intent,
                            created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            _uid("pat_"), session_id, project_id,
                            p["cluster_name"], p["title_type"],
                            p["sample_size"], p["avg_ctr"], p.get("avg_position", 0),
                            p["avg_conversions"], p["avg_revenue"], p["avg_cost"],
                            p.get("avg_time_on_page", 0), p.get("avg_bounce_rate", 0),
                            p["confidence"], p.get("pattern_score", 0),
                            p["best_length"], p["best_intent"],
                            now, now,
                        ),
                    )
                saved += 1
            conn.commit()
        finally:
            conn.close()
        return saved

    def get_best_for_cluster(self, session_id: str, cluster_name: str, top_n: int = 3) -> list[dict]:
        """Return top N patterns for a given cluster, sorted by pattern_score desc."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM kw2_patterns
                   WHERE session_id=? AND cluster_name=? AND sample_size > 0
                   ORDER BY pattern_score DESC LIMIT ?""",
                (session_id, cluster_name, top_n),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all(self, session_id: str) -> list[dict]:
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM kw2_patterns WHERE session_id=?
                   ORDER BY pattern_score DESC""",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def apply_to_content(self, session_id: str, cluster_name: str) -> dict:
        """
        Given a cluster, return the AI recommendation:
        title_style, content_length, best_intent, confidence.
        Falls back to global best if no cluster-specific data.
        """
        patterns = self.get_best_for_cluster(session_id, cluster_name, top_n=3)
        if not patterns:
            # Global fallback
            conn = db.get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM kw2_patterns WHERE session_id=? ORDER BY pattern_score DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                patterns = [dict(row)] if row else []
            finally:
                conn.close()
        if not patterns:
            return {"title_style": "how_to", "content_length": 2000, "best_intent": "informational", "confidence": 0.0}

        best = patterns[0]
        return {
            "title_style":    best["title_type"],
            "content_length": best["best_length"] or 1800,
            "best_intent":    best["best_intent"] or "informational",
            "confidence":     best["confidence"],
            "pattern_score":  best["pattern_score"],
        }


# ── 4. Cluster Scorer ──────────────────────────────────────────────────────────

class ClusterScorer:
    """
    Scores content clusters by revenue × 0.5 + conversion × 0.3 + traffic × 0.2.
    Uses kw2_content_performance joined to kw2_content_titles.
    """

    def score_all(self, session_id: str) -> list[dict]:
        """Return clusters sorted by cluster_score descending."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT
                     ct.cluster_name,
                     SUM(cp.revenue) as total_revenue,
                     SUM(cp.conversions) as total_conversions,
                     SUM(cp.organic_clicks) as total_traffic,
                     COUNT(cp.id) as data_points
                   FROM kw2_content_performance cp
                   JOIN kw2_content_titles ct ON cp.content_title_id = ct.id
                   WHERE cp.session_id=?
                   GROUP BY ct.cluster_name""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        clusters = []
        for r in rows:
            cluster = dict(r)
            rev = float(cluster["total_revenue"] or 0)
            conv = float(cluster["total_conversions"] or 0)
            traffic = float(cluster["total_traffic"] or 0)
            # Normalise to 0–1 (raw values, need cross-cluster normalisation)
            clusters.append({
                "cluster_name":      cluster["cluster_name"] or "Unclustered",
                "total_revenue":     round(rev, 2),
                "total_conversions": int(conv),
                "total_traffic":     int(traffic),
                "data_points":       cluster["data_points"],
                "_rev": rev, "_conv": conv, "_traffic": traffic,
            })

        if not clusters:
            return clusters

        max_rev = max(c["_rev"] for c in clusters) or 1.0
        max_conv = max(c["_conv"] for c in clusters) or 1.0
        max_traffic = max(c["_traffic"] for c in clusters) or 1.0

        for c in clusters:
            c["cluster_score"] = round(
                (c["_rev"] / max_rev) * 0.50 +
                (c["_conv"] / max_conv) * 0.30 +
                (c["_traffic"] / max_traffic) * 0.20,
                4,
            )
            del c["_rev"], c["_conv"], c["_traffic"]

        return sorted(clusters, key=lambda x: x["cluster_score"], reverse=True)


# ── 5. ROI Engine ──────────────────────────────────────────────────────────────

class ROIEngine:
    """
    Computes profit, roi_score per content title.
    Uses aggregated performance data.
    """

    # Thresholds for decisions
    SCALE_THRESHOLD = 3.0    # roi_score > 3 → scale
    KILL_THRESHOLD  = 1.0    # roi_score < 1 → kill (or optimize)

    def compute_for_session(self, session_id: str) -> list[dict]:
        """Return ROI metrics for all tracked content in this session."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT
                     ct.id, ct.title, ct.cluster_name, ct.intent, ct.pillar,
                     SUM(cp.revenue) as total_revenue,
                     SUM(cp.cost) as total_cost,
                     SUM(cp.conversions) as total_conversions,
                     SUM(cp.organic_clicks) as total_clicks,
                     AVG(cp.ctr) as avg_ctr,
                     AVG(cp.google_position) as avg_position,
                     AVG(cp.bounce_rate) as avg_bounce,
                     COUNT(cp.id) as data_points
                   FROM kw2_content_titles ct
                   JOIN kw2_content_performance cp ON cp.content_title_id = ct.id
                   WHERE ct.session_id=?
                   GROUP BY ct.id""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        results = []
        for r in rows:
            rev = float(r["total_revenue"] or 0)
            cost = float(r["total_cost"] or 0)
            profit = rev - cost
            roi_score = (profit / cost) if cost > 0 else (rev * 2 if rev > 0 else 0.0)
            results.append({
                "content_title_id": r["id"],
                "title":            r["title"],
                "cluster_name":     r["cluster_name"] or "",
                "intent":           r["intent"] or "",
                "pillar":           r["pillar"] or "",
                "total_revenue":    round(rev, 2),
                "total_cost":       round(cost, 2),
                "profit":           round(profit, 2),
                "roi_score":        round(roi_score, 3),
                "total_conversions":int(r["total_conversions"] or 0),
                "total_clicks":     int(r["total_clicks"] or 0),
                "avg_ctr":          round(float(r["avg_ctr"] or 0), 5),
                "avg_position":     round(float(r["avg_position"] or 0), 2),
                "avg_bounce_rate":  round(float(r["avg_bounce"] or 0), 4),
                "data_points":      r["data_points"],
            })

        return sorted(results, key=lambda x: x["roi_score"], reverse=True)

    def summary(self, roi_list: list[dict]) -> dict:
        """High-level ROI summary for a session."""
        if not roi_list:
            return {"total_revenue": 0, "total_profit": 0, "avg_roi": 0,
                    "scale_count": 0, "optimize_count": 0, "kill_count": 0}
        return {
            "total_revenue": round(sum(r["total_revenue"] for r in roi_list), 2),
            "total_profit":  round(sum(r["profit"] for r in roi_list), 2),
            "total_cost":    round(sum(r["total_cost"] for r in roi_list), 2),
            "avg_roi":       round(_mean([r["roi_score"] for r in roi_list]), 3),
            "scale_count":   sum(1 for r in roi_list if r["roi_score"] > self.SCALE_THRESHOLD),
            "optimize_count":sum(1 for r in roi_list if self.KILL_THRESHOLD <= r["roi_score"] <= self.SCALE_THRESHOLD),
            "kill_count":    sum(1 for r in roi_list if r["roi_score"] < self.KILL_THRESHOLD),
            "tracked_content": len(roi_list),
        }


# ── 6. Decision Engine ─────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Converts ROI scores + cluster signals into scale/kill/optimize decisions.
    Logs decisions to kw2_decisions_log.
    """

    def decide(
        self,
        session_id: str,
        project_id: str,
        roi_list: list[dict],
        cluster_scores: list[dict],
        scale_threshold: float = ROIEngine.SCALE_THRESHOLD,
        kill_threshold: float = ROIEngine.KILL_THRESHOLD,
    ) -> list[dict]:
        """
        Produce decisions for all content pieces.
        Writes to kw2_decisions_log. Returns list of decision records.
        """
        cluster_lookup = {c["cluster_name"]: c["cluster_score"] for c in cluster_scores}
        now = _now()
        decisions = []
        to_insert = []

        for item in roi_list:
            roi = item["roi_score"]
            cluster_boost = cluster_lookup.get(item["cluster_name"], 0)

            # Decision logic
            if roi > scale_threshold:
                decision = "scale"
                reason = f"roi_score={roi:.2f} > {scale_threshold} (high return)"
            elif roi < kill_threshold and cluster_boost < 0.2:
                decision = "kill"
                reason = f"roi_score={roi:.2f} < {kill_threshold} and cluster_score={cluster_boost:.2f} low"
            elif roi < kill_threshold:
                decision = "optimize"
                reason = f"roi_score={roi:.2f} low but cluster ({item['cluster_name']}) has potential ({cluster_boost:.2f})"
            else:
                decision = "optimize"
                reason = f"roi_score={roi:.2f} in mid range — needs targeting improvement"

            # Confidence: based on data_points and roi distance from threshold
            data_conf = min(1.0, item["data_points"] / 5.0)
            dist = abs(roi - (scale_threshold if decision == "scale" else kill_threshold))
            dist_conf = min(1.0, dist / 2.0)
            confidence = round((data_conf + dist_conf) / 2, 3)

            record = {
                "id":            _uid("dec_"),
                "session_id":    session_id,
                "project_id":    project_id,
                "entity_type":   "content",
                "entity_id":     item["content_title_id"],
                "entity_label":  (item["title"] or "")[:200],
                "decision":      decision,
                "reason":        reason,
                "roi_score":     roi,
                "confidence":    confidence,
                "created_at":    now,
            }
            decisions.append(record)
            to_insert.append((
                record["id"], session_id, project_id, "content",
                item["content_title_id"], (item["title"] or "")[:200],
                decision, reason, roi, confidence, 0, "", now,
            ))

        # Cluster-level decisions
        for c in cluster_scores:
            if c["cluster_score"] > 0.7:
                decision = "scale"
                reason = f"cluster_score={c['cluster_score']:.2f} → expand aggressively"
            elif c["cluster_score"] < 0.2:
                decision = "fade"
                reason = f"cluster_score={c['cluster_score']:.2f} → deprioritize"
            else:
                decision = "maintain"
                reason = f"cluster_score={c['cluster_score']:.2f} → steady investment"

            record = {
                "entity_type":  "cluster",
                "entity_id":    c["cluster_name"],
                "entity_label": c["cluster_name"],
                "decision":     decision,
                "reason":       reason,
                "roi_score":    c["cluster_score"],
                "confidence":   min(1.0, c["data_points"] / 5.0),
            }
            decisions.append(record)
            to_insert.append((
                _uid("dec_"), session_id, project_id, "cluster",
                c["cluster_name"], c["cluster_name"],
                decision, reason, c["cluster_score"],
                min(1.0, c["data_points"] / 5.0), 0, "", now,
            ))

        # Purge old decisions, write new ones
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_decisions_log WHERE session_id=?", (session_id,)
            )
            conn.executemany(
                """INSERT INTO kw2_decisions_log
                   (id, session_id, project_id, entity_type, entity_id, entity_label,
                    decision, reason, roi_score, confidence, overridden, override_reason, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()

        log.info("[DecisionEngine] %d decisions logged for session %s", len(decisions), session_id)
        return decisions

    def override(
        self, session_id: str, entity_id: str, new_decision: str, reason: str
    ) -> bool:
        """Manually override an AI decision."""
        conn = db.get_conn()
        try:
            conn.execute(
                """UPDATE kw2_decisions_log
                   SET decision=?, override_reason=?, overridden=1
                   WHERE session_id=? AND entity_id=?""",
                (new_decision, reason, session_id, entity_id),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def get_decisions(self, session_id: str, entity_type: str | None = None) -> list[dict]:
        conn = db.get_conn()
        try:
            if entity_type:
                rows = conn.execute(
                    "SELECT * FROM kw2_decisions_log WHERE session_id=? AND entity_type=? ORDER BY roi_score DESC",
                    (session_id, entity_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kw2_decisions_log WHERE session_id=? ORDER BY entity_type, roi_score DESC",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── 7. Content Mix Optimizer ───────────────────────────────────────────────────

class ContentMixOptimizer:
    """
    Computes dynamic content intent mix percentages from pattern performance.
    Replaces static "60% transactional" rules with data-driven allocation.
    """

    def optimize(self, patterns: list[dict]) -> dict:
        """
        Return normalized content mix dict: {"transactional": 0.65, ...}
        Weighted by pattern_score × avg_revenue.
        """
        intent_scores: dict[str, float] = defaultdict(float)
        intent_counts: dict[str, int] = defaultdict(int)

        for p in patterns:
            intent = p.get("best_intent") or "informational"
            if not intent:
                continue
            # Weight by both pattern_score and actual revenue
            weight = p.get("pattern_score", 0.01) * (1 + p.get("avg_revenue", 0))
            intent_scores[intent] += weight
            intent_counts[intent] += 1

        if not intent_scores:
            # No data: sensible defaults
            return {
                "transactional": 0.40,
                "commercial":    0.30,
                "informational": 0.25,
                "navigational":  0.05,
            }

        # Ensure all 4 intents have at least a floor weight (5%)
        for intent in ("transactional", "commercial", "informational", "navigational"):
            if intent not in intent_scores:
                intent_scores[intent] = 0.05

        total = sum(intent_scores.values())
        return {
            intent: round(score / total, 3)
            for intent, score in sorted(intent_scores.items(), key=lambda x: -x[1])
        }

    def cluster_priorities(self, cluster_scores: list[dict]) -> list[dict]:
        """
        Return cluster priority list with expansion recommendations.
        """
        priorities = []
        for i, c in enumerate(cluster_scores, start=1):
            cs = c["cluster_score"]
            if cs > 0.7:
                action = "expand"
                factor = 2.5
            elif cs > 0.4:
                action = "maintain"
                factor = 1.0
            else:
                action = "reduce"
                factor = 0.5
            priorities.append({
                "rank":          i,
                "cluster_name":  c["cluster_name"],
                "cluster_score": cs,
                "action":        action,
                "expansion_factor": factor,
                "revenue":       c["total_revenue"],
                "conversions":   c["total_conversions"],
            })
        return priorities


# ── 8. Feedback Loop (master orchestrator) ─────────────────────────────────────

class FeedbackLoop:
    """
    Runs the full learning pipeline end-to-end:
    Performance Data → Pattern Extraction → Scoring → Memory
    → ROI → Decisions → Strategy State update
    """

    def run(self, session_id: str, project_id: str) -> dict:
        """
        Execute the full feedback loop.
        Returns a summary dict of what changed.
        """
        log.info("[FeedbackLoop] Running for session %s", session_id)

        extractor = PatternExtractor()
        scorer = PatternScorer()
        memory = PatternMemory()
        cluster_scorer = ClusterScorer()
        roi_engine = ROIEngine()
        decision_engine = DecisionEngine()
        mix_optimizer = ContentMixOptimizer()

        # ── Step 1: Extract patterns ──────────────────────────────────────
        raw_patterns = extractor.extract(session_id)
        if not raw_patterns:
            log.info("[FeedbackLoop] No performance data — loop skipped")
            return {
                "ok": False,
                "reason": "No performance data recorded. Add performance metrics first.",
                "patterns_extracted": 0,
            }

        # ── Step 2: Score patterns ────────────────────────────────────────
        max_revenue = max((p["avg_revenue"] for p in raw_patterns), default=0.0)
        scored_patterns = scorer.score(raw_patterns, max_revenue=max_revenue)

        # ── Step 3: Persist to pattern memory ────────────────────────────
        patterns_saved = memory.update(session_id, project_id, scored_patterns)

        # ── Step 4: Score clusters ────────────────────────────────────────
        cluster_scores = cluster_scorer.score_all(session_id)

        # ── Step 5: ROI calculation ───────────────────────────────────────
        roi_list = roi_engine.compute_for_session(session_id)
        roi_summary = roi_engine.summary(roi_list)

        # ── Step 6: Decision engine ───────────────────────────────────────
        decisions = decision_engine.decide(
            session_id, project_id, roi_list, cluster_scores
        )

        # ── Step 7: Update content mix ────────────────────────────────────
        content_mix = mix_optimizer.optimize(scored_patterns)
        cluster_priorities = mix_optimizer.cluster_priorities(cluster_scores)
        expansion_candidates = [
            c for c in cluster_priorities if c["action"] == "expand"
        ]

        # ── Step 8: Persist strategy state ───────────────────────────────
        self._save_strategy_state(
            session_id, project_id,
            content_mix, cluster_priorities, expansion_candidates, roi_summary,
        )

        result = {
            "ok": True,
            "patterns_extracted": len(raw_patterns),
            "patterns_saved":     patterns_saved,
            "cluster_scores":     len(cluster_scores),
            "decisions_made":     len(decisions),
            "roi_tracked_items":  len(roi_list),
            "roi_summary":        roi_summary,
            "content_mix":        content_mix,
            "expansion_candidates": [c["cluster_name"] for c in expansion_candidates],
            "top_patterns": [
                {
                    "cluster": p["cluster_name"],
                    "title_type": p["title_type"],
                    "score": p["pattern_score"],
                    "confidence": p["confidence"],
                }
                for p in scored_patterns[:5]
            ],
        }
        log.info("[FeedbackLoop] Complete: %d patterns, %d decisions, ROI=%s",
                 patterns_saved, len(decisions), roi_summary.get("avg_roi", 0))
        return result

    def _save_strategy_state(
        self,
        session_id: str,
        project_id: str,
        content_mix: dict,
        cluster_priorities: list,
        expansion_candidates: list,
        roi_summary: dict,
    ) -> None:
        now = _now()
        conn = db.get_conn()
        try:
            existing = conn.execute(
                "SELECT id, version FROM kw2_strategy_state WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE kw2_strategy_state SET
                       content_mix=?, cluster_priorities=?, expansion_candidates=?,
                       roi_summary=?, last_decision_run=?, version=?, updated_at=?
                       WHERE session_id=?""",
                    (
                        _safe_json(content_mix),
                        _safe_json(cluster_priorities),
                        _safe_json(expansion_candidates),
                        _safe_json(roi_summary),
                        now,
                        (existing["version"] or 1) + 1,
                        now,
                        session_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO kw2_strategy_state
                       (id, session_id, project_id, content_mix, cluster_priorities,
                        expansion_candidates, roi_summary, last_decision_run, version, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,1,?)""",
                    (
                        _uid("ss_"), session_id, project_id,
                        _safe_json(content_mix),
                        _safe_json(cluster_priorities),
                        _safe_json(expansion_candidates),
                        _safe_json(roi_summary),
                        now, now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_strategy_state(self, session_id: str) -> dict | None:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_strategy_state WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            state = dict(row)
            for field in ("content_mix", "cluster_priorities", "expansion_candidates", "roi_summary"):
                try:
                    state[field] = json.loads(state[field] or "{}")
                except Exception:
                    state[field] = {}
            return state
        finally:
            conn.close()
