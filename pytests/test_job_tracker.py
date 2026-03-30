import pytest
import json
from main import app, get_db
from services import job_tracker
from jobqueue.jobs import run_single_call_job, run_pipeline_job
from engines.ruflo_final_strategy_engine import DefaultLLMClient
import uuid

from fastapi.testclient import TestClient as FastAPITestClient
from httpx import ASGITransport, AsyncClient
import anyio

# Force a stable TestClient wrapper for anyio/httpx version mismatches
class TestClient:
    def __init__(self, app):
        self._client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")

    def _run(self, func, *args, **kwargs):
        async def _coro():
            return await func(*args, **kwargs)
        return anyio.run(_coro)

    def get(self, *args, **kwargs):
        return self._run(self._client.get, *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._run(self._client.post, *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._run(self._client.put, *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._run(self._client.delete, *args, **kwargs)

    def close(self):
        return self._run(self._client.aclose)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

try:
    from jobqueue.connection import redis_conn
except Exception:
    redis_conn = None

import main as main_app


def _reset_strategy_jobs():
    db = get_db()
    db.execute("DELETE FROM strategy_jobs")
    db.commit()


def test_job_tracker_create_and_update():
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    created = job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="test", input_payload={"a":1})
    assert created is not None
    assert created["id"] == job_id
    assert created["project_id"] == "proj_test"
    assert created["status"] == "queued"

    updated = job_tracker.update_strategy_job(db, job_id, status="running", progress=10, current_step="init")
    assert updated["status"] == "running"
    assert updated["progress"] == 10
    assert updated["current_step"] == "init"

    fetched = job_tracker.get_strategy_job(db, job_id)
    assert fetched["id"] == job_id
    assert fetched["progress"] == 10


def test_job_tracker_idempotent_lock_key():
    _reset_strategy_jobs()
    db = get_db()
    key = "lock_key_test"
    id1 = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, id1, project_id="proj_test", job_type="test", input_payload={"a":1}, lock_key=key)
    id2 = f"job_{uuid.uuid4().hex[:8]}"
    same = job_tracker.create_strategy_job(db, id2, project_id="proj_test", job_type="test", input_payload={"a":1}, lock_key=key)
    assert same["id"] == id1


def test_job_tracker_auto_lock_key_idempotent():
    _reset_strategy_jobs()
    db = get_db()
    payload = {"a": 1}
    id1 = f"job_{uuid.uuid4().hex[:8]}"
    created = job_tracker.create_strategy_job(db, id1, project_id="proj_test", job_type="strategy", input_payload=payload)
    id2 = f"job_{uuid.uuid4().hex[:8]}"
    same = job_tracker.create_strategy_job(db, id2, project_id="proj_test", job_type="strategy", input_payload=payload)
    assert same["id"] == id1


def test_job_tracker_stale_lock_release():
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload={"a":1})
    db.execute("UPDATE strategy_jobs SET is_locked=1, locked_at=datetime('now','-20 minutes') WHERE id=?", (job_id,))
    db.commit()

    acquired = job_tracker.acquire_job_lock(db, job_id, stale_minutes=5)
    assert acquired

    job = job_tracker.get_strategy_job(db, job_id)
    assert job["is_locked"] is True

    job_tracker.release_job_lock(db, job_id)
    job = job_tracker.get_strategy_job(db, job_id)
    assert job["is_locked"] is False


def test_job_tracker_retry_max_reached():
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="test", input_payload={}, max_retries=1)
    j = job_tracker.get_strategy_job(db, job_id)
    assert j["max_retries"] == 1

    updated = job_tracker.update_strategy_job(db, job_id, status="failed", retry_count=1)
    assert updated["retry_count"] == 1
    assert updated["status"] == "failed"


@pytest.mark.skipif(redis_conn is None, reason="Redis not available")
def test_sequential_gate_redis():
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    main_app._close_seq_gate(run_id)
    assert not main_app._wait_seq_gate(run_id, timeout=1)
    main_app._open_seq_gate(run_id)
    assert main_app._wait_seq_gate(run_id, timeout=1)


