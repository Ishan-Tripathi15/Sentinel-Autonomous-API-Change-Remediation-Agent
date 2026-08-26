from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from threading import Event
from time import monotonic
from typing import Protocol

from .remediation_worker import RemediationWorkerError


class WorkerRuntimeError(ValueError):
    """Raised when worker runtime configuration is unsafe."""


@dataclass(frozen=True)
class WorkerRuntimeConfig:
    """Bounded runtime controls for a long-lived remediation worker."""

    lease_seconds: int = 300
    poll_interval_seconds: float = 1.0
    error_backoff_seconds: float = 1.0
    max_error_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.lease_seconds <= 3600:
            raise WorkerRuntimeError("lease_seconds must be between 1 and 3600")
        for name, value in (
            ("poll_interval_seconds", self.poll_interval_seconds),
            ("error_backoff_seconds", self.error_backoff_seconds),
            ("max_error_backoff_seconds", self.max_error_backoff_seconds),
        ):
            if not isfinite(value) or value <= 0:
                raise WorkerRuntimeError(f"{name} must be a finite positive number")
        if self.error_backoff_seconds > self.max_error_backoff_seconds:
            raise WorkerRuntimeError("error_backoff_seconds cannot exceed max_error_backoff_seconds")


@dataclass(frozen=True)
class WorkerRuntimeStats:
    """Counters produced by one runtime session."""

    jobs_completed: int = 0
    jobs_failed: int = 0
    runtime_errors: int = 0
    started_at: float = 0.0
    stopped_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.stopped_at - self.started_at)


class WorkerLoop(Protocol):
    """Minimal worker contract required by the runtime supervisor."""

    def run_once(self, *, lease_seconds: int = 300) -> object: ...


class RemediationWorkerRuntime:
    """Run a remediation worker continuously with bounded backoff and shutdown.

    The runtime owns process lifecycle only. Job safety remains inside
    ``RemediationWorker`` and durable ownership remains inside the queue.
    """

    def __init__(
        self,
        worker: WorkerLoop,
        *,
        config: WorkerRuntimeConfig | None = None,
        stop_event: Event | None = None,
    ) -> None:
        self._worker = worker
        self._config = config or WorkerRuntimeConfig()
        self._stop_event = stop_event or Event()

    def request_stop(self) -> None:
        """Request graceful shutdown; an active poll wait is interrupted."""
        self._stop_event.set()

    def run(self) -> WorkerRuntimeStats:
        """Process jobs until shutdown is requested, returning session counters."""
        started_at = monotonic()
        completed = 0
        failed = 0
        runtime_errors = 0
        backoff = self._config.error_backoff_seconds

        while not self._stop_event.is_set():
            try:
                result = self._worker.run_once(lease_seconds=self._config.lease_seconds)
            except RemediationWorkerError:
                runtime_errors += 1
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, self._config.max_error_backoff_seconds)
                continue

            backoff = self._config.error_backoff_seconds
            if result is None:
                self._stop_event.wait(timeout=self._config.poll_interval_seconds)
                continue

            if result.completed:
                completed += 1
            else:
                failed += 1

        return WorkerRuntimeStats(
            jobs_completed=completed,
            jobs_failed=failed,
            runtime_errors=runtime_errors,
            started_at=started_at,
            stopped_at=monotonic(),
        )
