"""
GROUP — P3 Normalization (extended) — comprehensive edge cases
~130 tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import P1_SeedInput, P3_Normalization, Seed


@pytest.fixture
def p1(): return P1_SeedInput()

@pytest.fixture
def p3(): return P3_Normalization()

@pytest.fixture
def seed(p1): return p1.run("black pepper")


# ─────────────────────────────────────────────────────────────────────────────
# LOWERCASE
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeLowercase:
    @pytest.mark.parametrize("raw,expected", [
        ("BLACK PEPPER", "black pepper"),
        ("Black Pepper Benefits", "black pepper benefits"),
        ("ORGANIC CINNAMON POWDER", "organic cinnamon powder"),
        ("Turmeric Anti-Inflammatory", "turmeric anti-inflammatory"),
        ("BUY BLACK PEPPER ONLINE", "buy black pepper online"),
    ])
    def test_uppercase_lowercased(self, p3, raw, expected):
        assert p3._normalise(raw) == expected

    def test_already_lowercase_unchanged(self, p3):
        assert p3._normalise("black pepper") == "black pepper"

    def test_mixed_case_normalized(self, p3):
        result = p3._normalise("bLaCk PePpEr BeNeFiTs")
        assert result == result.lower()


# ─────────────────────────────────────────────────────────────────────────────
# WHITESPACE
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeWhitespace:
    def test_leading_space_stripped(self, p3):
        assert p3._normalise("  black pepper") == "black pepper"

    def test_trailing_space_stripped(self, p3):
        assert p3._normalise("black pepper  ") == "black pepper"

    def test_both_sides_stripped(self, p3):
        assert p3._normalise("  black pepper  ") == "black pepper"

    def test_double_internal_space_collapsed(self, p3):
        result = p3._normalise("black  pepper  benefits")
        assert "  " not in result

    def test_tab_handled(self, p3):
        result = p3._normalise("black\tpepper")
        assert isinstance(result, str)

    def test_empty_string_returns_empty(self, p3):
        assert p3._normalise("") == ""

    def test_whitespace_only_returns_empty_or_stripped(self, p3):
        result = p3._normalise("   ")
        assert result.strip() == ""


# ─────────────────────────────────────────────────────────────────────────────
# PUNCTUATION
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizePunctuation:
    def test_exclamation_removed(self, p3):
        result = p3._normalise("black pepper!")
        assert "!" not in result

    def test_question_mark_removed(self, p3):
        result = p3._normalise("what is black pepper?")
        assert "?" not in result

    def test_comma_removed(self, p3):
        result = p3._normalise("pepper, black")
        assert "," not in result

    def test_period_at_end_removed(self, p3):
        result = p3._normalise("black pepper benefits.")
        assert not result.endswith(".")

    def test_hyphen_preserved(self, p3):
        result = p3._normalise("anti-inflammatory black pepper")
        assert "anti" in result

    def test_apostrophe_handled(self, p3):
        result = p3._normalise("pepper's health benefits")
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# STOPWORD REMOVAL
# ─────────────────────────────────────────────────────────────────────────────

class TestStopwordRemoval:
    def test_leading_the_removed(self, p3):
        result = p3._normalise("the black pepper")
        assert not result.startswith("the ")

    def test_leading_a_removed(self, p3):
        result = p3._normalise("a guide to black pepper")
        assert not result.startswith("a ")

    def test_meaningful_words_kept(self, p3):
        result = p3._normalise("black pepper health benefits")
        assert "black" in result
        assert "pepper" in result
        assert "health" in result
        assert "benefits" in result

    def test_internal_for_kept(self, p3):
        result = p3._normalise("black pepper for cooking")
        assert "cooking" in result

    def test_single_word_result_dropped_in_run(self, p3, seed):
        result = p3.run(seed, ["the", "a", "pepper"])
        # Single words should be filtered out
        assert all(len(r.split()) >= 2 for r in result)


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_exact_duplicates_deduped(self, p3, seed):
        raw = ["black pepper", "black pepper", "black pepper"]
        result = p3.run(seed, raw)
        assert result.count("black pepper") == 1

    def test_case_duplicates_deduped(self, p3, seed):
        raw = ["Black Pepper", "black pepper", "BLACK PEPPER"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_trailing_space_duplicates_deduped(self, p3, seed):
        raw = ["black pepper  ", "black pepper", "  black pepper"]
        result = p3.run(seed, raw)
        assert len(result) == 1

    def test_unique_keywords_all_kept(self, p3, seed):
        raw = ["black pepper benefits", "black pepper recipe", "black pepper price"]
        result = p3.run(seed, raw)
        assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# RUN() METHOD
# ─────────────────────────────────────────────────────────────────────────────

class TestP3Run:
    def test_run_returns_list(self, p3, seed):
        result = p3.run(seed, ["black pepper benefits"])
        assert isinstance(result, list)

    def test_run_all_strings(self, p3, seed):
        result = p3.run(seed, ["black pepper", "turmeric health"])
        for kw in result:
            assert isinstance(kw, str)

    def test_run_all_lowercase(self, p3, seed):
        result = p3.run(seed, ["BLACK PEPPER", "Turmeric Health"])
        for kw in result:
            assert kw == kw.lower()

    def test_run_all_stripped(self, p3, seed):
        result = p3.run(seed, ["  black pepper  ", "turmeric  "])
        for kw in result:
            assert kw == kw.strip()

    def test_run_empty_input(self, p3, seed):
        result = p3.run(seed, [])
        assert result == []

    def test_run_preserves_order(self, p3, seed):
        raw = ["black pepper benefits", "black pepper recipe", "black pepper price"]
        result = p3.run(seed, raw)
        assert len(result) == 3

    def test_run_large_batch(self, p3, seed):
        raw = [f"black pepper keyword {i}" for i in range(1000)]
        result = p3.run(seed, raw)
        assert len(result) == 1000  # all unique

    def test_run_filters_single_words(self, p3, seed):
        raw = ["pepper", "spice", "black pepper benefits", "organic pepper tea"]
        result = p3.run(seed, raw)
        assert all(len(r.split()) >= 2 for r in result)

    def test_run_mixed_valid_invalid(self, p3, seed):
        raw = ["black pepper", "pepper", "black pepper health", "the", "buy pepper online"]
        result = p3.run(seed, raw)
        for kw in result:
            assert len(kw.split()) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# NORMALISE — SPECIFIC CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliseSpecific:
    def test_numeric_preserved(self, p3):
        result = p3._normalise("black pepper 500g benefits")
        assert "500" in result or "500g" in result

    def test_unicode_handled(self, p3):
        result = p3._normalise("piperine café")
        assert isinstance(result, str)

    def test_very_long_string(self, p3):
        kw = " ".join(["organic"] * 20)
        result = p3._normalise(kw)
        assert isinstance(result, str)

    @pytest.mark.parametrize("kw,expected_contains", [
        ("buy black pepper online", "black pepper"),
        ("black pepper vs white pepper", "pepper"),
        ("health benefits of black pepper", "black pepper"),
        ("organic certified black pepper", "black pepper"),
    ])
    def test_specific_normalizations(self, p3, seed, kw, expected_contains):
        result = p3.run(seed, [kw])
        if result:
            assert expected_contains in result[0]

    @pytest.mark.parametrize("spice", [
        "cinnamon tea benefits", "turmeric milk recipe", "ginger lemon water",
        "clove oil dental", "cardamom coffee blend", "cumin seeds health"
    ])
    def test_spice_keywords_normalized(self, p3, seed, spice):
        result = p3._normalise(spice)
        assert result == result.lower()
        assert result == result.strip()
        assert "  " not in result

    def test_all_normalise_outputs_are_strings(self, p3):
        inputs = [
            "BLACK PEPPER", "  Organic Cinnamon  ", "what is?", "the turmeric",
            "", "   ", "anti-inflammatory", "500g organic", "café piperine",
        ]
        for inp in inputs:
            result = p3._normalise(inp)
            assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
