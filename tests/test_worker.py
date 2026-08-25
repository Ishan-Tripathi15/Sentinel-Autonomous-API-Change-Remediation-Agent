from sentinel.sandbox_execution import SandboxExecutionResult, SandboxManifest
from sentinel.worker import FailClosedWorker, WorkerStatus, bounded_artifact


def manifest() -> SandboxManifest:
    return SandboxManifest(workspace="workspace", command=("pytest", "-q"), environment={})


def test_fail_closed_worker_never_executes_customer_code() -> None:
    result = FailClosedWorker().verify(
        __import__("sentinel.worker", fromlist=["VerificationRequest"]).VerificationRequest(
            job_id="job-1", manifest=manifest()
        )
    )

    assert result.status == WorkerStatus.REJECTED
    assert result.exit_code is None
    assert result.error is not None


def test_bounded_artifact_limits_output() -> None:
    artifact = bounded_artifact(
        SandboxExecutionResult(
            exit_code=0,
            stdout="abcdefghij",
            stderr="123456789",
            duration_ms=25,
        ),
        max_output_bytes=4,
    )

    assert artifact.status == WorkerStatus.COMPLETED
    assert artifact.stdout == "abcd"
    assert artifact.stderr == "1234"
