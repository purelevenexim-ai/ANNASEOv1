"""
GROUP 7 — DomainContextEngine Extended Tests
~200 tests: all industries, noise priority, e-commerce signals, batch,
            pillar validation, multi-word phrases, real keyword universe
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))

import pytest
from quality.annaseo_domain_context import DomainContextEngine, Industry


@pytest.fixture(scope="module")
def dce():
    return DomainContextEngine()

@pytest.fixture(scope="module", autouse=True)
def setup_all_projects(dce):
    dce.setup_project("p_spice",   "Spice Co",      Industry.FOOD_SPICES, ["black pepper"])
    dce.setup_project("p_tour",    "Tour Agency",   Industry.TOURISM,     ["ceylon tour"])
    dce.setup_project("p_health",  "Health Clinic", Industry.HEALTHCARE,  ["ayurveda"])
    dce.setup_project("p_ecomm",   "Spice Shop",    Industry.ECOMMERCE,   ["buy pepper"])
    dce.setup_project("p_agri",    "Pepper Farm",   Industry.AGRICULTURE, ["pepper farm"])


# ─────────────────────────────────────────────────────────────────────────────
# GATE 0 — Universal noise (always rejects, no project override possible)
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversalNoisePriority:
    NOISE_KEYWORDS = [
        "black pepper meme", "cinnamon viral", "spice tiktok",
        "pepper instagram hack", "turmeric twitter trend",
        "black pepper facebook group", "cinnamon challenge video",
    ]
    PROJECTS = ["p_spice", "p_tour", "p_health", "p_ecomm"]

    @pytest.mark.parametrize("keyword", NOISE_KEYWORDS)
    def test_noise_rejected_for_spice(self, dce, keyword):
        result = dce.classify(keyword, "p_spice")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for spice"

    @pytest.mark.parametrize("keyword", NOISE_KEYWORDS)
    def test_noise_rejected_for_tourism(self, dce, keyword):
        result = dce.classify(keyword, "p_tour")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for tourism"

    @pytest.mark.parametrize("keyword", NOISE_KEYWORDS)
    def test_noise_rejected_for_healthcare(self, dce, keyword):
        result = dce.classify(keyword, "p_health")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for healthcare"

    @pytest.mark.parametrize("keyword", NOISE_KEYWORDS)
    def test_noise_rejected_for_ecommerce(self, dce, keyword):
        result = dce.classify(keyword, "p_ecomm")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for ecommerce"

    def test_meme_rejected_even_with_strong_seed(self, dce):
        # "cinnamon" is in tourism cross_domain_rules as accept, but meme still rejects
        result = dce.classify("cinnamon meme", "p_tour")
        assert result["verdict"] == "reject"

    def test_tiktok_rejected_over_product_accept(self, dce):
        result = dce.classify("buy black pepper tiktok", "p_ecomm")
        assert result["verdict"] == "reject"


# ─────────────────────────────────────────────────────────────────────────────
# GATE 2 — Industry-specific rejects in cross-domain vocabulary
# ─────────────────────────────────────────────────────────────────────────────

class TestIndustrySpecificRejects:
    def test_buy_rejected_for_tourism(self, dce):
        result = dce.classify("buy black pepper", "p_tour")
        assert result["verdict"] == "reject"

    def test_buy_accepted_for_spice(self, dce):
        result = dce.classify("buy black pepper", "p_spice")
        assert result["verdict"] == "accept"

    def test_buy_accepted_for_ecommerce(self, dce):
        result = dce.classify("buy black pepper online", "p_ecomm")
        assert result["verdict"] == "accept"

    def test_kg_rejected_for_tourism(self, dce):
        result = dce.classify("black pepper per kg", "p_tour")
        assert result["verdict"] == "reject"

    def test_kg_accepted_for_spice(self, dce):
        result = dce.classify("black pepper per kg", "p_spice")
        assert result["verdict"] == "accept"

    def test_wholesale_rejected_for_tourism(self, dce):
        result = dce.classify("black pepper wholesale", "p_tour")
        assert result["verdict"] == "reject"

    def test_wholesale_accepted_for_spice(self, dce):
        result = dce.classify("black pepper wholesale", "p_spice")
        assert result["verdict"] == "accept"

    def test_bulk_rejected_for_tourism(self, dce):
        result = dce.classify("black pepper bulk", "p_tour")
        assert result["verdict"] == "reject"

    def test_tour_rejected_for_spice(self, dce):
        result = dce.classify("black pepper tour", "p_spice")
        assert result["verdict"] == "reject"

    def test_tour_accepted_for_tourism(self, dce):
        result = dce.classify("black pepper tour", "p_tour")
        assert result["verdict"] == "accept"

    def test_hotel_rejected_for_spice(self, dce):
        result = dce.classify("black pepper hotel menu", "p_spice")
        assert result["verdict"] == "reject"

    def test_treatment_rejected_for_spice(self, dce):
        result = dce.classify("black pepper treatment", "p_spice")
        assert result["verdict"] == "reject"

    def test_treatment_accepted_for_healthcare(self, dce):
        result = dce.classify("black pepper treatment", "p_health")
        assert result["verdict"] in ("accept", "ambiguous")


# ─────────────────────────────────────────────────────────────────────────────
# ACCEPTED KEYWORDS PER INDUSTRY
# ─────────────────────────────────────────────────────────────────────────────

class TestIndustryAccepts:
    SPICE_ACCEPTS = [
        "black pepper health benefits",
        "buy organic black pepper",
        "black pepper wholesale price",
        "black pepper bulk order",
        "ceylon black pepper",
        "malabar pepper organic",
        "black pepper nutrition facts",
        "piperine supplement",
    ]
    TOURISM_ACCEPTS = [
        "black pepper tour kerala",
        "spice plantation visit",
        "ceylon cinnamon plantation",
        "ayurveda tourism india",
        "spice route history",
        "plantation visit kerala",
    ]

    @pytest.mark.parametrize("keyword", SPICE_ACCEPTS)
    def test_spice_accepts(self, dce, keyword):
        result = dce.classify(keyword, "p_spice")
        assert result["verdict"] == "accept", \
            f"'{keyword}' should be accepted for spice. Got: {result}"

    @pytest.mark.parametrize("keyword", TOURISM_ACCEPTS)
    def test_tourism_accepts(self, dce, keyword):
        result = dce.classify(keyword, "p_tour")
        assert result["verdict"] in ("accept", "ambiguous"), \
            f"'{keyword}' should be accepted/ambiguous for tourism. Got: {result}"


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-DOMAIN RULES — same keyword different verdict per project
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainIsolation:
    def test_cinnamon_tour_spice_reject_tour_accept(self, dce):
        spice = dce.classify("cinnamon tour", "p_spice")
        tour  = dce.classify("cinnamon tour", "p_tour")
        assert spice["verdict"] == "reject"
        assert tour["verdict"] == "accept"

    def test_ceylon_cinnamon_accepted_both(self, dce):
        spice = dce.classify("ceylon cinnamon", "p_spice")
        tour  = dce.classify("ceylon cinnamon", "p_tour")
        assert spice["verdict"] == "accept"
        assert tour["verdict"] == "accept"

    def test_buy_kg_rejected_tourism_accepted_spice(self, dce):
        spice = dce.classify("buy black pepper per kg", "p_spice")
        tour  = dce.classify("buy black pepper per kg", "p_tour")
        assert spice["verdict"] == "accept"
        assert tour["verdict"] == "reject"

    def test_plantation_valid_for_both(self, dce):
        spice = dce.classify("cinnamon plantation", "p_spice")
        tour  = dce.classify("spice plantation tour", "p_tour")
        assert spice["verdict"] == "accept"
        assert tour["verdict"] in ("accept", "ambiguous")

    def test_travel_rejected_spice(self, dce):
        result = dce.classify("black pepper travel", "p_spice")
        assert result["verdict"] == "reject"

    def test_travel_accepted_tourism(self, dce):
        result = dce.classify("black pepper travel", "p_tour")
        assert result["verdict"] == "accept"

    def test_flight_rejected_spice(self, dce):
        result = dce.classify("black pepper flight route", "p_spice")
        assert result["verdict"] == "reject"

    def test_flight_accepted_tourism(self, dce):
        result = dce.classify("kerala flight booking", "p_tour")
        assert result["verdict"] == "accept"

    def test_organic_accepted_spice(self, dce):
        result = dce.classify("organic black pepper", "p_spice")
        assert result["verdict"] == "accept"

    def test_dosage_rejected_spice(self, dce):
        result = dce.classify("black pepper dosage", "p_spice")
        assert result["verdict"] == "reject"

    def test_dosage_accepted_healthcare(self, dce):
        result = dce.classify("black pepper dosage health", "p_health")
        assert result["verdict"] in ("accept", "ambiguous")


# ─────────────────────────────────────────────────────────────────────────────
# RESULT STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestResultStructure:
    def test_result_has_verdict(self, dce):
        r = dce.classify("black pepper", "p_spice")
        assert "verdict" in r

    def test_result_has_score(self, dce):
        r = dce.classify("black pepper", "p_spice")
        assert "score" in r

    def test_result_has_reason(self, dce):
        r = dce.classify("black pepper benefits", "p_spice")
        assert "reason" in r
        assert len(r["reason"]) > 0

    def test_result_has_industry(self, dce):
        r = dce.classify("black pepper", "p_spice")
        assert "industry" in r
        assert r["industry"] == Industry.FOOD_SPICES

    def test_verdict_is_valid_value(self, dce):
        r = dce.classify("black pepper benefits", "p_spice")
        assert r["verdict"] in ("accept", "reject", "ambiguous")

    def test_score_range(self, dce):
        r = dce.classify("black pepper benefits", "p_spice")
        assert 0 <= r["score"] <= 100

    def test_unknown_project_returns_accept_default(self, dce):
        r = dce.classify("black pepper", "nonexistent_project_xyz")
        assert r["verdict"] == "accept"


# ─────────────────────────────────────────────────────────────────────────────
# BATCH CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchClassification:
    def test_batch_returns_three_lists(self, dce):
        accepted, rejected, ambiguous = dce.classify_batch(
            ["black pepper benefits", "buy black pepper"], "p_spice"
        )
        assert isinstance(accepted, list)
        assert isinstance(rejected, list)
        assert isinstance(ambiguous, list)

    def test_batch_total_equals_input(self, dce):
        keywords = ["black pepper benefits", "black pepper meme", "ceylon cinnamon tour"]
        accepted, rejected, ambiguous = dce.classify_batch(keywords, "p_spice")
        total = len(accepted) + len(rejected) + len([a for a in ambiguous])
        assert total == len(keywords)

    def test_batch_noise_always_rejected(self, dce):
        keywords = ["pepper meme", "spice viral", "cinnamon tiktok"]
        _, rejected, _ = dce.classify_batch(keywords, "p_spice")
        assert len(rejected) == 3

    def test_batch_project_isolation(self, dce):
        keywords = ["cinnamon tour", "buy cinnamon per kg", "cinnamon meme"]
        _, spice_rej, _ = dce.classify_batch(keywords, "p_spice")
        _, tour_rej, _  = dce.classify_batch(keywords, "p_tour")
        # "cinnamon meme" rejected by both
        assert "cinnamon meme" in spice_rej
        assert "cinnamon meme" in tour_rej
        # "cinnamon tour" rejected by spice, accepted by tour
        assert "cinnamon tour" in spice_rej
        assert "cinnamon tour" not in tour_rej

    def test_batch_empty_list(self, dce):
        a, r, amb = dce.classify_batch([], "p_spice")
        assert a == [] and r == [] and amb == []


# ─────────────────────────────────────────────────────────────────────────────
# PILLAR VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

class TestPillarValidation:
    def test_validate_valid_pillars(self, dce):
        pillars = {
            "health benefits": {"pillar_keyword": "black pepper health benefits"},
            "cooking guide":   {"pillar_keyword": "cooking with black pepper"},
        }
        valid, rejected = dce.validate_pillars(pillars, "p_spice")
        assert len(valid) == 2
        assert len(rejected) == 0

    def test_validate_rejects_tour_pillar_for_spice(self, dce):
        pillars = {
            "tour guide": {"pillar_keyword": "black pepper tour"},
        }
        valid, rejected = dce.validate_pillars(pillars, "p_spice")
        assert len(rejected) == 1
        assert rejected[0]["pillar_keyword"] == "black pepper tour"

    def test_validate_empty_pillars(self, dce):
        valid, rejected = dce.validate_pillars({}, "p_spice")
        assert valid == {}
        assert rejected == []

    def test_validate_noise_pillar_rejected(self, dce):
        pillars = {"noise": {"pillar_keyword": "black pepper meme"}}
        valid, rejected = dce.validate_pillars(pillars, "p_spice")
        assert len(rejected) == 1


# ─────────────────────────────────────────────────────────────────────────────
# REAL KEYWORD UNIVERSE — 50 Black Pepper keywords
# ─────────────────────────────────────────────────────────────────────────────

class TestBlackPepperKeywordUniverse:
    SPICE_ACCEPT = [
        "black pepper health benefits",
        "organic black pepper powder",
        "black pepper nutrition facts",
        "buy black pepper online",
        "malabar black pepper wholesale",
        "tellicherry peppercorns bulk",
        "black pepper export india",
        "piperine bioavailability",
        "black pepper anti-inflammatory",
        "black pepper cultivation guide",
        "black pepper vs white pepper",
        "black pepper price per kg",
        "ceylon black pepper",
    ]

    SPICE_REJECT = [
        "black pepper tour itinerary",
        "black pepper hotel restaurant",
        "cinnamon tour kerala",
        "spice tour guide",
        "black pepper travel blog",
        "black pepper meme viral",
        "pepper tiktok challenge",
    ]

    @pytest.mark.parametrize("keyword", SPICE_ACCEPT)
    def test_spice_universe_accepts(self, dce, keyword):
        result = dce.classify(keyword, "p_spice")
        assert result["verdict"] == "accept", \
            f"Expected accept for '{keyword}', got {result['verdict']}: {result['reason']}"

    @pytest.mark.parametrize("keyword", SPICE_REJECT)
    def test_spice_universe_rejects(self, dce, keyword):
        result = dce.classify(keyword, "p_spice")
        assert result["verdict"] == "reject", \
            f"Expected reject for '{keyword}', got {result['verdict']}: {result['reason']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
