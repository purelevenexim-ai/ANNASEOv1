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

    def close(self):
        return self._run(self.client.aclose)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def test_ready_endpoint_structure():
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "database" in body
    assert "redis" in body
    assert "all_ok" in body
    assert "latency_ms" in body["database"]
    assert "latency_ms" in body["redis"]
    assert "strategy_jobs" in body
    assert "queues" in body
    assert "lag_seconds" in body["strategy_jobs"]
