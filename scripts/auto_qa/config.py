from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class TestScenario:
    name: str
    domain: str
    competitor: str
    pillar: str
    modifiers: List[str]


@dataclass
class QAConfig:
    frontend_url: str = os.getenv("QA_FRONTEND_URL", "http://localhost:5173")
    api_url: str = os.getenv("QA_API_URL", "http://localhost:8000")
    project_id: str = os.getenv("QA_PROJECT_ID", "")

    username: str = os.getenv("QA_USERNAME", "test_api@test.com")
    password: str = os.getenv("QA_PASSWORD", "test123")
    token: str = os.getenv("QA_TOKEN", "")

    db_path: str = os.getenv("QA_DB_PATH", "/root/ANNASEOv1/annaseo.db")
    timeout_sec: int = int(os.getenv("QA_TIMEOUT_SEC", "240"))

    headless: bool = os.getenv("QA_HEADLESS", "1") != "0"
    slow_mo_ms: int = int(os.getenv("QA_SLOW_MO_MS", "0"))

    min_score_threshold: int = int(os.getenv("QA_MIN_SCORE", "70"))
    critical_threshold: int = int(os.getenv("QA_CRITICAL_THRESHOLD", "1"))
    slack_webhook_url: str = os.getenv("QA_SLACK_WEBHOOK_URL", "")

    qa_mode: str = os.getenv("QA_MODE", "once")
    interval_hours: int = int(os.getenv("QA_INTERVAL_HOURS", "6"))

    scenarios: List[TestScenario] = field(default_factory=list)


def default_scenarios() -> List[TestScenario]:
    return [
        TestScenario(
            name="basic-clove-organic",
            domain="www.pureleven.com",
            competitor="https://www.keralaspicesonline.com/",
            pillar="clove",
            modifiers=["organic"],
        ),
        TestScenario(
            name="complex-cardamom-export-wholesale",
            domain="www.pureleven.com",
            competitor="https://www.keralaspicesonline.com/",
            pillar="cardamom",
            modifiers=["export", "wholesale"],
        ),
        TestScenario(
            name="edge-empty-modifier",
            domain="www.pureleven.com",
            competitor="https://www.keralaspicesonline.com/",
            pillar="clove",
            modifiers=[],
        ),
        TestScenario(
            name="invalid-special-chars",
            domain="www.pureleven.com",
            competitor="https://www.keralaspicesonline.com/",
            pillar="clove@#$",
            modifiers=["organic!!!"],
        ),
    ]
