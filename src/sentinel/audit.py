from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Mapping, Protocol

from sentinel.models import RemediationJob


_MAX_TEXT_CHARS = 128_000
_MAX_VERSION_CHARS = 256
_MAX_DELIVERY_FIELDS = 32


class AuditError(ValueError):
    """Raised when an audit record violates the audit boundary."""


@dataclass(frozen=True)
class RemediationAuditRecord:
    """Immutable audit snapshot for one remediation lifecycle."""

    audit_id: str
    recorded_at: str
    organization_id: str
    installation_id: str
    job_id: str
    change_event_id: str
    status: str
    model_version: str | None
    prompt_version: str | None
    patch_diff: str | None
    verification: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    delivery_outcome: Mapping[str, object] = field(default_factory=dict)


class AuditSink(Protocol):
    """Storage-neutral audit sink used by workflow workers."""

    def append(self, record: RemediationAuditRecord) -> None:
        """Persist one immutable audit record."""


def build_audit_record(
    job: RemediationJob,
    *,
    audit_id: str,
    delivery_outcome: Mapping[str, object] | None = None,
    recorded_at: str | None = None,
) -> RemediationAuditRecord:
    """Build a bounded, secret-free audit snapshot from a remediation job."""
    if not audit_id.strip():
        raise AuditError("audit_id is required")
    if not job.job_id.strip() or not job.organization_id.strip() or not job.installation_id.strip():
        raise AuditError("job identity fields are required")
    if not job.change_event_id.strip() or not job.status.strip():
        raise AuditError("change event and status are required")
    for name, value in (
        ("model_version", job.model_version),
        ("prompt_version", job.prompt_version),
        ("patch_diff", job.patch_diff),
    ):
        if value is not None and len(value) > (_MAX_VERSION_CHARS if name != "patch_diff" else _MAX_TEXT_CHARS):
            raise AuditError(f"{name} exceeds the audit size limit")
        if value is not None and "\x00" in value:
            raise AuditError(f"{name} must not contain null bytes")

    delivery = dict(delivery_outcome or {})
    if len(delivery) > _MAX_DELIVERY_FIELDS:
        raise AuditError("delivery outcome contains too many fields")
    if any("\x00" in str(key) or "\x00" in str(value) for key, value in delivery.items()):
        raise AuditError("delivery outcome must not contain null bytes")

    verification = tuple(
        result.model_dump(exclude_none=True) for result in job.verification
    )
    return RemediationAuditRecord(
        audit_id=audit_id,
        recorded_at=recorded_at or datetime.now(UTC).isoformat(),
        organization_id=job.organization_id,
        installation_id=job.installation_id,
        job_id=job.job_id,
        change_event_id=job.change_event_id,
        status=job.status,
        model_version=job.model_version,
        prompt_version=job.prompt_version,
        patch_diff=job.patch_diff,
        verification=verification,
        delivery_outcome=delivery,
    )


class InMemoryAuditSink:
    """Thread-safe audit sink for MVP and deterministic tests.

    Production storage adapters can implement the same AuditSink protocol
    without changing the remediation domain objects.
    """

    def __init__(self) -> None:
        self._records: list[RemediationAuditRecord] = []
        self._lock = Lock()

    def append(self, record: RemediationAuditRecord) -> None:
        with self._lock:
            if any(existing.audit_id == record.audit_id for existing in self._records):
                raise AuditError("audit_id must be unique")
            self._records.append(record)

    def list(self) -> tuple[RemediationAuditRecord, ...]:
        with self._lock:
            return tuple(self._records)
