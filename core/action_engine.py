from core.selection_engine import pick_best_variant


def decide_actions(experiment: dict, db=None, context=None, meta_features=None):
    variants = experiment.get("variants", [])
    winner, score = pick_best_variant(variants, db=db, context=context, meta_features=meta_features)

    actions = []

    if winner:
        winner_id = winner.get("id") or winner.get("variant")

        for v in variants:
            vid = v.get("id") or v.get("variant")
            if vid != winner_id and v.get("sample_size", 0) >= 10:
                if v.get("mean_roi", 0) < winner.get("mean_roi", 0) * 0.5:
                    actions.append({"type": "pause_variant", "variant_id": vid})

        if winner_id is not None:
            actions.append({"type": "promote_winner", "variant_id": winner_id, "confidence": score})

    return actions


def execute_actions(db, experiment_id: int, actions: list):
    executed = []

    for action in actions:
        if action["type"] == "pause_variant":
            db.execute(
                "UPDATE strategy_experiment_assignments SET active=0 WHERE experiment_id=? AND variant=?",
                (experiment_id, action["variant_id"]),
            )
            executed.append(action)

        elif action["type"] == "promote_winner":
            db.execute(
                "UPDATE strategy_experiments SET forced_variant=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (action["variant_id"], experiment_id),
            )
            executed.append(action)

    db.commit()
    return executed
