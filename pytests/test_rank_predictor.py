from services.rank_predictor import extract_features, compute_difficulty, compute_probability, compute_opportunity, make_decision, predict_ranking


def test_rank_predictor_basic():
    pages = [
        {"word_count": 1800, "headings": ["h1", "h2"], "score": 15},
        {"word_count": 2200, "headings": ["h1", "h2", "h3"], "score": 18},
        {"word_count": 2000, "headings": ["h1"], "score": 17},
    ]

    features = extract_features(pages)
    assert isinstance(features, dict)
    assert features["number_of_pages"] == 3

    difficulty = compute_difficulty(features)
    probability = compute_probability(features)
    opportunity = compute_opportunity(probability, difficulty)
    decision = make_decision(opportunity)

    assert 0 <= difficulty <= 100
    assert 0 <= probability <= 100
    assert 0 <= opportunity <= 100
    assert decision in {"GO", "MEDIUM", "SKIP"}

    result = predict_ranking(pages)
    assert result["features"]["number_of_pages"] == 3
    assert result["decision"] in {"GO", "MEDIUM", "SKIP"}
