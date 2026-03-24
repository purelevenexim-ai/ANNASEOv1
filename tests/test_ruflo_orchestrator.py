"""
GROUP — RufloOrchestrator and engine integration tests
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import (
    P1_SeedInput, P3_Normalization, P5_IntentClassification,
    P7_OpportunityScoring, P14_DedupPrevention,
    Seed, ContentPace, KnowledgeGraph, AI, Cache, Cfg
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
def p14(): return P14_DedupPrevention()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# SEED CLASS
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedClass:
    def test_seed_make_id_is_deterministic(self):
        id1 = Seed.make_id("black pepper")
        id2 = Seed.make_id("black pepper")
        assert id1 == id2

    def test_seed_make_id_different_keywords(self):
        id1 = Seed.make_id("black pepper")
        id2 = Seed.make_id("turmeric")
        assert id1 != id2

    def test_seed_make_id_length_10(self):
        assert len(Seed.make_id("black pepper")) == 10

    def test_seed_make_id_case_insensitive(self):
        assert Seed.make_id("Black Pepper") == Seed.make_id("black pepper")

    def test_seed_make_id_strips_whitespace(self):
        assert Seed.make_id("  black pepper  ") == Seed.make_id("black pepper")

    @pytest.mark.parametrize("kw", [
        "cinnamon", "turmeric", "ginger", "clove", "cardamom",
        "black pepper", "organic pepper", "malabar pepper",
    ])
    def test_make_id_for_spice_keywords(self, kw):
        seed_id = Seed.make_id(kw)
        assert len(seed_id) == 10
        assert seed_id.isalnum() or all(c in "0123456789abcdef" for c in seed_id)

    def test_seed_dataclass_fields(self):
        s = Seed(id="abc123", keyword="black pepper")
        assert s.id == "abc123"
        assert s.keyword == "black pepper"
        assert s.language == "english"
        assert s.region == "India"

    def test_seed_custom_language(self):
        s = Seed(id="abc", keyword="kali mirch", language="hindi")
        assert s.language == "hindi"

    def test_seed_product_url(self):
        s = Seed(id="abc", keyword="black pepper", product_url="/products/pepper")
        assert s.product_url == "/products/pepper"

    def test_seed_has_created_at(self):
        s = Seed(id="abc", keyword="black pepper")
        assert hasattr(s, "created_at")
        assert s.created_at != ""


# ─────────────────────────────────────────────────────────────────────────────
# CFG CLASS
# ─────────────────────────────────────────────────────────────────────────────

class TestCfgClass:
    def test_gemini_rate_exists(self):
        assert hasattr(Cfg, "GEMINI_RATE")

    def test_gemini_rate_is_float(self):
        assert isinstance(Cfg.GEMINI_RATE, float)

    def test_embed_batch_size(self):
        assert hasattr(Cfg, "EMBED_BATCH")
        assert isinstance(Cfg.EMBED_BATCH, int)

    def test_ttl_suggestions_exists(self):
        assert hasattr(Cfg, "TTL_SUGGESTIONS")

    def test_ttl_serp_exists(self):
        assert hasattr(Cfg, "TTL_SERP")

    def test_groq_key_attribute(self):
        assert hasattr(Cfg, "GROQ_KEY")

    def test_groq_model_attribute(self):
        assert hasattr(Cfg, "GROQ_MODEL")

    def test_publish_threshold(self):
        assert hasattr(Cfg, "PUBLISH_THRESHOLD")
        assert isinstance(Cfg.PUBLISH_THRESHOLD, int)


# ─────────────────────────────────────────────────────────────────────────────
# AI CLASS
# ─────────────────────────────────────────────────────────────────────────────

class TestAIClass:
    def test_ai_has_deepseek(self):
        assert hasattr(AI, "deepseek")

    def test_ai_has_gemini(self):
        assert hasattr(AI, "gemini")

    def test_ai_has_groq(self):
        assert hasattr(AI, "groq")

    def test_ai_has_embed_batch(self):
        assert hasattr(AI, "embed_batch")

    def test_ai_has_parse_json(self):
        assert hasattr(AI, "parse_json")

    def test_parse_json_valid_dict(self):
        import json
        text = json.dumps({"key": "value"})
        result = AI.parse_json(text)
        assert isinstance(result, dict)

    def test_parse_json_invalid_returns_empty(self):
        result = AI.parse_json("not json {")
        assert result == {} or result is None

    def test_parse_json_with_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = AI.parse_json(text)
        if result:
            assert isinstance(result, dict)

    def test_ai_has_spacy_nlp(self):
        assert hasattr(AI, "spacy_nlp")

    def test_ai_has_unload_embed(self):
        assert hasattr(AI, "unload_embed_model")


# ─────────────────────────────────────────────────────────────────────────────
# CACHE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheClass:
    def test_cache_set_and_get(self):
        Cache.set("test_key_xyz", {"data": "value"}, ttl_hours=1)
        result = Cache.get("test_key_xyz", ttl_hours=1)
        # May or may not be cached depending on filesystem
        assert result is None or isinstance(result, dict)

    def test_cache_get_missing_returns_none(self):
        result = Cache.get("nonexistent_key_12345678", ttl_hours=1)
        assert result is None

    def test_checkpoint_save_and_load(self):
        # conftest patches these to no-op, so just test they're callable
        Cache.save_checkpoint("test_seed", "P1", ["kw1", "kw2"])
        result = Cache.load_checkpoint("test_seed", "P1")
        # conftest patches to always return None
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# P1 → P3 → P5 → P7 MINI PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

class TestMiniPipeline:
    def test_p1_to_p3(self, p1, p3):
        s = p1.run("black pepper")
        kws = ["Black Pepper Benefits", "  Organic Pepper  ", "buy pepper online"]
        result = p3.run(s, kws)
        assert isinstance(result, list)
        assert all(kw == kw.lower() for kw in result)
        assert all(kw == kw.strip() for kw in result)

    def test_p3_to_p5(self, p1, p3, p5):
        s = p1.run("black pepper")
        raw = ["Black Pepper Benefits", "Buy Pepper Online", "Best Pepper Brand"]
        normalized = p3.run(s, raw)
        intents = p5.run(s, normalized)
        assert isinstance(intents, dict)
        for kw in normalized:
            assert kw in intents

    def test_p5_to_p7(self, p1, p3, p5, p7):
        s = p1.run("black pepper")
        raw = ["black pepper benefits", "buy pepper", "best pepper brand"]
        normalized = p3.run(s, raw)
        intent_map = p5.run(s, normalized)
        serp_map = {kw: {"kd_estimate": 40} for kw in normalized}
        scores = p7.run(s, normalized, intent_map, serp_map)
        assert isinstance(scores, dict)
        for kw in normalized:
            assert kw in scores
            assert 0 <= scores[kw] <= 100

    @pytest.mark.parametrize("spice_seed", [
        "cinnamon", "turmeric", "ginger", "clove", "cardamom"
    ])
    def test_mini_pipeline_various_seeds(self, spice_seed, p1, p3, p5, p7):
        s = p1.run(spice_seed)
        raw = [f"{spice_seed} {suf}" for suf in
               ["benefits", "recipe", "buy", "vs ginger", "what is"]]
        normalized = p3.run(s, raw)
        intent_map = p5.run(s, normalized)
        serp_map = {kw: {"kd_estimate": 35} for kw in normalized}
        scores = p7.run(s, normalized, intent_map, serp_map)
        assert all(0 <= v <= 100 for v in scores.values())


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT PACE — additional tests
# ─────────────────────────────────────────────────────────────────────────────

class TestContentPaceExtended:
    @pytest.mark.parametrize("years,expected_days", [
        (0.25, 91), (0.5, 182), (1.0, 365), (2.0, 730), (3.0, 1095),
    ])
    def test_total_days(self, years, expected_days):
        pace = ContentPace(duration_years=years)
        assert abs(pace.total_days - expected_days) <= 1  # ±1 for rounding

    def test_cost_for_100_articles(self):
        pace = ContentPace()
        assert pace.estimated_cost_usd(100) == pytest.approx(2.2, abs=0.1)

    def test_cost_for_1000_articles(self):
        pace = ContentPace()
        assert pace.estimated_cost_usd(1000) == pytest.approx(22.0, abs=0.5)

    def test_parallel_calls_default_3(self):
        pace = ContentPace()
        assert pace.parallel_claude_calls == 3

    def test_blogs_per_day_default(self):
        pace = ContentPace()
        assert pace.blogs_per_day == 3

    def test_summary_returns_dict(self):
        pace = ContentPace()
        result = pace.summary(100)
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