def test_job_status_api_for_research_and_score():
    client = TestClient(app)

    # Register and authenticate
    email = f"test_{uuid.uuid4().hex[:8]}@x.com"
    auth = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert auth.status_code == 200
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Start a research job
    create_resp = client.post("/api/ki/proj_test/research", json={"session_id":"s1","customer_url":"https://example.com","competitor_urls":["https://c1.com"]}, headers=headers)
    assert create_resp.status_code == 200
    research_job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/ki/proj_test/research/{research_job_id}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["job_type"] == "research"

    # Create a score job directly via job_tracker
    score_job_id = f"score_{uuid.uuid4().hex[:12]}"
    job_tracker.create_strategy_job(get_db(), score_job_id, project_id="proj_test", job_type="score", input_payload={"session_id":"sess_123","total":0})

    score_status = client.get(f"/api/jobs/{score_job_id}", headers=headers)
    assert score_status.status_code == 200
    assert score_status.json()["job_type"] == "score"

    # Global endpoint
    gresp = client.get(f"/api/jobs/{score_job_id}", headers=headers)
    assert gresp.status_code == 200
    assert gresp.json()["id"] == score_job_id


def test_research_job_fallback_from_existing_universe():
    client = TestClient(app)
    email = f"test_{uuid.uuid4().hex[:8]}@x.com"
    auth = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert auth.status_code == 200
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project and a pre-seeded KI universe session (no live research sources)
    project_resp = client.post("/api/projects", json={"name": "research_proj", "industry": "general", "description": "x"}, headers=headers)
    assert project_resp.status_code == 200
    project_id = project_resp.json()["project_id"]

    from engines.annaseo_keyword_input import _db as _ki_db_fn
    ki_db = _ki_db_fn()
    session_id = f"kis_{project_id}_{uuid.uuid4().hex[:8]}"
    ki_db.execute(
        "INSERT OR REPLACE INTO keyword_input_sessions (session_id, project_id, seed_keyword, customer_url, competitor_urls) VALUES (?,?,?,?,?)",
        (session_id, project_id, "apple", "", "[]")
    )
    ki_db.execute(
        "INSERT OR REPLACE INTO keyword_universe_items (item_id, project_id, session_id, keyword, pillar_keyword, source, intent, volume_estimate, difficulty, opportunity_score, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (f"ki_{session_id}_x", project_id, session_id, "apple fruit", "apple", "cross_multiply", "informational", 100, 30, 70.0, "pending")
    )
    ki_db.commit()
    ki_db.close()

    create_resp = client.post(f"/api/ki/{project_id}/research", json={"session_id": session_id, "customer_url": "", "competitor_urls": []}, headers=headers)
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    # Poll until complete
    status_resp = None
    for _ in range(20):
        status_resp = client.get(f"/api/ki/{project_id}/research/{job_id}", headers=headers)
        assert status_resp.status_code == 200
        status = status_resp.json().get("status")
        if status in ("completed", "failed"):
            break
        time.sleep(0.5)

    assert status_resp is not None
    assert status_resp.json().get("status") == "completed"
    result_payload = status_resp.json().get("result_payload", {})
    assert result_payload.get("source_counts", {}).get("fallback_existing_universe", 0) >= 1
    assert result_payload.get("keyword_count", 0) >= 1


def test_autonomy_execute_enqueue_job():
    client = TestClient(app)
    email = f"test_{uuid.uuid4().hex[:8]}@x.com"
    auth = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert auth.status_code == 200
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # project must exist to tie job project_id
    project_resp = client.post("/api/projects", json={"name": "p1", "industry": "general", "description": "x"}, headers=headers)
    assert project_resp.status_code == 200

    resp = client.post("/api/autonomy/execute", json={"project_id": "proj_test"}, headers=headers)
    assert resp.status_code == 200
    result = resp.json()
    assert "job_id" in result
    assert result["status"] == "queued"

    status = client.get(f"/api/jobs/{result['job_id']}", headers=headers)
    assert status.status_code == 200
    assert status.json()["id"] == result["job_id"]


