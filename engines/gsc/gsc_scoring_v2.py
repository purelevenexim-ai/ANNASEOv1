"""
GSC Phase 2 — Advanced Scoring Engine (v2)
Upgrades Phase 1 scoring with:
  - intent_confidence boost
  - cluster importance signal
  - opportunity scoring (position-impressions gap)
  - business goal priority

Also: Topic Authority scoring per pillar.
"""
import logging
from collections import defaultdict

from . import gsc_db

log = logging.getLogger(__name__)


def rescore_keywords(project_id: str) -> dict:
    """
    Rescore all processed keywords with Phase 2 signals.

    New formula:
      score = source_score
            + impressions * 0.005 (cap 30)
            + clicks * 0.05 (cap 20)
            + intent_boost
            + opportunity_score
            + confidence_score      ← NEW
            + business_priority     ← NEW

    Returns: {rescored: N}
    """
    processed = gsc_db.get_processed_keywords(project_id)
    if not processed:
        return {"rescored": 0}

    # Load config for business goal
    config = gsc_db.get_project_config(project_id) or {}
    goal = config.get("goal", "sales")

    INTENT_BOOST = {
        "purchase": 5, "wholesale": 4, "commercial": 2,
        "informational": 1, "navigational": 0,
    }
    # Goal-based intent priorities
    GOAL_BONUS = {
        "sales":   {"purchase": 3, "wholesale": 2, "commercial": 1},
        "leads":   {"commercial": 3, "informational": 2, "purchase": 1},
        "traffic": {"informational": 3, "commercial": 2, "purchase": 1},
    }
    goal_map = GOAL_BONUS.get(goal, GOAL_BONUS["sales"])

    updates = []
    for kw in processed:
        impressions = kw.get("impressions", 0)
        clicks = kw.get("clicks", 0)
        position = kw.get("position", 0.0)
        intent = kw.get("intent", "informational")
        confidence = kw.get("intent_confidence", 0.0) or 0.0

        source_score = 5
        impression_score = min(impressions * 0.005, 30)
        click_score = min(clicks * 0.05, 20)
        intent_boost = INTENT_BOOST.get(intent, 0)

        # Opportunity: high impressions but poor rank
        opportunity_score = 0
        if position > 10 and impressions > 200:
            opportunity_score = min(impressions * 0.002, 15)
        elif position > 20 and impressions > 500:
            opportunity_score = min(impressions * 0.003, 20)

        # Phase 2 additions
        confidence_score = confidence * 5  # max +5
        business_priority = goal_map.get(intent, 0)

        total = (source_score + impression_score + click_score +
                 intent_boost + opportunity_score +
                 confidence_score + business_priority)

        updates.append((
            round(total, 2), round(impression_score, 2), round(click_score, 2),
            intent_boost, round(opportunity_score, 2), source_score,
            project_id, kw["keyword"],
        ))

    with gsc_db._conn() as c:
        c.executemany(
            """UPDATE gsc_keywords_processed SET
                 score=?, impression_score=?, click_score=?,
                 intent_boost=?, opportunity_score=?, source_score=?
               WHERE project_id=? AND keyword=?""",
            updates,
        )

    # Re-mark top 100 per pillar
    _remark_top100(project_id)

    log.info(f"[GSC Score] Rescored {len(updates)} keywords")
    return {"rescored": len(updates)}


def _remark_top100(project_id: str):
    """Re-mark top 100 per pillar after rescoring."""
    with gsc_db._conn() as c:
        # Reset all
        c.execute("UPDATE gsc_keywords_processed SET top100=0 WHERE project_id=?", (project_id,))
        # Get distinct pillars
        pillars = c.execute(
            "SELECT DISTINCT pillar FROM gsc_keywords_processed WHERE project_id=? AND pillar IS NOT NULL",
            (project_id,)
        ).fetchall()
        for (pillar,) in pillars:
            rows = c.execute(
                """SELECT id FROM gsc_keywords_processed
                   WHERE project_id=? AND pillar=?
                   ORDER BY score DESC LIMIT 100""",
                (project_id, pillar)
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                placeholders = ",".join("?" * len(ids))
                c.execute(
                    f"UPDATE gsc_keywords_processed SET top100=1 WHERE id IN ({placeholders})",
                    ids
                )


def calculate_authority(project_id: str) -> dict:
    """
    Calculate topic authority score per pillar.

    Formula:
      authority = coverage * 0.2 + traffic * 0.3 + intent_value * 0.2
                + ranking_strength * 0.2 + cluster_depth * 0.1

    Returns: {pillar_name: {authority_score, status, coverage, traffic, ...}}
    """
    processed = gsc_db.get_processed_keywords(project_id)
    if not processed:
        return {}

    clusters = gsc_db.get_clusters(project_id)

    per_pillar: dict[str, list[dict]] = defaultdict(list)
    for kw in processed:
        if kw.get("pillar"):
            per_pillar[kw["pillar"]].append(kw)

    results = {}
    for pillar, kws in per_pillar.items():
        coverage = len(kws)
        if coverage == 0:
            continue

        traffic = sum(kw.get("impressions", 0) for kw in kws)
        purchase_count = sum(1 for kw in kws if kw.get("intent") in ("purchase", "wholesale"))
        purchase_ratio = purchase_count / coverage if coverage else 0

        positions = [kw.get("position", 50.0) for kw in kws if kw.get("position", 0) > 0]
        avg_position = sum(positions) / len(positions) if positions else 50.0

        # Count clusters that belong to this pillar
        pillar_clusters = set()
        for cname, ckws in clusters.items():
            for ckw in ckws:
                if ckw.get("pillar") == pillar:
                    pillar_clusters.add(cname)
                    break
        cluster_depth = len(pillar_clusters)

        # Normalize components to 0-100 scale
        coverage_norm = min(coverage / 5, 100)  # 500 kws = max
        traffic_norm = min(traffic / 100, 100)   # 10000 imp = max
        intent_norm = purchase_ratio * 100
        rank_norm = max(0, (1 / max(avg_position, 1)) * 100) * 10  # lower position = better
        cluster_norm = min(cluster_depth * 10, 100)

        authority = (
            coverage_norm * 0.2 +
            traffic_norm * 0.3 +
            intent_norm * 0.2 +
            rank_norm * 0.2 +
            cluster_norm * 0.1
        )
        authority = round(min(authority, 100), 1)

        status = "strong" if authority >= 60 else "moderate" if authority >= 30 else "weak"

        results[pillar] = {
            "authority_score": authority,
            "status": status,
            "coverage": coverage,
            "traffic": traffic,
            "purchase_ratio": round(purchase_ratio, 2),
            "avg_position": round(avg_position, 1),
            "cluster_depth": cluster_depth,
        }

    return results
