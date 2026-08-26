from __future__ import annotations

from collections.abc import Sequence

from .models import RemediationJob, VerificationResult
from .orchestrator import OrchestrationError, RemediationStatus
from .verification import VerificationEngine, VerificationError


def verify_remediation_job(
    job: RemediationJob,
    *,
    engine: VerificationEngine,
    commands: Sequence[Sequence[str]],
) -> RemediationJob:
    """Verify a generated remediation and record every verification result.

    The job must already be in ``verification-pending``. Verification errors
    are represented as a failed job rather than being silently treated as a
    successful verification.
    """
    if job.status != RemediationStatus.VERIFICATION_PENDING.value:
        raise OrchestrationError(
            "verification requires a job in verification-pending status"
        )
    if not commands:
        raise OrchestrationError("at least one verification command is required")

    results: list[VerificationResult] = []
    for command in commands:
        try:
            result = engine.verify(command)
        except VerificationError:
            return job.model_copy(
                update={
                    "status": RemediationStatus.FAILED.value,
                    "verification": results,
                }
            )

        results.append(
            VerificationResult(
                passed=result.passed,
                command=" ".join(result.command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=result.duration_ms,
            )
        )
        if not result.passed:
            return job.model_copy(
                update={
                    "status": RemediationStatus.FAILED.value,
                    "verification": results,
                }
            )

    return job.model_copy(
        update={
            "status": RemediationStatus.VERIFIED.value,
            "verification": results,
        }
    )
