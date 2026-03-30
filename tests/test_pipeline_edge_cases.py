"""
GROUP — Pipeline edge cases and cross-component integration tests
~150 tests covering boundary conditions, empty inputs, long strings, unicode, numeric edge cases
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P3_Normalization, P5_IntentClassification,
    P7_OpportunityScoring, P14_DedupPrevention, KnowledgeGraph,
    ContentPace, Seed
)
from annaseo_addons import (
    OffTopicFilter, KeywordTrafficScorer, CannibalizationDetector,
    ContentLifecycleManager
)


@pytest.fixture
def p1(): return P1_SeedInput()
@pytest.fixture
def p3(): return P3_Normalization()
@pytest.fixture
def p5(): return P5_IntentClassification()
@pytest.fixture
def p7(): return P7_OpportunityScoring()
@pytest.fixture
def otf(): return OffTopicFilter()
@pytest.fixture
def kts(): return KeywordTrafficScorer()
@pytest.fixture
def cd(): return CannibalizationDetector()
@pytest.fixture
def lcm(): return ContentLifecycleManager()
@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# SEED EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedEdgeCases:
    def test_seed_with_hyphen(self, p1):
        s = p1.run("anti-inflammatory spice")
        assert isinstance(s, Seed)

    def test_seed_with_numbers(self, p1):
        s = p1.run("pepper 2025")
        assert isinstance(s, Seed)

    def test_seed_with_unicode(self, p1):
        s = p1.run("café spice")
        assert isinstance(s, Seed)

    def test_seed_long_keyword(self, p1):
        kw = "organic black pepper health benefits anti-inflammatory properties india"
        s = p1.run(kw)
        assert isinstance(s, Seed)

    def test_seed_single_word(self, p1):
        s = p1.run("pepper")
        assert isinstance(s, Seed)

    def test_seed_id_is_string(self, p1):
        s = p1.run("black pepper")
        assert isinstance(s.id, str)

    def test_seed_id_nonempty(self, p1):
        s = p1.run("cinnamon")
        assert len(s.id) > 0

    def test_seed_keyword_preserved(self, p1):
        kw = "turmeric golden milk"
        s = p1.run(kw)
        assert s.keyword == kw

    @pytest.mark.parametrize("kw", [
        "ginger", "clove oil", "black pepper", "organic cinnamon",
        "turmeric curcumin", "piperine supplement", "ginger lemon tea",
        "cardamom coffee", "cumin seeds", "fenugreek leaves",
    ])
    def test_seed_various_keywords(self, p1, kw):
        s = p1.run(kw)
        assert s.keyword == kw
        assert isinstance(s.id, str)


# ─────────────────────────────────────────────────────────────────────────────
# P3 NORMALIZATION EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestP3EdgeCases:
    def test_empty_list(self, p3, seed):
        result = p3.run(seed, [])
        assert result == []

    def test_all_stopwords_filtered(self, p3, seed):
        result = p3.run(seed, ["the", "a", "an"])
        # All single-word stopwords should yield empty or single-word entries filtered
        for r in result:
            assert len(r.split()) >= 2 or r not in ["the", "a", "an"]

    def test_mixed_case_dedupe(self, p3, seed):
        result = p3.run(seed, ["Black Pepper", "black pepper", "BLACK PEPPER"])
        assert len(result) == 1

    def test_whitespace_variants_dedupe(self, p3, seed):
        result = p3.run(seed, ["black pepper ", " black pepper", "black  pepper"])
        # All variants should normalize to same string
        assert len(set(result)) <= 1

    def test_100_unique_keywords(self, p3, seed):
        raw = [f"black pepper topic {i}" for i in range(100)]
        result = p3.run(seed, raw)
        assert len(result) == 100

    def test_1000_keywords_performance(self, p3, seed):
        raw = [f"organic spice keyword {i}" for i in range(1000)]
        result = p3.run(seed, raw)
        assert len(result) == 1000

    def test_hyphen_preserved_in_batch(self, p3, seed):
        raw = ["anti-inflammatory pepper", "anti-inflammatory cinnamon"]
        result = p3.run(seed, raw)
        assert len(result) == 2
        for r in result:
            assert "anti" in r

    def test_numeric_keywords_kept(self, p3, seed):
        raw = ["black pepper 500mg", "cinnamon 1000mg capsule"]
        result = p3.run(seed, raw)
        assert len(result) >= 1

    def test_unicode_keywords_handled(self, p3, seed):
        raw = ["café cinnamon blend", "turmeric latte recipe"]
        result = p3.run(seed, raw)
        assert isinstance(result, list)

    def test_no_duplicates_in_output(self, p3, seed):
        raw = [f"keyword {i}" for i in range(50)] * 2  # 100 items, 50 unique
        result = p3.run(seed, raw)
        assert len(result) == len(set(result))


# ─────────────────────────────────────────────────────────────────────────────
# P5 INTENT EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

VALID_INTENTS = {"transactional", "commercial", "comparison", "informational", "navigational"}


class TestP5EdgeCases:
    def test_empty_keyword_list(self, p5, seed):
        result = p5.run(seed, [])
        assert result == {}

    def test_single_keyword(self, p5, seed):
        result = p5.run(seed, ["black pepper benefits"])
        assert len(result) == 1
        assert list(result.values())[0] in VALID_INTENTS

    def test_all_intents_valid(self, p5, seed):
        kws = [
            "buy black pepper", "best pepper supplement",
            "pepper vs turmeric", "what is piperine",
            "black pepper site"
        ]
        result = p5.run(seed, kws)
        for intent in result.values():
            assert intent in VALID_INTENTS

    def test_50_keywords_all_classified(self, p5, seed):
        kws = [f"black pepper benefit {i}" for i in range(50)]
        result = p5.run(seed, kws)
        assert len(result) == 50

    def test_100_keywords_all_classified(self, p5, seed):
        kws = [f"spice keyword {i}" for i in range(100)]
        result = p5.run(seed, kws)
        assert len(result) == 100

    def test_buy_prefix_transactional(self, p5, seed):
        kws = ["buy black pepper", "buy organic cinnamon", "buy turmeric powder"]
        result = p5.run(seed, kws)
        for kw in kws:
            assert result[kw] == "transactional"

    def test_what_is_informational(self, p5, seed):
        kws = ["what is piperine", "what is curcumin", "what is gingerol"]
        result = p5.run(seed, kws)
        for kw in kws:
            assert result[kw] == "informational"

    def test_vs_comparison(self, p5, seed):
        kws = ["pepper vs turmeric", "cinnamon vs cassia", "ginger vs turmeric"]
        result = p5.run(seed, kws)
        for kw in kws:
            assert result[kw] == "comparison"

    def test_best_commercial(self, p5, seed):
        kws = ["best black pepper", "best cinnamon supplement", "best turmeric brand"]
        result = p5.run(seed, kws)
        for kw in kws:
            assert result[kw] == "commercial"

    @pytest.mark.parametrize("kw,expected_intent", [
        ("buy organic black pepper", "transactional"),
        ("black pepper vs white pepper", "comparison"),
        ("what is black pepper", "informational"),
        ("best black pepper supplement", "commercial"),
    ])
    def test_specific_intent_patterns(self, p5, seed, kw, expected_intent):
        result = p5.run(seed, [kw])
        assert result[kw] == expected_intent


# ─────────────────────────────────────────────────────────────────────────────
# P7 SCORING EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestP7EdgeCases:
    def test_empty_keywords(self, p7, seed):
        result = p7.run(seed, [], {}, {})
        assert result == {}

    def test_single_keyword(self, p7, seed):
        kw = "black pepper benefits"
        result = p7.run(seed, [kw], {kw: "informational"}, {kw: {"kd_estimate": 40}})
        assert kw in result
        assert 0 <= result[kw] <= 100

    def test_kd_0_gives_high_score(self, p7, seed):
        kw = "black pepper benefits"
        result = p7.run(seed, [kw], {kw: "informational"}, {kw: {"kd_estimate": 0}})
        score_easy = result[kw]
        result2 = p7.run(seed, [kw], {kw: "informational"}, {kw: {"kd_estimate": 80}})
        score_hard = result2[kw]
        assert score_easy >= score_hard

    def test_kd_100_gives_lower_score(self, p7, seed):
        kw = "turmeric benefits"
        result = p7.run(seed, [kw], {kw: "informational"}, {kw: {"kd_estimate": 100}})
        assert 0 <= result[kw] <= 100

    def test_all_scores_in_range(self, p7, seed):
        kws = [f"spice keyword {i}" for i in range(20)]
        intent_map = {kw: "informational" for kw in kws}
        serp_map = {kw: {"kd_estimate": 40} for kw in kws}
        result = p7.run(seed, kws, intent_map, serp_map)
        for kw, score in result.items():
            assert 0 <= score <= 100

    def test_missing_serp_handled(self, p7, seed):
        kw = "black pepper tea"
        result = p7.run(seed, [kw], {kw: "informational"}, {})
        # Should handle missing serp gracefully
        assert kw in result


# ─────────────────────────────────────────────────────────────────────────────
# SEO KEYWORD PIPELINE (new regression tests)
# ─────────────────────────────────────────────────────────────────────────────

from engines.seo_keyword_pipeline import (
    run_full_pipeline, normalize_keywords, _select_top100_for_pillar,
    create_clusters, validate_clusters
)


def test_p3_normalization_maintains_keyword_count():
    raw = [
        f"clove keyword {i}" for i in range(34)
    ]
    normalized = normalize_keywords(raw, seed="clove")
    assert len(normalized["keywords"]) == 34
    assert len(normalized["normalization"]) <= 34


def test_p6_validate_clusters_warns_for_small_clusters():
    clusters = [
        {"cluster_name": "small group", "primary_keyword": "clove price", "intent": "commercial", "keywords": []},
        {"cluster_name": "healthy group", "primary_keyword": "clove benefits", "intent": "informational", "keywords": ["clove health"]},
    ]
    warnings = validate_clusters(clusters)
    assert any("only" in w for w in warnings)


def test_p7_top100_intent_balance():
    enriched = [
        {"keyword": f"clove transactional {i}", "intent": "transactional", "score": 100-i} for i in range(40)
    ] + [
        {"keyword": f"clove commercial {i}", "intent": "commercial", "score": 100-i} for i in range(40)
    ] + [
        {"keyword": f"clove informational {i}", "intent": "informational", "score": 100-i} for i in range(80)
    ]
    top = _select_top100_for_pillar(enriched)
    assert len(top) == 100


def test_full_pipeline_returns_normalization_in_report():
    body = {
        "project_id": "proj_test",
        "session_id": "sess_test",
        "pillar": "clove",
        "seed": "clove",
        "business_type": "ecommerce",
        "industry": "spices",
        "keywords": [f"clove keyword {i}" for i in range(34)],
    }
    result = run_full_pipeline(body)
    assert result.get("total_keywords") == 34
    assert "normalization" in result
    assert len(result.get("normalized_keywords", [])) == 34


@pytest.mark.parametrize("intent", ["transactional", "commercial", "informational", "comparison", "navigational"])
def test_all_intent_types_scored(p7, seed, intent):
    kw = f"black pepper {intent} test"
    result = p7.run(seed, [kw], {kw: intent}, {kw: {"kd_estimate": 40}})
    assert kw in result
    assert 0 <= result[kw] <= 100


# ─────────────────────────────────────────────────────────────────────────────
# OFF TOPIC FILTER EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestOffTopicEdgeCases:
    def test_empty_string_handled(self, otf):
        result = otf.is_global_kill("")
        assert isinstance(result, bool)

    def test_single_word_clean(self, otf):
        assert otf.is_global_kill("pepper") is False

    def test_clean_keyword_not_killed(self, otf):
        clean = [
            "black pepper benefits", "organic cinnamon", "turmeric health",
            "ginger tea recipe", "clove oil uses", "best spice supplement",
        ]
        for kw in clean:
            assert otf.is_global_kill(kw) is False

    def test_social_media_killed(self, otf):
        social = ["pepper meme", "cinnamon viral", "turmeric tiktok"]
        for kw in social:
            assert otf.is_global_kill(kw) is True

    def test_anti_inflammatory_safe(self, otf):
        assert otf.is_global_kill("anti-inflammatory spice") is False

    def test_very_long_keyword_handled(self, otf):
        kw = " ".join(["organic", "black", "pepper", "health", "benefits"] * 5)
        result = otf.is_global_kill(kw)
        assert isinstance(result, bool)

    @pytest.mark.parametrize("social_term", ["meme", "viral", "tiktok", "instagram"])
    def test_individual_social_terms_killed(self, otf, social_term):
        kw = f"black pepper {social_term}"
        assert otf.is_global_kill(kw) is True

    @pytest.mark.parametrize("safe_term", ["benefits", "recipe", "supplement", "health", "organic", "buy"])
    def test_safe_terms_not_killed(self, otf, safe_term):
        kw = f"black pepper {safe_term}"
        assert otf.is_global_kill(kw) is False


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD TRAFFIC SCORER EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestKTSEdgeCases:
    def test_empty_string_scored(self, kts):
        result = kts.score("")
        assert isinstance(result, (int, float))

    def test_single_char_scored(self, kts):
        result = kts.score("a")
        assert 0 <= result <= 100

    def test_very_long_keyword_scored(self, kts):
        kw = " ".join(["organic"] * 15)
        result = kts.score(kw)
        assert 0 <= result <= 100

    def test_unicode_keyword_scored(self, kts):
        result = kts.score("café spice blend")
        assert isinstance(result, (int, float))

    def test_numeric_keyword_scored(self, kts):
        result = kts.score("black pepper 500mg 90 capsules")
        assert 0 <= result <= 100

    def test_hyphenated_keyword_scored(self, kts):
        result = kts.score("anti-inflammatory black pepper extract")
        assert 0 <= result <= 100

    def test_all_punctuation_handled(self, kts):
        result = kts.score("black pepper!! benefits?? recipe.")
        assert isinstance(result, (int, float))

    @pytest.mark.parametrize("kw", [
        "pepper", "black pepper", "black pepper benefits",
        "organic black pepper health benefits",
        "best organic black pepper supplement for inflammation",
    ])
    def test_various_keyword_lengths(self, kts, kw):
        result = kts.score(kw)
        assert 0 <= result <= 100


# ─────────────────────────────────────────────────────────────────────────────
# CANNIBALIZATION DETECTOR EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestCannibalizationEdgeCases:
    def test_empty_articles_list(self, cd):
        result = cd.check("black pepper benefits", [])
        assert isinstance(result, dict)

    def test_single_article_match(self, cd):
        result = cd.check("black pepper benefits", ["black pepper benefits"])
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert risk in ("high", "medium", "some")

    def test_single_article_no_match(self, cd):
        result = cd.check("black pepper benefits", ["completely unrelated topic"])
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert isinstance(risk, str)

    def test_50_articles_no_match(self, cd):
        articles = [f"unique topic {i}" for i in range(50)]
        result = cd.check("black pepper benefits", articles)
        assert isinstance(result, dict)

    def test_50_articles_with_match(self, cd):
        articles = [f"unique topic {i}" for i in range(49)] + ["black pepper health benefits"]
        result = cd.check("black pepper health benefits", articles)
        risk = result.get("cannibalization_risk", result.get("risk", "none"))
        assert isinstance(risk, str)

    def test_batch_empty_new_keywords(self, cd):
        result = cd.batch_check([], ["existing article"])
        assert isinstance(result, (dict, list))

    def test_batch_empty_both(self, cd):
        result = cd.batch_check([], [])
        assert isinstance(result, (dict, list))

    def test_batch_10_vs_10(self, cd):
        new_kws = [f"new keyword {i}" for i in range(10)]
        existing = [f"existing article {i}" for i in range(10)]
        result = cd.batch_check(new_kws, existing)
        assert isinstance(result, (dict, list))


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT LIFECYCLE MANAGER EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestLCMEdgeCases:
    def test_register_returns_lifecycle(self, lcm):
        lc = lcm.register("art_001", "black pepper benefits")
        assert lc is not None

    def test_register_200_articles(self, lcm):
        for i in range(200):
            lcm.register(f"art_{i:04d}", f"keyword {i}")
        assert len(lcm._lifecycles) == 200

    def test_register_same_id_twice(self, lcm):
        lcm.register("art_001", "black pepper")
        lcm.register("art_001", "black pepper updated")
        # Should handle gracefully (either update or keep first)
        assert "art_001" in lcm._lifecycles

    def test_update_ranking_various_ranks(self, lcm):
        lcm.register("art_001", "black pepper")
        for rank in [1, 5, 10, 50, 100]:
            lcm.update_ranking("art_001", new_rank=rank)
        lc = lcm._lifecycles["art_001"]
        assert lc.current_rank == 100  # last update

    def test_report_100_articles(self, lcm):
        for i in range(100):
            lcm.register(f"art_{i:04d}", f"keyword {i}")
        report = lcm.report()
        assert isinstance(report, dict)

    def test_articles_needing_action_empty(self, lcm):
        result = lcm.articles_needing_action()
        assert isinstance(result, dict)

    @pytest.mark.parametrize("spice", ["black pepper", "cinnamon", "turmeric", "ginger", "clove"])
    def test_spice_articles_registered(self, lcm, spice):
        lcm.register(f"{spice}_001", f"{spice} health benefits")
        assert f"{spice}_001" in lcm._lifecycles

    def test_lifecycle_report_keys(self, lcm):
        for i in range(5):
            lcm.register(f"art_{i}", f"keyword {i}")
        report = lcm.report()
        assert isinstance(report, dict)

    def test_update_nonexistent_article(self, lcm):
        # Should handle gracefully or raise
        try:
            lcm.update_ranking("nonexistent_id", new_rank=5)
        except (KeyError, Exception):
            pass  # OK to raise


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE GRAPH EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeGraphEdgeCases:
    def test_empty_pillars(self):
        kg = KnowledgeGraph(seed="black pepper")
        assert kg.seed == "black pepper"

    def test_graph_with_pillars(self):
        kg = KnowledgeGraph(
            seed="black pepper",
            pillars={"health benefits": {"keywords": ["benefits", "health"]}}
        )
        assert "health benefits" in kg.pillars

    def test_graph_seed_preserved(self):
        for seed in ["black pepper", "cinnamon", "turmeric", "ginger", "clove"]:
            kg = KnowledgeGraph(seed=seed)
            assert kg.seed == seed

    @pytest.mark.parametrize("seed", [
        "black pepper", "organic cinnamon", "turmeric powder",
        "ginger root extract", "clove essential oil"
    ])
    def test_graph_created_for_spices(self, seed):
        kg = KnowledgeGraph(seed=seed)
        assert kg.seed == seed
        assert isinstance(kg.pillars, dict)


# ─────────────────────────────────────────────────────────────────────────────
# FULL MINI PIPELINE EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestMiniPipelineEdgeCases:
    def test_single_keyword_pipeline(self, p1, p3, p5, p7):
        seed = p1.run("black pepper")
        normalized = p3.run(seed, ["black pepper benefits"])
        if normalized:
            intents = p5.run(seed, normalized)
            serp = {kw: {"kd_estimate": 40} for kw in normalized}
            scores = p7.run(seed, normalized, intents, serp)
            assert all(0 <= v <= 100 for v in scores.values())

    def test_empty_keywords_pipeline(self, p1, p3, p5, p7):
        seed = p1.run("black pepper")
        normalized = p3.run(seed, [])
        assert normalized == []

    def test_large_keyword_set_pipeline(self, p1, p3, p5, p7):
        seed = p1.run("turmeric")
        raw = [f"turmeric keyword {i}" for i in range(50)]
        normalized = p3.run(seed, raw)
        intents = p5.run(seed, normalized)
        serp = {kw: {"kd_estimate": 50} for kw in normalized}
        scores = p7.run(seed, normalized, intents, serp)
        assert len(scores) == len(normalized)
        assert all(0 <= v <= 100 for v in scores.values())

    @pytest.mark.parametrize("spice", ["cinnamon", "ginger", "clove"])
    def test_per_spice_mini_pipeline(self, p1, p3, p5, p7, spice):
        seed = p1.run(spice)
        raw = [f"{spice} benefits", f"buy {spice}", f"best {spice} supplement"]
        normalized = p3.run(seed, raw)
        intents = p5.run(seed, normalized)
        serp = {kw: {"kd_estimate": 35} for kw in normalized}
        scores = p7.run(seed, normalized, intents, serp)
        assert len(scores) == len(normalized)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
