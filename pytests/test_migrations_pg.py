import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")
def test_postgres_migration_tables_and_index():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        insp = inspect(conn)
        tables = insp.get_table_names()
        assert "strategy_jobs" in tables
        assert "serp_cache" in tables

        job_cols = {col["name"] for col in insp.get_columns("strategy_jobs")}
        assert {"id", "project_id", "status", "progress", "input_payload", "result_payload"}.issubset(job_cols)

        serp_cols = {col["name"] for col in insp.get_columns("serp_cache")}
        assert {"id", "query", "results", "hash"}.issubset(serp_cols)

        job_indexes = {idx["name"] for idx in insp.get_indexes("strategy_jobs")}
        assert "ix_strategy_jobs_project" in job_indexes
        assert "ix_strategy_jobs_status" in job_indexes

        serp_indexes = {idx["name"] for idx in insp.get_indexes("serp_cache")}
        assert "ix_serp_cache_query" in serp_indexes
        assert "ix_serp_cache_hash" in serp_indexes


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")
def test_postgres_migration_insert_job():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        job_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        conn.execute(text("INSERT INTO strategy_jobs (id, project_id, status, progress) VALUES (:id, :pid, :status, :progress)"), {
            "id": job_id,
            "pid": project_id,
            "status": "pending",
            "progress": 0,
        })
        row = conn.execute(text("SELECT id, status, progress FROM strategy_jobs WHERE id = :id"), {"id": job_id}).fetchone()
        assert row is not None
        assert row[0] == job_id
        assert row[1] == "pending"
        assert row[2] == 0
