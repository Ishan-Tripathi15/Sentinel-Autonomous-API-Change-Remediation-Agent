from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from psycopg_pool import ConnectionPool

from .models import RemediationJob


class WriteAuthorizationError(ValueError):
    """Raised when repository-write authorization is invalid or unavailable."""


@dataclass(frozen=True)
class RepositoryWriteAuthorization:
    """Immutable, job-bound authority for autonomous repository writes."""

    authorization_id: str
    job_id: str
    organization_id: str
    installation_id: str
    repository: str
    base_branch: str
    authorized_by: str
    policy_version: str
    authorized_at: datetime
    expires_at: datetime

    @classmethod
    def issue(
        cls,
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        authorized_by: str,
        policy_version: str = "write-v1",
        authorized_at: datetime | None = None,
        ttl_seconds: int = 900,
    ) -> RepositoryWriteAuthorization:
        now = authorized_at or datetime.now(UTC)
        if now.tzinfo is None:
            raise WriteAuthorizationError("authorization timestamp must be timezone-aware")
        if not authorized_by.strip() or not policy_version.strip():
            raise WriteAuthorizationError("authorizer and policy version are required")
        if not repository.strip() or not base_branch.strip():
            raise WriteAuthorizationError("repository and base branch are required")
        if not 1 <= ttl_seconds <= 3600:
            raise WriteAuthorizationError("authorization TTL must be between 1 and 3600 seconds")
        return cls(
            authorization_id=str(uuid4()),
            job_id=job.job_id,
            organization_id=job.organization_id,
            installation_id=job.installation_id,
            repository=repository,
            base_branch=base_branch,
            authorized_by=authorized_by,
            policy_version=policy_version,
            authorized_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    def validate_for(
        self,
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise WriteAuthorizationError("validation timestamp must be timezone-aware")
        if self.job_id != job.job_id:
            raise WriteAuthorizationError("authorization does not belong to this job")
        if self.organization_id != job.organization_id:
            raise WriteAuthorizationError("authorization organization does not match job")
        if self.installation_id != job.installation_id:
            raise WriteAuthorizationError("authorization installation does not match job")
        if self.repository != repository or self.base_branch != base_branch:
            raise WriteAuthorizationError("authorization repository target does not match")
        if job.dry_run:
            raise WriteAuthorizationError("dry-run remediation jobs cannot perform repository writes")
        if self.expires_at <= current:
            raise WriteAuthorizationError("repository-write authorization has expired")
        if self.authorized_at > current:
            raise WriteAuthorizationError("repository-write authorization is not yet active")

    def activate_job(
        self,
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        now: datetime | None = None,
    ) -> RemediationJob:
        """Cross the write gate while preserving every immutable job identity field."""
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise WriteAuthorizationError("validation timestamp must be timezone-aware")
        if self.job_id != job.job_id:
            raise WriteAuthorizationError("authorization does not belong to this job")
        if self.organization_id != job.organization_id:
            raise WriteAuthorizationError("authorization organization does not match job")
        if self.installation_id != job.installation_id:
            raise WriteAuthorizationError("authorization installation does not match job")
        if self.repository != repository or self.base_branch != base_branch:
            raise WriteAuthorizationError("authorization repository target does not match")
        if self.expires_at <= current:
            raise WriteAuthorizationError("repository-write authorization has expired")
        if self.authorized_at > current:
            raise WriteAuthorizationError("repository-write authorization is not yet active")
        return job.model_copy(update={"dry_run": False})


class WriteAuthorizationStore:
    """Durable PostgreSQL repository-write authorization store."""

    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def issue(self, authorization: RepositoryWriteAuthorization) -> RepositoryWriteAuthorization:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO remediation_write_authorizations
                    (authorization_id, job_id, organization_id, installation_id,
                     repository, base_branch, authorized_by, policy_version,
                     authorized_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id, repository, base_branch) DO NOTHING
                RETURNING authorization_id, job_id, organization_id, installation_id,
                          repository, base_branch, authorized_by, policy_version,
                          authorized_at, expires_at
                """,
                (
                    authorization.authorization_id,
                    authorization.job_id,
                    authorization.organization_id,
                    authorization.installation_id,
                    authorization.repository,
                    authorization.base_branch,
                    authorization.authorized_by,
                    authorization.policy_version,
                    authorization.authorized_at,
                    authorization.expires_at,
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise WriteAuthorizationError("repository-write authorization already exists")
        return RepositoryWriteAuthorization(**dict(row))

    def get_active(
        self,
        *,
        job: RemediationJob,
        repository: str,
        base_branch: str,
        now: datetime | None = None,
    ) -> RepositoryWriteAuthorization | None:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise WriteAuthorizationError("validation timestamp must be timezone-aware")
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT authorization_id, job_id, organization_id, installation_id,
                       repository, base_branch, authorized_by, policy_version,
                       authorized_at, expires_at
                FROM remediation_write_authorizations
                WHERE job_id = %s
                  AND organization_id = %s
                  AND installation_id = %s
                  AND repository = %s
                  AND base_branch = %s
                  AND revoked_at IS NULL
                  AND expires_at > %s
                ORDER BY authorized_at DESC
                LIMIT 1
                """,
                (job.job_id, job.organization_id, job.installation_id, repository, base_branch, current),
            ).fetchone()
        if row is None:
            return None
        return RepositoryWriteAuthorization(**dict(row))

    def revoke(self, *, authorization_id: str) -> None:
        if not authorization_id.strip():
            raise WriteAuthorizationError("authorization_id is required")
        with self._pool.connection() as connection:
            result = connection.execute(
                """
                UPDATE remediation_write_authorizations
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE authorization_id = %s AND revoked_at IS NULL
                """,
                (authorization_id,),
            )
            connection.commit()
        if result.rowcount != 1:
            raise WriteAuthorizationError("authorization not found or already revoked")
