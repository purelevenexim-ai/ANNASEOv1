from core.confidence_engine import compute_confidence
from core.selection_engine import pick_best_variant


def test_compute_confidence_no_data():
    c = compute_confidence(1.0, 1.0, 1)
    assert c == 0.0


def test_compute_confidence_common_case():
    c = compute_confidence(1.5, 0.5, 20)
    assert 0.0 < c <= 1.0


def test_pick_best_variant():
    variants = [
        {"id": "A", "mean_roi": 1.2, "variance": 0.2, "sample_size": 20, "weight": 0.8},
        {"id": "B", "mean_roi": 0.5, "variance": 0.1, "sample_size": 25, "weight": 0.9},
    ]

    best, score = pick_best_variant(variants)
    assert best is not None
    assert score > 0
    assert best["id"] in ["A", "B"]
