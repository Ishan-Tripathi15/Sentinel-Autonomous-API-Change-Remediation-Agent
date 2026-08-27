from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sentinel.models import RemediationJob
from sentinel.write_authorization import RepositoryWriteAuthorization, WriteAuthorizationError


def make_job(*, dry_run: bool = True) -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="verified",
        dry_run=dry_run,
    )


def make_authorization(*, job: RemediationJob | None = None, expires_in: int = 900):
    current = datetime(2026, 8, 28, 12, tzinfo=UTC)
    return RepositoryWriteAuthorization.issue(
        job or make_job(),
        repository="acme/service",
        base_branch="main",
        authorized_by="policy-engine",
        authorized_at=current,
        ttl_seconds=expires_in,
    )


def test_authorization_activation_is_required_for_write() -> None:
    authorization = make_authorization()
    with pytest.raises(WriteAuthorizationError, match="dry-run"):
        authorization.validate_for(
            make_job(),
            repository="acme/service",
            base_branch="main",
            now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
        )

    activated = authorization.activate_job(
        make_job(),
        repository="acme/service",
        base_branch="main",
        now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
    )
    assert activated.dry_run is False
    authorization.validate_for(
        activated,
        repository="acme/service",
        base_branch="main",
        now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
    )


def test_authorization_binds_job_and_repository_identity() -> None:
    authorization = make_authorization()
    job = authorization.activate_job(
        make_job(),
        repository="acme/service",
        base_branch="main",
        now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
    )
    with pytest.raises(WriteAuthorizationError, match="job"):
        authorization.validate_for(
            job.model_copy(update={"job_id": "other"}),
            repository="acme/service",
            base_branch="main",
            now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
        )

    with pytest.raises(WriteAuthorizationError, match="repository"):
        authorization.validate_for(
            job, repository="acme/other", base_branch="main", now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC)
        )


def test_expired_authorization_is_rejected() -> None:
    authorization = make_authorization(expires_in=60)
    job = authorization.activate_job(
        make_job(),
        repository="acme/service",
        base_branch="main",
        now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
    )
    with pytest.raises(WriteAuthorizationError, match="expired"):
        authorization.validate_for(
            job,
            repository="acme/service",
            base_branch="main",
            now=datetime(2026, 8, 28, 12, 1, 1, tzinfo=UTC),
        )


def test_authorization_cannot_activate_after_expiry() -> None:
    authorization = make_authorization(expires_in=60)
    with pytest.raises(WriteAuthorizationError, match="expired"):
        authorization.activate_job(
            make_job(),
            repository="acme/service",
            base_branch="main",
            now=datetime(2026, 8, 28, 12, 1, 1, tzinfo=UTC),
        )


def test_authorization_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(WriteAuthorizationError, match="timezone-aware"):
        RepositoryWriteAuthorization.issue(
            make_job(),
            repository="acme/service",
            base_branch="main",
            authorized_by="policy-engine",
            authorized_at=datetime(2026, 8, 28, 12),
        )


def test_authorization_ttl_is_bounded() -> None:
    with pytest.raises(WriteAuthorizationError, match="TTL"):
        RepositoryWriteAuthorization.issue(
            make_job(),
            repository="acme/service",
            base_branch="main",
            authorized_by="policy-engine",
            ttl_seconds=3601,
        )
