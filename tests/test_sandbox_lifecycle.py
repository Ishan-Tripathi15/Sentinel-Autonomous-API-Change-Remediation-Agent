import pytest

from sentinel.sandbox_lifecycle import SandboxLifecycle, SandboxLifecycleError, SandboxState


def test_valid_lifecycle_reaches_completion() -> None:
    lifecycle = SandboxLifecycle(execution_id="exec-1")
    for state in (
        SandboxState.PREPARING,
        SandboxState.READY,
        SandboxState.RUNNING,
        SandboxState.COMPLETED,
        SandboxState.TERMINATED,
    ):
        lifecycle.transition(state)

    assert lifecycle.terminal


def test_invalid_transition_is_rejected() -> None:
    lifecycle = SandboxLifecycle(execution_id="exec-2")

    with pytest.raises(SandboxLifecycleError):
        lifecycle.transition(SandboxState.RUNNING)


def test_terminal_state_cannot_restart() -> None:
    lifecycle = SandboxLifecycle(execution_id="exec-3")
    lifecycle.transition(SandboxState.TERMINATED)

    with pytest.raises(SandboxLifecycleError):
        lifecycle.transition(SandboxState.PREPARING)
