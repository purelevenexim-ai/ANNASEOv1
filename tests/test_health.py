"""
AnnaSEO — Health and import tests.
These run before every deployment to confirm all engines are importable.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestEngineImports:
    """All engines must import without errors."""

    def test_import_20phase(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
        from ruflo_20phase_engine import RufloOrchestrator, P1_SeedInput
        assert RufloOrchestrator is not None

    def test_import_content(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
        from ruflo_content_engine import ContentGenerationEngine
        assert ContentGenerationEngine is not None

    def test_import_domain_context(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))
        from annaseo_domain_context import DomainContextEngine
        assert DomainContextEngine is not None

    def test_import_qi_engine(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "quality"))
        from annaseo_qi_engine import QIEngine
        assert QIEngine is not None

    def test_import_addons(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
        from annaseo_addons import OffTopicFilter, HDBSCANClustering
        assert OffTopicFilter is not None

    def test_import_wiring(self):
        from annaseo_wiring import GSCConnector, RUFLO_JOBS
        assert len(RUFLO_JOBS) > 10


class TestOffTopicFilter:
    """OffTopicFilter must block global noise words."""

    def test_global_kill_blocks_social(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
        from annaseo_addons import OffTopicFilter
        f = OffTopicFilter()
        kept, removed = f.filter(["cinnamon benefits", "cinnamon meme", "cinnamon viral"])
        assert "cinnamon benefits" in kept
        assert any("meme" in r or "viral" in r for r in removed)

    def test_seed_kill_words(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
        from annaseo_addons import OffTopicFilter
        f = OffTopicFilter(seed_kill_words=["candle", "perfume"])
        kept, removed = f.filter(["cinnamon candle", "buy cinnamon", "cinnamon perfume"])
        assert "buy cinnamon" in kept
        assert len(removed) == 2


class TestIntentClassification:
    """P5 intent classification must handle all categories."""

    def test_transactional_intent(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
        from ruflo_20phase_engine import P5_IntentClassification
        p5 = P5_IntentClassification()
        assert p5._classify("buy cinnamon online") == "transactional"
        assert p5._classify("cinnamon price per kg") == "transactional"

    def test_informational_intent(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
        from ruflo_20phase_engine import P5_IntentClassification
        p5 = P5_IntentClassification()
        assert p5._classify("what is cinnamon") == "informational"
        assert p5._classify("cinnamon health benefits") == "informational"

    def test_comparison_intent(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
        from ruflo_20phase_engine import P5_IntentClassification
        p5 = P5_IntentClassification()
        assert p5._classify("ceylon vs cassia cinnamon") == "comparison"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
