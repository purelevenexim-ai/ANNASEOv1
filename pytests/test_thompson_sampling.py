import random

from core.thompson_sampling import sample_beta, pick_variant_thompson


def test_sample_beta_returns_float():
    val = sample_beta(1, 1)
    assert isinstance(val, float)
    assert 0.0 <= val <= 1.0


def test_pick_variant_thompson_with_variants():
    random.seed(0)
    variants = [
        {"id": "A", "sample_size": 100, "success_count": 80},
        {"id": "B", "sample_size": 100, "success_count": 10},
    ]

    winner = pick_variant_thompson(variants)
    assert winner is not None
    assert winner["id"] in {"A", "B"}
