from __future__ import annotations

from unittest.mock import MagicMock

from sentinel.delivery_idempotency import DeliveryAttemptStore
from sentinel.models import RemediationJob


def make_job() -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="installation-1",
        change_event_id="event-1",
        status="verified",
        dry_run=False,
    )


def make_store() -> tuple[DeliveryAttemptStore, MagicMock]:
    pool = MagicMock()
    connection = MagicMock()
    pool.connection.return_value.__enter__.return_value = connection
    return DeliveryAttemptStore(pool), connection


def attempt_row(status: str = "pending") -> dict[str, object]:
    return {
        "delivery_key": "key",
        "job_id": "job-1",
        "status": status,
        "provider": "github",
        "delivery_owner": "worker-1",
        "lease_until": None,
        "pull_request_number": None,
        "pull_request_url": None,
        "commit_sha": None,
    }


def test_acquire_persists_required_delivery_context() -> None:
    store, connection = make_store()
    connection.execute.return_value.fetchone.return_value = attempt_row()

    result = store.acquire(
        job=make_job(),
        provider="github",
        owner="worker-1",
        repository="acme/service",
        base_branch="main",
    )

    assert result.delivery_key == "key"
    sql, params = connection.execute.call_args.args
    assert "organization_id" in sql
    assert "installation_id" in sql
    assert "repository" in sql
    assert "base_branch" in sql
    assert "acme/service" in params
    assert "main" in params
    connection.commit.assert_called_once()


def test_begin_moves_pending_attempt_to_in_progress() -> None:
    store, connection = make_store()
    connection.execute.return_value.fetchone.return_value = attempt_row("in_progress")

    result = store.begin(delivery_key="key", owner="worker-1", lease_seconds=300)

    assert result.status == "in_progress"
    sql = connection.execute.call_args.args[0]
    assert "status = 'in_progress'" in sql
    assert "delivery_owner = %s" in sql
    connection.commit.assert_called_once()


def test_record_result_requires_in_progress_owner() -> None:
    store, connection = make_store()
    connection.execute.return_value.fetchone.return_value = attempt_row("succeeded")

    store.record_result(
        delivery_key="key",
        owner="worker-1",
        pull_request_number=42,
        pull_request_url="https://github.com/acme/service/pull/42",
        commit_sha="commit-sha",
    )

    sql = connection.execute.call_args.args[0]
    assert "status = 'in_progress'" in sql
    assert "delivery_owner = %s" in sql
