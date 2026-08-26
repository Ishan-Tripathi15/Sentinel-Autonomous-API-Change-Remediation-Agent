from __future__ import annotations

import json
from pathlib import Path

from sentinel.remediation_tools import RemediationToolRequest, RemediationToolResult
from sentinel.repository_tools import RepositoryToolError, _safe_path

_MAX_FILE_CHARS = 64_000


class ApplyPatchTool:
    """Apply an exact old-to-new text replacement inside the repository root.

    The request argument is a JSON object with ``path``, ``old`` and ``new``.
    Exact replacement prevents ambiguous fuzzy patching and never invokes a
    shell, subprocess, or external patch program.
    """

    name = "apply_patch"

    def __init__(self, root: Path) -> None:
        self._root = root

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        if len(request.arguments) != 1:
            raise RepositoryToolError("apply_patch requires exactly one JSON argument")
        try:
            payload = json.loads(request.arguments[0])
        except json.JSONDecodeError as exc:
            raise RepositoryToolError("apply_patch argument must be valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"path", "old", "new"}:
            raise RepositoryToolError("patch must contain exactly path, old, and new")
        path_value = payload["path"]
        old = payload["old"]
        new = payload["new"]
        if not isinstance(path_value, str) or not isinstance(old, str) or not isinstance(new, str):
            raise RepositoryToolError("patch path, old, and new must be strings")
        if not old:
            raise RepositoryToolError("patch old text must not be empty")
        if len(old) > _MAX_FILE_CHARS or len(new) > _MAX_FILE_CHARS:
            raise RepositoryToolError("patch text exceeds the maximum size")

        path = _safe_path(self._root, path_value)
        if not path.is_file():
            raise RepositoryToolError("patch target must be an existing file")
        current = path.read_text(encoding="utf-8")
        if len(current) > _MAX_FILE_CHARS:
            raise RepositoryToolError("target file exceeds the maximum size")
        occurrences = current.count(old)
        if occurrences != 1:
            raise RepositoryToolError("patch must match exactly one occurrence")

        updated = current.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        return RemediationToolResult(self.name, True, f"updated {path.relative_to(self._root)}")
