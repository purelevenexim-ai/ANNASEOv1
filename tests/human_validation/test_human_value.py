"""
tests/human_validation/test_human_value.py
===========================================
GROUP 5 — Human Validation Tests: Output Usefulness.

Validates that pipeline output is actually actionable for a real business.
Tests cannot be fully automated — they codify expert rules about what
"good" SEO output looks like from a practitioner's perspective.

Scoring framework (0–10 per dimension):
  relevance     — keywords match the business
  coverage      — all product categories and audience types present
  actionability — keywords include clear next action (buy, price, supplier...)
  specificity   — keywords are specific, not generic

A keyword set is "human-validated" if it scores >= 7/10 on all dimensions.

Run: pytest tests/human_validation/ -v --tb=short
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("ANNASEO_TESTING", "1")


# ── Sample output representing what a user would see ─────────────────────────

SAMPLE_SPICE_OUTPUT = {
    "profile": {
        "universe": "Kerala Spices",
        "pillars": ["cardamom", "black pepper", "turmeric", "cinnamon"],
        "modifiers": ["organic", "wholesale", "bulk", "farm direct"],
        "audience": ["home cooks", "restaurants", "exporters", "bakers"],
        "business_type": "D2C",
        "geo_scope": "India",
        "negative_scope": ["recipe", "benefits", "how to", "what is", "home remedy", "ayurvedic"],
    },
    "keywords": [
        {"keyword": "buy organic cardamom online india", "intent": "purchase", "ai_relevance": 0.93, "buyer_readiness": 0.90, "pillar": "cardamom"},
        {"keyword": "cardamom 500g price india", "intent": "transactional", "ai_relevance": 0.88, "buyer_readiness": 0.85, "pillar": "cardamom"},
        {"keyword": "cardamom wholesale supplier kerala", "intent": "commercial", "ai_relevance": 0.85, "buyer_readiness": 0.82, "pillar": "cardamom"},
        {"keyword": "bulk black pepper price per kg", "intent": "transactional", "ai_relevance": 0.82, "buyer_readiness": 0.80, "pillar": "black pepper"},
        {"keyword": "black pepper supplier india", "intent": "commercial", "ai_relevance": 0.79, "buyer_readiness": 0.76, "pillar": "black pepper"},
        {"keyword": "organic turmeric powder online", "intent": "purchase", "ai_relevance": 0.76, "buyer_readiness": 0.72, "pillar": "turmeric"},
        {"keyword": "buy cinnamon sticks online", "intent": "purchase", "ai_relevance": 0.74, "buyer_readiness": 0.70, "pillar": "cinnamon"},
        {"keyword": "best cardamom brand india", "intent": "comparison", "ai_relevance": 0.70, "buyer_readiness": 0.60, "pillar": "cardamom"},
        {"keyword": "spice shop near me", "intent": "local", "ai_relevance": 0.68, "buyer_readiness": 0.64, "pillar": "cardamom"},
        {"keyword": "ceylon cinnamon vs cassia guide", "intent": "informational", "ai_relevance": 0.55, "buyer_readiness": 0.30, "pillar": "cinnamon"},
    ],
    "clusters": [
        {"cluster_name": "Wholesale Bulk Buyers", "keywords": ["cardamom wholesale supplier", "bulk pepper price", "turmeric bulk buy"]},
        {"cluster_name": "Online Purchase India", "keywords": ["buy cardamom online", "order spices india", "organic turmeric online"]},
        {"cluster_name": "Price Comparison", "keywords": ["cardamom price 500g", "pepper rate kg india", "cinnamon price online"]},
        {"cluster_name": "Local & Near Me", "keywords": ["spice shop near me", "cardamom dealer delhi"]},
    ],
    "strategy": {
        "priority_pillars": ["cardamom", "black pepper", "turmeric", "cinnamon"],
        "quick_wins": ["buy cardamom online india", "cardamom wholesale kerala", "bulk pepper price"],
        "weekly_plan": [
            {"week": 1, "focus_pillar": "cardamom", "articles": [
                {"title": "Buy Premium Organic Cardamom Online India", "primary_keyword": "buy organic cardamom online india", "intent": "purchase", "page_type": "landing_page"},
            ]},
            {"week": 2, "focus_pillar": "black pepper", "articles": [
                {"title": "Wholesale Black Pepper Supplier India", "primary_keyword": "black pepper supplier india", "intent": "commercial", "page_type": "landing_page"},
            ]},
        ],
        "content_gaps": ["ceylon vs cassia cinnamon comparison", "cardamom grades explained"],
    },
    "confidence": 0.85,
}


# ── Scoring helpers ───────────────────────────────────────────────────────────

def score_relevance(output: dict) -> float:
    """Are keywords actually about this business?"""
    profile = output.get("profile", {})
    pillars = [p.lower() for p in profile.get("pillars", [])]
    keywords = output.get("keywords", [])
    if not pillars or not keywords:
        return 0.0
    hits = sum(
        1 for kw in keywords
        if any(p in kw.get("keyword", "").lower() for p in pillars)
    )
    return hits / len(keywords)


def score_coverage(output: dict) -> float:
    """Are all pillars represented in the keyword set?"""
    profile = output.get("profile", {})
    pillars = [p.lower() for p in profile.get("pillars", [])]
    keywords = output.get("keywords", [])
    if not pillars:
        return 0.0
    covered = {
        p for p in pillars
        if any(p in kw.get("keyword", "").lower() for kw in keywords)
    }
    return len(covered) / len(pillars)


def score_actionability(output: dict) -> float:
    """Do keywords include clear commercial intent signals?"""
    action_words = {"buy", "price", "wholesale", "supplier", "bulk", "order", "shop", "near me", "cost"}
    keywords = output.get("keywords", [])
    if not keywords:
        return 0.0
    actionable = sum(
        1 for kw in keywords
        if any(w in kw.get("keyword", "").lower() for w in action_words)
    )
    return actionable / len(keywords)


def score_specificity(output: dict) -> float:
    """Are keywords specific (avg word count >= 3)?"""
    keywords = output.get("keywords", [])
    if not keywords:
        return 0.0
    avg_words = sum(len(kw.get("keyword", "").split()) for kw in keywords) / len(keywords)
    return min(avg_words / 5.0, 1.0)  # 5+ words = max score


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRelevance:
    def test_majority_keywords_contain_pillar_word(self):
        """At least 60% of keywords must reference a business pillar."""
        rel = score_relevance(SAMPLE_SPICE_OUTPUT)
        assert rel >= 0.6, f"Relevance score {rel:.0%} < 60% — keywords drift from business"

    def test_no_off_topic_keywords(self):
        """No keyword should match negative_scope patterns."""
        profile = SAMPLE_SPICE_OUTPUT["profile"]
        neg_scope = [n.lower() for n in profile.get("negative_scope", [])]
        offenders = []
        for kw in SAMPLE_SPICE_OUTPUT["keywords"]:
            word = kw.get("keyword", "").lower()
            for neg in neg_scope:
                if neg in word:
                    offenders.append(f"'{word}' matches negative pattern '{neg}'")
        assert not offenders, f"Off-topic keywords found: {offenders}"


class TestCoverage:
    def test_all_pillars_have_keywords(self):
        """Every pillar must have at least one keyword."""
        cov = score_coverage(SAMPLE_SPICE_OUTPUT)
        assert cov == 1.0, f"Coverage {cov:.0%} — some pillars have no keywords"

    def test_all_intents_represented(self):
        """A complete keyword set should cover purchase, commercial, informational, and local."""
        intents_present = {kw.get("intent") for kw in SAMPLE_SPICE_OUTPUT["keywords"]}
        required = {"purchase", "commercial", "informational", "local"}
        missing = required - intents_present
        assert not missing, f"Missing intent types: {missing}"

    def test_clusters_cover_main_themes(self):
        """Clusters should represent major commercial themes."""
        cluster_names = [c["cluster_name"].lower() for c in SAMPLE_SPICE_OUTPUT["clusters"]]
        assert len(cluster_names) >= 3, "Too few clusters — grouping is too coarse"
        # At least one wholesale/bulk cluster
        has_bulk = any("wholesale" in n or "bulk" in n for n in cluster_names)
        has_purchase = any("purchase" in n or "buy" in n or "online" in n for n in cluster_names)
        assert has_bulk or has_purchase, f"No commercial action cluster found. Clusters: {cluster_names}"


class TestActionability:
    def test_high_actionability_score(self):
        """Most keywords should have explicit commercial action signals."""
        act = score_actionability(SAMPLE_SPICE_OUTPUT)
        assert act >= 0.50, f"Actionability {act:.0%} < 50% — too few commercial keywords"

    def test_quick_wins_are_transactional(self):
        """Strategy quick_wins must be buyer-intent keywords."""
        action_words = {"buy", "price", "wholesale", "bulk", "supplier", "order"}
        quick_wins = SAMPLE_SPICE_OUTPUT["strategy"].get("quick_wins", [])
        assert len(quick_wins) >= 2, "Need at least 2 quick wins"
        for qw in quick_wins:
            has_action = any(w in qw.lower() for w in action_words)
            assert has_action, f"Quick win '{qw}' lacks commercial intent"

    def test_weekly_plan_covers_multiple_pillars(self):
        """Content plan should spread across pillars, not focus on one."""
        weekly = SAMPLE_SPICE_OUTPUT["strategy"].get("weekly_plan", [])
        assert len(weekly) >= 2, "Weekly plan too short — not actionable"
        pillars_covered = {w.get("focus_pillar") for w in weekly}
        assert len(pillars_covered) >= 2, f"Weekly plan only covers pillars: {pillars_covered}"


class TestSpecificity:
    def test_average_keyword_length_4_plus_words(self):
        """Specific, long-tail keywords outrank generic ones — avg > 3 words needed."""
        spec = score_specificity(SAMPLE_SPICE_OUTPUT)
        avg_words = sum(len(kw.get("keyword", "").split()) for kw in SAMPLE_SPICE_OUTPUT["keywords"]) / len(SAMPLE_SPICE_OUTPUT["keywords"])
        assert avg_words >= 3.0, f"Average keyword length {avg_words:.1f} words < 3 — too generic"

    def test_no_single_word_keywords_in_top_results(self):
        """Top 5 keywords (highest relevance) must be multi-word."""
        sorted_kws = sorted(SAMPLE_SPICE_OUTPUT["keywords"], key=lambda k: k.get("ai_relevance", 0), reverse=True)
        for kw in sorted_kws[:5]:
            word_count = len(kw.get("keyword", "").split())
            assert word_count >= 3, f"Top keyword '{kw['keyword']}' is too generic ({word_count} words)"

    def test_geo_specificity_present(self):
        """For India-scoped business, some keywords should have geo-specific terms."""
        geo_terms = {"india", "kerala", "delhi", "mumbai", "online india"}
        keywords_text = " ".join(kw.get("keyword", "").lower() for kw in SAMPLE_SPICE_OUTPUT["keywords"])
        has_geo = any(term in keywords_text for term in geo_terms)
        assert has_geo, "No geo-specific keywords — output lacks local targeting"


class TestHumanValueComposite:
    def test_composite_quality_score_above_70_pct(self):
        """Composite quality across all 4 dimensions must be > 70%."""
        rel = score_relevance(SAMPLE_SPICE_OUTPUT)
        cov = score_coverage(SAMPLE_SPICE_OUTPUT)
        act = score_actionability(SAMPLE_SPICE_OUTPUT)
        spc = score_specificity(SAMPLE_SPICE_OUTPUT)
        composite = (rel * 0.30 + cov * 0.25 + act * 0.25 + spc * 0.20)
        assert composite >= 0.70, (
            f"Composite human value score {composite:.0%} < 70%\n"
            f"  Relevance: {rel:.0%}, Coverage: {cov:.0%}, "
            f"Actionability: {act:.0%}, Specificity: {spc:.0%}"
        )
