from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from .models import BlastRadiusReport, ChangeEvent, RemediationJob


class RemediationStatus(StrEnum):
    QUEUED = "queued"
    AWAITING_APPROVAL = "awaiting-approval"
    READY_FOR_REMEDIATION = "ready-for-remediation"
    PATCH_GENERATED = "patch-generated"
    VERIFICATION_PENDING = "verification-pending"
    VERIFIED = "verified"
    FAILED = "failed"
    DRY_RUN_COMPLETE = "dry-run-complete"


class OrchestrationError(ValueError):
    """Raised when a remediation job violates a safety or workflow invariant."""


def create_remediation_job(
    *,
    change_event: ChangeEvent,
    blast_radius: BlastRadiusReport,
    organization_id: str,
    installation_id: str,
    dry_run: bool = True,
) -> RemediationJob:
    """Create the deterministic remediation-job boundary.

    This function plans work only. It never executes customer code, invokes an
    LLM, writes a repository, or opens a pull request. Those capabilities are
    deliberately separate workflow stages so every transition can be audited.
    """
    if not organization_id.strip() or not installation_id.strip():
        raise OrchestrationError("organization_id and installation_id are required")
    if blast_radius.change_event_id != change_event.event_id:
        raise OrchestrationError("blast radius does not belong to the change event")
    if not dry_run:
        raise OrchestrationError("autonomous repository writes are disabled in MVP")

    # New-feature changes are opt-in by product definition; they cannot enter
    # an autonomous remediation workflow.
    status = (
        RemediationStatus.AWAITING_APPROVAL
        if change_event.change_type.value == "new-feature"
        else RemediationStatus.QUEUED
    )

    return RemediationJob(
        job_id=str(uuid4()),
        organization_id=organization_id,
        installation_id=installation_id,
        change_event_id=change_event.event_id,
        status=status.value,
        dry_run=True,
    )


def transition_job(job: RemediationJob, target: RemediationStatus) -> RemediationJob:
    """Apply an explicit state transition without performing side effects."""
    current = RemediationStatus(job.status)
    allowed: dict[RemediationStatus, set[RemediationStatus]] = {
        RemediationStatus.QUEUED: {RemediationStatus.READY_FOR_REMEDIATION},
        RemediationStatus.READY_FOR_REMEDIATION: {RemediationStatus.PATCH_GENERATED},
        RemediationStatus.PATCH_GENERATED: {RemediationStatus.VERIFICATION_PENDING},
        RemediationStatus.VERIFICATION_PENDING: {
            RemediationStatus.VERIFIED,
            RemediationStatus.FAILED,
        },
        RemediationStatus.VERIFIED: {RemediationStatus.DRY_RUN_COMPLETE},
        RemediationStatus.AWAITING_APPROVAL: set(),
        RemediationStatus.FAILED: set(),
        RemediationStatus.DRY_RUN_COMPLETE: set(),
    }
    if target not in allowed[current]:
        raise OrchestrationError(f"invalid remediation transition: {current} -> {target}")
    return job.model_copy(update={"status": target.value})
