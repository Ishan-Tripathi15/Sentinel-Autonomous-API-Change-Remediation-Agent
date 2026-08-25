import pytest

from sentinel.sandbox_execution import (
    SandboxExecutionError,
    SandboxManifest,
    UnavailableSandboxExecutor,
)
from sentinel.sandbox_policy import SandboxPolicyError


def manifest(**overrides: object) -> SandboxManifest:
    values = {
        "workspace": "workspace",
        "command": ("pytest", "-q"),
        "environment": {"CI": "1"},
    }
    values.update(overrides)
    return SandboxManifest(**values)


def test_manifest_accepts_tokenized_verification_command() -> None:
    manifest().validate()


def test_manifest_rejects_workspace_traversal() -> None:
    with pytest.raises(SandboxPolicyError, match="workspace"):
        manifest(workspace="workspace/../secret").validate()


def test_manifest_rejects_shell_execution() -> None:
    with pytest.raises(SandboxPolicyError, match="executable"):
        manifest(command=("bash", "-c", "pytest -q")).validate()


def test_manifest_rejects_network_tools() -> None:
    with pytest.raises(SandboxPolicyError, match="not permitted"):
        manifest(command=("curl", "https://example.com")).validate()


def test_manifest_rejects_dependency_installation() -> None:
    with pytest.raises(SandboxPolicyError, match="installation"):
        manifest(command=("npm", "install")).validate()


def test_manifest_requires_read_only_root() -> None:
    with pytest.raises(SandboxPolicyError, match="read-only"):
        manifest(read_only_root=False).validate()


def test_unavailable_executor_fails_closed() -> None:
    with pytest.raises(SandboxExecutionError, match="disabled"):
        UnavailableSandboxExecutor().execute(manifest())
