from __future__ import annotations

from unittest.mock import Mock

import pytest

from sentinel.models import RemediationJob
from sentinel.orchestrator import OrchestrationError, RemediationStatus
from sentinel.verification import VerificationError, VerificationResult
from sentinel.verification_workflow import verify_remediation_job

COMMAND = ("python", "-m", "pytest")


def make_job(status: RemediationStatus) -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="installation-1",
        change_event_id="event-1",
        status=status.value,
        dry_run=True,
    )


def make_result(*, passed: bool, exit_code: int) -> VerificationResult:
    return VerificationResult(
        command=COMMAND,
        returncode=exit_code,
        stdout="ok\n" if passed else "",
        stderr="" if passed else "failed\n",
        duration_ms=25,
    )


def test_successful_verification_marks_job_verified() -> None:
    engine = Mock()
    engine.verify.return_value = make_result(passed=True, exit_code=0)
    job = make_job(RemediationStatus.VERIFICATION_PENDING)

    verified = verify_remediation_job(job, engine=engine, commands=[COMMAND])

    assert verified.status == RemediationStatus.VERIFIED.value
    assert len(verified.verification) == 1
    assert verified.verification[0].passed is True
    engine.verify.assert_called_once_with(COMMAND)


def test_failed_verification_marks_job_failed_and_stops() -> None:
    engine = Mock()
    engine.verify.return_value = make_result(passed=False, exit_code=1)
    job = make_job(RemediationStatus.VERIFICATION_PENDING)

    failed = verify_remediation_job(
        job,
        engine=engine,
        commands=[COMMAND, ("python", "-m", "pytest", "extra")],
    )

    assert failed.status == RemediationStatus.FAILED.value
    assert len(failed.verification) == 1
    assert failed.verification[0].exit_code == 1
    engine.verify.assert_called_once_with(COMMAND)


def test_verification_engine_error_fails_closed() -> None:
    engine = Mock()
    engine.verify.side_effect = VerificationError("sandbox unavailable")
    job = make_job(RemediationStatus.VERIFICATION_PENDING)

    failed = verify_remediation_job(job, engine=engine, commands=[COMMAND])

    assert failed.status == RemediationStatus.FAILED.value
    assert failed.verification == []


def test_wrong_job_status_is_rejected() -> None:
    engine = Mock()
    job = make_job(RemediationStatus.PATCH_GENERATED)

    with pytest.raises(OrchestrationError, match="verification-pending"):
        verify_remediation_job(job, engine=engine, commands=[COMMAND])

    engine.verify.assert_not_called()


def test_empty_command_set_is_rejected() -> None:
    engine = Mock()
    job = make_job(RemediationStatus.VERIFICATION_PENDING)

    with pytest.raises(OrchestrationError, match="at least one"):
        verify_remediation_job(job, engine=engine, commands=[])

    engine.verify.assert_not_called()
