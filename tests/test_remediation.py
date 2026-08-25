from sentinel.models import BlastRadiusReport, ChangeEvent, ChangeSeverity, ChangeType
from sentinel.remediation import (
    DeterministicRemediationAgent,
    RemediationPolicyError,
    RemediationRequest,
    validate_remediation_request,
)
from sentinel.sandbox_policy import (
    SandboxLimits,
    SandboxPolicyError,
    SandboxRequest,
    validate_sandbox_request,
)


def event() -> ChangeEvent:
    return ChangeEvent(
        event_id="evt-1",
        vendor="stripe",
        change_type=ChangeType.BREAKING,
        severity=ChangeSeverity.HIGH,
        summary="payment endpoint changed",
        confidence=1.0,
        detected_at="2026-01-01T00:00:00Z",
    )


def radius() -> BlastRadiusReport:
    return BlastRadiusReport(
        change_event_id="evt-1",
        repository="acme/payments",
        call_sites=[],
        affected_files=["src/payments.ts"],
        confidence=0.9,
    )


def request(**overrides: object) -> RemediationRequest:
    values: dict[str, object] = {
        "change_event_id": "evt-1",
        "repository": "acme/payments",
        "base_revision": "abc123",
        "files": ("src/payments.ts",),
    }
    values.update(overrides)
    return RemediationRequest(**values)


def test_deterministic_agent_is_dry_run_and_does_not_patch() -> None:
    patch = DeterministicRemediationAgent().propose(
        change_event=event(), blast_radius=radius(), request=request()
    )
    assert patch.files == ()
    assert patch.unified_diff == ""
    assert patch.patch_id


def test_non_dry_run_is_rejected() -> None:
    try:
        validate_remediation_request(event(), radius(), request(dry_run=False))
    except RemediationPolicyError as exc:
        assert "repository writes" in str(exc)
    else:
        raise AssertionError("expected policy rejection")


def test_path_traversal_is_rejected() -> None:
    try:
        validate_remediation_request(event(), radius(), request(files=("../secret",)))
    except RemediationPolicyError as exc:
        assert "unsafe repository path" in str(exc)
    else:
        raise AssertionError("expected policy rejection")


def test_sandbox_defaults_disable_network() -> None:
    validate_sandbox_request(
        SandboxRequest(workspace="workspace", command=("pytest", "-q"))
    )


def test_sandbox_rejects_network() -> None:
    request = SandboxRequest(
        workspace="workspace",
        command=("pytest",),
        limits=SandboxLimits(network_enabled=True),
    )
    try:
        validate_sandbox_request(request)
    except SandboxPolicyError as exc:
        assert "network access" in str(exc)
    else:
        raise AssertionError("expected policy rejection")
