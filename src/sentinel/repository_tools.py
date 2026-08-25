from __future__ import annotations

from pathlib import Path

from sentinel.remediation_tools import RemediationToolRequest, RemediationToolResult


class RepositoryToolError(ValueError):
    """Raised when a repository operation is outside its safe scope."""


_MAX_OUTPUT_CHARS = 32_000
_MAX_QUERY_CHARS = 512


def _safe_path(root: Path, raw: str) -> Path:
    value = raw.strip()
    if not value or "\x00" in value:
        raise RepositoryToolError("path must be a non-empty string without null bytes")
    candidate = (root / value).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise RepositoryToolError("path escapes repository root") from exc
    return candidate


class ReadFileTool:
    name = "read_file"

    def __init__(self, root: Path) -> None:
        self._root = root

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        if len(request.arguments) != 1:
            raise RepositoryToolError("read_file requires exactly one path")
        path = _safe_path(self._root, request.arguments[0])
        if not path.is_file():
            raise RepositoryToolError("requested path is not a file")
        output = path.read_text(encoding="utf-8")
        return RemediationToolResult(self.name, True, output[:_MAX_OUTPUT_CHARS])


class SearchCodeTool:
    name = "search_code"

    def __init__(self, root: Path) -> None:
        self._root = root

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        if len(request.arguments) != 1:
            raise RepositoryToolError("search_code requires exactly one query")
        query = request.arguments[0].strip()
        if not query or len(query) > _MAX_QUERY_CHARS or "\x00" in query:
            raise RepositoryToolError("invalid search query")

        matches: list[str] = []
        for path in self._root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query in line:
                    matches.append(f"{path.relative_to(self._root)}:{number}:{line.strip()}")
                    if len("\n".join(matches)) >= _MAX_OUTPUT_CHARS:
                        return RemediationToolResult(self.name, True, "\n".join(matches)[:_MAX_OUTPUT_CHARS])
        return RemediationToolResult(self.name, True, "\n".join(matches))
