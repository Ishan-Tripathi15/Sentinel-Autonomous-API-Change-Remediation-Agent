import pytest

from sentinel.models import BlastRadiusReport, ChangeEvent
from sentinel.orchestrator import (
    OrchestrationError,
    RemediationStatus,
    create_remediation_job,
    transition_job,
)


def event(change_type: str = "breaking") -> ChangeEvent:
    return ChangeEvent(
        event_id="evt-1",
        vendor="stripe",
        version="2026-08-01",
        change_type=change_type,
        severity="high",
        summary="Payment field changed",
        affected_endpoints=["/v1/payments"],
        confidence=0.99,
        detected_at="2026-08-25T00:00:00Z",
    )


def report(event_id: str = "evt-1") -> BlastRadiusReport:
    return BlastRadiusReport(
        change_event_id=event_id,
        repository="acme/payments",
        affected_files=["src/payments.ts"],
        call_sites=[],
        confidence=0.91,
    )


def test_job_is_created_queued_and_dry_run_by_default() -> None:
    job = create_remediation_job(
        change_event=event(),
        blast_radius=report(),
        organization_id="org-1",
        installation_id="install-1",
    )
    assert job.status == RemediationStatus.QUEUED
    assert job.dry_run is True


def test_new_feature_requires_explicit_approval() -> None:
    job = create_remediation_job(
        change_event=event("new-feature"),
        blast_radius=report(),
        organization_id="org-1",
        installation_id="install-1",
    )
    assert job.status == RemediationStatus.AWAITING_APPROVAL


def test_mismatched_blast_radius_is_rejected() -> None:
    with pytest.raises(OrchestrationError, match="does not belong"):
        create_remediation_job(
            change_event=event(),
            blast_radius=report("other-event"),
            organization_id="org-1",
            installation_id="install-1",
        )


def test_non_dry_run_is_rejected_in_mvp() -> None:
    with pytest.raises(OrchestrationError, match="disabled in MVP"):
        create_remediation_job(
            change_event=event(),
            blast_radius=report(),
            organization_id="org-1",
            installation_id="install-1",
            dry_run=False,
        )


def test_state_machine_is_explicit() -> None:
    job = create_remediation_job(
        change_event=event(),
        blast_radius=report(),
        organization_id="org-1",
        installation_id="install-1",
    )
    job = transition_job(job, RemediationStatus.READY_FOR_REMEDIATION)
    job = transition_job(job, RemediationStatus.PATCH_GENERATED)
    job = transition_job(job, RemediationStatus.VERIFICATION_PENDING)
    job = transition_job(job, RemediationStatus.VERIFIED)
    job = transition_job(job, RemediationStatus.DRY_RUN_COMPLETE)
    assert job.status == RemediationStatus.DRY_RUN_COMPLETE


def test_invalid_transition_is_rejected() -> None:
    job = create_remediation_job(
        change_event=event(),
        blast_radius=report(),
        organization_id="org-1",
        installation_id="install-1",
    )
    with pytest.raises(OrchestrationError, match="invalid remediation transition"):
        transition_job(job, RemediationStatus.VERIFIED)
