"""
kw2 Phase 4a — Hybrid Keyword Scoring Engine.

Three-signal scoring system:
  1. Rule Score (40%): Intent tokens + modifier premiums + commercial boosts
  2. Context Score (35%): Business-intelligence alignment (products, audience, geo)
  3. Data Score (25%): AI relevance, buyer readiness, source volume proxy

Produces final_score (0-100) with per-keyword score breakdown.
"""
import json
import logging

from engines.kw2.constants import (
    COMMERCIAL_BOOSTS,
    HYBRID_SCORE_WEIGHTS,
    INTENT_WEIGHTS,
    RULE_SCORE_INTENT,
    RULE_SCORE_MODIFIER_GENERIC,
    RULE_SCORE_MODIFIER_PREMIUM,
)
from engines.kw2 import db

log = logging.getLogger("kw2.scorer")

# Source → volume signal proxy (higher = likely more search volume)
SOURCE_VOLUME = {
    "suggest": 0.70,
    "competitor": 0.60,
    "ai_expand": 0.50,
    "rules": 0.40,
    "seeds": 0.35,
    "audience": 0.55,
    "attribute": 0.60,
    "problem": 0.50,
}


def _extract_context_terms(biz_intel: dict) -> dict:
    """Extract product names, audience segments, and geo terms from BI knowledge."""
    terms = {"products": [], "audience": [], "geo": [], "attributes": []}
    ks_raw = biz_intel.get("knowledge_summary", "")
    if not ks_raw:
        return terms
    try:
        ks = json.loads(ks_raw) if isinstance(ks_raw, str) else ks_raw
    except (json.JSONDecodeError, TypeError):
        return terms

    # Products from product_intelligence
    pi = ks.get("product_intelligence", {})
    for cat in pi.get("product_categories", []):
        if isinstance(cat, str):
            terms["products"].append(cat.lower())
        elif isinstance(cat, dict):
            terms["products"].append(str(cat.get("name", "")).lower())
    for attr in pi.get("product_attributes", []):
        terms["attributes"].append(str(attr).lower())
    for qm in pi.get("quality_markers", []):
        terms["attributes"].append(str(qm).lower())

    # Audience from audience_segmentation
    aud = ks.get("audience_segmentation", {})
    for seg_type in ["b2c_segments", "b2b_segments"]:
        for seg in aud.get(seg_type, []):
            if isinstance(seg, str):
                terms["audience"].append(seg.lower())
            elif isinstance(seg, dict):
                terms["audience"].append(str(seg.get("segment", seg.get("name", ""))).lower())

    # Geo from geographic_intelligence
    geo = ks.get("geographic_intelligence", {})
    for region in geo.get("micro_regions", geo.get("primary_regions", [])):
        terms["geo"].append(str(region).lower())

    return terms


