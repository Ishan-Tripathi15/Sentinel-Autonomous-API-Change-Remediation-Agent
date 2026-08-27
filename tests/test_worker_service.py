from __future__ import annotations

from sentinel.worker_service import runtime_config_from_environment


def test_runtime_config_uses_safe_defaults(monkeypatch) -> None:
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


def test_runtime_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("SENTINEL_WORKER_LEASE_SECONDS", "120")
    monkeypatch.setenv("SENTINEL_WORKER_POLL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("SENTINEL_WORKER_ERROR_BACKOFF_SECONDS", "0.25")
    monkeypatch.setenv("SENTINEL_WORKER_MAX_ERROR_BACKOFF_SECONDS", "5")

    config = runtime_config_from_environment()

    assert config.lease_seconds == 120
    assert config.poll_interval_seconds == 0.5
    assert config.error_backoff_seconds == 0.25
    assert config.max_error_backoff_seconds == 5.0
