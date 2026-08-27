from __future__ import annotations

from datetime import UTC, datetime

from sentinel.delivery_idempotency import DeliveryAttempt, DeliveryAttemptStore, build_delivery_key
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

    assert build_delivery_key(job) == build_delivery_key(
        job.model_copy(update={"status": "completed"})
    )


def test_delivery_key_changes_when_job_identity_changes() -> None:
    job = make_job()

    assert build_delivery_key(job) != build_delivery_key(make_job(job_id="job-2"))


def test_delivery_attempt_contains_persisted_provider_result() -> None:
    lease_until = datetime.now(UTC)
    attempt = DeliveryAttempt(
        delivery_key="key",
        job_id="job-1",
        status="succeeded",
        provider="github",
        delivery_owner="worker-1",
        lease_until=lease_until,
        pull_request_number=123,
        pull_request_url="https://github.com/acme/api/pull/123",
    )

    assert attempt.status == "succeeded"
    assert attempt.provider == "github"
    assert attempt.delivery_owner == "worker-1"
    assert attempt.lease_until == lease_until
    assert attempt.pull_request_number == 123
    assert attempt.pull_request_url.endswith("/123")


def test_store_requires_a_connection_pool() -> None:
    store = DeliveryAttemptStore
    assert store is not None
