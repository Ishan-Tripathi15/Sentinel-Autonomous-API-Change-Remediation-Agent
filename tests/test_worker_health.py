from __future__ import annotations

from sentinel.worker_health import WorkerHealth


def test_worker_starts_not_ready() -> None:
    snapshot = WorkerHealth().snapshot()

    assert snapshot.ready is False
    assert snapshot.accepting_work is False
    assert snapshot.runtime_errors == 0
    assert snapshot.last_activity_at_monotonic is None


def test_worker_readiness_and_shutdown() -> None:
    health = WorkerHealth()
    health.mark_ready()

    ready = health.snapshot()
    assert ready.ready is True
    assert ready.accepting_work is True

    health.mark_stopping()
    stopping = health.snapshot()
    assert stopping.ready is True
    assert stopping.accepting_work is False


def test_worker_health_records_activity_and_errors() -> None:
    health = WorkerHealth()
    health.mark_activity()
    health.mark_runtime_error()

    snapshot = health.snapshot()
    assert snapshot.last_activity_at_monotonic is not None
    assert snapshot.runtime_errors == 1
