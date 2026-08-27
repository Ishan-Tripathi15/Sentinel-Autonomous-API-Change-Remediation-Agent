from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from sentinel.delivery_execution import DeliveryExecutionError, GitHubDeliveryExecutor
from sentinel.delivery_idempotency import DeliveryAttempt
from sentinel.delivery_reconciliation import RemoteDelivery
from sentinel.github_delivery import GitHubPullRequest
from sentinel.models import RemediationJob
from sentinel.write_authorization import RepositoryWriteAuthorization


def make_job() -> RemediationJob:
    return RemediationJob(
        job_id="job-123",
        organization_id="org-1",
        installation_id="installation-1",
        change_event_id="event-1",
        status="verified",
        dry_run=False,
    )


def make_authorization() -> RepositoryWriteAuthorization:
    return RepositoryWriteAuthorization.issue(
        make_job(),
        repository="acme/service",
        base_branch="main",
        authorized_by="policy-engine",
        authorized_at=datetime.now(UTC) - timedelta(seconds=1),
    )


def make_attempt(status: str, *, result: bool = False) -> DeliveryAttempt:
    return DeliveryAttempt(
        delivery_key="key",
        job_id="job-123",
        status=status,
        provider="github",
        delivery_owner="worker-1",
        lease_until=None,
        pull_request_number=42 if result else None,
        pull_request_url="https://github.com/acme/service/pull/42" if result else None,
        commit_sha="commit-sha" if result else None,
    )


def make_executor(attempt: DeliveryAttempt) -> tuple[GitHubDeliveryExecutor, MagicMock, MagicMock, MagicMock]:
    store = MagicMock()
    reconciler = MagicMock()
    client = MagicMock()
    store.acquire.return_value = attempt
    return (
        GitHubDeliveryExecutor(store, reconciler, client, owner="worker-1", lease_seconds=300),
        store,
        reconciler,
        client,
    )


def execute(executor: GitHubDeliveryExecutor, job: RemediationJob) -> object:
    return executor.execute(
        job,
        repository="acme/service",
        base_branch="main",
        title="chore: remediate",
        body="body",
        changes=[],
        authorization=make_authorization(),
    )


def test_fresh_delivery_is_started_and_persisted() -> None:
    executor, store, reconciler, client = make_executor(make_attempt("pending"))
    client.deliver.return_value = GitHubPullRequest(
        number=42,
        url="https://github.com/acme/service/pull/42",
        branch_name="sentinel/remediation/job-123",
        commit_sha="commit-sha",
    )
    store.record_result.return_value = make_attempt("succeeded", result=True)

    result = execute(executor, make_job())

    assert result.pull_request_number == 42
    store.begin.assert_called_once_with(delivery_key="key", owner="worker-1", lease_seconds=300)
    client.deliver.assert_called_once()
    store.record_result.assert_called_once()
    reconciler.reconcile.assert_not_called()


def test_succeeded_attempt_is_idempotent() -> None:
    executor, store, reconciler, client = make_executor(make_attempt("succeeded", result=True))

    result = execute(executor, make_job())

    assert result.commit_sha == "commit-sha"
    store.begin.assert_not_called()
    client.deliver.assert_not_called()
    reconciler.reconcile.assert_not_called()


def test_in_progress_attempt_is_reconciled_before_retry() -> None:
    executor, store, reconciler, client = make_executor(make_attempt("in_progress"))
    reconciler.reconcile.return_value = RemoteDelivery(
        pull_request_number=42,
        pull_request_url="https://github.com/acme/service/pull/42",
        branch_name="sentinel/remediation/job-123",
        commit_sha="commit-sha",
    )
    store.record_reconciled_result.return_value = make_attempt("succeeded", result=True)

    result = execute(executor, make_job())

    assert result.pull_request_number == 42
    reconciler.reconcile.assert_called_once()
    client.deliver.assert_not_called()
    store.record_reconciled_result.assert_called_once_with(
        delivery_key="key",
        owner="worker-1",
        pull_request_number=42,
        pull_request_url="https://github.com/acme/service/pull/42",
        commit_sha="commit-sha",
    )


def test_in_progress_attempt_without_remote_result_cannot_retry() -> None:
    executor, store, reconciler, client = make_executor(make_attempt("in_progress"))
    reconciler.reconcile.return_value = None

    with pytest.raises(DeliveryExecutionError, match="still ambiguous"):
        execute(executor, make_job())

    client.deliver.assert_not_called()
    store.record_reconciled_result.assert_not_called()
