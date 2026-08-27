from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Error
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .github_delivery import GitHubPullRequest
from .models import RemediationJob


class DeliveryIdempotencyError(RuntimeError):
    """Raised when durable delivery intent cannot be acquired or recorded."""


@dataclass(frozen=True)
class DeliveryAttempt:
    delivery_key: str
    job_id: str
    status: str
    provider: str
    delivery_owner: str | None = None
    lease_until: datetime | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    commit_sha: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class PostgresDeliveryIdempotency:
    """Persist and fence one provider delivery intent at a time."""

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
    def delivery_key(job: RemediationJob, *, provider: str, repository: str, base_branch: str) -> str:
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
        owner: str,
        lease_seconds: int = 300,
    ) -> DeliveryAttempt:
        if not all(value.strip() for value in (provider, repository, base_branch, owner)):
            raise DeliveryIdempotencyError("provider, repository, base_branch and owner are required")
        if lease_seconds < 1 or lease_seconds > 3600:
            raise DeliveryIdempotencyError("lease_seconds must be between 1 and 3600")
        key = self.delivery_key(job, provider=provider, repository=repository, base_branch=base_branch)
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    """
                    INSERT INTO remediation_delivery_attempts (
                        delivery_key, job_id, organization_id, installation_id,
                        repository, base_branch, status, provider,
                        delivery_owner, lease_until
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'in_progress', %s, %s,
                              CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
                    ON CONFLICT (delivery_key) DO UPDATE
                    SET delivery_owner = CASE
                            WHEN remediation_delivery_attempts.status = 'in_progress'
                                 AND remediation_delivery_attempts.lease_until >= CURRENT_TIMESTAMP
                            THEN remediation_delivery_attempts.delivery_owner
                            ELSE EXCLUDED.delivery_owner
                        END,
                        lease_until = CASE
                            WHEN remediation_delivery_attempts.status = 'in_progress'
                                 AND remediation_delivery_attempts.lease_until >= CURRENT_TIMESTAMP
                            THEN remediation_delivery_attempts.lease_until
                            ELSE EXCLUDED.lease_until
                        END,
                        status = CASE
                            WHEN remediation_delivery_attempts.status = 'succeeded'
                            THEN 'succeeded'
                            WHEN remediation_delivery_attempts.status = 'in_progress'
                                 AND remediation_delivery_attempts.lease_until >= CURRENT_TIMESTAMP
                            THEN 'in_progress'
                            ELSE 'in_progress'
                        END,
                        updated_at = CURRENT_TIMESTAMP
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
                        owner,
                        lease_seconds,
                    ),
                ).fetchone()
                if row is None:
                    raise DeliveryIdempotencyError("delivery attempt acquisition returned no row")
                attempt = self._attempt(row)
                if attempt.status == "in_progress" and attempt.delivery_owner != owner:
                    raise DeliveryIdempotencyError("delivery attempt is owned by another worker")
                return attempt
        except DeliveryIdempotencyError:
            raise
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

    def record_success(self, *, delivery_key: str, owner: str, pull_request_number: int, pull_request_url: str, commit_sha: str) -> DeliveryAttempt:
        return self._record_terminal(
            delivery_key,
            owner,
            "succeeded",
            (pull_request_number, pull_request_url, commit_sha),
        )

    def record_failure(self, *, delivery_key: str, owner: str, error_type: str, error_message: str) -> DeliveryAttempt:
        return self._record_terminal(delivery_key, owner, "failed", (error_type, error_message))

    def close(self) -> None:
        self._pool.close()

    def _record_terminal(self, delivery_key: str, owner: str, status: str, values: tuple[Any, ...]) -> DeliveryAttempt:
        try:
            with self._pool.connection() as connection:
                if status == "succeeded":
                    row = connection.execute(
                        """
                        UPDATE remediation_delivery_attempts
                        SET status = 'succeeded', pull_request_number = %s,
                            pull_request_url = %s, commit_sha = %s,
                            delivery_owner = NULL, lease_until = NULL,
                            completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE delivery_key = %s AND status = 'in_progress'
                          AND delivery_owner = %s AND lease_until >= CURRENT_TIMESTAMP
                        RETURNING *
                        """,
                        (*values, delivery_key, owner),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        UPDATE remediation_delivery_attempts
                        SET status = 'failed', error_type = %s, error_message = %s,
                            delivery_owner = NULL, lease_until = NULL,
                            completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE delivery_key = %s AND status = 'in_progress'
                          AND delivery_owner = %s AND lease_until >= CURRENT_TIMESTAMP
                        RETURNING *
                        """,
                        (*values, delivery_key, owner),
                    ).fetchone()
                if row is None:
                    raise DeliveryIdempotencyError("delivery attempt is no longer owned")
                return self._attempt(row)
        except DeliveryIdempotencyError:
            raise
        except Error as exc:
            raise DeliveryIdempotencyError("delivery terminal-state recording failed") from exc

    @staticmethod
    def _attempt(row: dict[str, Any]) -> DeliveryAttempt:
        return DeliveryAttempt(
            delivery_key=row["delivery_key"],
            job_id=row["job_id"],
            status=row["status"],
            provider=row["provider"],
            delivery_owner=row.get("delivery_owner"),
            lease_until=row.get("lease_until"),
            pull_request_number=row.get("pull_request_number"),
            pull_request_url=row.get("pull_request_url"),
            commit_sha=row.get("commit_sha"),
            error_type=row.get("error_type"),
            error_message=row.get("error_message"),
            completed_at=row.get("completed_at"),
        )
