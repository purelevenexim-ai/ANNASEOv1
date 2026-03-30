from main import get_db
from core.gsc_analytics_pipeline import ingest_gsc, ingest_ga4, sync_to_experiments
from core.experiment import get_experiment


def test_gsc_ga4_ingest_and_sync():
    db = get_db()
    db.execute("DELETE FROM gsc_metrics")
    db.execute("DELETE FROM ga4_metrics")
    db.execute("DELETE FROM strategy_experiments")
    db.execute("DELETE FROM strategy_experiment_results")
    db.commit()

    project_id = "proj_test"
    gsc_rows = [
        {"keyword": "test keyword", "impressions": 1000, "clicks": 50, "position": 12, "date": "2026-01-01"},
    ]
    ga4_rows = [
        {"keyword": "test keyword", "sessions": 40, "conversions": 2, "revenue": 200.0, "date": "2026-01-01"},
    ]

    gsc_metrics = ingest_gsc(db, project_id, gsc_rows)
    ga4_metrics = ingest_ga4(db, project_id, ga4_rows)
    assert "test keyword" in gsc_metrics
    assert "test keyword" in ga4_metrics

    results = sync_to_experiments(db, project_id, gsc_metrics, ga4_metrics)
    assert len(results) == 1
    res = results[0]
    assert res["keyword"] == "test keyword"
    assert res["roi"] > 0

    exp = get_experiment(db, res["experiment_id"])
    assert exp is not None
