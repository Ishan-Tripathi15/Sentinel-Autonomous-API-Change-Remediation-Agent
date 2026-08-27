from threading import Event

from sentinel.remediation_worker_runtime import RemediationWorkerRuntime
from sentinel.remediation_worker import RemediationWorkerResult
from sentinel.models import RemediationJob


def test_runtime_exposes_health_and_metrics() -> None:
    stop = Event()
    job = RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="dry-run-complete",
        dry_run=True,
    )
    results = iter([RemediationWorkerResult(job=job, completed=True), None])

    class Worker:
        def run_once(self, *, lease_seconds: int = 300):
            result = next(results)
            if result is None:
                stop.set()
            return result

    runtime = RemediationWorkerRuntime(Worker(), stop_event=stop)
    runtime.run()

    assert runtime.metrics.snapshot().jobs_completed == 1
    health = runtime.health.snapshot()
    assert health.ready is True
    assert health.accepting_work is False
