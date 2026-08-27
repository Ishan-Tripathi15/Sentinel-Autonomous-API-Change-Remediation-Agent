from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .approval_gate import ApprovalError, approve_remediation
from .audit import AuditError, build_audit_event, build_audit_record
from .audit_runtime import get_audit_sink
from .blast_radius import build_blast_radius
from .delivery import DryRunDelivery, build_dry_run_delivery
from .diff import classify_openapi_changes, diff_openapi
from .github_app import WebhookVerificationError, parse_installation_event, verify_webhook_signature
from .github_delivery import GitHubDeliveryClient, GitHubFileChange, GitHubPullRequest
from .job_queue import JobQueueError
from .job_queue_runtime import get_job_queue
from .models import ApiChange, BlastRadiusReport, ChangeEvent, RemediationJob
from .orchestrator import create_remediation_job
from .repository import RepositorySnapshot, build_repository_snapshot

app = FastAPI(title="Sentinel", version="0.1.0")


class OpenApiDiffRequest(BaseModel):
    vendor: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    version: str | None = None
    before: dict
    after: dict


class VendorEventRequest(BaseModel):
    vendor: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    version: str | None = None
    summary: str = Field(min_length=1)
    payload: dict


class BlastRadiusRequest(BaseModel):
    change_event: ChangeEvent
    repository: str = Field(min_length=1)
    files: dict[str, str]
    include_globs: list[str] | None = None


class RemediationJobRequest(BaseModel):
    change_event: ChangeEvent
    blast_radius: BlastRadiusReport
    organization_id: str = Field(min_length=1)
    installation_id: str = Field(min_length=1)
    dry_run: bool = True


class RemediationAuditEventRequest(BaseModel):
    job: RemediationJob
    event_type: str = Field(min_length=1, max_length=256)
    from_status: str | None = Field(default=None, max_length=256)
    to_status: str | None = Field(default=None, max_length=256)
    metadata: dict[str, object] = Field(default_factory=dict, max_length=32)


class RepositorySnapshotRequest(BaseModel):
    repository: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    files: dict[str, str]
    include_globs: list[str] | None = None


class DryRunDeliveryRequest(BaseModel):
    job: RemediationJob
    repository: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1)
    patch_diff: str = Field(min_length=1, max_length=128_000)


class GitHubFileChangeRequest(BaseModel):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=64_000)


class GitHubDeliveryRequest(BaseModel):
    job: RemediationJob
    repository: str = Field(min_length=1, max_length=256)
    base_branch: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=16_000)
    changes: list[GitHubFileChangeRequest] = Field(min_length=1, max_length=32)
    allow_write: bool = False


class JobApprovalRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=256)
    approved_by: str = Field(min_length=1, max_length=256)
    approved_at: datetime | None = None


class JobClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=256)
    lease_seconds: int = Field(default=300, ge=1, le=3600)


class JobCompleteRequest(BaseModel):
    job_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1, max_length=256)
    job: RemediationJob


class JobFailRequest(BaseModel):
    job_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1, max_length=256)
    job: RemediationJob
    retry_after_seconds: int = Field(default=30, ge=0, le=3600)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinel"}


@app.post("/v1/changes/openapi", response_model=ChangeEvent)
def ingest_openapi(request: OpenApiDiffRequest) -> ChangeEvent:
    changes = diff_openapi(request.before, request.after)
    if not changes:
        raise HTTPException(status_code=204, detail="No API changes detected")
    change_type, severity, endpoints, fields = classify_openapi_changes(changes)
    event = ApiChange(
        vendor=request.vendor,
        source_url=request.source_url,
        version=request.version,
        change_type=change_type,
        severity=severity,
        summary=f"Detected {len(changes)} OpenAPI change(s) for {request.vendor}",
        affected_endpoints=endpoints,
        affected_fields=fields,
        raw_diff={"changes": [change.__dict__ for change in changes]},
        confidence=0.98,
    )
    return ChangeEvent(**event.model_dump(), event_id=str(uuid4()), detected_at=datetime.now(UTC).isoformat())


@app.post("/v1/vendors/events", response_model=ChangeEvent)
def ingest_vendor_event(request: VendorEventRequest) -> ChangeEvent:
    return ChangeEvent(
        vendor=request.vendor,
        source_url=request.source_url,
        version=request.version,
        change_type="non-breaking-fix",
        severity="low",
        summary=request.summary,
        affected_endpoints=[],
        affected_fields=[],
        raw_diff=request.payload,
        confidence=0.7,
        event_id=str(uuid4()),
        detected_at=datetime.now(UTC).isoformat(),
    )


@app.post("/v1/github/webhooks")
def github_webhook(payload: bytes, x_hub_signature_256: str | None = Header(default=None)) -> dict[str, object]:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="missing GitHub webhook signature")
    try:
        verify_webhook_signature(payload, x_hub_signature_256, secret)
        installation_id, action, repositories = parse_installation_event(payload)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"accepted": True, "installation_id": installation_id, "action": action, "repositories": [repository.__dict__ for repository in repositories]}


