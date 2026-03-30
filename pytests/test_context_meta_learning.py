import json
from main import get_db
from core.experiment import create_experiment, record_result, get_experiment_summary
from core.global_memory_engine import compute_global_score
from core.meta_learning import compute_meta_score
from core.selection_engine import pick_best_variant


def test_context_aware_memory_and_meta_learning():
    db = get_db()
    db.execute("DELETE FROM strategy_experiments")
    db.execute("DELETE FROM strategy_experiment_results")
    db.execute("DELETE FROM global_strategy_memory")
    db.execute("DELETE FROM meta_learning")
    db.commit()

    exp = create_experiment(db, name="ctx-test", variants=["A", "B"], payload={"context": {"niche": "food", "country": "india", "intent": "commercial"}})
    exp_id = exp["id"]

    # variant A is positive, B is negative
    record_result(db, exp_id, "A", "jobA1", 1.0, extra_context={"category": "food", "country": "india", "intent": "commercial"}, serp_data={"listicle_ratio": 0.7})
    record_result(db, exp_id, "A", "jobA2", 1.2, extra_context={"category": "food", "country": "india", "intent": "commercial"}, serp_data={"listicle_ratio": 0.8})
    record_result(db, exp_id, "B", "jobB1", -0.5, extra_context={"category": "food", "country": "india", "intent": "commercial"}, serp_data={"listicle_ratio": 0.2})

    variants = get_experiment_summary(db, exp_id)
    assert any(v["variant"] == "A" for v in variants)
    assert any(v["variant"] == "B" for v in variants)

    context = {"niche": "food", "country": "india", "intent": "commercial"}

    # Ensure global score and meta after updates produce >0.0
    score_a = compute_global_score(db, {"variant": "A"}, context)
    score_b = compute_global_score(db, {"variant": "B"}, context)
    assert score_a > score_b

    result_variant, final_score = pick_best_variant(variants, db=db, context=context)
    assert result_variant is not None
    assert result_variant["variant"] == "A"

    meta_features = {"intent": "commercial", "format": "standard"}
    meta_score = compute_meta_score(db, meta_features)
    assert 0.0 <= meta_score <= 1.0
