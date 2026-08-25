from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.sandbox_execution import SandboxExecutionResult, SandboxManifest


class SandboxRuntimeUnavailable(RuntimeError):
    """Raised when no trusted isolated runtime is configured."""


class SandboxRuntime(Protocol):
    def execute(self, manifest: SandboxManifest) -> SandboxExecutionResult:
        """Execute a manifest inside a trusted isolated runtime."""


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str = "none"

    def validate(self) -> None:
        if self.provider not in {"none", "firecracker", "gvisor"}:
            raise ValueError("unsupported sandbox runtime provider")


class FailClosedRuntime:
    """Production-safe default: never execute without an isolated runtime."""

    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig()
        self.config.validate()

    def execute(self, manifest: SandboxManifest) -> SandboxExecutionResult:
        raise SandboxRuntimeUnavailable(
            "no trusted isolated sandbox runtime is configured; execution refused"
        )
