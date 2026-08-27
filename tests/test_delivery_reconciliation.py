from __future__ import annotations

from sentinel.delivery_idempotency import DeliveryAttempt
from sentinel.delivery_reconciliation import DeliveryReconciler, RemoteDelivery


def attempt(status: str = "in_progress") -> DeliveryAttempt:
    return DeliveryAttempt(
        delivery_key="delivery-key",
        job_id="job-1",
        status=status,
        provider="github",
        delivery_owner="worker-1",
    )


def test_reconciler_does_not_call_provider_for_terminal_attempt() -> None:
    class Provider:
        called = False

        def find_delivery(self, **_kwargs):
            self.called = True

    provider = Provider()
    result = DeliveryReconciler(provider).reconcile(
        attempt("succeeded"),
        repository="acme/api",
        base_branch="main",
        expected_branch="sentinel/remediation/job-1",
    )

    assert result is None
    assert provider.called is False


def test_reconciler_returns_remote_delivery_for_in_progress_attempt() -> None:
    remote = RemoteDelivery(
        pull_request_number=42,
        pull_request_url="https://github.com/acme/api/pull/42",
        branch_name="sentinel/remediation/job-1",
        commit_sha="abc123",
    )

    class Provider:
        def find_delivery(self, **kwargs):
            assert kwargs == {
                "repository": "acme/api",
                "branch_name": "sentinel/remediation/job-1",
                "base_branch": "main",
            }
            return remote

    assert DeliveryReconciler(Provider()).reconcile(
        attempt(),
        repository="acme/api",
        base_branch="main",
        expected_branch="sentinel/remediation/job-1",
    ) == remote
