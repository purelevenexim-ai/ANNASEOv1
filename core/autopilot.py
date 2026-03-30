import os
import sqlite3
import time
import logging
from pathlib import Path

from core.action_engine import decide_actions, execute_actions
from core.experiment import get_experiment_summary, list_experiments

logger = logging.getLogger("autopilot")

DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn




def run_autopilot_once(mode: str = "auto"):
    db = None
    try:
        db = _get_db()
        experiments = [e for e in list_experiments(db) if e.get("status") == "running"]

        for exp in experiments:
            exp_id = exp.get("id")
            if not exp_id:
                continue

            variants = get_experiment_summary(db, exp_id)
            actions = decide_actions({"id": exp_id, "variants": variants})

            if not actions:
                continue

            logger.info(f"Autopilot {mode}: experiment_id={exp_id} actions={actions}")

            if mode == "auto":
                execute_actions(db, exp_id, actions)

        return True
    except Exception as exc:
        logger.exception(f"[AUTOPILOT] error in one-shot step: {exc}")
        return False
    finally:
        if db is not None:
            db.close()


def run_autopilot(loop_interval: int = 60, mode: str = "auto"):
    """Run a continuous loop to decide and execute experiment actions."""
    logger.info(f"Starting autopilot loop mode={mode} interval={loop_interval}s")

    while True:
        run_autopilot_once(mode=mode)
        time.sleep(loop_interval)
