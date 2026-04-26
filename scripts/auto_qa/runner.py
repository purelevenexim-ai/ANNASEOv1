from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .alerts import build_failure_alert, pretty_json, send_slack_alert
from .config import QAConfig, TestScenario, default_scenarios
from .rules import evaluate
from .storage import QARunStorage
from .ui_runner import UIFlowRunner


def run_once(cfg: QAConfig, scenarios: List[TestScenario]) -> Dict[str, Any]:
    if not cfg.project_id:
        raise ValueError("QA_PROJECT_ID is required")

    storage = QARunStorage(cfg.db_path)
    storage.ensure_schema()

    ui_runner = UIFlowRunner(cfg)
    out_runs: List[Dict[str, Any]] = []

    for scenario in scenarios:
        started = datetime.now(timezone.utc)
        run_id = f"qa_{uuid.uuid4().hex[:12]}"

        previous = storage.last_run(scenario.name)
        capture = ui_runner.run(scenario)
        result = evaluate(capture, previous=previous)

        score = int(result["score"])
        critical_count = int(result["critical_count"])
        major_blockers = int(result["major_blockers"])
        status = "pass" if (score >= cfg.min_score_threshold and critical_count < cfg.critical_threshold) else "fail"

        session_id = capture.get("run_meta", {}).get("session_id", "")

        storage.save_run(
            run_id=run_id,
            scenario_name=scenario.name,
            status=status,
            score=score,
            critical_count=critical_count,
            major_blockers=major_blockers,
            frontend_url=cfg.frontend_url,
            api_url=cfg.api_url,
            project_id=cfg.project_id,
            session_id=session_id,
            summary=result["summary"],
            issues=result["issues"],
            capture=capture,
            started_at=started,
        )

        run_payload = {
            "run_id": run_id,
            "scenario": scenario.name,
            "status": status,
            "score": score,
            "critical_count": critical_count,
            "major_blockers": major_blockers,
            "summary": result["summary"],
            "issues": result["issues"],
            "session_id": session_id,
        }

        if status == "fail":
            send_slack_alert(cfg.slack_webhook_url, build_failure_alert(run_payload))

        out_runs.append(run_payload)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_id": cfg.project_id,
        "runs": out_runs,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Autonomous UI QA for KW3 -> Strategy V2")
    p.add_argument("--project-id", default="", help="Project id to run QA on (or use QA_PROJECT_ID)")
    p.add_argument("--frontend-url", default="", help="Frontend URL (or QA_FRONTEND_URL)")
    p.add_argument("--api-url", default="", help="API URL (or QA_API_URL)")
    p.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p.add_argument("--headed", action="store_true", help="Run browser with UI")
    p.add_argument("--interval-hours", type=int, default=0, help="Run continuously every N hours")
    p.add_argument("--scenario", action="append", default=[], help="Scenario names to run")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    cfg = QAConfig()
    if args.project_id:
        cfg.project_id = args.project_id
    if args.frontend_url:
        cfg.frontend_url = args.frontend_url
    if args.api_url:
        cfg.api_url = args.api_url

    if args.headed:
        cfg.headless = False
    elif args.headless:
        cfg.headless = True

    scenarios = default_scenarios()
    if args.scenario:
        wanted = set(args.scenario)
        scenarios = [s for s in scenarios if s.name in wanted]

    if not scenarios:
        raise ValueError("No scenarios selected")

    if args.interval_hours and args.interval_hours > 0:
        while True:
            payload = run_once(cfg, scenarios)
            print(pretty_json(payload))
            time.sleep(args.interval_hours * 3600)
    else:
        payload = run_once(cfg, scenarios)
        print(pretty_json(payload))


if __name__ == "__main__":
    main()
