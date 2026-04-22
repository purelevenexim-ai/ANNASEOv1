"""
GSC Phase 2 — Insight Engine
Generates actionable SEO insights from processed data.

Insight types:
  - quick_wins:    high impressions + poor rank (position 5-20)
  - money_keywords: transactional/purchase + high impressions
  - content_gaps:  clusters that exist but lack purchase-intent keywords
  - weak_pillars:  pillars with low authority scores
  - linking:       internal linking suggestions (supporting → purchase)
"""
import logging
from collections import defaultdict

from . import gsc_db

log = logging.getLogger(__name__)


def generate_insights(project_id: str) -> dict:
    """
    Generate all insight types from processed data.
    Stores each type in gsc_insights table.

    Returns: {quick_wins: N, money_keywords: N, content_gaps: N, ...}
    """
    processed = gsc_db.get_processed_keywords(project_id)
    if not processed:
        return {}

    clusters = gsc_db.get_clusters(project_id)

    result = {}

    # 1. Quick Wins — high impressions, rank 5-20 (easy to improve)
    quick_wins = []
    for kw in processed:
        pos = kw.get("position", 0)
        imp = kw.get("impressions", 0)
        if 5 <= pos <= 20 and imp >= 100:
            quick_wins.append({
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar"),
                "position": round(pos, 1),
                "impressions": imp,
                "score": kw.get("score", 0),
                "intent": kw.get("intent"),
                "potential": round(imp * (1 / max(pos, 1)), 1),
            })
    quick_wins.sort(key=lambda x: x["potential"], reverse=True)
    quick_wins = quick_wins[:50]
    gsc_db.save_insights(project_id, "quick_wins", {"items": quick_wins})
    result["quick_wins"] = len(quick_wins)

    # 2. Money Keywords — purchase/wholesale + high impressions
    money_kws = []
    for kw in processed:
        if kw.get("intent") in ("purchase", "wholesale") and kw.get("impressions", 0) >= 50:
            money_kws.append({
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar"),
                "intent": kw["intent"],
                "impressions": kw.get("impressions", 0),
                "clicks": kw.get("clicks", 0),
                "position": round(kw.get("position", 0), 1),
                "score": kw.get("score", 0),
            })
    money_kws.sort(key=lambda x: x["score"], reverse=True)
    money_kws = money_kws[:50]
    gsc_db.save_insights(project_id, "money_keywords", {"items": money_kws})
    result["money_keywords"] = len(money_kws)

    # 3. Content Gaps — clusters with only informational keywords (no purchase)
    gaps = []
    for cname, ckws in clusters.items():
        intents = set()
        for ckw in ckws:
            # Look up intent from processed
            for p in processed:
                if p["keyword"] == ckw["keyword"]:
                    intents.add(p.get("intent", ""))
                    break
        has_purchase = bool(intents & {"purchase", "wholesale", "commercial"})
        if not has_purchase and len(ckws) >= 3:
            gaps.append({
                "cluster": cname,
                "keyword_count": len(ckws),
                "sample_keywords": [k["keyword"] for k in ckws[:5]],
                "suggestion": f"Add transactional content targeting '{cname}' buyers",
            })
    gsc_db.save_insights(project_id, "content_gaps", {"items": gaps})
    result["content_gaps"] = len(gaps)

    # 4. Internal Linking Suggestions — supporting → purchase within same pillar
    links = []
    per_pillar: dict[str, dict[str, list]] = defaultdict(lambda: {"supporting": [], "purchase": []})
    for kw in processed:
        pil = kw.get("pillar")
        intent = kw.get("intent", "")
        if not pil:
            continue
        if intent in ("purchase", "wholesale"):
            per_pillar[pil]["purchase"].append(kw)
        elif intent in ("informational", "commercial"):
            per_pillar[pil]["supporting"].append(kw)

    for pil, groups in per_pillar.items():
        for supp in groups["supporting"][:10]:  # top 10 supporting
            for purch in groups["purchase"][:5]:  # top 5 purchase
                links.append({
                    "from_keyword": supp["keyword"],
                    "to_keyword": purch["keyword"],
                    "pillar": pil,
                    "reason": "supporting_to_purchase",
                    "from_impressions": supp.get("impressions", 0),
                    "to_impressions": purch.get("impressions", 0),
                })

    links.sort(key=lambda x: x["from_impressions"], reverse=True)
    links = links[:100]
    gsc_db.save_insights(project_id, "linking", {"items": links})
    result["linking_suggestions"] = len(links)

    # 5. Opportunity keywords — high impressions, very poor rank (20+)
    opportunities = []
    for kw in processed:
        pos = kw.get("position", 0)
        imp = kw.get("impressions", 0)
        if pos > 20 and imp >= 200:
            opportunities.append({
                "keyword": kw["keyword"],
                "pillar": kw.get("pillar"),
                "position": round(pos, 1),
                "impressions": imp,
                "intent": kw.get("intent"),
                "gap_score": round(imp * (pos / 100), 1),
            })
    opportunities.sort(key=lambda x: x["gap_score"], reverse=True)
    opportunities = opportunities[:30]
    gsc_db.save_insights(project_id, "opportunities", {"items": opportunities})
    result["opportunities"] = len(opportunities)

    log.info(f"[GSC Insights] Generated: {result}")
    return result
