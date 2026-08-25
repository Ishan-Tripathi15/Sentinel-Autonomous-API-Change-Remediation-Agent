from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ChangeSeverity, ChangeType


@dataclass(frozen=True)
class SpecChange:
    path: str
    kind: str
    before: Any = None
    after: Any = None


def _walk(before: Any, after: Any, path: str = "") -> list[SpecChange]:
    changes: list[SpecChange] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() - after.keys()):
            changes.append(SpecChange(f"{path}/{key}", "removed", before[key], None))
        for key in sorted(after.keys() - before.keys()):
            changes.append(SpecChange(f"{path}/{key}", "added", None, after[key]))
        for key in sorted(before.keys() & after.keys()):
            changes.extend(_walk(before[key], after[key], f"{path}/{key}"))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        if before != after:
            changes.append(SpecChange(path or "/", "changed", before, after))
        return changes
    if before != after:
        changes.append(SpecChange(path or "/", "changed", before, after))
    return changes


def diff_openapi(before: dict[str, Any], after: dict[str, Any]) -> list[SpecChange]:
    """Produce a deterministic structural diff for OpenAPI JSON documents."""
    return _walk(before, after)


def _is_endpoint(path: str) -> bool:
    return path.startswith("/paths/") and path.count("/") >= 3


def classify_openapi_changes(changes: list[SpecChange]) -> tuple[ChangeType, ChangeSeverity, list[str], list[str]]:
    affected_endpoints: set[str] = set()
    affected_fields: set[str] = set()
    breaking = False
    deprecation = False
    new_feature = False

    for change in changes:
        parts = change.path.split("/")
        if len(parts) >= 3 and parts[1] == "paths":
            endpoint = "/" + "/".join(parts[2:3])
            affected_endpoints.add(endpoint)
        if "/deprecated" in change.path and change.after is True:
            deprecation = True
        if change.kind == "removed":
            breaking = True
            if _is_endpoint(change.path):
                affected_endpoints.add(change.path.split("/paths/", 1)[1].split("/", 1)[0])
            else:
                affected_fields.add(change.path)
        elif change.kind == "changed" and any(token in change.path for token in ("/required", "/parameters/", "/requestBody", "/schema")):
            if change.before is not None and change.after is not None:
                breaking = True
        elif change.kind == "added":
            new_feature = True

    if breaking:
        return ChangeType.BREAKING, ChangeSeverity.HIGH, sorted(affected_endpoints), sorted(affected_fields)
    if deprecation:
        return ChangeType.DEPRECATION, ChangeSeverity.MEDIUM, sorted(affected_endpoints), sorted(affected_fields)
    if new_feature:
        return ChangeType.NEW_FEATURE, ChangeSeverity.LOW, sorted(affected_endpoints), sorted(affected_fields)
    return ChangeType.NON_BREAKING_FIX, ChangeSeverity.LOW, sorted(affected_endpoints), sorted(affected_fields)
