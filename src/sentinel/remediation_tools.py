from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RemediationToolError(ValueError):
    """Raised when a remediation tool request violates its contract."""


@dataclass(frozen=True)
class RemediationToolRequest:
    tool: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemediationToolResult:
    tool: str
    success: bool
    output: str


class RemediationTool(Protocol):
    name: str

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        """Execute an explicitly permitted remediation operation."""


ALLOWED_TOOLS = frozenset({"read_file", "search_code", "apply_patch"})


def validate_tool_request(request: RemediationToolRequest) -> None:
    if request.tool not in ALLOWED_TOOLS:
        raise RemediationToolError(f"tool is not permitted: {request.tool}")
    if any("\x00" in argument for argument in request.arguments):
        raise RemediationToolError("tool arguments must not contain null bytes")
    if any(argument.strip() == "" for argument in request.arguments):
        raise RemediationToolError("tool arguments must not be empty")
