import pytest
from main import app, get_db
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


def test_experiment_lifecycle():
    client = TestClient(app)

    email = f"test_{__import__('uuid').uuid4().hex[:8]}@x.com"
    register = client.post("/api/auth/register", json={"email": email, "name": "t", "password": "pwd"})
    assert register.status_code == 200
    token = register.json().get("access_token")

    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/experiment/create",
        json={"name": "exp1", "variants": ["A", "B"], "payload": {"test": 1}},
        headers=headers,
    )
    assert create_resp.status_code == 200
    exp = create_resp.json()
    exp_id = exp["id"]

    assign_resp = client.post(f"/api/experiment/{exp_id}/assign", headers=headers)
    assert assign_resp.status_code == 200
    variant = assign_resp.json().get("variant")
    assert variant in ["A", "B"]

    record_resp = client.post(
        f"/api/experiment/{exp_id}/record",
        json={"variant": variant, "job_id": "job123", "roi": 0.5},
        headers=headers,
    )
    assert record_resp.status_code == 200

    get_resp = client.get(f"/api/experiment/{exp_id}", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["name"] == "exp1"
    assert len(data.get("summary", [])) == 1

    client.close()
