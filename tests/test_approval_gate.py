from datetime import UTC, datetime

import pytest

from sentinel.approval_gate import ApprovalError, approve_remediation
from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus


def job(status: RemediationStatus) -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status=status.value,
        dry_run=True,
    )


def test_approve_releases_held_job() -> None:
    timestamp = datetime(2026, 8, 27, tzinfo=UTC)
    released, approval = approve_remediation(
        job(RemediationStatus.AWAITING_APPROVAL),
        approved_by="operator-1",
        approved_at=timestamp,
    )
    assert released.status == RemediationStatus.QUEUED.value
    assert approval.approved_by == "operator-1"
    assert approval.approved_at == timestamp


def test_approve_rejects_non_held_job() -> None:
    with pytest.raises(ApprovalError, match="awaiting approval"):
        approve_remediation(job(RemediationStatus.QUEUED), approved_by="operator-1")


def test_approve_rejects_blank_approver() -> None:
    with pytest.raises(ApprovalError, match="approved_by"):
        approve_remediation(job(RemediationStatus.AWAITING_APPROVAL), approved_by=" ")


def test_approve_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ApprovalError, match="timezone-aware"):
        approve_remediation(
            job(RemediationStatus.AWAITING_APPROVAL),
            approved_by="operator-1",
            approved_at=datetime.fromisoformat("2026-08-27T00:00:00"),
        )
