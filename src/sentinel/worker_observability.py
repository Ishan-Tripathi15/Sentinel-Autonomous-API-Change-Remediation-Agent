from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class WorkerMetricsSnapshot:
    """Point-in-time operational metrics for one worker process."""

    started_at_monotonic: float
    last_activity_at_monotonic: float | None
    jobs_completed: int
    jobs_failed: int
    runtime_errors: int
    jobs_in_progress: int

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, monotonic() - self.started_at_monotonic)

    @property
    def healthy(self) -> bool:
        return self.jobs_in_progress >= 0

    def as_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "uptime_seconds": self.uptime_seconds,
            "last_activity_at_monotonic": self.last_activity_at_monotonic,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "runtime_errors": self.runtime_errors,
            "jobs_in_progress": self.jobs_in_progress,
        }


class WorkerMetrics:
    """Thread-safe counters owned by the worker runtime boundary."""

    def __init__(self) -> None:
        now = monotonic()
        self._started_at = now
        self._last_activity: float | None = None
        self._completed = 0
        self._failed = 0
        self._runtime_errors = 0
        self._in_progress = 0
        self._lock = Lock()

    def job_started(self) -> None:
        with self._lock:
            self._in_progress += 1
            self._last_activity = monotonic()

    def job_completed(self) -> None:
        with self._lock:
            self._in_progress = max(0, self._in_progress - 1)
            self._completed += 1
            self._last_activity = monotonic()

    def job_failed(self) -> None:
        with self._lock:
            self._in_progress = max(0, self._in_progress - 1)
            self._failed += 1
            self._last_activity = monotonic()

    def runtime_error(self) -> None:
        with self._lock:
            self._runtime_errors += 1
            self._last_activity = monotonic()

    def snapshot(self) -> WorkerMetricsSnapshot:
        with self._lock:
            return WorkerMetricsSnapshot(
                started_at_monotonic=self._started_at,
                last_activity_at_monotonic=self._last_activity,
                jobs_completed=self._completed,
                jobs_failed=self._failed,
                runtime_errors=self._runtime_errors,
                jobs_in_progress=self._in_progress,
            )
