from fastapi.testclient import TestClient

from sentinel.api import app
from sentinel.audit import InMemoryAuditSink
from sentinel.audit_runtime import reset_audit_sink, set_audit_sink

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


def test_remediation_job_creation_persists_audit_record_and_event() -> None:
    sink = InMemoryAuditSink()
    set_audit_sink(sink)
    try:
        response = client.post(
            "/v1/remediation/jobs",
            json={
                "change_event": {
                    "event_id": "evt-api-audit",
                    "vendor": "stripe",
                    "version": "2026-08-01",
                    "change_type": "breaking",
                    "severity": "high",
                    "summary": "Payment field changed",
                    "affected_endpoints": ["/v1/payments"],
                    "confidence": 0.99,
                    "detected_at": "2026-08-25T00:00:00Z",
                },
                "blast_radius": {
                    "change_event_id": "evt-api-audit",
                    "repository": "acme/payments",
                    "affected_files": ["src/payments.ts"],
                    "call_sites": [],
                    "confidence": 0.91,
                },
                "organization_id": "org-1",
                "installation_id": "install-1",
            },
        )
        assert response.status_code == 200
        job = response.json()
        records = sink.list()
        events = sink.list_events()
        assert len(records) == 1
        assert records[0].job_id == job["job_id"]
        assert records[0].change_event_id == "evt-api-audit"
        assert records[0].status == "queued"
        assert len(events) == 1
        assert events[0].event_type == "job_created"
        assert events[0].to_status == "queued"
    finally:
        reset_audit_sink()


def test_remediation_lifecycle_event_endpoint_appends_transition() -> None:
    sink = InMemoryAuditSink()
    set_audit_sink(sink)
    try:
        response = client.post(
            "/v1/remediation/jobs/events",
            json={
                "job": {
                    "job_id": "job-event-1",
                    "organization_id": "org-1",
                    "installation_id": "install-1",
                    "change_event_id": "event-1",
                    "status": "running",
                    "dry_run": True,
                },
                "event_type": "status_changed",
                "from_status": "queued",
                "to_status": "running",
                "metadata": {"worker": "remediation-worker"},
            },
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is True
        events = sink.list_events()
        assert len(events) == 1
        assert events[0].from_status == "queued"
        assert events[0].to_status == "running"
        assert events[0].metadata["worker"] == "remediation-worker"
    finally:
        reset_audit_sink()


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
