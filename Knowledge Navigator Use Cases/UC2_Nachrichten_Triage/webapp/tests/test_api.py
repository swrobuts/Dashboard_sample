# webapp/tests/test_api.py
from fastapi.testclient import TestClient


def get_client():
    from backend.main import app
    return TestClient(app)


def test_health_returns_ok():
    client = get_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
