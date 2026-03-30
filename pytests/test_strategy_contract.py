from services.strategy_normalizer import normalize_strategy, empty_strategy
from services.strategy_validator import validate_strategy


def test_strategy_normalization_legacy_format():
    raw = {
        "market_analysis": {"persona": "buyer"},
        "content_angles": ["angle1"],
        "article_outline": [{"heading": "Intro", "points": ["p1"]}],
        "internal_link_map": [{"anchor": "a", "target": "t"}],
        "seo_scores": {"difficulty": 42},
    }

    strategy = normalize_strategy(raw)

    assert strategy["audience"] == {"persona": "buyer"}
    assert strategy["angles"] == ["angle1"]
    assert strategy["outline"] == [{"heading": "Intro", "points": ["p1"]}]
    assert strategy["links"] == [{"anchor": "a", "target": "t"}]
    assert strategy["scores"] == {"difficulty": 42}

    validate_strategy(strategy)


def test_strategy_normalization_empty():
    strategy = normalize_strategy(None)
    assert strategy == empty_strategy()
    validate_strategy(strategy)
