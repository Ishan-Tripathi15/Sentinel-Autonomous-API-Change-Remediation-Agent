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
        connection.execute("TRUNCATE remediation_write_authorizations, remediation_delivery_attempts, remediation_jobs")
    value = PostgresJobQueue(_DATABASE_URL, min_size=1, max_size=2)
    yield value
    value.close()


def job() -> RemediationJob:
    return RemediationJob(
        job_id="job-lease-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="queued",
        dry_run=True,
    )


def test_renew_lease_extends_owned_running_job(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)
    assert queue.claim(worker_id="worker-a", lease_seconds=60) == value
    queue.renew_lease(job_id=value.job_id, worker_id="worker-a", lease_seconds=300)
    with psycopg.connect(_DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT worker_id, status, lease_until > CURRENT_TIMESTAMP "
            "FROM remediation_jobs WHERE job_id = %s",
            (value.job_id,),
        ).fetchone()
    assert row == ("worker-a", "running", True)


def test_renew_lease_rejects_other_worker(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)
    assert queue.claim(worker_id="worker-a") == value
    with pytest.raises(JobQueueError, match="not owned"):
        queue.renew_lease(job_id=value.job_id, worker_id="worker-b")


def test_renew_lease_rejects_missing_identity(queue: PostgresJobQueue) -> None:
    with pytest.raises(JobQueueError, match="job_id and worker_id"):
        queue.renew_lease(job_id="", worker_id="worker-a")
    with pytest.raises(JobQueueError, match="job_id and worker_id"):
        queue.renew_lease(job_id="job-1", worker_id="")


def test_renew_lease_bounds_are_enforced(queue: PostgresJobQueue) -> None:
    with pytest.raises(JobQueueError, match="lease_seconds"):
        queue.renew_lease(job_id="job-1", worker_id="worker-a", lease_seconds=0)
    with pytest.raises(JobQueueError, match="lease_seconds"):
        queue.renew_lease(job_id="job-1", worker_id="worker-a", lease_seconds=3601)


def test_expired_lease_cannot_be_renewed(queue: PostgresJobQueue) -> None:
    value = job()
    queue.enqueue(value)
    assert queue.claim(worker_id="worker-a", lease_seconds=60) == value
    with psycopg.connect(_DATABASE_URL) as connection:
        connection.execute(
            "UPDATE remediation_jobs SET lease_until = CURRENT_TIMESTAMP - INTERVAL '1 second' "
            "WHERE job_id = %s",
            (value.job_id,),
        )
    with pytest.raises(JobQueueError, match="not owned"):
        queue.renew_lease(job_id=value.job_id, worker_id="worker-a")
