from __future__ import annotations

import os

import psycopg
import pytest

from sentinel.audit import AuditError, RemediationAuditEvent, RemediationAuditRecord
from sentinel.audit_storage import PostgresAuditSink
from sentinel.migrate import migrate

_DATABASE_URL = os.environ.get("SENTINEL_DATABASE_URL", "")


@pytest.fixture()
def sink() -> PostgresAuditSink:
    if not _DATABASE_URL:
        pytest.skip("SENTINEL_DATABASE_URL is not configured")
    migrate(_DATABASE_URL)
    with psycopg.connect(_DATABASE_URL) as connection:
        connection.execute("TRUNCATE remediation_audit, remediation_audit_events")
    storage = PostgresAuditSink(_DATABASE_URL, min_size=1, max_size=2)
    yield storage
    storage.close()


def record(*, audit_id: str = "audit-1", organization_id: str = "org-1") -> RemediationAuditRecord:
    return RemediationAuditRecord(
        audit_id=audit_id,
        recorded_at="2026-08-26T00:00:00+00:00",
        organization_id=organization_id,
        installation_id="install-1",
        job_id="job-1",
        change_event_id="event-1",
        source_vendor="stripe",
        source_url="https://example.com/change",
        source_version="2026-08-01",
        change_type="breaking",
        change_severity="high",
        change_summary="Payment field changed",
        status="verified",
        model_version="model-v1",
        prompt_version="prompt-v1",
        patch_diff="@@ -1 +1 @@\n-old\n+new\n",
        verification=({"passed": True, "command": "pytest"},),
        delivery_outcome={"provider": "github", "status": "created", "number": 42},
    )


def event(*, audit_event_id: str = "event-1", to_status: str | None = None) -> RemediationAuditEvent:
    return RemediationAuditEvent(
        audit_event_id=audit_event_id,
        recorded_at="2026-08-26T00:00:00+00:00",
        organization_id="org-1",
        installation_id="install-1",
        job_id="job-1",
        change_event_id="event-1",
        event_type="status_changed",
        from_status="queued",
        to_status=to_status,
        metadata={"worker": "test"},
    )


def test_persists_and_retrieves_audit_records(sink: PostgresAuditSink) -> None:
    original = record()
    sink.append(original)

    records = sink.list(organization_id="org-1")

    assert records == (original,)
    assert records[0].delivery_outcome["number"] == 42
    assert records[0].verification[0]["passed"] is True


def test_persists_append_only_lifecycle_events(sink: PostgresAuditSink) -> None:
    first = event(audit_event_id="event-1", to_status="running")
    second = event(audit_event_id="event-2", to_status="verified")
    sink.append_event(first)
    sink.append_event(second)

    events = sink.list_events(job_id="job-1")

    assert events == (first, second)
    assert events[0].to_status == "running"
    assert events[1].to_status == "verified"


def test_duplicate_audit_event_id_is_rejected(sink: PostgresAuditSink) -> None:
    original = event()
    sink.append_event(original)

    with pytest.raises(AuditError, match="unique"):
        sink.append_event(original)


def test_duplicate_audit_id_is_rejected(sink: PostgresAuditSink) -> None:
    original = record()
    sink.append(original)

    with pytest.raises(AuditError, match="unique"):
        sink.append(original)


def test_identity_filters_prevent_cross_tenant_reads(sink: PostgresAuditSink) -> None:
    sink.append(record(audit_id="audit-1", organization_id="org-1"))
    sink.append(record(audit_id="audit-2", organization_id="org-2"))

    records = sink.list(organization_id="org-1")

    assert [item.audit_id for item in records] == ["audit-1"]


def test_query_limit_is_bounded(sink: PostgresAuditSink) -> None:
    with pytest.raises(AuditError, match="limit"):
        sink.list(limit=0)
    with pytest.raises(AuditError, match="limit"):
        sink.list(limit=1001)
    with pytest.raises(AuditError, match="limit"):
        sink.list_events(limit=0)
    with pytest.raises(AuditError, match="limit"):
        sink.list_events(limit=1001)


def test_migration_is_idempotent() -> None:
    if not _DATABASE_URL:
        pytest.skip("SENTINEL_DATABASE_URL is not configured")

    migrate(_DATABASE_URL)
    migrate(_DATABASE_URL)

    with psycopg.connect(_DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = %s",
            ("002_create_remediation_audit_events.sql",),
        ).fetchone()[0]

    assert count == 1
