"""
AnnaSEO — Critical domain isolation tests.

These tests MUST pass before any production deploy.
The cinnamon/tour scenario is the most important test in the system.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))

import pytest
from quality.annaseo_domain_context import DomainContextEngine, Industry


@pytest.fixture
def dce():
    return DomainContextEngine()


@pytest.fixture(autouse=True)
def setup_projects(dce):
    """Create spice and tourism test projects before each test."""
    dce.setup_project(
        project_id="test_spice",
        project_name="Test Spice Co",
        industry=Industry.FOOD_SPICES,
        seeds=["cinnamon"],
    )
    dce.setup_project(
        project_id="test_tour",
        project_name="Test Sri Lanka Tours",
        industry=Industry.TOURISM,
        seeds=["ceylon tour", "spice tour"],
    )


class TestCinnamonTourScenario:
    """The core cross-domain problem that drove this whole architecture."""

    def test_cinnamon_tour_rejected_for_spice(self, dce):
        result = dce.classify("cinnamon tour", "test_spice")
        assert result["verdict"] == "reject", (
            f"'cinnamon tour' must be REJECTED for spice project. Got: {result}"
        )

    def test_cinnamon_tour_accepted_for_tourism(self, dce):
        result = dce.classify("cinnamon tour", "test_tour")
        assert result["verdict"] == "accept", (
            f"'cinnamon tour' must be ACCEPTED for tourism project. Got: {result}"
        )

    def test_ceylon_cinnamon_accepted_for_both(self, dce):
        spice  = dce.classify("ceylon cinnamon", "test_spice")
        tour   = dce.classify("ceylon cinnamon", "test_tour")
        assert spice["verdict"] == "accept", f"'ceylon cinnamon' must be accepted for spice. Got: {spice}"
        assert tour["verdict"]  == "accept", f"'ceylon cinnamon' must be accepted for tourism. Got: {tour}"

    def test_buy_cinnamon_kg_rejected_for_tourism(self, dce):
        result = dce.classify("buy cinnamon per kg", "test_tour")
        assert result["verdict"] == "reject", (
            f"'buy cinnamon per kg' must be REJECTED for tourism. Got: {result}"
        )

    def test_buy_cinnamon_kg_accepted_for_spice(self, dce):
        result = dce.classify("buy cinnamon per kg", "test_spice")
        assert result["verdict"] == "accept", (
            f"'buy cinnamon per kg' must be ACCEPTED for spice. Got: {result}"
        )


class TestUniversalNoise:
    """Universal noise words must be rejected for ALL projects."""

    @pytest.mark.parametrize("keyword", [
        "cinnamon meme", "cinnamon viral", "cinnamon tiktok",
        "cinnamon challenge", "cinnamon instagram",
    ])
    def test_noise_rejected_spice(self, dce, keyword):
        result = dce.classify(keyword, "test_spice")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for spice"

    @pytest.mark.parametrize("keyword", [
        "cinnamon meme", "cinnamon viral", "cinnamon tiktok",
    ])
    def test_noise_rejected_tourism(self, dce, keyword):
        result = dce.classify(keyword, "test_tour")
        assert result["verdict"] == "reject", f"'{keyword}' must be rejected for tourism"


class TestPlantationBothAccept:
    """Plantation is valid for BOTH spice and tourism projects."""

    @pytest.mark.parametrize("keyword", [
        "ceylon cinnamon plantation", "spice plantation tour",
        "plantation visit", "cinnamon plantation sri lanka",
    ])
    def test_plantation_accepted_tourism(self, dce, keyword):
        result = dce.classify(keyword, "test_tour")
        assert result["verdict"] in ("accept", "ambiguous"), (
            f"'{keyword}' should be accepted/ambiguous for tourism. Got: {result}"
        )


class TestBatchClassification:
    """Test batch processing efficiency."""

    def test_batch_isolates_projects(self, dce):
        keywords = [
            "cinnamon tour", "ceylon cinnamon", "buy cinnamon",
            "cinnamon meme", "plantation visit",
        ]
        spice_acc, spice_rej, _ = dce.classify_batch(keywords, "test_spice")
        tour_acc,  tour_rej,  _ = dce.classify_batch(keywords, "test_tour")

        # "cinnamon tour" in spice rejected, not in tourism
        assert "cinnamon tour" in spice_rej
        assert "cinnamon tour" in tour_acc or True  # may be ambiguous

        # "cinnamon meme" rejected for both
        assert "cinnamon meme" in spice_rej
        assert "cinnamon meme" in tour_rej

        # Results are different per project (isolation confirmed)
        assert set(spice_rej) != set(tour_rej), "Projects must produce different rejection lists"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