def test_job_control_pause_resume_cancel():
    client = TestClient(app)
    email = f"test_{uuid.uuid4().hex[:8]}@x.com"
    auth = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert auth.status_code == 200
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # create a fake job in DB
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(get_db(), job_id, project_id="proj_test", job_type="test", input_payload={"a":1})

    # Pause
    resp = client.post(f"/api/jobs/{job_id}/pause", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["control"] == "paused"

    j = job_tracker.get_strategy_job(get_db(), job_id)
    assert j["control_state"] == "paused"

    # Resume
    resp = client.post(f"/api/jobs/{job_id}/resume", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["control"] == "running"

    j = job_tracker.get_strategy_job(get_db(), job_id)
    assert j["control_state"] == "running"

    # Cancel
    resp = client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["control"] == "cancelling"

    j = job_tracker.get_strategy_job(get_db(), job_id)
    assert j["control_state"] == "cancelling"
    assert j["cancel_requested"] == 1


def test_job_tracker_single_call_execution_mode():
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    created = job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload={"a": 1}, execution_mode="single_call")
    assert created is not None
    assert created["execution_mode"] == "single_call"

    fetched = job_tracker.get_strategy_job(db, job_id)
    assert fetched is not None
    assert fetched["execution_mode"] == "single_call"


def test_run_pipeline_job(monkeypatch):
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    payload = {"project_id": "proj_test", "seed_keywords": ["alpha", "beta"], "pillar": "alpha"}
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload=payload, execution_mode="multi_step")

    monkeypatch.setattr('jobqueue.jobs.acquire_job_lock', lambda job_id: True)
    monkeypatch.setattr('jobqueue.jobs.release_job_lock', lambda job_id: None)

    class FakeSerpEngine:
        def get_serp(self, keyword, project_id=None):
            return {'keyword': keyword, 'organic_results': []}

    monkeypatch.setattr('jobqueue.jobs.SERPEngine', lambda *args, **kwargs: FakeSerpEngine())

    class FakeFinal:
        def run(self, ctx):
            return {'success': True, 'data': {'strategy_meta': {'project_id': 'proj_test'}, 'content_strategy': {'content_pieces': [{'slug': 'alpha', 'word_count': 1200, 'is_pillar': True}]}}}

    monkeypatch.setattr('jobqueue.jobs.FinalStrategyEngine', lambda *args, **kwargs: FakeFinal())

    run_pipeline_job(job_id, 'proj_test', 'alpha')
    job = job_tracker.get_strategy_job(db, job_id)

    assert job['status'] == 'completed'
    assert job['keywords']
    assert job['serp']
    assert job['strategy']
    assert job['links']
    assert job['scores']


def test_run_single_call_parser_retry(monkeypatch):
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload={
        "project": {"project_id":"proj_test"},
        "keyword_universe": [],
        "gsc_data": {},
        "serp_data": {},
        "competitors": [],
        "strategy_meta": {"project_id": "proj_test", "generated_at": "2026-03-28T00:00:00Z", "execution_mode": "single_call"}
    }, execution_mode="single_call")

    monkeypatch.setattr('jobqueue.jobs.acquire_job_lock', lambda job_id: True)
    monkeypatch.setattr('jobqueue.jobs.release_job_lock', lambda job_id: None)

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return 'invalid json'
            return '{"strategy_meta": {"project_id":"proj_test", "generated_at":"2026-03-28T00:00:00Z", "execution_mode":"single_call"}, "market_analysis": {"target_audience": [], "search_intent_types": ["informational"], "pain_points": []}, "keyword_strategy": {"primary_keywords": [], "secondary_keywords": [], "long_tail_keywords": []}, "content_strategy": {"pillar_pages": [], "cluster_topics": []}, "authority_strategy": {"backlink_plan": [], "topical_depth": []}, "execution_plan": {"phases": [{"phase_name":"p1", "tasks": [{"task_name": "task1", "priority": 1}] }]}}'

    monkeypatch.setattr('jobqueue.jobs.DefaultLLMClient', FakeLLM)
    run_single_call_job(job_id)
    job = job_tracker.get_strategy_job(db, job_id)
    assert job['status'] == 'completed'


