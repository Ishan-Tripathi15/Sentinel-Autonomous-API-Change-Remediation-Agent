from __future__ import annotations

from dataclasses import dataclass

from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus


MAX_PATCH_CHARS = 128_000
MAX_REPOSITORY_CHARS = 256


class DeliveryError(ValueError):
    """Raised when a remediation cannot safely enter delivery."""


@dataclass(frozen=True)
class DryRunDelivery:
    """The side-effect-free artifact that represents a proposed PR."""

    job_id: str
    repository: str
    branch_name: str
    title: str
    body: str
    patch_diff: str
    would_create_pull_request: bool = True


def build_dry_run_delivery(
    job: RemediationJob,
    *,
    repository: str,
    summary: str,
    patch_diff: str,
) -> DryRunDelivery:
    """Build a deterministic PR artifact without writing to GitHub.

    Delivery is intentionally limited to verified, dry-run jobs. The returned
    artifact can later be handed to a provider-specific GitHub delivery adapter
    after the product's autonomous-write safety gate is explicitly enabled.
    """
    if job.status != RemediationStatus.VERIFIED.value:
        raise DeliveryError("only verified remediation jobs can be delivered")
    if not job.dry_run:
        raise DeliveryError("non-dry-run delivery is disabled in MVP")
    if not repository.strip() or len(repository) > MAX_REPOSITORY_CHARS:
        raise DeliveryError("repository must be non-empty and bounded")
    if not summary.strip():
        raise DeliveryError("delivery summary is required")
    if not patch_diff.strip():
        raise DeliveryError("patch diff is required for delivery")
    if any(char == "\x00" for char in (repository, summary, patch_diff)):
        raise DeliveryError("delivery fields must not contain null bytes")

    if len(patch_diff) > MAX_PATCH_CHARS:
        raise DeliveryError("patch diff exceeds delivery size limit")

    branch_name = f"sentinel/remediation/{job.job_id}"
    title = f"chore: remediate API change ({job.job_id})"
    verification_lines = [
        f"- `{result.command}` — {'passed' if result.passed else 'failed'} "
        f"(exit {result.exit_code}, {result.duration_ms}ms)"
        for result in job.verification
    ]
    verification = "\n".join(verification_lines) or "- No verification results recorded"
    body = (
        "## Sentinel dry-run remediation\n\n"
        f"{summary.strip()}\n\n"
        "### Verification\n"
        f"{verification}\n\n"
        "### Safety\n"
        "This artifact is dry-run only. Sentinel did not write to the repository "
        "or create a pull request.\n\n"
        f"Job: `{job.job_id}`\n"
    )

    return DryRunDelivery(
        job_id=job.job_id,
        repository=repository,
        branch_name=branch_name,
        title=title,
        body=body,
        patch_diff=patch_diff,
    )
