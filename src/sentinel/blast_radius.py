from __future__ import annotations

from fnmatch import fnmatch

from .matcher import match_typescript_javascript
from .models import BlastRadiusReport, CallSite, ChangeEvent

SUPPORTED_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def _endpoint_matches(candidate: str | None, affected: list[str]) -> bool:
    if not candidate:
        return False
    return any(candidate == endpoint or candidate.startswith(endpoint.rstrip("/") + "/") for endpoint in affected)


def _rank(call_site: CallSite, affected_endpoints: list[str]) -> tuple[int, int, str, int]:
    exact = 0 if _endpoint_matches(call_site.endpoint, affected_endpoints) else 1
    confidence = int((1.0 - call_site.confidence) * 1000)
    return (exact, confidence, call_site.file, call_site.line)


def build_blast_radius(
    *,
    change_event: ChangeEvent,
    repository: str,
    files: dict[str, str],
    include_globs: list[str] | None = None,
) -> BlastRadiusReport:
    """Build a deterministic, evidence-backed first-pass blast-radius report.

    Only source files matching the supported JS/TS extensions are scanned. Files can
    optionally be constrained with glob patterns. No customer code is executed.
    """
    patterns = include_globs or ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"]
    candidate_files = {
        path: source
        for path, source in files.items()
        if any(fnmatch(path, pattern) or fnmatch(path.lstrip("./"), pattern.lstrip("./")) for pattern in patterns)
        and any(path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    }

    sites = match_typescript_javascript(candidate_files, change_event.affected_endpoints, change_event.vendor)
    sites.sort(key=lambda site: _rank(site, change_event.affected_endpoints))

    affected_files = sorted({site.file for site in sites})
    confidence = max((site.confidence for site in sites), default=0.0)
    if len(sites) > 1:
        confidence = min(0.99, confidence + 0.02)

    return BlastRadiusReport(
        change_event_id=change_event.event_id,
        repository=repository,
        affected_files=affected_files,
        call_sites=sites,
        confidence=confidence,
    )
