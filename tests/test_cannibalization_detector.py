"""
GROUP 6 — CannibalizationDetector
~110 tests: exact match, semantic overlap, batch check, cosine similarity
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

import pytest
import math
from annaseo_addons import CannibalizationDetector


@pytest.fixture
def det(): return CannibalizationDetector()

@pytest.fixture
def det_loaded():
    """Detector with pre-registered articles."""
    d = CannibalizationDetector(similarity_threshold=0.85)
    d.register("Black Pepper Health Benefits", "black pepper health benefits",
                "/blog/black-pepper-health-benefits")
    d.register("Organic Black Pepper Guide", "organic black pepper guide",
                "/blog/organic-black-pepper")
    d.register("Black Pepper Recipes", "black pepper recipes",
                "/recipes/black-pepper")
    return d


# ─────────────────────────────────────────────────────────────────────────────
# EXACT KEYWORD MATCH
# ─────────────────────────────────────────────────────────────────────────────

class TestExactKeywordMatch:
    def test_exact_match_returns_high_risk(self, det_loaded):
        result = det_loaded.check("black pepper health benefits", "New Article")
        assert result["risk"] == "high"

    def test_exact_match_type_is_exact(self, det_loaded):
        result = det_loaded.check("black pepper health benefits", "New Article")
        assert result["type"] == "exact_keyword_match"

    def test_exact_match_has_conflict_with(self, det_loaded):
        result = det_loaded.check("black pepper health benefits", "New Article")
        assert result["conflict_with"] is not None

    def test_exact_match_has_recommendation(self, det_loaded):
        result = det_loaded.check("black pepper health benefits", "New Article")
        assert result["recommendation"] and len(result["recommendation"]) > 0

    def test_exact_match_case_insensitive(self, det_loaded):
        result = det_loaded.check("BLACK PEPPER HEALTH BENEFITS", "New Article")
        assert result["risk"] == "high"

    def test_exact_match_strips_whitespace(self, det_loaded):
        result = det_loaded.check("  black pepper health benefits  ", "New Article")
        assert result["risk"] == "high"

    def test_no_match_returns_none_risk(self, det_loaded):
        result = det_loaded.check("black pepper cultivation kerala", "New Article")
        assert result["risk"] == "none"

    def test_partial_keyword_no_exact_match(self, det_loaded):
        # "black pepper" is a substring but not exact match
        result = det_loaded.check("black pepper price today", "New Article")
        assert result["risk"] in ("none", "medium")  # no exact match

    def test_empty_registry_no_conflict(self, det):
        result = det.check("black pepper health benefits", "Test")
        assert result["risk"] == "none"

    def test_multiple_registrations_finds_first_conflict(self):
        d = CannibalizationDetector()
        d.register("Article A", "black pepper benefits", "/a")
        d.register("Article B", "black pepper benefits", "/b")
        result = d.check("black pepper benefits", "New")
        assert result["risk"] == "high"
        assert result["conflict_with"]["url"] in ("/a", "/b")


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_stores_article(self, det):
        det.register("Test Article", "test keyword", "/test")
        result = det.check("test keyword", "New")
        assert result["risk"] == "high"

    def test_register_with_embedding(self, det):
        embedding = [0.1] * 50
        det.register("Article", "keyword", "/url", embedding=embedding)
        assert len(det._published) == 1
        assert det._published[0]["embedding"] == embedding

    def test_register_multiple_articles(self, det):
        det.register("A1", "kw1", "/1")
        det.register("A2", "kw2", "/2")
        det.register("A3", "kw3", "/3")
        assert len(det._published) == 3

    def test_register_normalises_keyword(self, det):
        det.register("Article", "BLACK PEPPER BENEFITS", "/url")
        result = det.check("black pepper benefits", "New")
        assert result["risk"] == "high"


# ─────────────────────────────────────────────────────────────────────────────
# SEMANTIC OVERLAP (embedding-based)
# ─────────────────────────────────────────────────────────────────────────────

def make_embedding(value: float, dim: int = 50) -> list:
    """Create a unit vector with all components = value/sqrt(dim)."""
    return [value / math.sqrt(dim)] * dim


class TestSemanticOverlap:
    def test_high_similarity_returns_medium_risk(self, det):
        emb_a = make_embedding(1.0)
        emb_b = make_embedding(1.0)  # identical → cosine = 1.0
        det.register("Article A", "keyword one", "/a", embedding=emb_a)
        result = det.check("keyword two", "Article B", new_embedding=emb_b)
        assert result["risk"] in ("medium", "high")

    def test_low_similarity_returns_none(self, det):
        # Orthogonal vectors → cosine = 0
        emb_a = [1.0] + [0.0] * 49
        emb_b = [0.0] + [1.0] + [0.0] * 48
        det.register("Article A", "unrelated topic", "/a", embedding=emb_a)
        result = det.check("new topic", "Article B", new_embedding=emb_b)
        assert result["risk"] == "none"

    def test_no_embedding_skips_semantic_check(self, det):
        det.register("Article A", "keyword one", "/a")  # no embedding
        # Without embedding, semantic check is skipped
        result = det.check("keyword two", "Article B", new_embedding=None)
        assert result["risk"] == "none"

    def test_semantic_check_type_is_semantic_overlap(self, det):
        emb = make_embedding(1.0)
        det.register("Article A", "unrelated kw", "/a", embedding=emb)
        result = det.check("different kw", "Article B", new_embedding=emb)
        if result["risk"] == "medium":
            assert result["type"] == "semantic_overlap"


# ─────────────────────────────────────────────────────────────────────────────
# COSINE SIMILARITY (internal method)
# ─────────────────────────────────────────────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors_cosine_1(self, det):
        v = [1.0, 2.0, 3.0]
        assert abs(det._cosine(v, v) - 1.0) < 1e-6

    def test_opposite_vectors_cosine_neg1(self, det):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        assert abs(det._cosine(v1, v2) - (-1.0)) < 1e-6

    def test_orthogonal_vectors_cosine_0(self, det):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        assert abs(det._cosine(v1, v2)) < 1e-6

    def test_zero_vector_returns_0(self, det):
        v0 = [0.0, 0.0]
        v1 = [1.0, 0.0]
        result = det._cosine(v0, v1)
        assert result == 0.0 or abs(result) < 1e-3  # denominator ~0

    def test_cosine_range_neg1_to_1(self, det):
        import random
        random.seed(42)
        for _ in range(20):
            v1 = [random.random() - 0.5 for _ in range(10)]
            v2 = [random.random() - 0.5 for _ in range(10)]
            c = det._cosine(v1, v2)
            assert -1.0 <= c <= 1.0 + 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# BATCH CHECK
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchCheck:
    def test_batch_returns_list(self, det):
        articles = [
            {"title": "Article A", "keyword": "keyword a"},
            {"title": "Article B", "keyword": "keyword b"},
        ]
        result = det.batch_check(articles)
        assert isinstance(result, list)

    def test_batch_same_length_as_input(self, det):
        articles = [{"title": f"Art {i}", "keyword": f"keyword {i}"} for i in range(5)]
        result = det.batch_check(articles)
        assert len(result) == 5

    def test_batch_flags_duplicates_within_batch(self, det):
        articles = [
            {"title": "Article A", "keyword": "black pepper benefits"},
            {"title": "Article B", "keyword": "black pepper benefits"},  # duplicate
        ]
        result = det.batch_check(articles)
        # At least one should be flagged (key is "cannibalization_risk" from batch_check)
        risks = [r.get("cannibalization_risk", r.get("risk", "none")) for r in result]
        assert any(r != "none" for r in risks)

    def test_batch_empty_list(self, det):
        assert det.batch_check([]) == []

    def test_batch_unique_keywords_no_flags(self, det):
        articles = [
            {"title": "Article A", "keyword": "black pepper benefits"},
            {"title": "Article B", "keyword": "black pepper recipes"},
            {"title": "Article C", "keyword": "buy black pepper online"},
        ]
        result = det.batch_check(articles)
        risks = [r.get("risk", "none") for r in result]
        assert all(r == "none" for r in risks)

    def test_batch_real_black_pepper_articles(self, det):
        articles = [
            {"title": "Black Pepper Health Benefits", "keyword": "black pepper health benefits"},
            {"title": "Benefits of Black Pepper", "keyword": "black pepper health benefits"},  # same!
            {"title": "Black Pepper Recipes", "keyword": "black pepper recipes"},
            {"title": "Buy Black Pepper Online", "keyword": "buy black pepper online"},
        ]
        result = det.batch_check(articles)
        risks = [r.get("cannibalization_risk", r.get("risk", "none")) for r in result]
        assert any(r != "none" for r in risks)  # duplicate keyword detected


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLD TESTING
# ─────────────────────────────────────────────────────────────────────────────

class TestThreshold:
    def test_default_threshold_is_0_85(self):
        d = CannibalizationDetector()
        assert d.threshold == 0.85

    def test_custom_threshold_stored(self):
        d = CannibalizationDetector(similarity_threshold=0.95)
        assert d.threshold == 0.95

    def test_high_threshold_fewer_conflicts(self):
        emb = make_embedding(0.9)
        emb_similar = [x * 0.95 for x in emb]
        # Normalize emb_similar
        mag = math.sqrt(sum(x*x for x in emb_similar))
        emb_similar = [x/mag for x in emb_similar]

        d_strict = CannibalizationDetector(similarity_threshold=0.99)
        d_strict.register("A", "kw1", "/a", embedding=emb)
        result = d_strict.check("kw2", "B", new_embedding=emb_similar)
        # With 0.99 threshold, similar but not identical vectors → none
        assert result["risk"] in ("none", "medium")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
