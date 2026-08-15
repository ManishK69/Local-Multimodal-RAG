from app.main import create_app
from fastapi.testclient import TestClient


def test_health_degraded_without_ollama(monkeypatch):
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["postgres"] in {"ok", "error"}
    assert "models" in body
    assert set(body["models"]) == {"embed", "vision", "generate"}