class KeywordScorer:
    """Phase 4a: Hybrid scoring with rule, context, and data signals."""

    def score_all(self, project_id: str, session_id: str) -> dict:
        """
        Compute final_score for all validated keywords in a session.

        Returns: {scored, score_range, score_distribution}
        """
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT id, keyword, ai_relevance, intent, buyer_readiness, source "
                "FROM kw2_validated_keywords WHERE session_id=?",
                (session_id,),
            ).fetchall()

            if not rows:
                return {"scored": 0, "score_range": {"min": 0, "max": 0, "avg": 0},
                        "score_distribution": {}}

            # Load business context for context-aware scoring
            biz_intel = db.get_biz_intel(session_id) or {}
            ctx_terms = _extract_context_terms(biz_intel)
            w = HYBRID_SCORE_WEIGHTS  # rule=0.40, context=0.35, data=0.25

            scores = []
            updates = []
            for row in rows:
                kw = row["keyword"].lower()
                ai_rel = row["ai_relevance"] or 0.0
                intent = row["intent"] or "unknown"
                readiness = row["buyer_readiness"] or 0.0
                source = row["source"] or ""

                # ── Signal 1: Rule Score (0-100) ──
                rule_pts = 0.0
                for token, pts in RULE_SCORE_INTENT.items():
                    if token in kw:
                        rule_pts += pts
                for token, pts in RULE_SCORE_MODIFIER_PREMIUM.items():
                    if token in kw:
                        rule_pts += pts
                for token, pts in RULE_SCORE_MODIFIER_GENERIC.items():
                    if token in kw:
                        rule_pts += pts
                commercial = self._commercial_score(kw)
                rule_pts += commercial * 30  # commercial boost contributes up to 30pts
                rule_score = min(rule_pts, 100.0)

                # ── Signal 2: Context Score (0-100) ──
                ctx_pts = 0.0
                # Product alignment: does keyword mention a known product?
                for prod in ctx_terms["products"]:
                    if prod and prod in kw:
                        ctx_pts += 25
                        break
                # Audience alignment
                for seg in ctx_terms["audience"]:
                    if seg and seg in kw:
                        ctx_pts += 20
                        break
                # Geo alignment
                for geo in ctx_terms["geo"]:
                    if geo and geo in kw:
                        ctx_pts += 20
                        break
                # Attribute alignment (quality markers, grades)
                for attr in ctx_terms["attributes"]:
                    if attr and attr in kw:
                        ctx_pts += 15
                        break
                # Intent boost from BI knowledge
                intent_weight = INTENT_WEIGHTS.get(intent, 0.3)
                ctx_pts += intent_weight * 20  # up to ~18pts for transactional
                context_score = min(ctx_pts, 100.0)

                # ── Signal 3: Data Score (0-100) ──
                volume_signal = SOURCE_VOLUME.get(source, 0.35)
                data_score = min(
                    (ai_rel * 40)           # AI relevance: up to 40pts
                    + (volume_signal * 30)   # Source proxy: up to 21pts
                    + (readiness * 30),      # Buyer readiness: up to 30pts
                    100.0,
                )

                # ── Signal 4: Naturalness / quality factor (0.75–1.0 multiplier) ──
                # Penalises keywords that are unnatural constructions or unlikely to
                # appear in real search results. This multiplier squeezes the score
                # range so each keyword's unique signals differentiate better.
                words = kw.split()
                wc = len(words)
                nat = 1.0
                # Word count sweet spot: 3–6 words best for long-tail transactional
                if wc < 2:
                    nat -= 0.20     # single-word: too broad
                elif wc == 2:
                    nat -= 0.05     # short, generic
                elif wc > 8:
                    nat -= 0.10     # very long: may be unnatural concatenation
                # Unnatural role-term as lead modifier (e.g. "buy supplier cardamom")
                _ROLE_TERMS = {"supplier", "manufacturer", "exporter", "distributor",
                               "wholesaler", "retailer", "dealer", "vendor"}
                if wc >= 3 and words[0] in ("buy", "order", "get") and words[1] in _ROLE_TERMS:
                    nat -= 0.15     # "buy supplier X" is unnatural (role word in wrong slot)
                # Duplicate intent tokens (e.g. "buy cheap bulk wholesale price") - stacking signals
                intent_tokens = {"buy", "order", "wholesale", "bulk", "cheap", "cheapest", "price"}
                intent_count = sum(1 for w in words if w in intent_tokens)
                if intent_count > 3:
                    nat -= 0.08 * (intent_count - 3)   # each extra stacked signal hurts naturalness

                # Apply multiplier capped to [0.75, 1.0]
                nat = max(0.75, min(1.0, nat))

                # ── Weighted combination with naturalness ──
                final = round(
                    (
                        (rule_score * w["rule"])
                        + (context_score * w["context"])
                        + (data_score * w["data"])
                    ) * nat,
                    2,
                )

                scores.append(final)
                updates.append((final, commercial, row["id"]))

            conn.executemany(
                "UPDATE kw2_validated_keywords SET final_score=?, commercial_score=? WHERE id=?",
                updates,
            )
            conn.commit()

            db.update_session(session_id, phase4_done=1)

            # Build score distribution for frontend chart
            dist = {}
            for s in scores:
                bucket = int(s // 10) * 10
                label = f"{bucket}-{bucket + 10}"
                dist[label] = dist.get(label, 0) + 1

            return {
                "scored": len(scores),
                "score_range": {
                    "min": round(min(scores), 2),
                    "max": round(max(scores), 2),
                    "avg": round(sum(scores) / len(scores), 2),
                },
                "score_distribution": dist,
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
