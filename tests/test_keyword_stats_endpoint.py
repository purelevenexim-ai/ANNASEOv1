import os

from fastapi.testclient import TestClient

import main
from engines.kw2.db import init_kw2_db


def test_keyword_stats_handles_plain_string_kw2_metadata(tmp_path, monkeypatch):
    temp_db = tmp_path / "annaseo-test.db"

    monkeypatch.setenv("ANNASEO_TESTING", "1")
    monkeypatch.setenv("ANNASEO_DB", str(temp_db))
    monkeypatch.setattr(main, "DEFAULT_DB_PATH", temp_db)
    monkeypatch.setattr(main, "FALLBACK_DB_PATH", tmp_path / "annaseo-fallback.db")
    monkeypatch.setattr(main, "DB_PATH", temp_db)

    db = main.get_db()
    db.close()
    init_kw2_db(str(temp_db))

    db = main.get_db()
    try:
        db.execute(
            "INSERT INTO projects(project_id, name, industry) VALUES(?, ?, ?)",
            ("proj_test_kw_stats", "Test Project", "spices"),
        )
        db.execute(
            "INSERT INTO kw2_sessions(id, project_id, current_phase, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
            ("kw2_test_session", "proj_test_kw_stats", "9", "2026-04-26T12:00:00+00:00", "2026-04-26T12:00:00+00:00"),
        )
        db.execute(
            "INSERT INTO kw2_business_profile(id, project_id, pillars, geo_scope, business_type, confidence_score) VALUES(?, ?, ?, ?, ?, ?)",
            (
                "bp_test_profile",
                "proj_test_kw_stats",
                '["cassia cinnamon", "clove"]',
                "India",
                "ecommerce",
                0.82,
            ),
        )
        db.execute(
            "INSERT INTO kw2_biz_intel(id, session_id, project_id, goals, pricing_model) VALUES(?, ?, ?, ?, ?)",
            (
                "bi_test_profile",
                "kw2_test_session",
                "proj_test_kw_stats",
                "Traffic, Conversions",
                "premium",
            ),
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(main.app)
    response = client.get("/api/projects/proj_test_kw_stats/keyword-stats")

    assert response.status_code == 200
    data = response.json()
    assert data["kw2"]["target_locations"] == ["India"]
    assert data["kw2"]["goals"] == ["Traffic", "Conversions"]
    assert data["kw2"]["pillar_names"] == ["cassia cinnamon", "clove"]
    assert data["kw2"]["confidence_score"] == 82