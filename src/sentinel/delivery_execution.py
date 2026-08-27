from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .delivery_idempotency import (
    DeliveryAttempt,
    DeliveryAttemptStore,
    DeliveryIdempotencyError,
)
from .delivery_reconciliation import DeliveryReconciliationError, DeliveryReconciler
from .github_delivery import GitHubDeliveryClient, GitHubFileChange
from .models import RemediationJob


class DeliveryExecutionError(RuntimeError):
    """Raised when delivery cannot safely proceed or be completed."""


@dataclass(frozen=True)
class DeliveryExecutionResult:
    """Durable provider result returned after a successful delivery."""

    delivery_key: str
    pull_request_number: int
    pull_request_url: str
    commit_sha: str


class GitHubDeliveryExecutor:
    """Fence GitHub delivery with durable ownership and reconciliation."""

    def __init__(
        self,
        store: DeliveryAttemptStore,
        reconciler: DeliveryReconciler,
        client: GitHubDeliveryClient,
        *,
        owner: str,
        lease_seconds: int = 300,
    ) -> None:
        if not owner.strip():
            raise DeliveryExecutionError("delivery owner is required")
        if not 1 <= lease_seconds <= 3600:
            raise DeliveryExecutionError("lease_seconds must be between 1 and 3600")
        self._store = store
        self._reconciler = reconciler
        self._client = client
        self._owner = owner
        self._lease_seconds = lease_seconds

    def execute(
        self,
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        title: str,
        body: str,
        changes: Sequence[GitHubFileChange],
        allow_write: bool,
    ) -> DeliveryExecutionResult:
        change_list = list(changes)
        try:
            self._client.validate_request(
                job,
                repository=repository,
                base_branch=base_branch,
                title=title,
                body=body,
                changes=change_list,
                allow_write=allow_write,
            )
        except ValueError as exc:
            raise DeliveryExecutionError(str(exc)) from exc

        try:
            attempt = self._store.acquire(
                job=job,
                provider="github",
                owner=self._owner,
                repository=repository,
                base_branch=base_branch,
                lease_seconds=self._lease_seconds,
            )
        except DeliveryIdempotencyError as exc:
            raise DeliveryExecutionError(str(exc)) from exc

        if attempt.status == "succeeded":
            return self._result(attempt)
        if attempt.status == "in_progress":
            return self._reconcile(attempt, repository=repository, base_branch=base_branch)
        if attempt.status != "pending":
            raise DeliveryExecutionError(f"unsupported delivery attempt status: {attempt.status}")

        try:
            self._store.begin(
                delivery_key=attempt.delivery_key,
                owner=self._owner,
                lease_seconds=self._lease_seconds,
            )
        except DeliveryIdempotencyError as exc:
            raise DeliveryExecutionError(str(exc)) from exc

        try:
            remote = self._client.deliver(
                job,
                repository=repository,
                base_branch=base_branch,
                title=title,
                body=body,
                changes=change_list,
                allow_write=allow_write,
            )
        except Exception as exc:  # noqa: BLE001 - preserve ambiguity for reconciliation
            raise DeliveryExecutionError(
                "GitHub delivery outcome is ambiguous; reconcile before retrying"
            ) from exc

        try:
            persisted = self._store.record_result(
                delivery_key=attempt.delivery_key,
                owner=self._owner,
                pull_request_number=remote.number,
                pull_request_url=remote.url,
                commit_sha=remote.commit_sha,
            )
        except DeliveryIdempotencyError as exc:
            raise DeliveryExecutionError(
                "GitHub delivery succeeded but durable result could not be fenced"
            ) from exc
        return self._result(persisted)

    def _reconcile(
        self,
        attempt: DeliveryAttempt,
        *,
        repository: str,
        base_branch: str,
    ) -> DeliveryExecutionResult:
        expected_branch = f"sentinel/remediation/{attempt.job_id}"
        try:
            remote = self._reconciler.reconcile(
                attempt,
                repository=repository,
                base_branch=base_branch,
                expected_branch=expected_branch,
            )
        except DeliveryReconciliationError as exc:
            raise DeliveryExecutionError(str(exc)) from exc
        if remote is None:
            raise DeliveryExecutionError(
                "delivery is still ambiguous; provider reconciliation found no result"
            )
        if not remote.commit_sha:
            raise DeliveryExecutionError("reconciled GitHub delivery is missing commit SHA")
        try:
            persisted = self._store.record_reconciled_result(
                delivery_key=attempt.delivery_key,
                owner=self._owner,
                pull_request_number=remote.pull_request_number,
                pull_request_url=remote.pull_request_url,
                commit_sha=remote.commit_sha,
            )
        except DeliveryIdempotencyError as exc:
            raise DeliveryExecutionError(str(exc)) from exc
        return self._result(persisted)

    @staticmethod
    def _result(attempt: DeliveryAttempt) -> DeliveryExecutionResult:
        if (
            attempt.pull_request_number is None
            or not attempt.pull_request_url
            or not attempt.commit_sha
        ):
            raise DeliveryExecutionError("durable delivery result is incomplete")
        return DeliveryExecutionResult(
            delivery_key=attempt.delivery_key,
            pull_request_number=attempt.pull_request_number,
            pull_request_url=attempt.pull_request_url,
            commit_sha=attempt.commit_sha,
        )
