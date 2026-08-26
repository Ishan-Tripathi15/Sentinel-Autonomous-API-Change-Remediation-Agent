from __future__ import annotations

import pytest

from sentinel.delivery import DeliveryError, build_dry_run_delivery
from sentinel.models import RemediationJob, VerificationResult
from sentinel.orchestrator import RemediationStatus


def _job(*, status: str = RemediationStatus.VERIFIED.value, dry_run: bool = True) -> RemediationJob:
    return RemediationJob(
        job_id="job-123",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status=status,
        dry_run=dry_run,
        verification=[
            VerificationResult(
                passed=True,
                command="npm test",
                exit_code=0,
                duration_ms=120,
            )
        ],
    )


def test_builds_deterministic_dry_run_delivery() -> None:
    artifact = build_dry_run_delivery(
        _job(),
        repository="acme/example",
        summary="Update the changed API field usage.",
        patch_diff="@@ -1 +1 @@\n-old\n+new\n",
    )

    assert artifact.job_id == "job-123"
    assert artifact.repository == "acme/example"
    assert artifact.branch_name == "sentinel/remediation/job-123"
    assert artifact.title == "chore: remediate API change (job-123)"
    assert artifact.patch_diff.startswith("@@")
    assert artifact.would_create_pull_request is True
    assert "npm test" in artifact.body
    assert "did not write to the repository" in artifact.body


@pytest.mark.parametrize(
    "status",
    [
        RemediationStatus.QUEUED.value,
        RemediationStatus.PATCH_GENERATED.value,
        RemediationStatus.VERIFICATION_PENDING.value,
        RemediationStatus.FAILED.value,
    ],
)
def test_requires_verified_job(status: str) -> None:
    with pytest.raises(DeliveryError, match="only verified"):
        build_dry_run_delivery(
            _job(status=status),
            repository="acme/example",
            summary="summary",
            patch_diff="patch",
        )


def test_rejects_non_dry_run_job() -> None:
    with pytest.raises(DeliveryError, match="non-dry-run"):
        build_dry_run_delivery(
            _job(dry_run=False),
            repository="acme/example",
            summary="summary",
            patch_diff="patch",
        )


@pytest.mark.parametrize(
    "repository,summary,patch_diff",
    [
        ("", "summary", "patch"),
        ("acme/example", "", "patch"),
        ("acme/example", "summary", ""),
        ("acme/example\x00repo", "summary", "patch"),
    ],
)
def test_rejects_invalid_delivery_fields(
    repository: str,
    summary: str,
    patch_diff: str,
) -> None:
    with pytest.raises(DeliveryError):
        build_dry_run_delivery(
            _job(),
            repository=repository,
            summary=summary,
            patch_diff=patch_diff,
        )


def test_rejects_oversized_patch() -> None:
    with pytest.raises(DeliveryError, match="size limit"):
        build_dry_run_delivery(
            _job(),
            repository="acme/example",
            summary="summary",
            patch_diff="x" * 128_001,
        )
