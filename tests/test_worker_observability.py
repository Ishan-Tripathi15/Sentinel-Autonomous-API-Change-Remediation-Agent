from __future__ import annotations

from sentinel.worker_observability import WorkerMetrics


def test_metrics_start_idle() -> None:
    snapshot = WorkerMetrics().snapshot()
    assert snapshot.jobs_completed == 0
    assert snapshot.jobs_failed == 0
    assert snapshot.runtime_errors == 0
    assert snapshot.jobs_in_progress == 0
    assert snapshot.last_activity_at_monotonic is None
    assert snapshot.uptime_seconds >= 0


def test_metrics_track_lifecycle() -> None:
    metrics = WorkerMetrics()
    metrics.job_started()
    assert metrics.snapshot().jobs_in_progress == 1
    metrics.job_completed()
    metrics.job_started()
    metrics.job_failed()
    metrics.runtime_error()
    snapshot = metrics.snapshot()
    assert snapshot.jobs_completed == 1
    assert snapshot.jobs_failed == 1
    assert snapshot.runtime_errors == 1
    assert snapshot.jobs_in_progress == 0
    assert snapshot.last_activity_at_monotonic is not None


def test_metrics_snapshot_serializes_stable_fields() -> None:
    payload = WorkerMetrics().snapshot().as_dict()
    assert set(payload) == {
        "uptime_seconds",
        "last_activity_at_monotonic",
        "jobs_completed",
        "jobs_failed",
        "runtime_errors",
        "jobs_in_progress",
    }
