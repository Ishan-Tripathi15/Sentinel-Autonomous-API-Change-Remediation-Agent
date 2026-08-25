from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class Sandbox(Protocol):
    def run(self, command: list[str], timeout_seconds: int = 600) -> CommandResult: ...


class IsolatedSandboxRequired(RuntimeError):
    """Raised when customer code would otherwise execute outside an isolation boundary."""


class ProductionSandbox:
    """Production placeholder enforcing the security contract.

    A Firecracker/gVisor implementation must be injected before customer code can run.
    """

    def run(self, command: list[str], timeout_seconds: int = 600) -> CommandResult:
        raise IsolatedSandboxRequired(
            "No production sandbox configured. Customer code execution is disabled. "
            "Configure the Firecracker/gVisor adapter before enabling remediation verification."
        )
