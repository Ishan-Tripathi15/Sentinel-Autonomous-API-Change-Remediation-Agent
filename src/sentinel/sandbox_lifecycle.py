from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SandboxLifecycleError(RuntimeError):
    """Raised when a sandbox lifecycle transition is invalid."""


class SandboxState(StrEnum):
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


_ALLOWED: dict[SandboxState, frozenset[SandboxState]] = {
    SandboxState.CREATED: frozenset({SandboxState.PREPARING, SandboxState.TERMINATED}),
    SandboxState.PREPARING: frozenset({SandboxState.READY, SandboxState.FAILED, SandboxState.TERMINATED}),
    SandboxState.READY: frozenset({SandboxState.RUNNING, SandboxState.TERMINATED}),
    SandboxState.RUNNING: frozenset({SandboxState.COMPLETED, SandboxState.FAILED, SandboxState.TERMINATED}),
    SandboxState.COMPLETED: frozenset({SandboxState.TERMINATED}),
    SandboxState.FAILED: frozenset({SandboxState.TERMINATED}),
    SandboxState.TERMINATED: frozenset(),
}


@dataclass
class SandboxLifecycle:
    execution_id: str
    state: SandboxState = SandboxState.CREATED

    def transition(self, target: SandboxState) -> None:
        if target not in _ALLOWED[self.state]:
            raise SandboxLifecycleError(
                f"invalid sandbox transition: {self.state} -> {target}"
            )
        self.state = target

    @property
    def terminal(self) -> bool:
        return self.state in {
            SandboxState.COMPLETED,
            SandboxState.FAILED,
            SandboxState.TERMINATED,
        }
