from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Protocol

from .models import BlastRadiusReport, ChangeEvent


class RemediationPolicyError(ValueError):
    """Raised when a remediation request violates Sentinel's safety policy."""


@dataclass(frozen=True)
class RemediationRequest:
    change_event_id: str
    repository: str
    base_revision: str
    files: tuple[str, ...]
    dry_run: bool = True


@dataclass(frozen=True)
class Patch:
    patch_id: str
    files: tuple[str, ...]
    unified_diff: str
    rationale: str


class RemediationAgent(Protocol):
    def propose(
        self,
        *,
        change_event: ChangeEvent,
        blast_radius: BlastRadiusReport,
        request: RemediationRequest,
    ) -> Patch: ...


class DeterministicRemediationAgent:
    """Safe MVP adapter that produces no code changes.

    The production LLM agent will implement the same interface. Keeping this
    adapter deterministic lets orchestration and policy be tested without
    granting an AI agent repository or process access.
    """

    def propose(
        self,
        *,
        change_event: ChangeEvent,
        blast_radius: BlastRadiusReport,
        request: RemediationRequest,
    ) -> Patch:
        validate_remediation_request(change_event, blast_radius, request)
        rationale = (
            "No patch generated: remediation agent is not enabled in the MVP. "
            "The request was validated and remains dry-run only."
        )
        patch_id = sha256(
            f"{request.repository}:{request.base_revision}:{change_event.event_id}".encode()
        ).hexdigest()[:16]
        return Patch(patch_id=patch_id, files=(), unified_diff="", rationale=rationale)


def validate_remediation_request(
    change_event: ChangeEvent,
    blast_radius: BlastRadiusReport,
    request: RemediationRequest,
) -> None:
    if not request.dry_run:
        raise RemediationPolicyError("repository writes are disabled until production approval")
    if request.change_event_id != change_event.event_id:
        raise RemediationPolicyError("request does not belong to the change event")
    if blast_radius.change_event_id != change_event.event_id:
        raise RemediationPolicyError("blast radius does not belong to the change event")
    if not request.repository.strip() or not request.base_revision.strip():
        raise RemediationPolicyError("repository and base_revision are required")
    if not request.files:
        raise RemediationPolicyError("at least one affected file is required")
    for path in request.files:
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise RemediationPolicyError(f"unsafe repository path: {path}")
        if not path.strip() or path.startswith("\\"):
            raise RemediationPolicyError(f"unsafe repository path: {path}")
