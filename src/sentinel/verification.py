from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .sandbox import IsolatedSandboxRequired, Sandbox


class VerificationError(RuntimeError):
    """Raised when a verification command is unsafe or cannot be completed."""


@dataclass(frozen=True)
class VerificationResult:
    """Structured result of one allowlisted verification command."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def passed(self) -> bool:
        """Whether the verification command completed successfully."""
        return self.returncode == 0


class VerificationEngine:
    """Validate verification commands and execute them only through a sandbox."""

    def __init__(
        self,
        allowed_commands: Sequence[Sequence[str]],
        sandbox: Sandbox,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        normalized = tuple(tuple(command) for command in allowed_commands)
        if any(not command for command in normalized):
            raise ValueError("allowed verification commands must not be empty")
        self._allowed_commands = frozenset(normalized)
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds

    def verify(self, command: Sequence[str]) -> VerificationResult:
        """Run one exact allowlisted command inside the configured sandbox."""
        normalized = tuple(command)
        if not normalized:
            raise VerificationError("verification command must not be empty")
        if normalized not in self._allowed_commands:
            raise VerificationError("verification command is not allowlisted")

        try:
            result = self._sandbox.run(
                list(normalized),
                timeout_seconds=self._timeout_seconds,
            )
        except IsolatedSandboxRequired as exc:
            raise VerificationError("verification sandbox is not configured") from exc
        except (OSError, TimeoutError) as exc:
            raise VerificationError("verification command could not be completed") from exc

        return VerificationResult(
            command=normalized,
            returncode=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
        )
