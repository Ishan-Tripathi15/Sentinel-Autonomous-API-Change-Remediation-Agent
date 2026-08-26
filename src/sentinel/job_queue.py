from __future__ import annotations

import json

from psycopg import Error
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .models import RemediationJob


class JobQueueError(RuntimeError):
    """Raised when the persistent remediation queue cannot complete an operation."""


class PostgresJobQueue:
    """PostgreSQL-backed durable queue using row locks for worker coordination."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        if not database_url.strip():
            raise JobQueueError("database URL is required")
        if min_size < 1 or max_size < min_size:
            raise JobQueueError("invalid database pool size")
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def enqueue(self, job: RemediationJob) -> None:
        """Insert a job exactly once; duplicate job IDs are idempotent."""
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO remediation_jobs (
                        job_id, organization_id, installation_id, change_event_id,
                        status, payload, available_at
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                    ON CONFLICT (job_id) DO NOTHING
                    """,
                    (
                        job.job_id, job.organization_id, job.installation_id,
                        job.change_event_id, job.status,
                        json.dumps(job.model_dump(mode="json")),
                    ),
                )
        except Error as exc:
            raise JobQueueError("job enqueue failed") from exc

    def claim(self, *, worker_id: str, lease_seconds: int = 300) -> RemediationJob | None:
        """Atomically claim one ready job and lease it to a worker."""
        if not worker_id.strip():
            raise JobQueueError("worker_id is required")
        if lease_seconds < 1 or lease_seconds > 3600:
            raise JobQueueError("lease_seconds must be between 1 and 3600")
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    WITH candidate AS (
                        SELECT job_id
                        FROM remediation_jobs
                        WHERE available_at <= CURRENT_TIMESTAMP
                          AND (status = 'queued' OR (status = 'running' AND lease_until < CURRENT_TIMESTAMP))
                        ORDER BY created_at ASC, job_id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE remediation_jobs AS job
                    SET status = 'running', worker_id = %s, attempts = attempts + 1,
                        lease_until = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                        updated_at = CURRENT_TIMESTAMP
                    FROM candidate
                    WHERE job.job_id = candidate.job_id
                    RETURNING job.payload
                    """,
                    (worker_id, lease_seconds),
                ).fetchone()
                return RemediationJob.model_validate(row["payload"]) if row else None
        except Error as exc:
            raise JobQueueError("job claim failed") from exc

    def complete(self, *, job_id: str, worker_id: str, payload: RemediationJob) -> None:
        """Complete a lease owned by this worker."""
        self._update_owned(job_id, worker_id, payload, payload.status, None)

    def fail(self, *, job_id: str, worker_id: str, payload: RemediationJob, retry_after_seconds: int = 30) -> None:
        """Return a failed job to the queue with bounded retry delay."""
        if retry_after_seconds < 0 or retry_after_seconds > 3600:
            raise JobQueueError("retry_after_seconds must be between 0 and 3600")
        self._update_owned(job_id, worker_id, payload, "queued", retry_after_seconds)

    def _update_owned(self, job_id: str, worker_id: str, payload: RemediationJob, status: str, retry_after_seconds: int | None) -> None:
        if not job_id.strip() or not worker_id.strip():
            raise JobQueueError("job_id and worker_id are required")
        try:
            with self._pool.connection() as connection:
                if retry_after_seconds is None:
                    result = connection.execute(
                        """
                        UPDATE remediation_jobs
                        SET status = %s, payload = %s::jsonb, worker_id = NULL,
                            lease_until = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s AND worker_id = %s
                        """,
                        (status, json.dumps(payload.model_dump(mode="json")), job_id, worker_id),
                    )
                else:
                    result = connection.execute(
                        """
                        UPDATE remediation_jobs
                        SET status = %s, payload = %s::jsonb, worker_id = NULL,
                            lease_until = NULL,
                            available_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = %s AND worker_id = %s
                        """,
                        (status, json.dumps(payload.model_dump(mode="json")), retry_after_seconds, job_id, worker_id),
                    )
                if result.rowcount != 1:
                    raise JobQueueError("job lease is not owned by worker")
        except JobQueueError:
            raise
        except Error as exc:
            raise JobQueueError("job update failed") from exc

    def close(self) -> None:
        self._pool.close()
