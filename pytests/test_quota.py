from main import get_db
from services.quota import check_and_consume_quota
import uuid


def test_quota_overflow_serp_calls():
    db = get_db()
    project_id = f"test-quota-project-{uuid.uuid4().hex}"
    # ensure project row exists
    db.execute("INSERT OR IGNORE INTO projects(project_id, name, industry, max_serp_calls_per_day, max_tokens_per_day) VALUES(?,?,?,?,?)",
               (project_id, "Test", "general", 2, 1000))
    db.commit()

    ok, used, limit = check_and_consume_quota(db, project_id, "serp_calls", 1)
    assert ok and used == 1 and limit == 2

    ok, used, limit = check_and_consume_quota(db, project_id, "serp_calls", 1)
    assert ok and used == 2 and limit == 2

    ok, used, limit = check_and_consume_quota(db, project_id, "serp_calls", 1)
    assert not ok and used == 2 and limit == 2


def test_quota_overflow_llm_tokens():
    db = get_db()
    project_id = f"test-quota-project-llm-{uuid.uuid4().hex}"
    db.execute("INSERT OR IGNORE INTO projects(project_id, name, industry, max_serp_calls_per_day, max_tokens_per_day) VALUES(?,?,?,?,?)",
               (project_id, "Test", "general", 50, 5))
    db.commit()

    ok, used, limit = check_and_consume_quota(db, project_id, "llm_tokens", 3)
    assert ok and used == 3 and limit == 5

    ok, used, limit = check_and_consume_quota(db, project_id, "llm_tokens", 3)
    assert not ok and used == 3 and limit == 5
