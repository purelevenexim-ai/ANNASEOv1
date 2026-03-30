import datetime

from core.experiment import create_experiment, record_result, get_experiment_summary


def ingest_gsc(db, project_id: str, rows: list):
    """Persist GSC rows and return indexed by keyword."""
    metrics = {}
    for r in rows:
        keyword = r.get("keyword")
        if not keyword:
            continue
        date = r.get("date", datetime.datetime.utcnow().isoformat())
        impressions = int(r.get("impressions", 0))
        clicks = int(r.get("clicks", 0))
        position = float(r.get("position", 99.0))
        ctr = float(r.get("ctr", (clicks / max(1, impressions))))

        db.execute(
            "INSERT OR REPLACE INTO gsc_metrics(project_id, keyword, date, impressions, clicks, ctr, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, keyword, date, impressions, clicks, ctr, position),
        )
        metrics[keyword] = metrics.get(keyword, {})
        metrics[keyword].update({"impressions": impressions, "clicks": clicks, "ctr": ctr, "position": position})
    db.commit()
    return metrics


def ingest_ga4(db, project_id: str, rows: list):
    """Persist GA4 rows and return indexed by keyword."""
    metrics = {}
    for r in rows:
        keyword = r.get("keyword")
        if not keyword:
            continue
        date = r.get("date", datetime.datetime.utcnow().isoformat())
        sessions = int(r.get("sessions", 0))
        conversions = int(r.get("conversions", 0))
        revenue = float(r.get("revenue", 0.0))

        db.execute(
            "INSERT OR REPLACE INTO ga4_metrics(project_id, keyword, date, sessions, conversions, revenue) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, keyword, date, sessions, conversions, revenue),
        )
        metrics[keyword] = metrics.get(keyword, {})
        metrics[keyword].update({"sessions": sessions, "conversions": conversions, "revenue": revenue})
    db.commit()
    return metrics


def compute_keyword_roi(gsc: dict, ga4: dict) -> float:
    if not gsc and not ga4:
        return 0.0

    gsc_clicks = gsc.get("clicks", 0)
    ga4_revenue = ga4.get("revenue", 0.0)
    ga4_conversions = ga4.get("conversions", 0)

    # ROI = revenue + conversion value + click value - cost (assume cost ~ 0 for now)
    return ga4_revenue + ga4_conversions * 8.0 + gsc_clicks * 0.15


def sync_to_experiments(db, project_id: str, gsc_metrics: dict, ga4_metrics: dict):
    """Translate metrics into experiment results for DSL."""
    results = []

    all_keywords = set(gsc_metrics.keys()) | set(ga4_metrics.keys())
    for keyword in all_keywords:
        gsc = gsc_metrics.get(keyword, {})
        ga4 = ga4_metrics.get(keyword, {})
        roi = compute_keyword_roi(gsc, ga4)

        exp_name = f"gsc-ga4::{keyword}"
        existing = db.execute("SELECT * FROM strategy_experiments WHERE name=?", (exp_name,)).fetchone()
        if existing:
            experiment_id = existing["id"]
        else:
            exp = create_experiment(db, name=exp_name, variants=["baseline", "variant"], payload={"context": {"niche": "auto", "country": "global", "intent": "auto"}})
            experiment_id = exp["id"]

        # pick the variant to give results to (simple mapping, can improve)
        variant = "baseline" if roi >= 0 else "variant"
        job_id = f"gscga4:{keyword}:{datetime.datetime.utcnow().isoformat()}"

        record_result(db, experiment_id, variant, job_id, float(roi), status="completed", extra_context={"keyword": keyword}, serp_data=gsc)

        results.append({"keyword": keyword, "roi": roi, "experiment_id": experiment_id, "variant": variant})

    return results
