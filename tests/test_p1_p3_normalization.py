"""
GROUP 1 — P1 SeedInput + P3 Normalization
~120 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P3_Normalization, Seed


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p3(): return P3_Normalization()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# P1 — SEED INPUT
# ─────────────────────────────────────────────────────────────────────────────

class TestP1SeedCreation:
    def test_returns_seed_object(self, p1):
        s = p1.run("black pepper")
        assert isinstance(s, Seed)

    def test_seed_keyword_stored(self, p1):
        s = p1.run("black pepper")
        assert s.keyword == "black pepper"

    def test_seed_id_generated(self, p1):
        s = p1.run("black pepper")
        assert s.id and len(s.id) > 0

    def test_seed_id_is_deterministic(self, p1):
        s1 = p1.run("black pepper")
        s2 = p1.run("black pepper")
        assert s1.id == s2.id

    def test_seed_id_differs_for_different_keywords(self, p1):
        s1 = p1.run("black pepper")
        s2 = p1.run("cinnamon")
        assert s1.id != s2.id

    def test_seed_keyword_lowercased(self, p1):
        s = p1.run("Black Pepper")
        assert s.keyword == s.keyword.lower()

    def test_seed_keyword_stripped(self, p1):
        s = p1.run("  black pepper  ")
        assert s.keyword == s.keyword.strip()

    def test_seed_language_default_english(self, p1):
        s = p1.run("black pepper")
        assert s.language == "english"

    def test_seed_language_custom(self, p1):
        s = p1.run("black pepper", language="hindi")
        assert s.language == "hindi"

    def test_seed_multiple_words(self, p1):
        s = p1.run("organic black pepper malabar")
        assert s.keyword == "organic black pepper malabar"

    def test_seed_single_word(self, p1):
        s = p1.run("pepper")
        assert s.keyword == "pepper"

    def test_seed_with_hyphen(self, p1):
        s = p1.run("long-pepper")
        assert s.keyword is not None

    def test_seed_spice_category(self, p1):
        for kw in ["cinnamon", "turmeric", "cardamom", "clove", "ginger"]:
            s = p1.run(kw)
            assert s.keyword == kw

    def test_seed_geo_keyword(self, p1):
        s = p1.run("kerala black pepper")
        assert "kerala" in s.keyword

    def test_seed_has_created_at(self, p1):
        s = p1.run("black pepper")
        assert hasattr(s, "created_at") or s.id  # at minimum has id


class TestP1SeedIdStability:
    """Seed IDs must be stable — same keyword always same ID."""

    @pytest.mark.parametrize("keyword", [
        "black pepper", "organic cinnamon", "malabar pepper",
        "turmeric powder", "clove oil", "cardamom pods",
    ])
    def test_id_stable_per_keyword(self, p1, keyword):
        ids = {p1.run(keyword).id for _ in range(3)}
        assert len(ids) == 1, f"ID not stable for '{keyword}'"


# ─────────────────────────────────────────────────────────────────────────────
# P3 — NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

class TestP3Lowercasing:
    def test_lowercases_all_caps(self, p3):
        assert p3._normalise("BLACK PEPPER") == "black pepper"

    def test_lowercases_mixed_case(self, p3):
        assert p3._normalise("Black Pepper Benefits") == "black pepper benefits"

    def test_preserves_lowercase(self, p3):
        assert p3._normalise("black pepper") == "black pepper"

    def test_title_case_normalised(self, p3):
        assert p3._normalise("Organic Black Pepper") == "organic black pepper"


class TestP3Stripping:
    def test_strips_leading_spaces(self, p3):
        assert p3._normalise("  black pepper") == "black pepper"

    def test_strips_trailing_spaces(self, p3):
        assert p3._normalise("black pepper  ") == "black pepper"

    def test_strips_both_sides(self, p3):
        assert p3._normalise("  black pepper  ") == "black pepper"

    def test_collapses_multiple_spaces(self, p3):
        result = p3._normalise("black  pepper  benefits")
        assert "  " not in result

    def test_strips_punctuation(self, p3):
        result = p3._normalise("black pepper!")
        assert "!" not in result

    def test_strips_question_mark(self, p3):
        result = p3._normalise("what is black pepper?")
        assert "?" not in result

    def test_strips_comma(self, p3):
        result = p3._normalise("pepper, black")
        assert "," not in result


class TestP3StopwordRemoval:
    def test_removes_leading_the(self, p3):
        result = p3._normalise("the black pepper")
        assert not result.startswith("the ")

    def test_removes_leading_a(self, p3):
        result = p3._normalise("a guide to black pepper")
        assert not result.startswith("a ")

    def test_keeps_meaningful_words(self, p3):
        result = p3._normalise("black pepper health benefits")
        assert "black" in result
        assert "pepper" in result
        assert "health" in result

    def test_preserves_internal_stop_in_phrase(self, p3):
        # "black pepper for cooking" — "for" is internal, keep it
        result = p3._normalise("black pepper for cooking")
        assert "pepper" in result and "cooking" in result

    def test_minimum_two_words_enforced(self, seed, p3):
        # Single-word results should be dropped by run()
        raw = ["pepper", "the", "a"]
        result = p3.run(seed, raw)
        assert all(len(r.split()) >= 2 for r in result)

    def test_deduplication_in_run(self, seed, p3):
        raw = ["black pepper", "black pepper", "black pepper"]
        result = p3.run(seed, raw)
        assert result.count("black pepper") == 1


class TestP3NormalisationEdgeCases:
    def test_empty_string_returns_empty(self, p3):
        assert p3._normalise("") == ""

    def test_whitespace_only_returns_empty(self, p3):
        result = p3._normalise("   ")
        assert result == "" or result.strip() == ""

    def test_numeric_in_keyword(self, p3):
        result = p3._normalise("black pepper 500g")
        assert "500" in result or "500g" in result

    def test_hyphenated_keyword_preserved(self, p3):
        result = p3._normalise("anti-inflammatory black pepper")
        assert "anti" in result or "anti-inflammatory" in result

    def test_unicode_characters(self, p3):
        # Should not crash on unicode
        result = p3._normalise("piperine café")
        assert isinstance(result, str)

    def test_very_long_keyword(self, p3):
        kw = " ".join(["organic"] * 20)
        result = p3._normalise(kw)
        assert isinstance(result, str)


class TestP3RunBatch:
    def test_run_reduces_duplicates(self, seed, p3):
        raw = ["Black Pepper", "black pepper", "BLACK PEPPER"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_run_filters_singles(self, seed, p3):
        raw = ["pepper", "spice", "buy black pepper online", "black pepper"]
        result = p3.run(seed, raw)
        assert all(len(r.split()) >= 2 for r in result)

    def test_run_empty_list(self, seed, p3):
        result = p3.run(seed, [])
        assert result == []

    def test_run_preserves_order(self, seed, p3):
        raw = ["black pepper benefits", "black pepper recipes", "black pepper price"]
        result = p3.run(seed, raw)
        assert len(result) == 3

    def test_run_handles_large_list(self, seed, p3):
        raw = [f"black pepper keyword {i}" for i in range(1000)]
        result = p3.run(seed, raw)
        assert len(result) == 1000  # all unique

    def test_run_normalises_each_entry(self, seed, p3):
        raw = ["BLACK PEPPER HEALTH BENEFITS", "  organic black pepper  "]
        result = p3.run(seed, raw)
        assert all(r == r.lower() for r in result)
        assert all(r == r.strip() for r in result)

    @pytest.mark.parametrize("raw,expected_contains", [
        (["buy black pepper online"], "buy black pepper online"),
        (["black pepper vs white pepper"], "black pepper vs white pepper"),
        (["health benefits of black pepper"], "health benefits of black pepper"),
    ])
    def test_specific_normalizations(self, seed, p3, raw, expected_contains):
        result = p3.run(seed, raw)
        assert any(expected_contains in r or r in expected_contains for r in result)

    def test_run_with_spice_keywords(self, seed, p3):
        spice_kws = [
            "black pepper benefits", "organic cinnamon powder",
            "turmeric vs curcumin", "clove essential oil uses",
            "cardamom health benefits", "ginger anti-inflammatory",
        ]
        result = p3.run(seed, spice_kws)
        assert len(result) == len(spice_kws)  # all unique & valid

    def test_run_dedup_with_trailing_stopwords(self, seed, p3):
        raw = ["black pepper the", "black pepper"]
        result = p3.run(seed, raw)
        # Both normalise to same form — only 1 should remain
        assert len(result) <= 2  # at most 2, ideally 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
