from __future__ import annotations

import pytest

from sentinel.worker_service import runtime_config_from_environment


def test_worker_service_defaults_are_bounded(monkeypatch) -> None:
    for name in (
        "SENTINEL_WORKER_LEASE_SECONDS",
        "SENTINEL_WORKER_POLL_INTERVAL_SECONDS",
        "SENTINEL_WORKER_ERROR_BACKOFF_SECONDS",
        "SENTINEL_WORKER_MAX_ERROR_BACKOFF_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    config = runtime_config_from_environment()

    assert config.lease_seconds == 300
    assert config.poll_interval_seconds == 1.0
    assert config.error_backoff_seconds == 1.0
    assert config.max_error_backoff_seconds == 30.0


def test_worker_service_rejects_invalid_environment(monkeypatch) -> None:
    monkeypatch.setenv("SENTINEL_WORKER_LEASE_SECONDS", "0")
    with pytest.raises(ValueError, match="lease_seconds"):
        runtime_config_from_environment()

    monkeypatch.setenv("SENTINEL_WORKER_LEASE_SECONDS", "300")
    monkeypatch.setenv("SENTINEL_WORKER_POLL_INTERVAL_SECONDS", "-1")
    with pytest.raises(ValueError, match="positive number"):
        runtime_config_from_environment()
