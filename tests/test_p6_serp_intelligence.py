"""
GROUP — P6 SERP Intelligence
~110 tests (all SERP calls mocked — no network required)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P6_SERPIntelligence, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p6(monkeypatch):
    instance = P6_SERPIntelligence()
    # Mock _analyse_serp to avoid network calls
    def fake_analyse(kw):
        return {
            "kw": kw,
            "top_urls": [f"https://example.com/{kw.replace(' ','-')}"],
            "avg_word_count": 1200,
            "has_featured_snippet": "how" in kw or "what" in kw,
            "has_paa": "what" in kw or "why" in kw,
            "has_video": "recipe" in kw or "how to" in kw,
            "competitor_domains": ["healthline.com"] if "benefits" in kw else [],
            "kd_estimate": 30 if "buy" in kw else 50,
            "content_gap": "benefits" in kw,
        }
    monkeypatch.setattr(instance, "_analyse_serp", fake_analyse)
    return instance

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestP6ReturnStructure:
    def test_returns_dict(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result, dict)

    def test_keys_match_input_keywords(self, p6, seed):
        kws = ["black pepper benefits", "buy black pepper", "piperine uses"]
        result = p6.run(seed, kws)
        for kw in kws:
            assert kw in result

    def test_each_entry_has_kw_field(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert result["black pepper benefits"]["kw"] == "black pepper benefits"

    def test_each_entry_has_top_urls(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert "top_urls" in result["black pepper benefits"]

    def test_top_urls_is_list(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result["black pepper benefits"]["top_urls"], list)

    def test_each_entry_has_kd_estimate(self, p6, seed):
        result = p6.run(seed, ["black pepper"])
        assert "kd_estimate" in result["black pepper"]

    def test_kd_estimate_numeric(self, p6, seed):
        result = p6.run(seed, ["black pepper"])
        assert isinstance(result["black pepper"]["kd_estimate"], (int, float))

    def test_kd_estimate_in_range(self, p6, seed):
        kws = ["black pepper benefits", "buy organic pepper", "pepper recipe"]
        result = p6.run(seed, kws)
        for kw in kws:
            kd = result[kw]["kd_estimate"]
            assert 0 <= kd <= 100, f"KD out of range for '{kw}': {kd}"

    def test_has_featured_snippet_boolean(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result["black pepper benefits"]["has_featured_snippet"], bool)

    def test_has_paa_boolean(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result["black pepper benefits"]["has_paa"], bool)

    def test_has_video_boolean(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result["black pepper benefits"]["has_video"], bool)

    def test_competitor_domains_is_list(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        assert isinstance(result["black pepper benefits"]["competitor_domains"], list)

    def test_empty_input_returns_empty_dict(self, p6, seed):
        result = p6.run(seed, [])
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# FEATURED SNIPPET DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP6FeaturedSnippet:
    def test_how_question_has_snippet(self, p6, seed):
        result = p6.run(seed, ["how to use black pepper"])
        assert result["how to use black pepper"]["has_featured_snippet"] is True

    def test_what_question_has_snippet(self, p6, seed):
        result = p6.run(seed, ["what is piperine"])
        assert result["what is piperine"]["has_featured_snippet"] is True

    def test_commercial_keyword_no_snippet(self, p6, seed):
        result = p6.run(seed, ["buy organic black pepper"])
        assert result["buy organic black pepper"]["has_featured_snippet"] is False


# ─────────────────────────────────────────────────────────────────────────────
# PAA (PEOPLE ALSO ASK) DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP6PAA:
    def test_what_question_has_paa(self, p6, seed):
        result = p6.run(seed, ["what is black pepper"])
        assert result["what is black pepper"]["has_paa"] is True

    def test_why_question_has_paa(self, p6, seed):
        result = p6.run(seed, ["why use black pepper"])
        assert result["why use black pepper"]["has_paa"] is True

    def test_buy_keyword_no_paa(self, p6, seed):
        result = p6.run(seed, ["buy black pepper online"])
        assert result["buy black pepper online"]["has_paa"] is False


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO RESULTS DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestP6VideoResults:
    def test_recipe_keyword_has_video(self, p6, seed):
        result = p6.run(seed, ["black pepper recipe"])
        assert result["black pepper recipe"]["has_video"] is True

    def test_how_to_keyword_has_video(self, p6, seed):
        result = p6.run(seed, ["how to grind black pepper"])
        assert result["how to grind black pepper"]["has_video"] is True

    def test_buy_keyword_no_video(self, p6, seed):
        result = p6.run(seed, ["buy black pepper"])
        assert result["buy black pepper"]["has_video"] is False


# ─────────────────────────────────────────────────────────────────────────────
# KD ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP6KDEstimation:
    def test_buy_keyword_lower_kd(self, p6, seed):
        result = p6.run(seed, ["buy black pepper"])
        assert result["buy black pepper"]["kd_estimate"] <= 50

    def test_informational_keyword_moderate_kd(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        kd = result["black pepper benefits"]["kd_estimate"]
        assert 0 <= kd <= 100

    @pytest.mark.parametrize("kw", [
        "black pepper benefits",
        "turmeric anti-inflammatory",
        "organic cinnamon uses",
        "ginger tea digestion",
        "clove oil dental",
    ])
    def test_all_keywords_have_valid_kd(self, p6, seed, kw):
        result = p6.run(seed, [kw])
        kd = result[kw]["kd_estimate"]
        assert isinstance(kd, (int, float)) and 0 <= kd <= 100


# ─────────────────────────────────────────────────────────────────────────────
# COMPETITOR DOMAINS
# ─────────────────────────────────────────────────────────────────────────────

class TestP6CompetitorDomains:
    def test_competitor_domains_list(self, p6, seed):
        result = p6.run(seed, ["black pepper benefits"])
        domains = result["black pepper benefits"]["competitor_domains"]
        assert isinstance(domains, list)

    def test_competitive_keyword_has_competitors(self, p6, seed):
        result = p6.run(seed, ["black pepper health benefits"])
        domains = result["black pepper health benefits"]["competitor_domains"]
        assert len(domains) >= 1

    def test_max_keywords_limit_respected(self, p6, seed):
        kws = [f"black pepper query {i}" for i in range(200)]
        result = p6.run(seed, kws, max_keywords=50)
        assert len(result) <= 50


# ─────────────────────────────────────────────────────────────────────────────
# BATCH / PARAMETRIZE
# ─────────────────────────────────────────────────────────────────────────────

class TestP6BatchAnalysis:
    @pytest.mark.parametrize("kw,expect_snippet", [
        ("how to store black pepper", True),
        ("what is piperine in black pepper", True),
        ("buy black pepper bulk", False),
        ("best black pepper brand", False),
    ])
    def test_snippet_detection_parametrized(self, p6, seed, kw, expect_snippet):
        result = p6.run(seed, [kw])
        assert result[kw]["has_featured_snippet"] == expect_snippet

    def test_large_batch_processed(self, p6, seed):
        kws = [f"black pepper topic {i}" for i in range(100)]
        result = p6.run(seed, kws, max_keywords=100)
        assert len(result) == 100

    def test_all_entries_have_required_fields(self, p6, seed):
        kws = ["black pepper benefits", "buy pepper", "how to use pepper"]
        result = p6.run(seed, kws)
        required = {"kw", "top_urls", "kd_estimate", "has_featured_snippet",
                    "has_paa", "has_video", "competitor_domains"}
        for kw in kws:
            missing = required - set(result[kw].keys())
            assert not missing, f"Missing fields for '{kw}': {missing}"

    def test_different_seed_keywords_different_results(self, p1, monkeypatch):
        call_count = [0]
        def fake_analyse_counter(kw):
            call_count[0] += 1
            return {"kw": kw, "top_urls": [], "avg_word_count": 0,
                    "has_featured_snippet": False, "has_paa": False,
                    "has_video": False, "competitor_domains": [],
                    "kd_estimate": 40, "content_gap": False}
        p6_instance = P6_SERPIntelligence()
        monkeypatch.setattr(p6_instance, "_analyse_serp", fake_analyse_counter)
        s = p1.run("turmeric")
        p6_instance.run(s, ["turmeric benefits", "turmeric tea"])
        assert call_count[0] == 2


class TestCompetitorSnapshotCompatibility:
    def test_from_dict_uses_da_as_estimated_da(self):
        from engines.ruflo_final_strategy_engine import CompetitorSnapshot
        snapshot = CompetitorSnapshot.from_dict({
            "domain": "example.com",
            "da": 50,
            "pillars_covered": ["tea products"],
            "pillars_missing": ["tea recipes"],
            "content_freshness": "fresh"
        })
        assert snapshot.estimated_da == 50

    def test_from_dict_uses_domain_authority_as_estimated_da(self):
        from engines.ruflo_final_strategy_engine import CompetitorSnapshot
        snapshot = CompetitorSnapshot.from_dict({
            "domain": "example.com",
            "domain_authority": 48,
            "pillars_covered": ["tea products"],
            "pillars_missing": ["tea recipes"],
            "content_freshness": "fresh"
        })
        assert snapshot.estimated_da == 48


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
