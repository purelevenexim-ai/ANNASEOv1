from datetime import datetime
from services.db_utils import row_to_dict, rows_to_dicts


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def get_project_quota_config(db, project_id):
    row = db.execute("SELECT max_serp_calls_per_day, max_tokens_per_day FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        return {"max_serp_calls_per_day": 500, "max_tokens_per_day": 500000}
    return {
        "max_serp_calls_per_day": row["max_serp_calls_per_day"] if row["max_serp_calls_per_day"] is not None else 500,
        "max_tokens_per_day": row["max_tokens_per_day"] if row["max_tokens_per_day"] is not None else 500000,
    }


def get_quota_usage(db, project_id, usage_type, date=None):
    date = date or _today()
    # Ensure table exists (safe idempotent, in-case migrations not run yet)
    db.execute("CREATE TABLE IF NOT EXISTS api_quota_usage(project_id TEXT, date TEXT, usage_type TEXT, amount REAL, PRIMARY KEY(project_id,date,usage_type))")
    db.commit()

    row = db.execute(
        "SELECT amount FROM api_quota_usage WHERE project_id=? AND date=? AND usage_type=?",
        (project_id, date, usage_type),
    ).fetchone()
    if not row:
        return 0
    return float(row["amount"] or 0)


def add_quota_usage(db, project_id, usage_type, value, date=None):
    date = date or _today()
    current = get_quota_usage(db, project_id, usage_type, date)
    total = current + value
    # upsert
    db.execute(
        "INSERT OR REPLACE INTO api_quota_usage(project_id, date, usage_type, amount) VALUES(?,?,?,?)",
        (project_id, date, usage_type, total),
    )
    db.commit()
    return total


def check_and_consume_quota(db, project_id, usage_type, amount=1):
    config = get_project_quota_config(db, project_id)
    if usage_type == "serp_calls":
        limit = config.get("max_serp_calls_per_day", 500)
    elif usage_type == "llm_tokens":
        limit = config.get("max_tokens_per_day", 500000)
    else:
        raise ValueError("Unknown usage type")

    current = get_quota_usage(db, project_id, usage_type)
    if current + amount > limit:
        return False, current, limit

    add_quota_usage(db, project_id, usage_type, amount)
    return True, current + amount, limit
