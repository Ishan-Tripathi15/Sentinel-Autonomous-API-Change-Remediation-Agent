from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .models import RemediationJob
from .orchestrator import RemediationStatus


class ApprovalError(ValueError):
    """Raised when an approval violates a workflow invariant."""


@dataclass(frozen=True)
class RemediationApproval:
    """Immutable record of an explicit human approval decision."""

    job_id: str
    organization_id: str
    installation_id: str
    approved_by: str
    approved_at: datetime

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ApprovalError("job_id is required")
        if not self.organization_id.strip():
            raise ApprovalError("organization_id is required")
        if not self.installation_id.strip():
            raise ApprovalError("installation_id is required")
        if not self.approved_by.strip():
            raise ApprovalError("approved_by is required")
        if self.approved_at.tzinfo is None:
            raise ApprovalError("approved_at must be timezone-aware")


def approve_remediation(
    job: RemediationJob,
    *,
    approved_by: str,
    approved_at: datetime | None = None,
) -> tuple[RemediationJob, RemediationApproval]:
    """Release an explicitly approved held job back into the queue.

    This helper performs no external side effects and does not grant repository
    write authority. Delivery remains independently gated.
    """
    if job.status != RemediationStatus.AWAITING_APPROVAL.value:
        raise ApprovalError("only jobs awaiting approval can be approved")

    approval = RemediationApproval(
        job_id=job.job_id,
        organization_id=job.organization_id,
        installation_id=job.installation_id,
        approved_by=approved_by,
        approved_at=approved_at or datetime.now(UTC),
    )
    return job.model_copy(update={"status": RemediationStatus.QUEUED.value}), approval
