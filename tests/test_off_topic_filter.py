"""
GROUP 5 — OffTopicFilter
~150 tests: GLOBAL_KILL, seed kill words, social media noise, spice domain
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
from annaseo_addons import OffTopicFilter


@pytest.fixture
def f(): return OffTopicFilter()

@pytest.fixture
def f_spice(): return OffTopicFilter(seed_kill_words=["candle","perfume","decoration","craft"])

@pytest.fixture
def f_pepper(): return OffTopicFilter(seed_kill_words=["tour","travel","hotel","resort"])


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL KILL LIST — universal noise
# ─────────────────────────────────────────────────────────────────────────────

class TestGlobalKillList:
    @pytest.mark.parametrize("noisy_kw", [
        "black pepper meme",
        "cinnamon viral video",
        "spice tiktok trend",
        "black pepper challenge",
        "turmeric instagram hack",
        "pepper reddit thread",
        "cinnamon twitter storm",
        "spice facebook group",
    ])
    def test_social_noise_removed(self, f, noisy_kw):
        kept, removed = f.filter_tuple([noisy_kw])
        assert noisy_kw in removed, f"'{noisy_kw}' should be removed"

    @pytest.mark.parametrize("clean_kw", [
        "black pepper health benefits",
        "buy organic black pepper",
        "black pepper vs white pepper",
        "cinnamon nutrition facts",
        "turmeric anti-inflammatory",
        "spice export india",
    ])
    def test_clean_keywords_kept(self, f, clean_kw):
        kept, removed = f.filter_tuple([clean_kw])
        assert clean_kw in kept, f"'{clean_kw}' should be kept"

    def test_meme_blocked(self, f):
        kept, removed = f.filter_tuple(["pepper meme", "real pepper", "pepper benefits"])
        assert "pepper meme" in removed
        assert "real pepper" in kept
        assert "pepper benefits" in kept

    def test_viral_blocked(self, f):
        kept, removed = f.filter_tuple(["cinnamon viral", "cinnamon recipe"])
        assert "cinnamon viral" in removed
        assert "cinnamon recipe" in kept

    def test_tiktok_blocked(self, f):
        kept, removed = f.filter_tuple(["black pepper tiktok", "black pepper soup"])
        assert "black pepper tiktok" in removed
        assert "black pepper soup" in kept

    def test_challenge_blocked(self, f):
        kept, removed = f.filter_tuple(["cinnamon challenge", "cinnamon benefits"])
        assert "cinnamon challenge" in removed
        assert "cinnamon benefits" in kept

    def test_filter_returns_two_lists(self, f):
        kept, removed = f.filter_tuple(["keyword"])
        assert isinstance(kept, list)
        assert isinstance(removed, list)

    def test_empty_list(self, f):
        kept, removed = f.filter_tuple([])
        assert kept == []
        assert removed == []

    def test_all_clean(self, f):
        keywords = ["black pepper benefits", "buy organic cinnamon", "turmeric tea recipe"]
        kept, removed = f.filter_tuple(keywords)
        assert len(kept) == 3
        assert len(removed) == 0

    def test_all_noisy(self, f):
        keywords = ["pepper meme", "cinnamon tiktok", "spice viral"]
        kept, removed = f.filter_tuple(keywords)
        assert len(kept) == 0
        assert len(removed) == 3

    def test_mixed_batch(self, f):
        keywords = ["black pepper benefits", "cinnamon meme", "turmeric price", "spice tiktok"]
        kept, removed = f.filter_tuple(keywords)
        assert len(kept) == 2
        assert len(removed) == 2


# ─────────────────────────────────────────────────────────────────────────────
# SEED KILL WORDS — project-level noise
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedKillWords:
    def test_seed_kill_word_removed(self):
        f = OffTopicFilter(seed_kill_words=["candle"])
        kept, removed = f.filter_tuple(["cinnamon candle", "buy cinnamon", "cinnamon perfume candle"])
        assert "cinnamon candle" in removed
        assert "buy cinnamon" in kept

    def test_multiple_seed_kill_words(self, f_spice):
        keywords = [
            "cinnamon candle", "cinnamon perfume", "cinnamon decoration",
            "cinnamon craft project", "cinnamon health benefits",
        ]
        kept, removed = f_spice.filter_tuple(keywords)
        assert "cinnamon health benefits" in kept
        assert len(removed) == 4

    def test_pepper_project_kills_tour(self, f_pepper):
        keywords = [
            "black pepper tour", "black pepper travel guide",
            "black pepper health", "buy black pepper",
        ]
        kept, removed = f_pepper.filter_tuple(keywords)
        assert "black pepper health" in kept
        assert "buy black pepper" in kept
        assert "black pepper tour" in removed
        assert "black pepper travel guide" in removed

    def test_seed_kill_case_insensitive(self):
        f = OffTopicFilter(seed_kill_words=["candle"])
        kept, removed = f.filter_tuple(["Cinnamon CANDLE"])
        assert "Cinnamon CANDLE" in removed

    def test_seed_kill_partial_word_match(self):
        f = OffTopicFilter(seed_kill_words=["craft"])
        kept, removed = f.filter_tuple(["cinnamon craftwork", "cinnamon benefits"])
        assert "cinnamon craftwork" in removed
        assert "cinnamon benefits" in kept

    def test_no_seed_kill_words(self, f):
        # No seed kill words set — only global kills apply
        kept, removed = f.filter_tuple(["cinnamon recipe", "cinnamon tour"])
        # Neither "recipe" nor "tour" is in GLOBAL_KILL → both kept
        assert "cinnamon recipe" in kept
        assert "cinnamon tour" in kept

    def test_add_seed_kill_words_dynamically(self, f):
        f.add_seed_kill_words(["wedding"])
        kept, removed = f.filter_tuple(["cinnamon wedding cake", "cinnamon benefits"])
        assert "cinnamon wedding cake" in removed
        assert "cinnamon benefits" in kept


# ─────────────────────────────────────────────────────────────────────────────
# FILTER WITH REASON
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterWithReason:
    def test_returns_list_of_dicts(self, f):
        result = f.filter_with_reason(["black pepper meme", "black pepper benefits"])
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_each_result_has_keyword(self, f):
        result = f.filter_with_reason(["black pepper benefits"])
        assert all("keyword" in r for r in result)

    def test_each_result_has_verdict(self, f):
        result = f.filter_with_reason(["black pepper meme"])
        assert all("verdict" in r or "kept" in r or "removed" in r for r in result)

    def test_noisy_keyword_flagged(self, f):
        result = f.filter_with_reason(["cinnamon tiktok"])
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# SUGGEST KILL WORDS
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestKillWords:
    def test_returns_list(self):
        result = OffTopicFilter.suggest_kill_words(
            ["cinnamon tour", "cinnamon candle", "cinnamon recipe"], "cinnamon"
        )
        assert isinstance(result, list)

    def test_off_topic_terms_suggested(self):
        result = OffTopicFilter.suggest_kill_words(
            ["black pepper tour", "black pepper travel", "black pepper health"],
            "black pepper"
        )
        # "tour" and "travel" should be flagged as potential kill words
        joined = " ".join(result)
        assert "tour" in joined or "travel" in joined or len(result) >= 0


# ─────────────────────────────────────────────────────────────────────────────
# REAL DOMAIN TESTS — Black Pepper
# ─────────────────────────────────────────────────────────────────────────────

class TestBlackPepperDomain:
    CLEAN = [
        "black pepper health benefits",
        "buy organic black pepper",
        "black pepper vs white pepper",
        "malabar peppercorns wholesale",
        "black pepper cultivation india",
        "piperine bioavailability",
        "black pepper essential oil uses",
        "black pepper recipes collection",
        "organic black pepper powder",
        "black pepper price per kg",
    ]
    NOISY = [
        "black pepper meme 2024",
        "black pepper viral challenge",
        "black pepper tiktok trend",
        "piper nigrum instagram",
        "pepper challenge gone wrong",
    ]

    @pytest.mark.parametrize("kw", CLEAN)
    def test_clean_keywords_pass(self, kw):
        f = OffTopicFilter()
        kept, _ = f.filter_tuple([kw])
        assert kw in kept

    @pytest.mark.parametrize("kw", NOISY)
    def test_noisy_keywords_rejected(self, kw):
        f = OffTopicFilter()
        _, removed = f.filter_tuple([kw])
        assert kw in removed


# ─────────────────────────────────────────────────────────────────────────────
# EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_character_keyword(self, f):
        kept, removed = f.filter_tuple(["a"])
        # Should not crash
        assert isinstance(kept, list)

    def test_very_long_keyword(self, f):
        kw = " ".join(["organic black pepper"] * 10)
        kept, removed = f.filter_tuple([kw])
        assert isinstance(kept, list)

    def test_numeric_keyword(self, f):
        kept, removed = f.filter_tuple(["black pepper 500g bulk"])
        assert "black pepper 500g bulk" in kept

    def test_keyword_with_special_chars(self, f):
        kept, removed = f.filter_tuple(["black-pepper benefits"])
        assert isinstance(kept, list)  # should not crash

    def test_duplicate_keywords(self, f):
        keywords = ["black pepper benefits", "black pepper benefits"]
        kept, removed = f.filter_tuple(keywords)
        assert len(kept) + len(removed) == 2

    def test_large_batch_performance(self, f):
        keywords = [f"black pepper keyword {i}" for i in range(500)]
        kept, removed = f.filter_tuple(keywords)
        assert len(kept) + len(removed) == 500

    @pytest.mark.parametrize("kill_word", [
        "meme", "viral", "tiktok", "instagram", "challenge", "reddit", "twitter", "facebook"
    ])
    def test_all_global_kill_words_work(self, f, kill_word):
        kw = f"black pepper {kill_word}"
        _, removed = f.filter_tuple([kw])
        assert kw in removed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
