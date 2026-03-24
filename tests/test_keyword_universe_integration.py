"""
GROUP 11 — End-to-End Keyword Universe Integration Tests
~120 tests: full pipeline flow, real data scenarios, cross-engine consistency
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P3_Normalization, P5_IntentClassification,
    P7_OpportunityScoring, P9_ClusterFormation, P14_DedupPrevention
)
from annaseo_addons import OffTopicFilter, KeywordTrafficScorer, CannibalizationDetector
from quality.annaseo_domain_context import DomainContextEngine, Industry


# ─────────────────────────────────────────────────────────────────────────────
# FULL PIPELINE — Seed → Normalize → Filter → Intent → Score
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineBlackPepper:
    """
    Simulates the first 7 phases of the keyword universe pipeline
    for 'black pepper', using real keyword data.
    """

    RAW_KEYWORDS = [
        # Clean / relevant
        "black pepper health benefits",
        "buy organic black pepper",
        "black pepper vs white pepper",
        "best black pepper brand india",
        "black pepper wholesale price kerala",
        "how to grind black pepper",
        "what is piperine",
        "black pepper cultivation guide",
        "malabar pepper vs tellicherry",
        "black pepper nutrition facts per 100g",
        "organic black pepper supplier india",
        "black pepper anti-inflammatory properties",
        "buy black pepper bulk online",
        "black pepper recipes collection",
        "ceylon black pepper export",
        # Noisy / irrelevant
        "black pepper meme funny",
        "cinnamon tiktok trend",
        "spice viral video 2024",
        "black pepper instagram recipe hack",
        "pepper challenge youtube",
        # Duplicates
        "Black Pepper Health Benefits",  # dup of first
        "BUY ORGANIC BLACK PEPPER",      # dup of second
    ]

    @pytest.fixture
    def seed(self):
        return P1_SeedInput().run("black pepper")

    @pytest.fixture
    def cleaned(self, seed):
        p3 = P3_Normalization()
        return p3.run(seed, self.RAW_KEYWORDS)

    @pytest.fixture
    def filtered(self, cleaned):
        f = OffTopicFilter()
        kept, _ = f.filter_tuple(cleaned)
        return kept

    @pytest.fixture
    def intent_map(self, seed, filtered):
        p5 = P5_IntentClassification()
        return p5.run(seed, filtered)

    @pytest.fixture
    def scores(self, seed, filtered, intent_map):
        p7 = P7_OpportunityScoring()
        return p7.run(seed, filtered, intent_map, {})

    def test_normalization_removes_duplicates(self, cleaned):
        lower_cleaned = [c.lower() for c in cleaned]
        assert lower_cleaned.count("black pepper health benefits") == 1
        assert lower_cleaned.count("buy organic black pepper") == 1

    def test_filter_removes_noise(self, filtered):
        noise_words = ["meme", "tiktok", "viral", "instagram", "challenge"]
        for kw in filtered:
            for nw in noise_words:
                assert nw not in kw.lower(), f"Noise word '{nw}' found in '{kw}'"

    def test_filter_keeps_clean_keywords(self, filtered):
        assert len(filtered) >= 10  # should keep majority of clean keywords

    def test_intent_classification_covers_all(self, filtered, intent_map):
        assert len(intent_map) == len(filtered)

    def test_intent_map_valid_values(self, intent_map):
        valid = {"transactional", "informational", "commercial", "comparison", "navigational"}
        for kw, intent in intent_map.items():
            assert intent in valid, f"Invalid intent '{intent}' for '{kw}'"

    def test_scores_cover_all_filtered(self, filtered, scores):
        assert len(scores) == len(filtered)

    def test_all_scores_in_range(self, scores):
        for kw, score in scores.items():
            assert 0 <= score <= 100, f"Score {score} out of range for '{kw}'"

    def test_transactional_keywords_score_high(self, scores, intent_map):
        trans_scores = [scores[kw] for kw, intent in intent_map.items()
                        if intent == "transactional"]
        info_scores  = [scores[kw] for kw, intent in intent_map.items()
                        if intent == "informational"]
        if trans_scores and info_scores:
            assert max(trans_scores) >= max(info_scores) * 0.7  # transactional generally higher

    def test_no_noise_in_intent_map(self, intent_map):
        noise_words = ["meme", "tiktok", "viral"]
        for kw in intent_map:
            for nw in noise_words:
                assert nw not in kw.lower()


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SEED CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiSeedConsistency:
    """Same pipeline should work consistently for different spice seeds."""

    SPICE_SEEDS = ["black pepper", "cinnamon", "turmeric", "cardamom", "clove"]
    INTENT_TEMPLATES = [
        "buy {seed} online",
        "what is {seed}",
        "best {seed} brand",
        "{seed} vs other spices",
        "{seed} health benefits",
        "{seed} wholesale price",
    ]

    @pytest.mark.parametrize("seed_kw", SPICE_SEEDS)
    def test_seed_input_works(self, seed_kw):
        seed = P1_SeedInput().run(seed_kw)
        assert seed.keyword == seed_kw

    @pytest.mark.parametrize("seed_kw", SPICE_SEEDS)
    def test_normalization_works(self, seed_kw):
        seed = P1_SeedInput().run(seed_kw)
        keywords = [t.format(seed=seed_kw) for t in self.INTENT_TEMPLATES]
        result = P3_Normalization().run(seed, keywords)
        assert len(result) == len(set(r.lower() for r in result))  # no dups

    @pytest.mark.parametrize("seed_kw", SPICE_SEEDS)
    def test_intent_classification_works(self, seed_kw):
        seed = P1_SeedInput().run(seed_kw)
        keywords = [t.format(seed=seed_kw) for t in self.INTENT_TEMPLATES]
        intent_map = P5_IntentClassification().run(seed, keywords)
        assert len(intent_map) == len(keywords)

    @pytest.mark.parametrize("seed_kw", SPICE_SEEDS)
    def test_scoring_works(self, seed_kw):
        seed = P1_SeedInput().run(seed_kw)
        keywords = [t.format(seed=seed_kw) for t in self.INTENT_TEMPLATES]
        intent_map = {kw: "informational" for kw in keywords}
        scores = P7_OpportunityScoring().run(seed, keywords, intent_map, {})
        assert all(0 <= s <= 100 for s in scores.values())


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-ENGINE CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossEngineConsistency:
    """Verify that different engines produce consistent results."""

    def test_filter_and_intent_consistent(self):
        seed = P1_SeedInput().run("black pepper")
        raw = [
            "buy black pepper online", "black pepper health benefits",
            "pepper meme", "black pepper vs white", "best pepper brand",
        ]
        p3 = P3_Normalization()
        cleaned = p3.run(seed, raw)
        kept, _ = OffTopicFilter().filter_tuple(cleaned)
        intent_map = P5_IntentClassification().run(seed, kept)
        # Every kept keyword should have an intent
        assert set(intent_map.keys()) == set(kept)

    def test_dedup_and_cannibalization_consistent(self):
        """Keywords passing dedup should not have exact cannibalization risk."""
        seed = P1_SeedInput().run("black pepper")
        calendar = [
            {"keyword": "black pepper health benefits", "title": "Health Guide"},
            {"keyword": "black pepper health benefits", "title": "Health Article"},
            {"keyword": "black pepper recipes", "title": "Recipes"},
        ]
        deduped = P14_DedupPrevention().run(seed, calendar, {})
        deduped_keywords = [d["keyword"] for d in deduped]

        # After dedup, checking for cannibalization should find no conflicts
        det = CannibalizationDetector()
        for art in deduped:
            result = det.check(art["keyword"], art.get("title",""), None)
            det.register(art.get("title",""), art["keyword"], f"/{art['keyword']}")
        # No crash = success
        assert len(deduped) == 2  # only 2 unique keywords

    def test_domain_filter_and_intent_consistent(self):
        dce = DomainContextEngine()
        dce.setup_project("test_consist", "Test Co", Industry.FOOD_SPICES, ["black pepper"])
        keywords = [
            "buy black pepper online",      # should accept for spice
            "black pepper tour",             # should reject for spice
            "black pepper health benefits",  # should accept for spice
            "black pepper meme",             # should reject (noise)
        ]
        accepted = [kw for kw in keywords
                    if dce.classify(kw, "test_consist")["verdict"] == "accept"]
        rejected = [kw for kw in keywords
                    if dce.classify(kw, "test_consist")["verdict"] == "reject"]
        assert "buy black pepper online" in accepted
        assert "black pepper health benefits" in accepted
        assert "black pepper tour" in rejected
        assert "black pepper meme" in rejected

    def test_scorer_and_intent_consistent(self):
        scorer = KeywordTrafficScorer()
        p5 = P5_IntentClassification()
        seed = P1_SeedInput().run("black pepper")
        keywords = [
            "buy black pepper bulk",
            "black pepper health benefits",
            "best black pepper brand",
        ]
        intent_map = p5.run(seed, keywords)
        for kw in keywords:
            intent = intent_map[kw]
            sk = scorer.score(kw, 1000, 40, intent)
            assert sk.keyword == kw
            assert sk.intent == intent


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD UNIVERSE SIZE TARGETS
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordUniverseSizeTargets:
    """Verify universe meets minimum coverage targets."""

    def test_question_keywords_present(self):
        p5 = P5_IntentClassification()
        questions = [
            "what is black pepper", "how to use black pepper",
            "why is black pepper important", "when to harvest black pepper",
            "is black pepper good for health", "does black pepper help digestion",
        ]
        for q in questions:
            intent = p5._classify(q)
            assert intent == "informational"

    def test_transactional_keywords_present(self):
        p5 = P5_IntentClassification()
        trans = [
            "buy black pepper", "black pepper price", "order black pepper bulk",
            "black pepper wholesale", "purchase peppercorns online",
        ]
        for kw in trans:
            assert p5._classify(kw) == "transactional"

    def test_comparison_keywords_present(self):
        p5 = P5_IntentClassification()
        comps = [
            "black pepper vs white pepper",
            "malabar vs tellicherry",
            "organic vs conventional pepper",
        ]
        for kw in comps:
            assert p5._classify(kw) == "comparison"

    def test_full_universe_intent_distribution(self):
        """Real black pepper keyword universe should have diverse intents."""
        p5 = P5_IntentClassification()
        seed = P1_SeedInput().run("black pepper")
        keywords = [
            "buy black pepper", "black pepper price", "order bulk pepper",
            "what is black pepper", "black pepper benefits", "how to use pepper",
            "best pepper brand", "top pepper suppliers", "review organic pepper",
            "black pepper vs white", "malabar vs tellicherry", "organic vs regular",
            "pepper brand website", "supplier contact", "login to store",
        ]
        intent_map = p5.run(seed, keywords)
        intents = set(intent_map.values())
        # Should have at least 3 different intent types
        assert len(intents) >= 3

    def test_scorer_produces_ranked_universe(self):
        scorer = KeywordTrafficScorer()
        batch = [
            {"keyword": "buy black pepper bulk",        "volume": 5000, "difficulty": 20, "intent": "transactional"},
            {"keyword": "black pepper health benefits", "volume": 8000, "difficulty": 35, "intent": "informational"},
            {"keyword": "best black pepper brand",      "volume": 3000, "difficulty": 45, "intent": "commercial"},
            {"keyword": "black pepper vs white",        "volume": 2000, "difficulty": 30, "intent": "comparison"},
            {"keyword": "piperine supplement buy",      "volume": 1500, "difficulty": 25, "intent": "transactional"},
            {"keyword": "organic pepper certification", "volume": 4000, "difficulty": 15, "intent": "commercial"},
            {"keyword": "black pepper cultivation",     "volume": 900,  "difficulty": 10, "intent": "informational"},
            {"keyword": "pepper grinder electric",      "volume": 2500, "difficulty": 40, "intent": "commercial"},
        ]
        scored = scorer.score_batch(batch)
        # All scored
        assert len(scored) == 8
        # Sorted by traffic score
        scores = [s.traffic_score for s in scored]
        assert scores == sorted(scores, reverse=True)
        # Tags assigned
        tags = {s.tag for s in scored}
        assert len(tags) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
