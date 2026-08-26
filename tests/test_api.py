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


def test_github_delivery_requires_installation_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_INSTALLATION_TOKEN", raising=False)
    response = client.post(
        "/v1/remediation/github-delivery",
        json={
            "job": {
                "job_id": "job-1",
                "organization_id": "org-1",
                "installation_id": "installation-1",
                "change_event_id": "event-1",
                "status": "verified",
                "dry_run": False,
            },
            "repository": "acme/service",
            "base_branch": "main",
            "title": "chore: remediate",
            "body": "body",
            "changes": [{"path": "src/client.py", "content": "updated"}],
            "allow_write": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "GitHub installation token is not configured"
