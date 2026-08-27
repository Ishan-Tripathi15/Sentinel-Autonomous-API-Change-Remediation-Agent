from __future__ import annotations

from threading import Event, Thread

import pytest

from sentinel.models import RemediationJob
from sentinel.remediation_worker import RemediationWorkerError, RemediationWorkerResult
from sentinel.remediation_worker_runtime import (
    RemediationWorkerRuntime,
    WorkerRuntimeConfig,
    WorkerRuntimeError,
)


class FakeWorker:
    def __init__(self, results: list[RemediationWorkerResult | Exception | None]) -> None:
        self.results = iter(results)
        self.calls = 0
        self.lease_seconds: list[int] = []

    def run_once(self, *, lease_seconds: int = 300) -> RemediationWorkerResult | None:
        self.calls += 1
        self.lease_seconds.append(lease_seconds)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def make_result(completed: bool) -> RemediationWorkerResult:
    job = RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="dry-run-complete" if completed else "failed",
        dry_run=True,
    )
    return RemediationWorkerResult(job=job, completed=completed)


def test_runtime_counts_jobs_until_worker_requests_shutdown() -> None:
    stop_event = Event()
    worker = FakeWorker([make_result(True), make_result(False), None])

    original_run_once = worker.run_once

    def run_once(*, lease_seconds: int = 300) -> RemediationWorkerResult | None:
        result = original_run_once(lease_seconds=lease_seconds)
        if result is None:
            stop_event.set()
        return result

    worker.run_once = run_once
    runtime = RemediationWorkerRuntime(
        worker,
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
    worker = FakeWorker([
        RemediationWorkerError("queue unavailable"),
        make_result(True),
        None,
    ])

    original_run_once = worker.run_once

    def run_once(*, lease_seconds: int = 300) -> RemediationWorkerResult | None:
        result = original_run_once(lease_seconds=lease_seconds)
        if result is None:
            stop_event.set()
        return result

    worker.run_once = run_once
    runtime = RemediationWorkerRuntime(
        worker,
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
    worker = FakeWorker([None])
    runtime = RemediationWorkerRuntime(
        worker,
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
