from __future__ import annotations

from threading import Event

from sentinel.models import RemediationJob
from sentinel.remediation_worker import RemediationWorkerResult
from sentinel.remediation_worker_runtime import RemediationWorkerRuntime


def _result() -> RemediationWorkerResult:
    job = RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="dry-run-complete",
        dry_run=True,
    )
    return RemediationWorkerResult(job=job, completed=True)


def test_runtime_marks_ready_then_stops_accepting_work() -> None:
    stop_event = Event()
    results = iter([_result(), None])

    class Worker:
        def run_once(self, *, lease_seconds: int = 300):
            result = next(results)
            if result is None:
                stop_event.set()
            return result

    runtime = RemediationWorkerRuntime(Worker(), stop_event=stop_event)
    runtime.run()

    snapshot = runtime.health.snapshot()
    assert snapshot.ready is True
    assert snapshot.accepting_work is False
