from __future__ import annotations

from sentinel.worker_observability import WorkerMetrics


def test_metrics_start_healthy_and_idle() -> None:
    metrics = WorkerMetrics()

    snapshot = metrics.snapshot()

    assert snapshot.healthy is True
    assert snapshot.jobs_completed == 0
    assert snapshot.jobs_failed == 0
    assert snapshot.runtime_errors == 0
    assert snapshot.jobs_in_progress == 0
    assert snapshot.last_activity_at_monotonic is None
    assert snapshot.uptime_seconds >= 0


def test_metrics_track_job_lifecycle() -> None:
    metrics = WorkerMetrics()

    metrics.job_started()
    assert metrics.snapshot().jobs_in_progress == 1

    metrics.job_completed()
    snapshot = metrics.snapshot()
    assert snapshot.jobs_in_progress == 0
    assert snapshot.jobs_completed == 1
    assert snapshot.jobs_failed == 0
    assert snapshot.last_activity_at_monotonic is not None

    metrics.job_started()
    metrics.job_failed()
    snapshot = metrics.snapshot()
    assert snapshot.jobs_in_progress == 0
    assert snapshot.jobs_completed == 1
    assert snapshot.jobs_failed == 1


def test_metrics_track_runtime_errors_and_serialize() -> None:
    metrics = WorkerMetrics()
    metrics.runtime_error()

    snapshot = metrics.snapshot()
    payload = snapshot.as_dict()

    assert snapshot.runtime_errors == 1
    assert payload["healthy"] is True
    assert payload["runtime_errors"] == 1
    assert payload["jobs_in_progress"] == 0
