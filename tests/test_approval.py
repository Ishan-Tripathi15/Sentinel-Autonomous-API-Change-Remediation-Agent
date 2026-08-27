from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sentinel.approval import ApprovalError, RemediationApproval, approve_remediation
from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus


def make_job(status: RemediationStatus) -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status=status.value,
        dry_run=True,
    )


def test_approval_releases_waiting_job_to_queue() -> None:
    approved_at = datetime(2026, 8, 27, tzinfo=timezone.utc)
    job, approval = approve_remediation(
        make_job(RemediationStatus.AWAITING_APPROVAL),
        approved_by="operator-1",
        approved_at=approved_at,
    )
    assert job.status == RemediationStatus.QUEUED.value
    assert job.dry_run is True
    assert approval.job_id == job.job_id
    assert approval.organization_id == job.organization_id
    assert approval.installation_id == job.installation_id
    assert approval.approved_by == "operator-1"
    assert approval.approved_at == approved_at


def test_approval_requires_waiting_status() -> None:
    with pytest.raises(ApprovalError, match="awaiting approval"):
        approve_remediation(make_job(RemediationStatus.QUEUED), approved_by="operator-1")


def test_approval_requires_non_blank_approver() -> None:
    with pytest.raises(ApprovalError, match="approved_by"):
        approve_remediation(make_job(RemediationStatus.AWAITING_APPROVAL), approved_by=" ")


def test_approval_requires_timezone_aware_timestamp() -> None:
    naive_timestamp = datetime.fromisoformat("2026-08-27T00:00:00")
    with pytest.raises(ApprovalError, match="timezone-aware"):
        approve_remediation(
            make_job(RemediationStatus.AWAITING_APPROVAL),
            approved_by="operator-1",
            approved_at=naive_timestamp,
        )


def test_approval_record_requires_identity_fields() -> None:
    timestamp = datetime(2026, 8, 27, tzinfo=timezone.utc)
    with pytest.raises(ApprovalError, match="job_id"):
        RemediationApproval(" ", "org-1", "install-1", "operator-1", timestamp)
    with pytest.raises(ApprovalError, match="organization_id"):
        RemediationApproval("job-1", " ", "install-1", "operator-1", timestamp)
    with pytest.raises(ApprovalError, match="installation_id"):
        RemediationApproval("job-1", "org-1", " ", "operator-1", timestamp)
