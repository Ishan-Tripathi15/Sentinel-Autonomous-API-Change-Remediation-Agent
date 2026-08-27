from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class WorkerHealthSnapshot:
    """Read-only health state for a worker process."""

    ready: bool
    accepting_work: bool
    last_activity_at_monotonic: float | None
    runtime_errors: int


class WorkerHealth:
    """Thread-safe lifecycle state used by readiness probes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ready = False
        self._accepting_work = False
        self._last_activity: float | None = None
        self._runtime_errors = 0

    def mark_ready(self) -> None:
        with self._lock:
            self._ready = True
            self._accepting_work = True

    def mark_stopping(self) -> None:
        with self._lock:
            self._accepting_work = False

    def mark_activity(self) -> None:
        with self._lock:
            self._last_activity = monotonic()

    def mark_runtime_error(self) -> None:
        with self._lock:
            self._runtime_errors += 1
            self._last_activity = monotonic()

    def snapshot(self) -> WorkerHealthSnapshot:
        with self._lock:
            return WorkerHealthSnapshot(
                ready=self._ready,
                accepting_work=self._accepting_work,
                last_activity_at_monotonic=self._last_activity,
                runtime_errors=self._runtime_errors,
            )
