from __future__ import annotations

from threading import Event, Thread

import pytest

from sentinel.remediation_worker_runtime import (
    RemediationWorkerRuntime,
    WorkerRuntimeConfig,
    WorkerRuntimeError,
)


class FakeWorker:
    def __init__(self, results: list[object], stop_event: Event) -> None:
        self.results = iter(results)
        self.stop_event = stop_event
        self.calls = 0
        self.lease_seconds: list[int] = []

    def run_once(self, *, lease_seconds: int = 300) -> object:
        self.calls += 1
        self.lease_seconds.append(lease_seconds)
        result = next(self.results)
        if result == "stop":
            self.stop_event.set()
            return None
        return result


class Result:
    def __init__(self, completed: bool) -> None:
        self.completed = completed


def test_runtime_counts_completed_and_failed_jobs() -> None:
    stop_event = Event()
    worker = FakeWorker([Result(True), Result(False), "stop"], stop_event)
    runtime = RemediationWorkerRuntime(
        worker,  # type: ignore[arg-type]
        config=WorkerRuntimeConfig(lease_seconds=42),
        stop_event=stop_event,
    )

    stats = runtime.run()

    assert stats.jobs_completed == 1
    assert stats.jobs_failed == 1
    assert stats.runtime_errors == 0
    assert worker.lease_seconds == [42, 42, 42]
    assert stats.duration_seconds >= 0


def test_runtime_backs_off_after_worker_error_and_recovers() -> None:
    stop_event = Event()
    worker = FakeWorker([RuntimeError("placeholder"), Result(True), "stop"], stop_event)

    original = worker.results

    def run_once(*, lease_seconds: int = 300) -> object:
        worker.calls += 1
        worker.lease_seconds.append(lease_seconds)
        value = next(original)
        if isinstance(value, Exception):
            from sentinel.remediation_worker import RemediationWorkerError

            raise RemediationWorkerError(str(value))
        if value == "stop":
            stop_event.set()
            return None
        return value

    worker.run_once = run_once  # type: ignore[method-assign]
    runtime = RemediationWorkerRuntime(
        worker,  # type: ignore[arg-type]
        config=WorkerRuntimeConfig(
            poll_interval_seconds=0.001,
            error_backoff_seconds=0.001,
            max_error_backoff_seconds=0.002,
        ),
        stop_event=stop_event,
    )

    stats = runtime.run()

    assert stats.runtime_errors == 1
    assert stats.jobs_completed == 1


def test_request_stop_interrupts_runtime() -> None:
    stop_event = Event()
    worker = FakeWorker([], stop_event)
    runtime = RemediationWorkerRuntime(
        worker,  # type: ignore[arg-type]
        config=WorkerRuntimeConfig(poll_interval_seconds=10),
        stop_event=stop_event,
    )

    thread = Thread(target=runtime.run)
    thread.start()
    runtime.request_stop()
    thread.join(timeout=1)

    assert not thread.is_alive()


def test_runtime_config_rejects_unsafe_values() -> None:
    with pytest.raises(WorkerRuntimeError, match="lease_seconds"):
        WorkerRuntimeConfig(lease_seconds=0)
    with pytest.raises(WorkerRuntimeError, match="finite positive"):
        WorkerRuntimeConfig(poll_interval_seconds=0)
    with pytest.raises(WorkerRuntimeError, match="cannot exceed"):
        WorkerRuntimeConfig(error_backoff_seconds=2, max_error_backoff_seconds=1)
