from __future__ import annotations

import os
from collections.abc import Callable
from signal import SIGINT, SIGTERM, signal

from .remediation_worker import RemediationWorker
from .remediation_worker_runtime import RemediationWorkerRuntime, WorkerRuntimeConfig

WorkerFactory = Callable[[], RemediationWorker]


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        field_name = name.removeprefix("SENTINEL_WORKER_").lower()
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def runtime_config_from_environment() -> WorkerRuntimeConfig:
    """Build bounded worker runtime configuration from environment variables."""
    return WorkerRuntimeConfig(
        lease_seconds=_bounded_int("SENTINEL_WORKER_LEASE_SECONDS", 300, 1, 3600),
        poll_interval_seconds=_positive_float("SENTINEL_WORKER_POLL_INTERVAL_SECONDS", 1.0),
        error_backoff_seconds=_positive_float("SENTINEL_WORKER_ERROR_BACKOFF_SECONDS", 1.0),
        max_error_backoff_seconds=_positive_float("SENTINEL_WORKER_MAX_ERROR_BACKOFF_SECONDS", 30.0),
    )


def install_signal_handlers(runtime: RemediationWorkerRuntime) -> None:
    """Stop cleanly on normal container/process termination signals."""
    def stop_handler(_signum: int, _frame: object) -> None:
        runtime.request_stop()

    signal(SIGTERM, stop_handler)
    signal(SIGINT, stop_handler)


def run_worker(factory: WorkerFactory) -> int:
    """Run the worker service and return a process exit code."""
    runtime = RemediationWorkerRuntime(factory(), config=runtime_config_from_environment())
    install_signal_handlers(runtime)
    runtime.run()
    return 0


def main() -> None:
    """Worker CLI entrypoint; dependency construction belongs to deployment code."""
    raise RuntimeError(
        "Worker dependencies are not configured. Use run_worker(factory) from the service deployment entrypoint."
    )


if __name__ == "__main__":
    main()
