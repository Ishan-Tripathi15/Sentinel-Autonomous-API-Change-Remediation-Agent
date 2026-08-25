from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Sequence


class VerificationError(RuntimeError):
    """Raised when a verification command is not permitted or fails."""


@dataclass(frozen=True)
class VerificationResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


class VerificationEngine:
    """Run only explicitly allowlisted executable commands."""

    def __init__(
        self,
        allowed_commands: Sequence[tuple[str, ...]],
        *,
        timeout_seconds: int = 120,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._allowed = frozenset(tuple(command) for command in allowed_commands)
        self._timeout = timeout_seconds

    def verify(self, command: Sequence[str]) -> VerificationResult:
        normalized = tuple(command)
        if not normalized:
            raise VerificationError("verification command must not be empty")
        if normalized not in self._allowed:
            raise VerificationError("verification command is not allowlisted")

        try:
            completed = subprocess.run(
                normalized,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
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