@app.post("/v1/repositories/snapshots", response_model=RepositorySnapshot)
def ingest_repository_snapshot(request: RepositorySnapshotRequest) -> RepositorySnapshot:
    try:
        return build_repository_snapshot(repository=request.repository, revision=request.revision, files=request.files, include_globs=request.include_globs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/analysis/blast-radius", response_model=BlastRadiusReport)
def analyze_blast_radius(request: BlastRadiusRequest) -> BlastRadiusReport:
    return build_blast_radius(change_event=request.change_event, repository=request.repository, files=request.files, include_globs=request.include_globs)


@app.post("/v1/remediation/jobs", response_model=RemediationJob)
def create_job(request: RemediationJobRequest) -> RemediationJob:
    try:
        job = create_remediation_job(change_event=request.change_event, blast_radius=request.blast_radius, organization_id=request.organization_id, installation_id=request.installation_id, dry_run=request.dry_run)
        sink = get_audit_sink()
        sink.append(build_audit_record(job, request.change_event, audit_id=str(uuid4())))
        sink.append_event(build_audit_event(job, audit_event_id=str(uuid4()), event_type="job_created", to_status=job.status))
        get_job_queue().enqueue(job)
        return job
    except AuditError as exc:
        raise HTTPException(status_code=503, detail="audit persistence is unavailable") from exc
    except JobQueueError as exc:
        raise HTTPException(status_code=503, detail="job queue is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/remediation/jobs/approve", response_model=RemediationJob)
def approve_job(request: JobApprovalRequest) -> RemediationJob:
    try:
        queue = get_job_queue()
        job = queue.get(job_id=request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="remediation job not found")
        released, approval = approve_remediation(job, approved_by=request.approved_by, approved_at=request.approved_at)
        queue.release_approval(job=released)
        get_audit_sink().append_event(
            build_audit_event(
                released,
                audit_event_id=str(uuid4()),
                event_type="job_approved",
                from_status=job.status,
                to_status=released.status,
                metadata={
                    "approved_by": approval.approved_by,
                    "approved_at": approval.approved_at.isoformat(),
                },
            )
        )
        return released
    except HTTPException:
        raise
    except (ApprovalError, JobQueueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuditError as exc:
        raise HTTPException(status_code=503, detail="audit persistence is unavailable") from exc


@app.post("/v1/remediation/jobs/events")
def append_remediation_event(request: RemediationAuditEventRequest) -> dict[str, object]:
    try:
        event = build_audit_event(request.job, audit_event_id=str(uuid4()), event_type=request.event_type, from_status=request.from_status, to_status=request.to_status, metadata=request.metadata)
        get_audit_sink().append_event(event)
        return {"accepted": True, "audit_event_id": event.audit_event_id}
    except AuditError as exc:
        raise HTTPException(status_code=503, detail="audit persistence is unavailable") from exc


@app.post("/v1/remediation/jobs/claim", response_model=RemediationJob | None)
def claim_job(request: JobClaimRequest) -> RemediationJob | None:
    try:
        job = get_job_queue().claim(worker_id=request.worker_id, lease_seconds=request.lease_seconds)
        if job is not None:
            get_audit_sink().append_event(build_audit_event(job, audit_event_id=str(uuid4()), event_type="job_claimed", from_status="queued", to_status="running", metadata={"worker_id": request.worker_id}))
        return job
    except (JobQueueError, AuditError) as exc:
        raise HTTPException(status_code=503, detail="job queue or audit storage is unavailable") from exc


@app.post("/v1/remediation/jobs/complete")
def complete_job(request: JobCompleteRequest) -> dict[str, bool]:
    try:
        get_job_queue().complete(job_id=request.job_id, worker_id=request.worker_id, payload=request.job)
        get_audit_sink().append_event(build_audit_event(request.job, audit_event_id=str(uuid4()), event_type="job_completed", from_status="running", to_status=request.job.status, metadata={"worker_id": request.worker_id}))
        return {"accepted": True}
    except (JobQueueError, AuditError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/remediation/jobs/fail")
def fail_job(request: JobFailRequest) -> dict[str, bool]:
    try:
        get_job_queue().fail(job_id=request.job_id, worker_id=request.worker_id, payload=request.job, retry_after_seconds=request.retry_after_seconds)
        get_audit_sink().append_event(build_audit_event(request.job, audit_event_id=str(uuid4()), event_type="job_requeued", from_status="running", to_status="queued", metadata={"worker_id": request.worker_id, "retry_after_seconds": request.retry_after_seconds}))
        return {"accepted": True}
    except (JobQueueError, AuditError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/remediation/dry-run-delivery", response_model=DryRunDelivery)
def build_delivery(request: DryRunDeliveryRequest) -> DryRunDelivery:
    try:
        return build_dry_run_delivery(request.job, repository=request.repository, summary=request.summary, patch_diff=request.patch_diff)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/remediation/github-delivery", response_model=GitHubPullRequest)
def github_delivery(request: GitHubDeliveryRequest) -> GitHubPullRequest:
    token = os.environ.get("GITHUB_INSTALLATION_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="GitHub installation token is not configured")
    try:
        with GitHubDeliveryClient(token) as client:
            return client.deliver(request.job, repository=request.repository, base_branch=request.base_branch, title=request.title, body=request.body, changes=[GitHubFileChange(path=change.path, content=change.content) for change in request.changes], allow_write=request.allow_write)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
