from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from sentinel.delivery_idempotency import (
    DeliveryAttempt,
    DeliveryAttemptStore,
    DeliveryIdempotencyError,
    build_delivery_key,
)
from sentinel.models import RemediationJob

REPOSITORY = "acme/api"
BASE_BRANCH = "main"
PROVIDER = "github"


def make_job(*, job_id: str = "job-1") -> RemediationJob:
    return RemediationJob(
        job_id=job_id,
        organization_id="org-1",
        installation_id="installation-1",
        change_event_id="event-1",
        status="verified",
        dry_run=False,
    )


def make_store() -> tuple[DeliveryAttemptStore, MagicMock, MagicMock]:
    pool = MagicMock()
    connection = MagicMock()
    pool.connection.return_value.__enter__.return_value = connection
    return DeliveryAttemptStore(pool), pool, connection


def delivery_key(job: RemediationJob) -> str:
    return build_delivery_key(
        job,
        provider=PROVIDER,
        repository=REPOSITORY,
        base_branch=BASE_BRANCH,
    )


def test_delivery_key_is_stable_for_same_delivery_identity() -> None:
    job = make_job()

    assert delivery_key(job) == delivery_key(job.model_copy(update={"status": "completed"}))


def test_delivery_key_changes_when_job_identity_changes() -> None:
    job = make_job()

    assert delivery_key(job) != delivery_key(make_job(job_id="job-2"))


def test_delivery_key_changes_when_repository_identity_changes() -> None:
    job = make_job()

    assert delivery_key(job) != build_delivery_key(
        job,
        provider=PROVIDER,
        repository="acme/other-api",
        base_branch=BASE_BRANCH,
    )


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
        commit_sha="abc123",
    )

    assert attempt.status == "succeeded"
    assert attempt.provider == "github"
    assert attempt.delivery_owner == "worker-1"
    assert attempt.lease_until == lease_until
    assert attempt.pull_request_number == 123
    assert attempt.pull_request_url.endswith("/123")
    assert attempt.commit_sha == "abc123"


def test_record_reconciled_result_persists_remote_commit_and_pr() -> None:
    store, _, connection = make_store()
    connection.execute.return_value.fetchone.return_value = {
        "delivery_key": "key",
        "job_id": "job-1",
        "status": "succeeded",
        "provider": "github",
        "delivery_owner": "worker-1",
        "lease_until": None,
        "pull_request_number": 123,
        "pull_request_url": "https://github.com/acme/api/pull/123",
        "commit_sha": "abc123",
    }

    result = store.record_reconciled_result(
        delivery_key="key",
        owner="worker-1",
        pull_request_number=123,
        pull_request_url="https://github.com/acme/api/pull/123",
        commit_sha="abc123",
    )

    assert result.status == "succeeded"
    assert result.pull_request_number == 123
    assert result.commit_sha == "abc123"
    connection.commit.assert_called_once()
    sql = connection.execute.call_args.args[0]
    assert "commit_sha = %s" in sql
    assert "delivery_owner = %s" in sql


def test_record_reconciled_result_requires_commit_sha() -> None:
    store, pool, _ = make_store()

    with pytest.raises(DeliveryIdempotencyError, match="commit SHA"):
        store.record_reconciled_result(
            delivery_key="key",
            owner="worker-1",
            pull_request_number=123,
            pull_request_url="https://github.com/acme/api/pull/123",
            commit_sha="",
        )

    pool.connection.assert_not_called()
