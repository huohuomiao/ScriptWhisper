from fastapi.testclient import TestClient

from backend.main import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "ok"
    assert payload["data"] == {"status": "ok"}
    assert payload["error_code"] is None
