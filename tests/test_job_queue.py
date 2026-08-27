from __future__ import annotations

import os

import psycopg
import pytest

from sentinel.job_queue import PostgresJobQueue
from sentinel.migrate import migrate
from sentinel.models import RemediationJob

_DATABASE_URL = os.environ.get("SENTINEL_DATABASE_URL", "")


@pytest.fixture()
def queue() -> PostgresJobQueue:
    if not _DATABASE_URL:
        pytest.skip("SENTINEL_DATABASE_URL is not configured")
    migrate(_DATABASE_URL)
    with psycopg.connect(_DATABASE_URL) as connection:
        connection.execute("TRUNCATE remediation_delivery_attempts")
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
