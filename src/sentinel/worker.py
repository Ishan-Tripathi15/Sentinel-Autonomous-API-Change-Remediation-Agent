from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sentinel.sandbox_execution import SandboxExecutionResult, SandboxManifest


class WorkerStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class VerificationRequest:
    """Immutable request handed to an isolated verification worker."""

    job_id: str
    manifest: SandboxManifest


@dataclass(frozen=True)
class VerificationArtifact:
    """Bounded metadata returned by an isolated worker."""

    status: WorkerStatus
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int | None
    error: str | None = None


class IsolatedWorker(Protocol):
    """Boundary implemented by a real Firecracker/gVisor worker service."""

    def verify(self, request: VerificationRequest) -> VerificationArtifact: ...


class FailClosedWorker:
    """Worker boundary that refuses execution until isolation is configured."""

    def verify(self, request: VerificationRequest) -> VerificationArtifact:
        request.manifest.validate()
        return VerificationArtifact(
            status=WorkerStatus.REJECTED,
            exit_code=None,
            stdout="",
            stderr="",
            duration_ms=None,
            error="No isolated worker runtime is configured; execution is disabled.",
        )


def bounded_artifact(
    result: SandboxExecutionResult,
    *,
    max_output_bytes: int,
) -> VerificationArtifact:
    """Normalize worker output without allowing unbounded process output."""

    if max_output_bytes < 1:
        raise ValueError("max_output_bytes must be positive")

    stdout = result.stdout.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="replace")
    stderr = result.stderr.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="replace")
    return VerificationArtifact(
        status=WorkerStatus.COMPLETED if result.exit_code == 0 else WorkerStatus.FAILED,
        exit_code=result.exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=result.duration_ms,
    )
