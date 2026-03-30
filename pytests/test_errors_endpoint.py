import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from httpx import ASGITransport, AsyncClient
import anyio
from main import app, ERROR_LOG

class TestClient:
    def __init__(self, app):
        self._client = AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver')

    def _run(self, func, *args, **kwargs):
        async def _coro():
            return await func(*args, **kwargs)
        return anyio.run(_coro)

    def get(self, *args, **kwargs):
        return self._run(self._client.get, *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._run(self._client.post, *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._run(self._client.aclose)

client = TestClient(app)


def test_api_errors_empty_on_start():
    response = client.get("/api/errors")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] == 0
    assert isinstance(data["errors"], list)


def test_realtime_error_store_exposes_entries():
    response = client.get("/api/errors/realtime")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert isinstance(data["errors"], list)

    # Inject into in-memory store and verify query
    ERROR_LOG.appendleft({
        "timestamp": "2026-03-29T00:00:00Z",
        "path": "/api/test", "method": "GET",
        "error": "test-error", "type": "ValueError", "trace": ""
    })
    response2 = client.get("/api/errors/realtime")
    assert response2.status_code == 200
    assert response2.json()["count"] >= 1
