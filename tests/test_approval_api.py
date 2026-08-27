from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from sentinel.api import JobApprovalRequest, approve_job
from sentinel.audit import RemediationAuditEvent
from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus


class FakeQueue:
    def __init__(self, job: RemediationJob | None) -> None:
        self.job = job
        self.released: RemediationJob | None = None

    def get(self, *, job_id: str) -> RemediationJob | None:
        return self.job if self.job and self.job.job_id == job_id else None

    def release_approval(self, *, job: RemediationJob) -> None:
        if not self.job or self.job.status != RemediationStatus.AWAITING_APPROVAL.value:
            from sentinel.job_queue import JobQueueError

            raise JobQueueError("job is no longer awaiting approval")
        self.released = job
        self.job = job


class FakeAuditSink:
    def __init__(self) -> None:
        self.events: list[RemediationAuditEvent] = []

    def append_event(self, event: RemediationAuditEvent) -> None:
        self.events.append(event)


def job(status: RemediationStatus) -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status=status.value,
        dry_run=True,
    )


def test_approve_job_uses_durable_job_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue(job(RemediationStatus.AWAITING_APPROVAL))
    audit = FakeAuditSink()
    monkeypatch.setattr("sentinel.api.get_job_queue", lambda: queue)
    monkeypatch.setattr("sentinel.api.get_audit_sink", lambda: audit)

    approved_at = datetime(2026, 8, 27, tzinfo=UTC)
    released = approve_job(
        JobApprovalRequest(job_id="job-1", approved_by="operator-1", approved_at=approved_at)
    )

    assert released.status == RemediationStatus.QUEUED.value
    assert queue.released == released
    assert len(audit.events) == 1
    assert audit.events[0].event_type == "job_approved"
    assert audit.events[0].from_status == RemediationStatus.AWAITING_APPROVAL.value
    assert audit.events[0].to_status == RemediationStatus.QUEUED.value
    assert audit.events[0].metadata["approved_by"] == "operator-1"


def test_approve_job_returns_404_for_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue(None)
    monkeypatch.setattr("sentinel.api.get_job_queue", lambda: queue)
    monkeypatch.setattr("sentinel.api.get_audit_sink", FakeAuditSink)

    with pytest.raises(HTTPException) as exc_info:
        approve_job(JobApprovalRequest(job_id="missing", approved_by="operator-1"))

    assert exc_info.value.status_code == 404


def test_approve_job_rejects_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue(job(RemediationStatus.QUEUED))
    monkeypatch.setattr("sentinel.api.get_job_queue", lambda: queue)
    monkeypatch.setattr("sentinel.api.get_audit_sink", FakeAuditSink)

    with pytest.raises(HTTPException) as exc_info:
        approve_job(JobApprovalRequest(job_id="job-1", approved_by="operator-1"))

    assert exc_info.value.status_code == 409
