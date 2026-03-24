"""
GROUP — P2 KeywordExpansion — question variants + dedup logic
~130 tests (network autosuggest calls are mocked)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P2_KeywordExpansion, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p2_instance(): return P2_KeywordExpansion()

@pytest.fixture
def p2(p2_instance, monkeypatch):
    """Patch all network calls — test logic only."""
    def fake_google(kw): return [f"{kw} benefits", f"{kw} uses", f"{kw} recipe"]
    def fake_youtube(kw): return [f"{kw} video", f"{kw} tutorial"]
    def fake_amazon(kw): return [f"buy {kw}", f"organic {kw}", f"{kw} supplement"]
    def fake_ddg(kw): return [f"{kw} health", f"{kw} side effects"]
    def fake_reddit(kw): return [f"{kw} reddit", f"best {kw}"]

    monkeypatch.setattr(p2_instance, "_google_autosuggest", fake_google)
    monkeypatch.setattr(p2_instance, "_youtube_autosuggest", fake_youtube)
    monkeypatch.setattr(p2_instance, "_amazon_autosuggest", fake_amazon)
    monkeypatch.setattr(p2_instance, "_duckduckgo", fake_ddg)
    monkeypatch.setattr(p2_instance, "_reddit_titles", fake_reddit)
    return p2_instance

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION VARIANTS (pure logic — no network)
# ─────────────────────────────────────────────────────────────────────────────

class TestP2QuestionVariants:
    def test_question_variants_returns_list(self, p2_instance, seed):
        result = p2_instance._question_variants("black pepper")
        assert isinstance(result, list)

    def test_what_question_generated(self, p2_instance):
        result = p2_instance._question_variants("black pepper")
        assert any("what" in kw for kw in result)

    def test_how_question_generated(self, p2_instance):
        result = p2_instance._question_variants("black pepper")
        assert any("how" in kw for kw in result)

    def test_why_question_generated(self, p2_instance):
        result = p2_instance._question_variants("black pepper")
        assert any("why" in kw for kw in result)

    def test_does_question_generated(self, p2_instance):
        result = p2_instance._question_variants("black pepper")
        assert any("does" in kw or "is" in kw for kw in result)

    def test_questions_contain_keyword(self, p2_instance):
        kw = "black pepper"
        result = p2_instance._question_variants(kw)
        for q in result:
            assert kw in q

    def test_non_empty_output(self, p2_instance):
        result = p2_instance._question_variants("cinnamon")
        assert len(result) > 0

    @pytest.mark.parametrize("kw", [
        "black pepper", "turmeric", "cinnamon", "ginger", "clove oil",
    ])
    def test_question_variants_for_spices(self, p2_instance, kw):
        result = p2_instance._question_variants(kw)
        assert len(result) >= 3

    def test_no_duplicate_questions(self, p2_instance):
        result = p2_instance._question_variants("black pepper")
        assert len(result) == len(set(result))

    def test_questions_are_lowercase(self, p2_instance):
        result = p2_instance._question_variants("Black Pepper")
        for q in result:
            assert q == q.lower() or q[0].islower()


# ─────────────────────────────────────────────────────────────────────────────
# FULL P2 RUN (mocked network)
# ─────────────────────────────────────────────────────────────────────────────

class TestP2Run:
    def test_returns_list(self, p2, seed):
        result = p2.run(seed)
        assert isinstance(result, list)

    def test_result_not_empty(self, p2, seed):
        result = p2.run(seed)
        assert len(result) > 0

    def test_all_strings(self, p2, seed):
        result = p2.run(seed)
        for kw in result:
            assert isinstance(kw, str)

    def test_all_lowercase(self, p2, seed):
        result = p2.run(seed)
        for kw in result:
            assert kw == kw.lower()

    def test_all_stripped(self, p2, seed):
        result = p2.run(seed)
        for kw in result:
            assert kw == kw.strip()

    def test_no_empty_strings(self, p2, seed):
        result = p2.run(seed)
        for kw in result:
            assert kw.strip() != ""

    def test_no_duplicates(self, p2, seed):
        result = p2.run(seed)
        assert len(result) == len(set(result))

    def test_includes_google_suggestions(self, p2, seed):
        result = p2.run(seed)
        assert "black pepper benefits" in result

    def test_includes_youtube_suggestions(self, p2, seed):
        result = p2.run(seed)
        assert "black pepper video" in result or "black pepper tutorial" in result

    def test_includes_amazon_suggestions(self, p2, seed):
        result = p2.run(seed)
        assert "buy black pepper" in result or "organic black pepper" in result

    def test_includes_duckduckgo_suggestions(self, p2, seed):
        result = p2.run(seed)
        assert "black pepper health" in result or "black pepper side effects" in result

    def test_includes_reddit_suggestions(self, p2, seed):
        result = p2.run(seed)
        assert "black pepper reddit" in result or "best black pepper" in result

    def test_count_is_sum_of_sources(self, p2, seed):
        result = p2.run(seed)
        # google=3, youtube=2, amazon=3, ddg=2, reddit=2, questions=N → deduped
        assert len(result) >= 10


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION IN P2
# ─────────────────────────────────────────────────────────────────────────────

class TestP2Deduplication:
    def test_identical_from_two_sources_deduped(self, p2_instance, p1, monkeypatch):
        def same_google(kw): return [f"{kw} health"]
        def same_youtube(kw): return [f"{kw} health"]  # same as google
        def no_amazon(kw): return []
        def no_ddg(kw): return []
        def no_reddit(kw): return []
        monkeypatch.setattr(p2_instance, "_google_autosuggest", same_google)
        monkeypatch.setattr(p2_instance, "_youtube_autosuggest", same_youtube)
        monkeypatch.setattr(p2_instance, "_amazon_autosuggest", no_amazon)
        monkeypatch.setattr(p2_instance, "_duckduckgo", no_ddg)
        monkeypatch.setattr(p2_instance, "_reddit_titles", no_reddit)
        s = p1.run("black pepper")
        result = p2_instance.run(s)
        assert result.count("black pepper health") == 1

    def test_case_normalized_before_dedup(self, p2_instance, p1, monkeypatch):
        def mixed_case_google(kw): return ["Black Pepper Health", "black pepper health"]
        def no_other(kw): return []
        monkeypatch.setattr(p2_instance, "_google_autosuggest", mixed_case_google)
        monkeypatch.setattr(p2_instance, "_youtube_autosuggest", no_other)
        monkeypatch.setattr(p2_instance, "_amazon_autosuggest", no_other)
        monkeypatch.setattr(p2_instance, "_duckduckgo", no_other)
        monkeypatch.setattr(p2_instance, "_reddit_titles", no_other)
        s = p1.run("black pepper")
        result = p2_instance.run(s)
        count = sum(1 for kw in result if kw == "black pepper health")
        assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# MULTI SEED
# ─────────────────────────────────────────────────────────────────────────────

class TestP2MultiSeed:
    @pytest.mark.parametrize("spice", [
        "cinnamon", "turmeric", "ginger", "clove", "cardamom",
    ])
    def test_different_spice_seeds(self, p2, p1, spice):
        s = p1.run(spice)
        result = p2.run(s)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(spice in kw for kw in result
                   if kw not in [f"buy {spice}", f"organic {spice}", f"{spice} supplement"])

    def test_seed_keyword_included_in_output(self, p2, p1):
        s = p1.run("turmeric")
        result = p2.run(s)
        assert any("turmeric" in kw for kw in result)


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE COUNTING
# ─────────────────────────────────────────────────────────────────────────────

class TestP2SourceCounting:
    def test_five_sources_called(self, p2_instance, p1, monkeypatch):
        calls = {"google": 0, "youtube": 0, "amazon": 0, "ddg": 0, "reddit": 0}

        def track_google(kw): calls["google"] += 1; return []
        def track_youtube(kw): calls["youtube"] += 1; return []
        def track_amazon(kw): calls["amazon"] += 1; return []
        def track_ddg(kw): calls["ddg"] += 1; return []
        def track_reddit(kw): calls["reddit"] += 1; return []

        monkeypatch.setattr(p2_instance, "_google_autosuggest", track_google)
        monkeypatch.setattr(p2_instance, "_youtube_autosuggest", track_youtube)
        monkeypatch.setattr(p2_instance, "_amazon_autosuggest", track_amazon)
        monkeypatch.setattr(p2_instance, "_duckduckgo", track_ddg)
        monkeypatch.setattr(p2_instance, "_reddit_titles", track_reddit)

        s = p1.run("black pepper")
        p2_instance.run(s)

        assert calls["google"] == 1
        assert calls["youtube"] == 1
        assert calls["amazon"] == 1
        assert calls["ddg"] == 1
        assert calls["reddit"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
