from __future__ import annotations

from dataclasses import dataclass, field


class SandboxPolicyError(ValueError):
    """Raised when a verification request exceeds the configured limits."""


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int = 600
    memory_mb: int = 2048
    cpu_count: int = 2
    max_output_bytes: int = 1_000_000
    network_enabled: bool = False

    def validate(self) -> None:
        if not 1 <= self.timeout_seconds <= 3600:
            raise SandboxPolicyError("timeout_seconds must be between 1 and 3600")
        if not 128 <= self.memory_mb <= 16_384:
            raise SandboxPolicyError("memory_mb must be between 128 and 16384")
        if not 1 <= self.cpu_count <= 16:
            raise SandboxPolicyError("cpu_count must be between 1 and 16")
        if not 1024 <= self.max_output_bytes <= 10_000_000:
            raise SandboxPolicyError("max_output_bytes must be between 1024 and 10000000")
        if self.network_enabled:
            raise SandboxPolicyError("network access is disabled for remediation verification")


@dataclass(frozen=True)
class SandboxRequest:
    workspace: str
    command: tuple[str, ...]
    limits: SandboxLimits = field(default_factory=SandboxLimits)


def validate_sandbox_request(request: SandboxRequest) -> None:
    request.limits.validate()
    if not request.workspace.strip():
        raise SandboxPolicyError("workspace is required")
    if not request.command:
        raise SandboxPolicyError("command is required")
    if any(not token.strip() for token in request.command):
        raise SandboxPolicyError("command tokens must not be empty")
    if any(token in {"sudo", "su", "doas"} for token in request.command):
        raise SandboxPolicyError("privilege escalation commands are forbidden")
