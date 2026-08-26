from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass


class VerificationError(RuntimeError):
    """Raised when a verification command is unsafe or cannot be completed."""


@dataclass(frozen=True)
class VerificationResult:
    """Structured result of one allowlisted verification command."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """Whether the verification command completed successfully."""
        return self.returncode == 0


class VerificationEngine:
    """Execute only exact allowlisted verification commands without a shell."""

    def __init__(
        self,
        allowed_commands: Sequence[Sequence[str]],
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        normalized = tuple(tuple(command) for command in allowed_commands)
        if any(not command for command in normalized):
            raise ValueError("allowed verification commands must not be empty")
        self._allowed_commands = frozenset(normalized)
        self._timeout_seconds = timeout_seconds

    def verify(self, command: Sequence[str]) -> VerificationResult:
        """Run one exact allowlisted command and return its captured result."""
        normalized = tuple(command)
        if not normalized:
            raise VerificationError("verification command must not be empty")
        if normalized not in self._allowed_commands:
            raise VerificationError("verification command is not allowlisted")

        try:
            completed = subprocess.run(
                normalized,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VerificationError("verification command timed out") from exc
        except OSError as exc:
            raise VerificationError("verification command could not start") from exc

        return VerificationResult(
            command=normalized,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
