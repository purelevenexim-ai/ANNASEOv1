from core.autopilot import run_autopilot_once
from core.experiment import create_experiment
from core.experiment import record_result
from services.db_utils import row_to_dict
from main import get_db


def test_autopilot_promotes_winner():
    db = get_db()
    db.execute("DELETE FROM strategy_experiments")
    db.execute("DELETE FROM strategy_experiment_results")
    db.execute("DELETE FROM strategy_experiment_assignments")
    db.commit()

    exp = create_experiment(db, name="auto-test", variants=["A", "B"])
    exp_id = exp["id"]

    for i in range(10):
        record_result(db, exp_id, "A", f"jobA{i}", 1.0 + (i * 0.01))
    for i in range(10):
        record_result(db, exp_id, "B", f"jobB{i}", 0.1 + (i * 0.005))

    # Add assignment for B to be paused by autopilot
    db.execute("INSERT INTO strategy_experiment_assignments (experiment_id, variant, active) VALUES (?, ?, 1)", (exp_id, "B"))
    db.commit()

    ok = run_autopilot_once(mode="auto")
    assert ok

    row = db.execute("SELECT forced_variant FROM strategy_experiments WHERE id = ?", (exp_id,)).fetchone()
    assert row is not None
    assert row["forced_variant"] == "A"

    paused = db.execute("SELECT active FROM strategy_experiment_assignments WHERE experiment_id = ? AND variant = ?", (exp_id, "B")).fetchone()
    assert paused is not None
    assert paused["active"] == 0
