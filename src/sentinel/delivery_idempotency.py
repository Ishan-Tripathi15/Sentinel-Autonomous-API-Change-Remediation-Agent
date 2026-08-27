from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from psycopg import Error
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .models import RemediationJob


class DeliveryIdempotencyError(RuntimeError):
    """Raised when durable delivery intent cannot be acquired or recorded."""


@dataclass(frozen=True)
class DeliveryAttempt:
    delivery_key: str
    job_id: str
    status: str
    provider: str
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    commit_sha: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class PostgresDeliveryIdempotency:
    """Persist provider delivery intent so retries resolve to one attempt."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        if not database_url.strip():
            raise DeliveryIdempotencyError("database URL is required")
        if min_size < 1 or max_size < min_size:
            raise DeliveryIdempotencyError("invalid database pool size")
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    @staticmethod
    def delivery_key(
        job: RemediationJob,
        *,
        provider: str,
        repository: str,
        base_branch: str,
    ) -> str:
        """Build a stable key from immutable delivery identity, not mutable status."""
        material = {
            "job_id": job.job_id,
            "organization_id": job.organization_id,
            "installation_id": job.installation_id,
            "change_event_id": job.change_event_id,
            "provider": provider,
            "repository": repository,
            "base_branch": base_branch,
        }
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def acquire(
        self,
        job: RemediationJob,
        *,
        provider: str,
        repository: str,
        base_branch: str,
    ) -> DeliveryAttempt:
        if not provider.strip() or not repository.strip() or not base_branch.strip():
            raise DeliveryIdempotencyError("provider, repository and base_branch are required")
        key = self.delivery_key(
            job,
            provider=provider,
            repository=repository,
            base_branch=base_branch,
        )
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO remediation_delivery_attempts (
                        delivery_key, job_id, organization_id, installation_id,
                        repository, base_branch, status, provider
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                    ON CONFLICT (delivery_key) DO UPDATE
                    SET updated_at = remediation_delivery_attempts.updated_at
                    RETURNING *
                    """,
                    (
                        key,
                        job.job_id,
                        job.organization_id,
                        job.installation_id,
                        repository,
                        base_branch,
                        provider,
                    ),
                ).fetchone()
                if row is None:
                    raise DeliveryIdempotencyError("delivery attempt acquisition returned no row")
                return self._attempt(row)
        except Error as exc:
            raise DeliveryIdempotencyError("delivery attempt acquisition failed") from exc

    def get(self, delivery_key: str) -> DeliveryAttempt | None:
        if not delivery_key.strip():
            raise DeliveryIdempotencyError("delivery_key is required")
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    "SELECT * FROM remediation_delivery_attempts WHERE delivery_key = %s",
                    (delivery_key,),
                ).fetchone()
                return self._attempt(row) if row else None
        except Error as exc:
            raise DeliveryIdempotencyError("delivery attempt lookup failed") from exc

    def record_success(
        self,
        *,
        delivery_key: str,
        pull_request_number: int,
        pull_request_url: str,
        commit_sha: str,
    ) -> DeliveryAttempt:
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    UPDATE remediation_delivery_attempts
                    SET status = 'succeeded', pull_request_number = %s,
                        pull_request_url = %s, commit_sha = %s,
                        completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE delivery_key = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (pull_request_number, pull_request_url, commit_sha, delivery_key),
                ).fetchone()
                if row is None:
                    raise DeliveryIdempotencyError("delivery attempt is not pending")
                return self._attempt(row)
        except DeliveryIdempotencyError:
            raise
        except Error as exc:
            raise DeliveryIdempotencyError("delivery success recording failed") from exc

    def record_failure(
        self,
        *,
        delivery_key: str,
        error_type: str,
        error_message: str,
    ) -> DeliveryAttempt:
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    UPDATE remediation_delivery_attempts
                    SET status = 'failed', error_type = %s, error_message = %s,
                        completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE delivery_key = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (error_type, error_message, delivery_key),
                ).fetchone()
                if row is None:
                    raise DeliveryIdempotencyError("delivery attempt is not pending")
                return self._attempt(row)
        except DeliveryIdempotencyError:
            raise
        except Error as exc:
            raise DeliveryIdempotencyError("delivery failure recording failed") from exc

    def close(self) -> None:
        self._pool.close()

    @staticmethod
    def _attempt(row: dict[str, Any]) -> DeliveryAttempt:
        return DeliveryAttempt(
            delivery_key=row["delivery_key"],
            job_id=row["job_id"],
            status=row["status"],
            provider=row["provider"],
            pull_request_number=row.get("pull_request_number"),
            pull_request_url=row.get("pull_request_url"),
            commit_sha=row.get("commit_sha"),
            error_type=row.get("error_type"),
            error_message=row.get("error_message"),
            completed_at=row.get("completed_at"),
        )
