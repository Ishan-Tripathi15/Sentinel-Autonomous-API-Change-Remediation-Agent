from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Error
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
    delivery_owner: str | None = None
    lease_until: datetime | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    commit_sha: str | None = None


def build_delivery_key(
    job: RemediationJob,
    *,
    provider: str,
    repository: str,
    base_branch: str,
) -> str:
    """Build a stable key from every immutable delivery identity input."""
    material = {
        "job_id": job.job_id,
        "organization_id": job.organization_id,
        "installation_id": job.installation_id,
        "change_event_id": job.change_event_id,
        "provider": provider,
        "repository": repository,
        "base_branch": base_branch,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class DeliveryAttemptStore:
    """Persist delivery ownership and provider results."""

    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def acquire(
        self,
        *,
        job: RemediationJob,
        provider: str,
        owner: str,
        repository: str,
        base_branch: str,
        lease_seconds: int = 300,
    ) -> DeliveryAttempt:
        if not provider.strip() or not owner.strip():
            raise DeliveryIdempotencyError("provider and owner are required")
        if not repository.strip() or not base_branch.strip():
            raise DeliveryIdempotencyError("repository and base branch are required")
        if not 1 <= lease_seconds <= 3600:
            raise DeliveryIdempotencyError("lease_seconds must be between 1 and 3600")

        key = build_delivery_key(
            job,
            provider=provider,
            repository=repository,
            base_branch=base_branch,
        )
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO remediation_delivery_attempts
                        (delivery_key, job_id, organization_id, installation_id,
                         repository, base_branch, provider, status, delivery_owner, lease_until)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s,
                            CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
                    ON CONFLICT (delivery_key) DO UPDATE SET
                        delivery_owner = CASE
                            WHEN remediation_delivery_attempts.status IN ('pending', 'in_progress')
                             AND (remediation_delivery_attempts.lease_until IS NULL
                                  OR remediation_delivery_attempts.lease_until < CURRENT_TIMESTAMP)
                            THEN EXCLUDED.delivery_owner
                            ELSE remediation_delivery_attempts.delivery_owner
                        END,
                        lease_until = CASE
                            WHEN remediation_delivery_attempts.status IN ('pending', 'in_progress')
                             AND (remediation_delivery_attempts.lease_until IS NULL
                                  OR remediation_delivery_attempts.lease_until < CURRENT_TIMESTAMP)
                            THEN EXCLUDED.lease_until
                            ELSE remediation_delivery_attempts.lease_until
                        END
                    RETURNING delivery_key, job_id, status, provider, delivery_owner,
                              lease_until, pull_request_number, pull_request_url, commit_sha
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
                conn.commit()
            except Error as exc:
                conn.rollback()
                raise DeliveryIdempotencyError("could not acquire delivery intent") from exc

        if row is None:
            raise DeliveryIdempotencyError("delivery intent was not returned")
        attempt = DeliveryAttempt(**dict(row))
        if attempt.status in {"pending", "in_progress"} and attempt.delivery_owner != owner:
            raise DeliveryIdempotencyError("delivery intent is owned by another worker")
        return attempt

    def begin(self, *, delivery_key: str, owner: str, lease_seconds: int = 300) -> DeliveryAttempt:
        if not owner.strip():
            raise DeliveryIdempotencyError("owner is required")
        if not 1 <= lease_seconds <= 3600:
            raise DeliveryIdempotencyError("lease_seconds must be between 1 and 3600")
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE remediation_delivery_attempts
                SET status = 'in_progress',
                    lease_until = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE delivery_key = %s
                  AND status = 'pending'
                  AND delivery_owner = %s
                  AND (lease_until IS NULL OR lease_until >= CURRENT_TIMESTAMP)
                RETURNING delivery_key, job_id, status, provider, delivery_owner,
                          lease_until, pull_request_number, pull_request_url, commit_sha
                """,
                (lease_seconds, delivery_key, owner),
            ).fetchone()
            conn.commit()
        if row is None:
            raise DeliveryIdempotencyError("delivery intent could not be started")
        return DeliveryAttempt(**dict(row))

    def record_result(
        self,
        *,
        delivery_key: str,
        owner: str,
        pull_request_number: int,
        pull_request_url: str,
        commit_sha: str | None = None,
    ) -> DeliveryAttempt:
        return self._record_success(
            delivery_key=delivery_key,
            owner=owner,
            pull_request_number=pull_request_number,
            pull_request_url=pull_request_url,
            commit_sha=commit_sha,
        )

    def record_reconciled_result(
        self,
        *,
        delivery_key: str,
        owner: str,
        pull_request_number: int,
        pull_request_url: str,
        commit_sha: str,
    ) -> DeliveryAttempt:
        """Persist a provider-discovered result after an ambiguous external call."""
        if not commit_sha:
            raise DeliveryIdempotencyError("reconciled result requires a commit SHA")
        return self._record_success(
            delivery_key=delivery_key,
            owner=owner,
            pull_request_number=pull_request_number,
            pull_request_url=pull_request_url,
            commit_sha=commit_sha,
        )

    def _record_success(
        self,
        *,
        delivery_key: str,
        owner: str,
        pull_request_number: int,
        pull_request_url: str,
        commit_sha: str | None,
    ) -> DeliveryAttempt:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE remediation_delivery_attempts
                SET status = 'succeeded',
                    pull_request_number = %s,
                    pull_request_url = %s,
                    commit_sha = %s,
                    lease_until = NULL,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE delivery_key = %s
                  AND status = 'in_progress'
                  AND delivery_owner = %s
                  AND (lease_until IS NULL OR lease_until >= CURRENT_TIMESTAMP)
                RETURNING delivery_key, job_id, status, provider, delivery_owner,
                          lease_until, pull_request_number, pull_request_url, commit_sha
                """,
                (
                    pull_request_number,
                    pull_request_url,
                    commit_sha,
                    delivery_key,
                    owner,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise DeliveryIdempotencyError("delivery result could not be fenced to owner")
        return DeliveryAttempt(**dict(row))
