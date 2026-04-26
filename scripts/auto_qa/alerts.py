from __future__ import annotations

import json
from typing import Any, Dict

import requests


def send_slack_alert(webhook_url: str, payload: Dict[str, Any]) -> None:
    if not webhook_url:
        return
    text = payload.get("text", "QA alert")
    blocks = payload.get("blocks")
    body: Dict[str, Any] = {"text": text}
    if blocks:
        body["blocks"] = blocks
    try:
        requests.post(webhook_url, json=body, timeout=10)
    except Exception:
        # Alert failures should not crash the QA run.
        pass


def build_failure_alert(run: Dict[str, Any]) -> Dict[str, Any]:
    issues = run.get("issues", [])
    top = issues[:5]
    lines = [
        f"*Run:* {run.get('run_id')}",
        f"*Scenario:* {run.get('scenario')}",
        f"*Score:* {run.get('score')}",
        f"*Critical:* {run.get('critical_count')}",
        "*Top issues:*",
    ]
    for it in top:
        lines.append(f"- [{it.get('severity')}] {it.get('issue')}")
    return {"text": "QA FAILURE DETECTED", "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]}


def pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)
