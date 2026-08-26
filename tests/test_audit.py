from __future__ import annotations

import pytest

from sentinel.audit import AuditError, InMemoryAuditSink, build_audit_record
from sentinel.models import RemediationJob, VerificationResult


def job() -> RemediationJob:
    return RemediationJob(
        job_id="job-1",
        organization_id="org-1",
        installation_id="install-1",
        change_event_id="event-1",
        status="verified",
        dry_run=True,
        patch_diff="@@ -1 +1 @@\n-old\n+new\n",
        model_version="model-v1",
        prompt_version="prompt-v1",
        verification=[
            VerificationResult(
                passed=True,
                command="pytest",
                exit_code=0,
                duration_ms=250,
            )
        ],
    )


def test_build_audit_record_captures_required_lifecycle_data() -> None:
    record = build_audit_record(
        job(),
        audit_id="audit-1",
        recorded_at="2026-08-26T00:00:00+00:00",
        delivery_outcome={"provider": "github", "status": "created", "number": 42},
    )

    assert record.audit_id == "audit-1"
    assert record.organization_id == "org-1"
    assert record.installation_id == "install-1"
    assert record.job_id == "job-1"
    assert record.change_event_id == "event-1"
    assert record.status == "verified"
    assert record.model_version == "model-v1"
    assert record.prompt_version == "prompt-v1"
    assert record.patch_diff is not None
    assert record.verification[0]["command"] == "pytest"
    assert record.delivery_outcome["number"] == 42


def test_in_memory_sink_is_append_only_and_rejects_duplicate_ids() -> None:
    sink = InMemoryAuditSink()
    record = build_audit_record(job(), audit_id="audit-1")

    sink.append(record)
    assert sink.list() == (record,)

    with pytest.raises(AuditError, match="unique"):
        sink.append(record)


def test_rejects_oversized_or_null_audit_fields() -> None:
    oversized = job().model_copy(update={"patch_diff": "x" * 128_001})
    with pytest.raises(AuditError, match="patch_diff"):
        build_audit_record(oversized, audit_id="audit-1")

    invalid = job().model_copy(update={"model_version": "model\x00v1"})
    with pytest.raises(AuditError, match="model_version"):
        build_audit_record(invalid, audit_id="audit-2")


def test_rejects_duplicate_or_empty_identity() -> None:
    with pytest.raises(AuditError, match="audit_id"):
        build_audit_record(job(), audit_id="")

    invalid = job().model_copy(update={"organization_id": ""})
    with pytest.raises(AuditError, match="identity"):
        build_audit_record(invalid, audit_id="audit-3")
