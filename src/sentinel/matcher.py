from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import CallSite

_IMPORT_RE = re.compile(r"(?:import\s+(?:[^;\n]+?\s+from\s+)?|require\()\s*[\"']([^\"']+)[\"']")
_HTTP_RE = re.compile(r"(?:get|post|put|patch|delete|request)\s*\(\s*[\"'`]([^\"'`]+)")
_STRIPE_RE = re.compile(r"\bstripe\.[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")


def match_typescript_javascript(files: dict[str, str], affected_endpoints: list[str], vendor: str) -> list[CallSite]:
    """Find likely API call sites using cheap lexical/static signals.

    This is intentionally deterministic. An LLM can be layered on later only for
    ambiguous dynamic dispatch; it must not replace this first-pass evidence.
    """
    sites: list[CallSite] = []
    endpoint_tokens = tuple(affected_endpoints)
    vendor_token = vendor.lower()

    for filename, source in files.items():
        if PurePosixPath(filename).suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            continue
        imported_vendor = any(vendor_token in package.lower() for package in _IMPORT_RE.findall(source))
        lines = source.splitlines()
        for index, line in enumerate(lines, start=1):
            endpoint_hit = any(endpoint in line for endpoint in endpoint_tokens)
            stripe_hit = vendor_token == "stripe" and bool(_STRIPE_RE.search(line))
            http_hit = bool(_HTTP_RE.search(line))
            if endpoint_hit or (imported_vendor and stripe_hit) or (imported_vendor and http_hit):
                evidence: list[str] = []
                confidence = 0.65
                if imported_vendor:
                    evidence.append("vendor import")
                    confidence += 0.1
                if endpoint_hit:
                    evidence.append("affected endpoint literal")
                    confidence += 0.2
                if stripe_hit:
                    evidence.append("Stripe SDK call")
                if http_hit:
                    evidence.append("HTTP call literal")
                sites.append(CallSite(
                    file=filename,
                    line=index,
                    symbol=line.strip()[:160],
                    endpoint=next((e for e in endpoint_tokens if e in line), None),
                    confidence=min(confidence, 0.99),
                    evidence=evidence,
                ))
    return sites
