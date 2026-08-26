from __future__ import annotations

import os

import psycopg
import pytest

from sentinel.job_queue import JobQueueError, PostgresJobQueue
from sentinel.migrate import migrate
from sentinel.models import RemediationJob

_DATABASE_URL = os.environ.get("SENTINEL_DATABASE_URL", "")


@pytest.fixture()
def queue() -> PostgresJobQueue:
    if not _DATABASE_URL:
        pytest.skip("SENTINEL_DATABASE_URL is not configured")
    migrate(_DATABASE_URL)
    with psycopg.connect(_DATABASE_URL) as connection:
        connection.execute("TRUNCATE remediation_jobs")
    value = PostgresJobQueue(_DATABASE_URL, min_size=1, max_size=2)
    yield value
    value.close()


def job(job_id: str = "job-1") -> RemediationJob:
    return RemediationJob(
        job_id=job_id,
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="queued",
        dry_run=True,
    )


def test_enqueue_is_idempotent(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)
    queue.enqueue(value)

    with psycopg.connect(_DATABASE_URL) as connection:
        count = connection.execute("SELECT COUNT(*) FROM remediation_jobs").fetchone()[0]
    assert count == 1


def test_claim_and_complete_requires_lease_owner(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)

    claimed = queue.claim(worker_id="worker-a")
    assert claimed == value

    with pytest.raises(JobQueueError, match="not owned"):
        queue.complete(job_id=value.job_id, worker_id="worker-b", payload=value.model_copy(update={"status": "verified"}))

    completed = value.model_copy(update={"status": "dry-run-complete"})
    queue.complete(job_id=value.job_id, worker_id="worker-a", payload=completed)
    assert queue.claim(worker_id="worker-b") is None


def test_claim_is_exclusive(queue: PostgresJobQueue) -> None:
    queue.enqueue(job())

    first = queue.claim(worker_id="worker-a")
    second = queue.claim(worker_id="worker-b")

    assert first is not None
    assert second is None


def test_fail_returns_job_to_queue(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)
    assert queue.claim(worker_id="worker-a") == value

    failed = value.model_copy(update={"status": "failed"})
    queue.fail(job_id=value.job_id, worker_id="worker-a", payload=failed, retry_after_seconds=0)

    retried = queue.claim(worker_id="worker-b")
    assert retried is not None
    assert retried.job_id == value.job_id


def test_lease_bounds_are_enforced(queue: PostgresJobQueue) -> None:
    with pytest.raises(JobQueueError, match="lease_seconds"):
        queue.claim(worker_id="worker-a", lease_seconds=0)
    with pytest.raises(JobQueueError, match="lease_seconds"):
        queue.claim(worker_id="worker-a", lease_seconds=3601)
