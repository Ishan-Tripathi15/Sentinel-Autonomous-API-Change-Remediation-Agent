from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .delivery_idempotency import DeliveryAttempt


class DeliveryReconciliationError(RuntimeError):
    """Raised when an ambiguous delivery cannot be safely reconciled."""


@dataclass(frozen=True)
class RemoteDelivery:
    """Provider-side delivery discovered during reconciliation."""

    pull_request_number: int
    pull_request_url: str
    branch_name: str
    commit_sha: str | None = None


class DeliveryProvider(Protocol):
    def find_delivery(
        self, *, repository: str, branch_name: str, base_branch: str
    ) -> RemoteDelivery | None: ...


class DeliveryReconciler:
    """Resolve durable in-progress attempts against provider state before retrying."""

    def __init__(self, provider: DeliveryProvider) -> None:
        self._provider = provider

    def reconcile(
        self,
        attempt: DeliveryAttempt,
        *,
        repository: str,
        base_branch: str,
        expected_branch: str,
    ) -> RemoteDelivery | None:
        if attempt.status != "in_progress":
            return None
        if not expected_branch:
            raise DeliveryReconciliationError("expected delivery branch is required")

        remote = self._provider.find_delivery(
            repository=repository,
            branch_name=expected_branch,
            base_branch=base_branch,
        )
        if remote is None:
            return None
        if remote.branch_name != expected_branch:
            raise DeliveryReconciliationError("provider returned an unexpected delivery branch")
        return remote
