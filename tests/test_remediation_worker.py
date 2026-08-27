from __future__ import annotations

from sentinel.audit import InMemoryAuditSink
from sentinel.models import RemediationJob
from sentinel.remediation_worker import RemediationWorker


class FakeQueue:
    def __init__(self, job: RemediationJob) -> None:
        self.job = job
        self.claimed = False
        self.completed = None
        self.failed = None
        self.checkpoints: list[RemediationJob] = []

    def claim(self, *, worker_id: str, lease_seconds: int) -> RemediationJob | None:
        if self.claimed:
            return None
        self.claimed = True
        return self.job

    def checkpoint(self, *, job_id: str, worker_id: str, payload: RemediationJob) -> None:
        self.checkpoints.append(payload)
        self.job = payload

    def complete(self, *, job_id: str, worker_id: str, payload: RemediationJob) -> None:
        self.completed = payload

    def fail(
        self,
        *,
        job_id: str,
        worker_id: str,
        payload: RemediationJob,
        retry_after_seconds: int = 30,
    ) -> None:
        self.failed = payload


def make_job(status: str = "queued") -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status=status,
        dry_run=True,
    )


def identity(job: RemediationJob) -> RemediationJob:
    return job


def test_worker_runs_all_dry_run_stages_and_completes() -> None:
    queue = FakeQueue(make_job())
    audit = InMemoryAuditSink()
    worker = RemediationWorker(
        queue,
        audit,
        worker_id="worker-1",
        prepare=identity,
        generate_patch=identity,
        verify=identity,
    )

    result = worker.run_once()

    assert result is not None
    assert result.completed is True
    assert result.job.status == "dry-run-complete"
    assert queue.completed is not None
    assert [checkpoint.status for checkpoint in queue.checkpoints] == [
        "ready-for-remediation",
        "patch-generated",
        "verification-pending",
        "verified",
        "dry-run-complete",
    ]
    assert [event.event_type for event in audit.list_events()] == [
        "job_claimed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "job_completed",
    ]


def test_worker_requeues_after_stage_failure() -> None:
    queue = FakeQueue(make_job())
    audit = InMemoryAuditSink()

    def fail(_: RemediationJob) -> RemediationJob:
        raise RuntimeError("verification failed")

    worker = RemediationWorker(
        queue,
        audit,
        worker_id="worker-1",
        prepare=identity,
        generate_patch=fail,
        verify=identity,
    )

    result = worker.run_once()

    assert result is not None
    assert result.completed is False
    assert result.job.status == "failed"
    assert queue.failed is not None
    assert queue.failed.status == "queued"
    assert audit.list_events()[-1].event_type == "job_failed"


def test_worker_resumes_from_durable_checkpoint() -> None:
    queue = FakeQueue(make_job("ready-for-remediation"))
    audit = InMemoryAuditSink()
    calls = {"prepare": 0, "generate": 0, "verify": 0}

    def prepare(job: RemediationJob) -> RemediationJob:
        calls["prepare"] += 1
        return job

    def generate(job: RemediationJob) -> RemediationJob:
        calls["generate"] += 1
        return job

    def verify(job: RemediationJob) -> RemediationJob:
        calls["verify"] += 1
        return job

    worker = RemediationWorker(
        queue,
        audit,
        worker_id="worker-1",
        prepare=prepare,
        generate_patch=generate,
        verify=verify,
    )

    result = worker.run_once()

    assert result is not None
    assert result.completed is True
    assert result.job.status == "dry-run-complete"
    assert calls == {"prepare": 0, "generate": 1, "verify": 1}
    assert [checkpoint.status for checkpoint in queue.checkpoints] == [
        "patch-generated",
        "verification-pending",
        "verified",
        "dry-run-complete",
    ]


def test_worker_rejects_stage_identity_changes() -> None:
    queue = FakeQueue(make_job())
    audit = InMemoryAuditSink()

    def change_tenant(job: RemediationJob) -> RemediationJob:
        return job.model_copy(update={"organization_id": "other-org"})

    worker = RemediationWorker(
        queue,
        audit,
        worker_id="worker-1",
        prepare=change_tenant,
        generate_patch=identity,
        verify=identity,
    )

    result = worker.run_once()

    assert result is not None
    assert result.completed is False
    assert result.job.status == "failed"
    assert queue.failed is not None
    assert queue.failed.organization_id == "org-1"
