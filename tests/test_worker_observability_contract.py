from sentinel.worker_health import WorkerHealth
from sentinel.worker_observability import WorkerMetrics


def test_health_snapshot_is_safe_before_and_after_shutdown() -> None:
    health = WorkerHealth()
    assert health.snapshot().accepting_work is False
    health.mark_ready()
    assert health.snapshot().accepting_work is True
    health.mark_stopping()
    assert health.snapshot().accepting_work is False


def test_metrics_snapshot_has_stable_operational_fields() -> None:
    metrics = WorkerMetrics()
    metrics.job_started()
    metrics.job_completed()
    payload = metrics.snapshot().as_dict()

    assert set(payload) == {
        "healthy",
        "uptime_seconds",
        "last_activity_at_monotonic",
        "jobs_completed",
        "jobs_failed",
        "runtime_errors",
        "jobs_in_progress",
    }
    assert payload["jobs_completed"] == 1
    assert payload["jobs_in_progress"] == 0