def test_run_single_call_schema_fail(monkeypatch):
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload={"strategy_meta": {"project_id": "proj_test", "generated_at": "2026-03-28T00:00:00Z", "execution_mode": "single_call"}}, execution_mode="single_call")

    monkeypatch.setattr('jobqueue.jobs.acquire_job_lock', lambda job_id: True)
    monkeypatch.setattr('jobqueue.jobs.release_job_lock', lambda job_id: None)

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, *args, **kwargs):
            self.calls += 1
            # intentionally missing required `strategy_meta` fields to trigger schema validation failure
            return '{"strategy_meta": {"project_id": "proj_test", "generated_at": "2026-03-28T00:00:00Z"}, "keyword_strategy": {"primary_keywords": [], "secondary_keywords": [], "long_tail_keywords": []}, "content_strategy": {"pillar_pages": [], "cluster_topics": []}, "authority_strategy": {"backlink_plan": [], "topical_depth": []}, "execution_plan": {"phases": []}}'

    monkeypatch.setattr('jobqueue.jobs.DefaultLLMClient', FakeLLM)
    run_single_call_job(job_id)
    job = job_tracker.get_strategy_job(db, job_id)
    assert job['status'] == 'failed'
    assert job['error_type'] in ('schema_error', 'provider_error')


def test_run_single_call_extra_field_rejected(monkeypatch):
    _reset_strategy_jobs()
    db = get_db()
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    job_tracker.create_strategy_job(db, job_id, project_id="proj_test", job_type="strategy", input_payload={"project":{},"keyword_universe":[],"gsc_data":{},"serp_data":{},"competitors":[],"strategy_meta":{"project_id":"proj_test","generated_at":"2026-03-28T00:00:00Z"}}, execution_mode="single_call")

    monkeypatch.setattr('jobqueue.jobs.acquire_job_lock', lambda job_id: True)
    monkeypatch.setattr('jobqueue.jobs.release_job_lock', lambda job_id: None)

    class FakeLLM:
        def generate(self, *args, **kwargs):
            return '{"strategy_meta": {"project_id": "proj_test", "generated_at": "2026-03-28T00:00:00Z", "execution_mode": "single_call"}, "market_analysis": {"target_audience": [], "search_intent_types": ["informational"], "pain_points": []}, "keyword_strategy": {"primary_keywords": [], "secondary_keywords": [], "long_tail_keywords": []}, "content_strategy": {"pillar_pages": [], "cluster_topics": []}, "authority_strategy": {"backlink_plan": [], "topical_depth": []}, "execution_plan": {"phases": []}, "unwanted": "value"}'

    monkeypatch.setattr('jobqueue.jobs.DefaultLLMClient', FakeLLM)
    run_single_call_job(job_id)
    job = job_tracker.get_strategy_job(db, job_id)
    assert job['status'] == 'failed'
    assert job['error_type'] == 'schema_error'


def test_final_strategy_engine_requires_full_context():
    from engines.ruflo_final_strategy_engine import FinalStrategyEngine
    from engines.ruflo_final_strategy_engine import DefaultLLMClient

    class FakeLLM:
        def generate(self, *args, **kwargs):
            return ('{"strategy": {}}', 50)

    engine = FinalStrategyEngine(FakeLLM())
    res = engine.run({"strategy_meta": {"project_id":"proj_test"}})
    assert not res["success"]
    assert res["error_type"] == "input_validation"


def test_final_strategy_engine_success_and_cost():
    from engines.ruflo_final_strategy_engine import FinalStrategyEngine
    class FakeLLM:
        def generate(self, *args, **kwargs):
            data = {
                "strategy_meta": {"project_id":"proj_test", "generated_at":"2026-03-28T00:00:00Z", "execution_mode":"single_call"},
                "market_analysis": {"target_audience": [], "search_intent_types": ["informational"], "pain_points": []},
                "keyword_strategy": {"primary_keywords": [], "secondary_keywords": [], "long_tail_keywords": []},
                "content_strategy": {"pillar_pages": [], "cluster_topics": []},
                "authority_strategy": {"backlink_plan": [], "topical_depth": []},
                "execution_plan": {"phases": [{"phase_name": "p1", "tasks": [{"task_name": "t", "priority": 1}]}]}
            }
            return (json.dumps(data), 100)

    engine = FinalStrategyEngine(FakeLLM())
    payload = {"project":{}, "keyword_universe":[], "gsc_data":{}, "serp_data":{}, "competitors":[], "strategy_meta":{"project_id":"proj_test","generated_at":"2026-03-28T00:00:00Z"}}
    res = engine.run(payload)
    assert res["success"] is True
    assert res["validation_status"] == "valid"
    assert res["tokens_used"] == 100
    assert res["cost_usd"] == 100 * engine.CLAUDE_COST_PER_TOKEN if hasattr(engine, 'CLAUDE_COST_PER_TOKEN') else res["cost_usd"]


