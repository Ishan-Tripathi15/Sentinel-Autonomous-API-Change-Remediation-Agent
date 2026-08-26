from __future__ import annotations

from unittest.mock import Mock

import pytest

from sentinel.sandbox import CommandResult, IsolatedSandboxRequired
from sentinel.verification import VerificationEngine, VerificationError


def make_sandbox(
    *,
    exit_code: int = 0,
    stdout: str = "7 passed\n",
    stderr: str = "",
    duration_ms: int = 42,
) -> Mock:
    sandbox = Mock()
    sandbox.run.return_value = CommandResult(
        command="python -m pytest tests/test_diff.py",
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
    )
    return sandbox


def test_allowlisted_command_runs_through_sandbox() -> None:
    command = ("python", "-m", "pytest", "tests/test_diff.py")
    sandbox = make_sandbox()
    engine = VerificationEngine([command], sandbox)

    result = engine.verify(command)

    assert result.command == command
    assert result.passed is True
    assert result.returncode == 0
    assert result.stdout == "7 passed\n"
    assert result.stderr == ""
    assert result.duration_ms == 42
    sandbox.run.assert_called_once_with(
        list(command),
        timeout_seconds=120,
    )


def test_nonzero_command_is_returned_as_failed_result() -> None:
    command = ("python", "-m", "pytest", "tests/test_diff.py")
    sandbox = make_sandbox(exit_code=1, stdout="", stderr="1 failed\n")
    engine = VerificationEngine([command], sandbox)

    result = engine.verify(command)

    assert result.passed is False
    assert result.returncode == 1
    assert result.stderr == "1 failed\n"


def test_unknown_command_fails_closed_without_sandbox_execution() -> None:
    allowed = ("python", "-m", "pytest")
    sandbox = Mock()
    engine = VerificationEngine([allowed], sandbox)

    with pytest.raises(VerificationError, match="not allowlisted"):
        engine.verify(("python", "-c", "print('unsafe')"))

    sandbox.run.assert_not_called()


def test_empty_command_is_rejected() -> None:
    sandbox = Mock()
    engine = VerificationEngine([], sandbox)

    with pytest.raises(VerificationError, match="must not be empty"):
        engine.verify(())


def test_empty_allowlist_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        VerificationEngine([()], Mock())


def test_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        VerificationEngine([], Mock(), timeout_seconds=0)


def test_unconfigured_production_sandbox_fails_closed() -> None:
    command = ("python", "-m", "pytest")
    sandbox = Mock()
    sandbox.run.side_effect = IsolatedSandboxRequired("sandbox missing")
    engine = VerificationEngine([command], sandbox)

    with pytest.raises(VerificationError, match="sandbox is not configured"):
        engine.verify(command)


def test_sandbox_timeout_fails_closed() -> None:
    command = ("python", "-m", "pytest")
    sandbox = Mock()
    sandbox.run.side_effect = TimeoutError("timed out")
    engine = VerificationEngine([command], sandbox)

    with pytest.raises(VerificationError, match="could not be completed"):
        engine.verify(command)


def test_sandbox_start_failure_fails_closed() -> None:
    command = ("python", "-m", "pytest")
    sandbox = Mock()
    sandbox.run.side_effect = OSError("executable missing")
    engine = VerificationEngine([command], sandbox)

    with pytest.raises(VerificationError, match="could not be completed"):
        engine.verify(command)
