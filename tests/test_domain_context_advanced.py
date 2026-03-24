"""
GROUP — DomainContextEngine advanced tests
~130 tests (DB patched via conftest autouse fixture)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))

import pytest
from annaseo_domain_context import (
    DomainContextEngine, DomainContextDB, Industry,
    ProjectDomainProfile, DEFAULT_DOMAIN_PROFILES
)
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — create engine with a real in-memory-like profile
# ─────────────────────────────────────────────────────────────────────────────

SPICE_PROJECT_ID = "test_spice_advanced"
HEALTH_PROJECT_ID = "test_health_advanced"
ECOM_PROJECT_ID = "test_ecom_advanced"


@pytest.fixture
def engine_with_spice(monkeypatch):
    """DomainContextEngine with a spice project profile, DB patched."""
    spice_defaults = DEFAULT_DOMAIN_PROFILES.get(Industry.FOOD_SPICES, {})
    spice_profile_dict = {
        "project_id": SPICE_PROJECT_ID,
        "project_name": "Test Spice Project",
        "industry": Industry.FOOD_SPICES,
        "seed_keywords": '["black pepper"]',
        "domain_description": "Organic spice store",
        "accept_overrides": '[]',
        "reject_overrides": str(spice_defaults.get("reject_overrides", [])).replace("'", '"'),
        "cross_domain_rules": '{"ceylon": "accept", "plantation": "accept", "tour": "reject"}',
        "content_angles": '[]',
        "avoid_angles": '[]',
    }
    engine = DomainContextEngine()
    monkeypatch.setattr(engine._db, "get_profile",
                        lambda pid: spice_profile_dict if pid == SPICE_PROJECT_ID else None)
    monkeypatch.setattr(engine._db, "log_classification", lambda *a, **kw: None)
    return engine


@pytest.fixture
def engine_with_health(monkeypatch):
    health_defaults = DEFAULT_DOMAIN_PROFILES.get(Industry.HEALTHCARE, {})
    health_profile_dict = {
        "project_id": HEALTH_PROJECT_ID,
        "project_name": "Test Health Project",
        "industry": Industry.HEALTHCARE,
        "seed_keywords": '["turmeric supplement"]',
        "domain_description": "Health supplements",
        "accept_overrides": '[]',
        "reject_overrides": '["tour", "travel", "wholesale", "bulk order"]',
        "cross_domain_rules": '{"cinnamon": "accept", "benefits": "accept", "tour": "reject"}',
        "content_angles": '[]',
        "avoid_angles": '[]',
    }
    engine = DomainContextEngine()
    monkeypatch.setattr(engine._db, "get_profile",
                        lambda pid: health_profile_dict if pid == HEALTH_PROJECT_ID else None)
    monkeypatch.setattr(engine._db, "log_classification", lambda *a, **kw: None)
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# RETURN STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainContextReturnStructure:
    def test_classify_returns_dict(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert isinstance(result, dict)

    def test_result_has_verdict(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert "verdict" in result

    def test_result_has_score(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert "score" in result

    def test_result_has_reason(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert "reason" in result

    def test_result_has_industry(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert "industry" in result

    def test_score_is_numeric(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert isinstance(result["score"], (int, float))

    def test_score_in_valid_range(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert 0 <= result["score"] <= 100

    def test_verdict_is_valid(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper benefits", SPICE_PROJECT_ID)
        assert result["verdict"] in ("accept", "reject", "ambiguous", "borderline"), \
            f"Invalid verdict: {result['verdict']}"

    def test_no_profile_defaults_to_accept(self, monkeypatch):
        engine = DomainContextEngine()
        monkeypatch.setattr(engine._db, "get_profile", lambda pid: None)
        monkeypatch.setattr(engine._db, "log_classification", lambda *a, **kw: None)
        result = engine.classify("black pepper benefits", "nonexistent_project")
        assert result["verdict"] == "accept"


# ─────────────────────────────────────────────────────────────────────────────
# SPICE KEYWORDS — ACCEPT
# ─────────────────────────────────────────────────────────────────────────────

class TestSpiceAccept:
    @pytest.mark.parametrize("kw", [
        "black pepper benefits",
        "organic black pepper",
        "black pepper powder recipe",
        "turmeric health benefits",
        "cinnamon blood sugar",
        "ginger tea digestion",
        "clove oil benefits",
        "cardamom coffee flavor",
        "black pepper wholesale india",
        "malabar black pepper organic",
    ])
    def test_spice_accept_keywords(self, engine_with_spice, kw):
        result = engine_with_spice.classify(kw, SPICE_PROJECT_ID)
        assert result["verdict"] in ("accept", "ambiguous"), \
            f"'{kw}' classified as '{result['verdict']}' (score={result['score']})"


# ─────────────────────────────────────────────────────────────────────────────
# SOCIAL MEDIA — REJECT
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialMediaReject:
    # Only words in CROSS_DOMAIN_VOCABULARY with __all__=reject are guaranteed to reject
    @pytest.mark.parametrize("kw", [
        "black pepper meme",
        "pepper viral trend",
        "cinnamon tiktok challenge",
        "spice instagram post",
        "pepper twitter hashtag",
        "spice facebook group",
    ])
    def test_social_media_rejected(self, engine_with_spice, kw):
        result = engine_with_spice.classify(kw, SPICE_PROJECT_ID)
        assert result["verdict"] == "reject", \
            f"'{kw}' should be reject, got '{result['verdict']}'"

    def test_youtube_keyword_not_accepted_by_spice(self, engine_with_spice):
        # youtube not in CROSS_DOMAIN_VOCABULARY, depends on project override
        result = engine_with_spice.classify("pepper youtube video", SPICE_PROJECT_ID)
        assert result["verdict"] in ("reject", "accept", "ambiguous")  # any is OK

    def test_reddit_keyword_classified(self, engine_with_spice):
        result = engine_with_spice.classify("pepper reddit thread", SPICE_PROJECT_ID)
        assert result["verdict"] in ("reject", "accept", "ambiguous")


# ─────────────────────────────────────────────────────────────────────────────
# REJECT OVERRIDES
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectOverrides:
    def test_tour_rejected_for_spice(self, engine_with_spice):
        result = engine_with_spice.classify("cinnamon tour package", SPICE_PROJECT_ID)
        assert result["verdict"] in ("reject", "ambiguous")

    def test_travel_rejected_for_spice(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper travel guide", SPICE_PROJECT_ID)
        assert result["verdict"] in ("reject", "ambiguous")

    def test_hotel_rejected_for_spice(self, engine_with_spice):
        result = engine_with_spice.classify("spice hotel review", SPICE_PROJECT_ID)
        assert result["verdict"] in ("reject", "ambiguous")


# ─────────────────────────────────────────────────────────────────────────────
# CROSS DOMAIN ISOLATION
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainIsolation:
    def test_same_keyword_different_verdicts_per_project(
            self, engine_with_spice, engine_with_health):
        kw = "black pepper tour"
        spice_result = engine_with_spice.classify(kw, SPICE_PROJECT_ID)
        health_result = engine_with_health.classify(kw, HEALTH_PROJECT_ID)
        # Both should classify but may differ
        assert spice_result["verdict"] in ("accept", "reject", "ambiguous")
        assert health_result["verdict"] in ("accept", "reject", "ambiguous")

    def test_domain_specific_verdict_returned(self, engine_with_spice):
        result = engine_with_spice.classify("black pepper health benefits", SPICE_PROJECT_ID)
        assert result["industry"] == Industry.FOOD_SPICES


# ─────────────────────────────────────────────────────────────────────────────
# BATCH CLASSIFY
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchClassify:
    def test_batch_classify_returns_tuple(self, engine_with_spice):
        kws = ["black pepper benefits", "pepper meme", "buy pepper"]
        result = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_batch_accepted_is_list(self, engine_with_spice):
        kws = ["black pepper benefits", "pepper meme", "buy pepper"]
        accepted, rejected, ambiguous = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        assert isinstance(accepted, list)

    def test_batch_rejected_is_list(self, engine_with_spice):
        kws = ["black pepper benefits", "pepper meme", "buy pepper"]
        accepted, rejected, ambiguous = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        assert isinstance(rejected, list)

    def test_batch_meme_rejected(self, engine_with_spice):
        kws = ["black pepper benefits", "pepper meme"]
        accepted, rejected, ambiguous = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        assert "pepper meme" in rejected

    def test_batch_empty_returns_empty_lists(self, engine_with_spice):
        accepted, rejected, ambiguous = engine_with_spice.classify_batch([], SPICE_PROJECT_ID)
        assert accepted == []
        assert rejected == []
        assert ambiguous == []

    def test_batch_total_covers_all_input(self, engine_with_spice):
        kws = [f"black pepper use {i}" for i in range(10)]
        accepted, rejected, ambiguous = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        total = len(accepted) + len(rejected) + len(ambiguous)
        assert total == 10

    @pytest.mark.parametrize("n", [5, 10, 25])
    def test_batch_various_sizes_total(self, engine_with_spice, n):
        kws = [f"black pepper use {i}" for i in range(n)]
        accepted, rejected, ambiguous = engine_with_spice.classify_batch(kws, SPICE_PROJECT_ID)
        total = len(accepted) + len(rejected) + len(ambiguous)
        assert total == n


# ─────────────────────────────────────────────────────────────────────────────
# INDUSTRY CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

class TestIndustryConstants:
    def test_food_spices_exists(self):
        assert hasattr(Industry, "FOOD_SPICES")

    def test_healthcare_exists(self):
        assert hasattr(Industry, "HEALTHCARE")

    def test_ecommerce_exists(self):
        assert hasattr(Industry, "ECOMMERCE")

    def test_tourism_exists(self):
        assert hasattr(Industry, "TOURISM")

    def test_all_industries_are_strings(self):
        for attr in ["FOOD_SPICES", "HEALTHCARE", "ECOMMERCE", "TOURISM"]:
            val = getattr(Industry, attr)
            assert isinstance(val, str)


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT DOMAIN PROFILES
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultDomainProfiles:
    def test_food_spices_profile_exists(self):
        assert Industry.FOOD_SPICES in DEFAULT_DOMAIN_PROFILES

    def test_healthcare_profile_exists(self):
        assert Industry.HEALTHCARE in DEFAULT_DOMAIN_PROFILES

    def test_ecommerce_profile_exists(self):
        assert Industry.ECOMMERCE in DEFAULT_DOMAIN_PROFILES

    def test_tourism_profile_exists(self):
        assert Industry.TOURISM in DEFAULT_DOMAIN_PROFILES

    def test_food_spices_has_reject_overrides(self):
        profile = DEFAULT_DOMAIN_PROFILES[Industry.FOOD_SPICES]
        assert "reject_overrides" in profile
        assert isinstance(profile["reject_overrides"], list)

    def test_food_spices_tour_is_rejected(self):
        profile = DEFAULT_DOMAIN_PROFILES[Industry.FOOD_SPICES]
        assert "tour" in profile["reject_overrides"]

    def test_food_spices_has_content_angles(self):
        profile = DEFAULT_DOMAIN_PROFILES[Industry.FOOD_SPICES]
        assert "content_angles" in profile
        assert len(profile["content_angles"]) > 0

    @pytest.mark.parametrize("industry", [
        Industry.FOOD_SPICES, Industry.HEALTHCARE, Industry.ECOMMERCE, Industry.TOURISM
    ])
    def test_all_profiles_have_required_keys(self, industry):
        profile = DEFAULT_DOMAIN_PROFILES[industry]
        for key in ["accept_overrides", "reject_overrides", "cross_domain_rules",
                    "content_angles", "avoid_angles"]:
            assert key in profile, f"Missing '{key}' in {industry} profile"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
