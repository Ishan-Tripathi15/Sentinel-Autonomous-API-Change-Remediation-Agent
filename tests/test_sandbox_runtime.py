import pytest

from sentinel.sandbox_execution import SandboxManifest
from sentinel.sandbox_runtime import (
    FailClosedRuntime,
    RuntimeConfig,
    SandboxRuntimeUnavailable,
)


def manifest() -> SandboxManifest:
    return SandboxManifest(workspace="workspace", command=("pytest", "-q"), environment={})


def test_default_runtime_refuses_execution() -> None:
    with pytest.raises(SandboxRuntimeUnavailable):
        FailClosedRuntime().execute(manifest())


def test_runtime_provider_is_explicit() -> None:
    with pytest.raises(ValueError):
        RuntimeConfig(provider="host-subprocess").validate()


def test_supported_runtime_names_are_accepted() -> None:
    for provider in ("none", "firecracker", "gvisor"):
        RuntimeConfig(provider=provider).validate()
