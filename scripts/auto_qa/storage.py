from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class QARunStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE NOT NULL,
                    scenario_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    critical_count INTEGER NOT NULL,
                    major_blockers INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    frontend_url TEXT,
                    api_url TEXT,
                    project_id TEXT,
                    session_id TEXT,
                    summary_json TEXT NOT NULL,
                    issues_json TEXT NOT NULL,
                    capture_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_qa_runs_scenario_completed
                ON qa_runs(scenario_name, completed_at DESC)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_run(
        self,
        run_id: str,
        scenario_name: str,
        status: str,
        score: int,
        critical_count: int,
        major_blockers: int,
        frontend_url: str,
        api_url: str,
        project_id: str,
        session_id: str,
        summary: Dict[str, Any],
        issues: list[Dict[str, Any]],
        capture: Dict[str, Any],
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_runs (
                    run_id, scenario_name, status, score, critical_count, major_blockers,
                    started_at, completed_at, frontend_url, api_url, project_id, session_id,
                    summary_json, issues_json, capture_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    scenario_name,
                    status,
                    int(score),
                    int(critical_count),
                    int(major_blockers),
                    started_at.isoformat(),
                    completed_at.isoformat(),
                    frontend_url,
                    api_url,
                    project_id,
                    session_id,
                    json.dumps(summary, ensure_ascii=True),
                    json.dumps(issues, ensure_ascii=True),
                    json.dumps(capture, ensure_ascii=True),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def last_run(self, scenario_name: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM qa_runs
                WHERE scenario_name = ?
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (scenario_name,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
