import pytest
from main import app
from httpx import ASGITransport, AsyncClient
import anyio

class TestClient:
    def __init__(self, app):
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")

    def _run(self, func, *args, **kwargs):
        async def run_coroutine():
            return await func(*args, **kwargs)
        return anyio.run(run_coroutine)

    def get(self, path, **kwargs):
        return self._run(self.client.get, path, **kwargs)

    def post(self, path, **kwargs):
        return self._run(self.client.post, path, **kwargs)

    def close(self):
        return self._run(self.client.aclose)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def test_strategy_api_contract():
    client = TestClient(app)
    project_id = "test-project"

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")
    assert token

    response = client.get(f"/api/strategy/{project_id}/latest", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    data = response.json()
    assert "strategy" in data
    assert "meta" in data

    strategy = data["strategy"]
    assert set(strategy.keys()) == {"audience", "angles", "outline", "links", "scores"}

    assert isinstance(strategy["audience"], dict)
    assert isinstance(strategy["angles"], list)
    assert isinstance(strategy["outline"], list)
    assert isinstance(strategy["links"], list)
    assert isinstance(strategy["scores"], dict)

    assert data["meta"]["version"] == "v1"
    assert data["meta"]["project_id"] == project_id


def test_rank_prediction_route():
    client = TestClient(app)
    project_id = "test-project-prediction"

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")
    assert token

    body = {
        "pages": [
            {"word_count": 1700, "headings": ["h1", "h2"], "score": 14},
            {"word_count": 2100, "headings": ["h1", "h2", "h3"], "score": 18}
        ],
        "your_site": {"domain_authority": 30}
    }

    response = client.post(
        f"/api/rankings/{project_id}/predict",
        json=body,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id
    assert "prediction" in data
    assert "decision" in data["prediction"]
    assert data["prediction"]["decision"] in ["GO", "MEDIUM", "SKIP"]


def test_metrics_endpoint():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    if response.text:
        assert "strategy_jobs_total" in response.text

    response = client.get("/metrics/json")
    assert response.status_code == 200
    json_data = response.json()
    assert "strategy_jobs_total" in json_data
    assert "strategy_jobs_failed" in json_data


def test_serp_cache_stats_endpoint():
    client = TestClient(app)

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    response = client.get("/api/serp/cache/stats", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    stats = response.json()
    assert all(k in stats for k in ["hit", "miss", "stale", "total", "hit_rate", "fallback_rate"])
    assert stats["total"] >= 0


def test_dashboard_metrics_route():
    client = TestClient(app)

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    response = client.get("/api/dashboard/metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "kpis" in data and "serp" in data and "raw" in data
    assert data["kpis"].get("job_success_rate") is not None
    assert data["serp"].get("hit_rate") is not None


def test_healthcheck_endpoints():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"

    response = client.get("/ready")
    assert response.status_code == 200
    assert "database" in response.json() and "redis" in response.json()


def test_strategy_validator_strict():
    from services.strategy_validator import validate_strategy_output
    data = {
        "audience": {},
        "angles": [],
        "outline": [],
        "links": [],
        "scores": {},
        "extra": "not allowed"
    }
    valid, err = validate_strategy_output(data, {"type": "object", "properties": {}, "additionalProperties": False})
    assert not valid
    assert err is not None


def test_pipeline_job_enqueue_route():
    client = TestClient(app)
    project_id = "test-project-pipeline"

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")
    assert token

    # ensure project row exists
    db = __import__('main').get_db()
    db.execute("INSERT OR IGNORE INTO projects(project_id,name,industry) VALUES(?,?,?)", (project_id, "Test", "general"))
    db.commit()

    response = client.post(
        f"/api/strategy/{project_id}/jobs/create",
        json={"pillar": "test-keyword", "language": "english", "region": "india"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["enqueued"] is True
    job_id = payload["job_id"]

    status_response = client.get(f"/api/strategy/{project_id}/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] in ["queued", "running", "completed", "failed"]


def test_authority_map_endpoint():
    client = TestClient(app)
    project_id = "test-project-auth"
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    db = __import__('main').get_db()
    db.execute("INSERT OR IGNORE INTO projects(project_id,name,industry) VALUES(?,?,?)", (project_id, "Test", "general"))
    db.commit()

    response = client.get(f"/api/strategy/{project_id}/authority-map", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "clusters" in data and "summary" in data


def test_roi_endpoint():
    client = TestClient(app)
    project_id = "test-project-roi"
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    db = __import__('main').get_db()
    db.execute("INSERT OR IGNORE INTO projects(project_id,name,industry) VALUES(?,?,?)", (project_id, "Test", "general"))
    db.commit()

    response = client.get(f"/api/strategy/{project_id}/roi", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data and "actions" in data


def test_authority_map_export_endpoints():
    client = TestClient(app)
    project_id = "test-project-auth-export"
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    db = __import__('main').get_db()
    db.execute("INSERT OR IGNORE INTO projects(project_id,name,industry) VALUES(?,?,?)", (project_id, "Test", "general"))
    db.commit()

    response_csv = client.get(f"/api/strategy/{project_id}/authority-map/export?format=csv", headers={"Authorization": f"Bearer {token}"})
    assert response_csv.status_code == 200
    assert response_csv.headers.get("content-type", "").startswith("text/csv")
    assert "cluster" in response_csv.text

    response_json = client.get(f"/api/strategy/{project_id}/authority-map/export?format=json", headers={"Authorization": f"Bearer {token}"})
    assert response_json.status_code == 200
    assert response_json.json().get("clusters") is not None


def test_roi_export_endpoints():
    client = TestClient(app)
    project_id = "test-project-roi-export"
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    db = __import__('main').get_db()
    db.execute("INSERT OR IGNORE INTO projects(project_id,name,industry) VALUES(?,?,?)", (project_id, "Test", "general"))
    db.commit()

    response_csv = client.get(f"/api/strategy/{project_id}/roi/export?format=csv", headers={"Authorization": f"Bearer {token}"})
    assert response_csv.status_code == 200
    assert response_csv.headers.get("content-type", "").startswith("text/csv")
    assert "title" in response_csv.text

    response_json = client.get(f"/api/strategy/{project_id}/roi/export?format=json", headers={"Authorization": f"Bearer {token}"})
    assert response_json.status_code == 200
    assert response_json.json().get("actions") is not None

def test_enrich_endpoint():
    client = TestClient(app)
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")
    project_id = "test-project-enrich"
    client.post("/api/projects", json={"project_id": project_id, "name": "Test"}, headers={"Authorization": f"Bearer {token}"})

    response = client.get(f"/api/enrich?keyword=smartphone&project_id={project_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data.get("keyword") == "smartphone"
    assert "clusters" in data
    assert "competitors" in data


def test_enrich_caches_results():
    client = TestClient(app)
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    db = __import__('main').get_db()
    project_id = "test-project-enrich-cache"
    client.post("/api/projects", json={"project_id": project_id, "name": "Test"}, headers={"Authorization": f"Bearer {token}"})

    response1 = client.get(f"/api/enrich?keyword=computer&project_id={project_id}", headers={"Authorization": f"Bearer {token}"})
    assert response1.status_code == 200

    row = db.execute("SELECT fetched_at FROM serp_cache WHERE keyword=?", ("computer",)).fetchone()
    assert row is not None

    # Second call should hit cache and also return same data shape
    response2 = client.get("/api/enrich?keyword=computer", headers={"Authorization": f"Bearer {token}"})
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2.get("keyword") == "computer"


def test_metrics_endpoint_exposes_counters():
    client = TestClient(app)
    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    # Prime a couple endpoints
    client.get("/api/health")
    client.get("/api/strategy/test-project-roi/jobs/unknown", headers={"Authorization": f"Bearer {token}"})

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    body = metrics_resp.text

    from core import metrics as cm
    if cm.Counter is None:
        # Prometheus client not installed in this environment; endpoint returns empty payload.
        assert body == ""
    else:
        assert "api_requests_total" in body
        assert "strategy_jobs_total" in body
