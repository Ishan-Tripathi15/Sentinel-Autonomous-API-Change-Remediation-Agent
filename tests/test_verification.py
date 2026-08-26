from __future__ import annotations

from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

import pytest

from sentinel.verification import VerificationEngine, VerificationError


def test_allowlisted_command_captures_success_output() -> None:
    command = ("python", "-m", "pytest", "tests/test_diff.py")
    engine = VerificationEngine([command])

    completed = CompletedProcess(command, 0, stdout="7 passed\n", stderr="")
    with patch("sentinel.verification.subprocess.run", return_value=completed) as run:
        result = engine.verify(command)

    assert result.command == command
    assert result.passed is True
    assert result.returncode == 0
    assert result.stdout == "7 passed\n"
    assert result.stderr == ""
    run.assert_called_once_with(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120.0,
        shell=False,
    )


def test_nonzero_command_is_returned_as_failed_result() -> None:
    command = ("python", "-m", "pytest", "tests/test_diff.py")
    engine = VerificationEngine([command])
    completed = CompletedProcess(command, 1, stdout="", stderr="1 failed\n")

    with patch("sentinel.verification.subprocess.run", return_value=completed):
        result = engine.verify(command)

    assert result.passed is False
    assert result.returncode == 1
    assert result.stderr == "1 failed\n"


def test_unknown_command_fails_closed_without_execution() -> None:
    allowed = ("python", "-m", "pytest")
    engine = VerificationEngine([allowed])

    with (
        patch("sentinel.verification.subprocess.run") as run,
        pytest.raises(VerificationError, match="not allowlisted"),
    ):
        engine.verify(("python", "-c", "print('unsafe')"))

    run.assert_not_called()


def test_empty_command_is_rejected() -> None:
    engine = VerificationEngine([])

    with pytest.raises(VerificationError, match="must not be empty"):
        engine.verify(())


def test_empty_allowlist_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        VerificationEngine([()])


def test_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        VerificationEngine([], timeout_seconds=0)


def test_timeout_fails_closed() -> None:
    command = ("python", "-m", "pytest")
    engine = VerificationEngine([command], timeout_seconds=1)
    timeout = TimeoutExpired(command, 1)

    with (
        patch("sentinel.verification.subprocess.run", side_effect=timeout),
        pytest.raises(VerificationError, match="timed out"),
    ):
        engine.verify(command)


def test_process_start_failure_fails_closed() -> None:
    command = ("python", "-m", "pytest")
    engine = VerificationEngine([command])

    with (
        patch(
            "sentinel.verification.subprocess.run",
            side_effect=OSError("executable missing"),
        ),
        pytest.raises(VerificationError, match="could not start"),
    ):
        engine.verify(command)
