from core.action_engine import decide_actions


def test_decide_actions_promote_and_pause():
    exp = {
        "variants": [
            {"id": "A", "mean_roi": 2.0, "variance": 0.5, "sample_size": 20, "weight": 0.9},
            {"id": "B", "mean_roi": 0.4, "variance": 0.3, "sample_size": 20, "weight": 0.8},
            {"id": "C", "mean_roi": 0.6, "variance": 0.1, "sample_size": 8, "weight": 0.7},
        ]
    }

    actions = decide_actions(exp)
    assert any(a["type"] == "promote_winner" for a in actions)
    assert any(a["type"] == "pause_variant" for a in actions)
