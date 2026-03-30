import sqlite3
import json
from datetime import datetime


def save_llm_audit(db: sqlite3.Connection, job_id: str, step: str, prompt: str, raw_output: str,
                   validated_output: dict, error: str, attempt: int, model: str, tokens: int, cost_usd: float):
    db.execute(
        """
        INSERT INTO llm_audit_logs
        (job_id, step, prompt, raw_output, validated_output, error, attempt, model, tokens_used, cost_usd, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            step,
            prompt[:10000] if prompt else "",
            raw_output[:20000] if raw_output else "",
            json.dumps(validated_output) if validated_output is not None else "",
            error or "",
            attempt,
            model or "unknown",
            tokens or 0,
            cost_usd or 0.0,
            datetime.now().isoformat(),
        ),
    )
    db.commit()
