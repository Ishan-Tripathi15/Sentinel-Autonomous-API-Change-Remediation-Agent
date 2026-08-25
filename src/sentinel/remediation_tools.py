from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.tool_policy import DEFAULT_TOOL_POLICY, ToolPolicyError


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


ALLOWED_TOOLS = DEFAULT_TOOL_POLICY.allowed_tools


def validate_tool_request(request: RemediationToolRequest) -> None:
    try:
        DEFAULT_TOOL_POLICY.authorize(request.tool, request.arguments)
    except ToolPolicyError as exc:
        raise RemediationToolError(str(exc)) from exc
