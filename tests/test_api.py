from fastapi.testclient import TestClient

from sentinel.api import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_ingestion_creates_change_event() -> None:
    response = client.post(
        "/v1/changes/openapi",
        json={
            "vendor": "stripe",
            "version": "2026-01-01",
            "before": {"paths": {"/v1/payment_intents": {"post": {}}}},
            "after": {"paths": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["change_type"] == "breaking"
    assert body["vendor"] == "stripe"
    assert body["event_id"]
