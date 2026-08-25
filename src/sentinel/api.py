from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .diff import classify_openapi_changes, diff_openapi
from .models import ApiChange, ChangeEvent

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
    return ChangeEvent(
        **event.model_dump(),
        event_id=str(uuid4()),
        detected_at=datetime.now(UTC).isoformat(),
    )


@app.post("/v1/vendors/events", response_model=ChangeEvent)
def ingest_vendor_event(request: VendorEventRequest) -> ChangeEvent:
    """Vendor push interface shared by future embedded-agent deployments."""
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
