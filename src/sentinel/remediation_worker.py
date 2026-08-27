from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread
from uuid import uuid4

from .audit import AuditSink, build_audit_event
from .job_queue import JobQueueError, PostgresJobQueue
from .models import RemediationJob
from .orchestrator import RemediationStatus, transition_job


class RemediationWorkerError(RuntimeError):
    """Raised when the remediation state machine cannot proceed safely."""


@dataclass(frozen=True)
class RemediationWorkerResult:
    job: RemediationJob
    completed: bool


StageHandler = Callable[[RemediationJob], RemediationJob]


class _LeaseHeartbeat:
    """Renew a worker lease while a long-running stage is executing."""

    def __init__(
        self,
        queue: PostgresJobQueue,
        *,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self._queue = queue
        self._job_id = job_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._stop = Event()
        self._error: Exception | None = None
        self._thread = Thread(
            target=self._run,
            name=f"sentinel-lease-{job_id}",
            daemon=True,
        )

    def __enter__(self) -> "_LeaseHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._stop.set()
        self._thread.join(timeout=min(5.0, max(1.0, self._lease_seconds / 4)))
        if exc_value is None and self._error is not None:
            raise RemediationWorkerError("worker lease renewal failed") from self._error

    def _run(self) -> None:
        interval = max(1.0, min(30.0, self._lease_seconds / 3))
        while not self._stop.wait(interval):
            try:
                self._queue.renew_lease(
                    job_id=self._job_id,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - stage boundary handles renewal failures
                self._error = exc
                self._stop.set()
                return


class RemediationWorker:
    """Coordinate one durable remediation job through explicit safe stages.

    Stage handlers are dependency-injected. This worker never executes
    customer code and never performs repository writes itself.
    """

    def __init__(
        self,
        queue: PostgresJobQueue,
        audit: AuditSink,
        *,
        worker_id: str,
        prepare: StageHandler,
        generate_patch: StageHandler,
        verify: StageHandler,
    ) -> None:
        if not worker_id.strip():
            raise RemediationWorkerError("worker_id is required")
        self._queue = queue
        self._audit = audit
        self._worker_id = worker_id
        self._prepare = prepare
        self._generate_patch = generate_patch
        self._verify = verify

    def run_once(self, *, lease_seconds: int = 300) -> RemediationWorkerResult | None:
        """Claim and execute one job; return None when the queue is empty."""
        try:
            job = self._queue.claim(worker_id=self._worker_id, lease_seconds=lease_seconds)
        except JobQueueError as exc:
            raise RemediationWorkerError(str(exc)) from exc
        if job is None:
            return None

        original = job
        current = job.model_copy(
            update={
                "status": (
                    RemediationStatus.QUEUED.value
                    if job.status == "running"
                    else job.status
                )
            }
        )
        try:
            self._emit(
                original,
                "job_claimed",
                from_status=original.status,
                to_status="running",
            )
            current = self._resume(current, lease_seconds=lease_seconds)
            if current.status == RemediationStatus.VERIFIED.value:
                current = transition_job(current, RemediationStatus.DRY_RUN_COMPLETE)
                self._queue.checkpoint(
                    job_id=current.job_id,
                    worker_id=self._worker_id,
                    payload=current,
                )
            self._emit(
                current,
                "job_completed",
                from_status="verified",
                to_status=current.status,
            )
            self._queue.complete(
                job_id=current.job_id,
                worker_id=self._worker_id,
                payload=current,
            )
            return RemediationWorkerResult(job=current, completed=True)
        except Exception as exc:  # noqa: BLE001 - worker boundary must requeue every stage failure safely
            failed = current.model_copy(update={"status": RemediationStatus.FAILED.value})
            retry_payload = failed.model_copy(update={"status": RemediationStatus.QUEUED.value})
            try:
                self._emit(
                    failed,
                    "job_failed",
                    from_status=current.status,
                    to_status=failed.status,
                    metadata={"error_type": type(exc).__name__},
                )
                self._queue.fail(
                    job_id=failed.job_id,
                    worker_id=self._worker_id,
                    payload=retry_payload,
                )
            except Exception as cleanup_exc:
                raise RemediationWorkerError(
                    "worker failed and could not persist failure state"
                ) from cleanup_exc
            return RemediationWorkerResult(job=failed, completed=False)

    def _resume(self, job: RemediationJob, *, lease_seconds: int) -> RemediationJob:
        """Continue from the last stage persisted in the durable payload."""
        current = job
        if current.status == RemediationStatus.QUEUED.value:
            current = self._run_stage(
                current,
                RemediationStatus.READY_FOR_REMEDIATION,
                self._prepare,
                lease_seconds=lease_seconds,
            )
        if current.status == RemediationStatus.READY_FOR_REMEDIATION.value:
            current = self._run_stage(
                current,
                RemediationStatus.PATCH_GENERATED,
                self._generate_patch,
                lease_seconds=lease_seconds,
            )
        if current.status == RemediationStatus.PATCH_GENERATED.value:
            current = self._run_stage(
                current,
                RemediationStatus.VERIFICATION_PENDING,
                lambda value: value,
                lease_seconds=lease_seconds,
            )
        if current.status == RemediationStatus.VERIFICATION_PENDING.value:
            current = self._run_stage(
                current,
                RemediationStatus.VERIFIED,
                self._verify,
                lease_seconds=lease_seconds,
            )
        if current.status not in {
            RemediationStatus.VERIFIED.value,
            RemediationStatus.DRY_RUN_COMPLETE.value,
        }:
            raise RemediationWorkerError(f"unsupported checkpoint status: {current.status}")
        return current

    def _run_stage(
        self,
        job: RemediationJob,
        target: RemediationStatus,
        handler: StageHandler,
        *,
        lease_seconds: int,
    ) -> RemediationJob:
        self._emit(job, "stage_started", from_status=job.status, to_status=target.value)
        staged = transition_job(job, target)
        with _LeaseHeartbeat(
            self._queue,
            job_id=job.job_id,
            worker_id=self._worker_id,
            lease_seconds=lease_seconds,
        ):
            updated = handler(staged)
        if updated.job_id != job.job_id:
            raise RemediationWorkerError("stage changed job identity")
        if (
            updated.organization_id != job.organization_id
            or updated.installation_id != job.installation_id
        ):
            raise RemediationWorkerError("stage changed job tenant identity")
        if updated.status != target.value:
            raise RemediationWorkerError("stage handler changed workflow status unexpectedly")
        self._queue.checkpoint(
            job_id=updated.job_id,
            worker_id=self._worker_id,
            payload=updated,
        )
        self._emit(updated, "stage_completed", from_status=job.status, to_status=updated.status)
        return updated

    def _emit(
        self,
        job: RemediationJob,
        event_type: str,
        *,
        from_status: str | None = None,
        to_status: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._audit.append_event(
            build_audit_event(
                job,
                audit_event_id=str(uuid4()),
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                metadata=metadata,
            )
        )
