from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ChangeType(StrEnum):
    BREAKING = "breaking"
    DEPRECATION = "deprecation"
    NEW_FEATURE = "new-feature"
    NON_BREAKING_FIX = "non-breaking-fix"


class ChangeSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApiChange(BaseModel):
    vendor: str
    source_url: HttpUrl | None = None
    version: str | None = None
    change_type: ChangeType
    severity: ChangeSeverity
    summary: str
    affected_endpoints: list[str] = Field(default_factory=list)
    affected_fields: list[str] = Field(default_factory=list)
    raw_diff: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)


class ChangeEvent(ApiChange):
    event_id: str
    detected_at: str


class CallSite(BaseModel):
    file: str
    line: int = Field(gt=0)
    symbol: str
    endpoint: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class BlastRadiusReport(BaseModel):
    change_event_id: str
    repository: str
    affected_files: list[str]
    call_sites: list[CallSite]
    confidence: float = Field(ge=0, le=1)


class VerificationResult(BaseModel):
    passed: bool
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0


class RemediationJob(BaseModel):
    job_id: str
    organization_id: str
    installation_id: str
    change_event_id: str
    status: str
    dry_run: bool = True
    patch_diff: str | None = None
    verification: list[VerificationResult] = Field(default_factory=list)
    model_version: str | None = None
    prompt_version: str | None = None
