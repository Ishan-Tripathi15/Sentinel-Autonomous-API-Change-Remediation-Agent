from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

from sentinel.sandbox_policy import SandboxLimits, SandboxPolicyError


class SandboxExecutionError(RuntimeError):
    """Raised when an execution request cannot be safely delegated to a sandbox."""


@dataclass(frozen=True)
class SandboxManifest:
    """Immutable, auditable description of one sandbox execution attempt."""

    workspace: str
    command: tuple[str, ...]
    environment: Mapping[str, str]
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    network_enabled: bool = False
    read_only_root: bool = True

    def validate(self) -> None:
        self.limits.validate()
        if self.network_enabled or self.limits.network_enabled:
            raise SandboxPolicyError("sandbox execution requires network access to be disabled")
        if not self.read_only_root:
            raise SandboxPolicyError("sandbox root filesystem must be read-only")

        path = PurePosixPath(self.workspace)
        if path.is_absolute() or ".." in path.parts or "\x00" in self.workspace:
            raise SandboxPolicyError("workspace must be a relative, traversal-free path")
        if not self.workspace.strip() or self.workspace == ".":
            raise SandboxPolicyError("workspace must identify a dedicated sandbox directory")
        if not self.command or any(not token.strip() for token in self.command):
            raise SandboxPolicyError("command must contain non-empty tokens")
        _validate_command(self.command)
        for key, value in self.environment.items():
            if not key or "\x00" in key or "\x00" in value:
                raise SandboxPolicyError("environment contains an invalid value")


@dataclass(frozen=True)
class SandboxExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class SandboxExecutor(Protocol):
    def execute(self, manifest: SandboxManifest) -> SandboxExecutionResult: ...


class UnavailableSandboxExecutor:
    """Fail-closed executor used until a real isolated runtime is configured."""

    def execute(self, manifest: SandboxManifest) -> SandboxExecutionResult:
        manifest.validate()
        raise SandboxExecutionError(
            "No isolated sandbox runtime is configured. Customer code execution is disabled."
        )


_SHELLS = frozenset({"sh", "bash", "dash", "zsh", "fish", "csh", "ksh", "cmd", "powershell"})
_BLOCKED_EXECUTABLES = frozenset(
    {"curl", "wget", "nc", "netcat", "ssh", "scp", "sftp", "sudo", "su", "doas", "git"}
)
_BLOCKED_PACKAGE_OPERATIONS = frozenset({"install", "add", "upgrade", "uninstall", "remove"})
_ALLOWED_EXECUTABLES = frozenset(
    {"python", "python3", "pytest", "node", "npm", "pnpm", "yarn", "npx", "uv", "ruff"}
)


def _validate_command(command: tuple[str, ...]) -> None:
    executable = PurePosixPath(command[0]).name.lower()
    if executable in _SHELLS or executable in _BLOCKED_EXECUTABLES:
        raise SandboxPolicyError(f"executable '{executable}' is not permitted")
    if executable not in _ALLOWED_EXECUTABLES:
        raise SandboxPolicyError(f"executable '{executable}' is not on the verification allowlist")
    if any(token in {"-c", "--command", "/c", "-Command"} for token in command[1:]):
        raise SandboxPolicyError("shell command evaluation is forbidden")
    if executable in {"npm", "pnpm", "yarn", "uv"} and any(
        token.lower() in _BLOCKED_PACKAGE_OPERATIONS for token in command[1:]
    ):
        raise SandboxPolicyError("dependency installation or mutation is forbidden during verification")
