from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
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
    delivery_owner: str | None = None
    lease_until: datetime | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None


def build_delivery_key(job: RemediationJob) -> str:
    """Build a stable key from immutable remediation identity."""
    material = {
        "job_id": job.job_id,
        "organization_id": job.organization_id,
        "installation_id": job.installation_id,
        "change_event_id": job.change_event_id,
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
        lease_seconds: int = 300,
    ) -> DeliveryAttempt:
        key = build_delivery_key(job)
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO remediation_delivery_attempts
                        (delivery_key, job_id, provider, status, delivery_owner, lease_until)
                    VALUES (%s, %s, %s, 'pending', %s,
                            CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
                    ON CONFLICT (delivery_key) DO UPDATE SET
                        delivery_owner = CASE
                            WHEN remediation_delivery_attempts.status = 'pending'
                             AND (remediation_delivery_attempts.lease_until IS NULL
                                  OR remediation_delivery_attempts.lease_until < CURRENT_TIMESTAMP)
                            THEN EXCLUDED.delivery_owner
                            ELSE remediation_delivery_attempts.delivery_owner
                        END,
                        lease_until = CASE
                            WHEN remediation_delivery_attempts.status = 'pending'
                             AND (remediation_delivery_attempts.lease_until IS NULL
                                  OR remediation_delivery_attempts.lease_until < CURRENT_TIMESTAMP)
                            THEN EXCLUDED.lease_until
                            ELSE remediation_delivery_attempts.lease_until
                        END
                    RETURNING delivery_key, job_id, status, provider, delivery_owner,
                              lease_until, pull_request_number, pull_request_url
                    """,
                    (key, job.job_id, provider, owner, lease_seconds),
                ).fetchone()
                conn.commit()
            except Error as exc:
                conn.rollback()
                raise DeliveryIdempotencyError("could not acquire delivery intent") from exc

        if row is None:
            raise DeliveryIdempotencyError("delivery intent was not returned")
        attempt = DeliveryAttempt(**dict(row))
        if attempt.status == "pending" and attempt.delivery_owner != owner:
            raise DeliveryIdempotencyError("delivery intent is owned by another worker")
        return attempt

    def record_result(
        self,
        *,
        delivery_key: str,
        owner: str,
        pull_request_number: int,
        pull_request_url: str,
    ) -> DeliveryAttempt:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE remediation_delivery_attempts
                SET status = 'succeeded',
                    pull_request_number = %s,
                    pull_request_url = %s,
                    lease_until = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE delivery_key = %s
                  AND status = 'pending'
                  AND delivery_owner = %s
                  AND (lease_until IS NULL OR lease_until >= CURRENT_TIMESTAMP)
                RETURNING delivery_key, job_id, status, provider, delivery_owner,
                          lease_until, pull_request_number, pull_request_url
                """,
                (pull_request_number, pull_request_url, delivery_key, owner),
            ).fetchone()
            conn.commit()
        if row is None:
            raise DeliveryIdempotencyError("delivery result could not be fenced to owner")
        return DeliveryAttempt(**dict(row))
