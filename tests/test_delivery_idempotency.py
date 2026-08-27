from __future__ import annotations

from datetime import datetime, timezone

from sentinel.delivery_idempotency import DeliveryAttempt, PostgresDeliveryIdempotency
from sentinel.models import RemediationJob


def make_job(*, job_id: str = "job-1") -> RemediationJob:
    return RemediationJob(
        job_id=job_id,
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="verified",
        dry_run=False,
    )


def test_delivery_key_is_stable_for_same_delivery_identity() -> None:
    job = make_job()

    first = PostgresDeliveryIdempotency.delivery_key(
        job,
        provider="github",
        repository="acme/api",
        base_branch="main",
    )
    second = PostgresDeliveryIdempotency.delivery_key(
        job.model_copy(update={"status": "completed"}),
        provider="github",
        repository="acme/api",
        base_branch="main",
    )

    assert first == second
    assert len(first) == 64


def test_delivery_key_changes_when_repository_identity_changes() -> None:
    job = make_job()

    github_key = PostgresDeliveryIdempotency.delivery_key(
        job,
        provider="github",
        repository="acme/api",
        base_branch="main",
    )
    other_repo_key = PostgresDeliveryIdempotency.delivery_key(
        job,
        provider="github",
        repository="acme/other-api",
        base_branch="main",
    )

    assert github_key != other_repo_key


def test_delivery_attempt_is_provider_result_container() -> None:
    completed_at = datetime.now(timezone.utc)
    attempt = DeliveryAttempt(
        delivery_key="key",
        job_id="job-1",
        status="succeeded",
        provider="github",
        pull_request_number=123,
        pull_request_url="https://github.com/acme/api/pull/123",
        commit_sha="abc123",
        completed_at=completed_at,
    )

    assert attempt.status == "succeeded"
    assert attempt.pull_request_number == 123
    assert attempt.commit_sha == "abc123"
    assert attempt.completed_at == completed_at
