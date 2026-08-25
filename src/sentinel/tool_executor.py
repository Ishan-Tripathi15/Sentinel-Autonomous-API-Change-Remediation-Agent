from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sentinel.remediation_tools import (
    RemediationTool,
    RemediationToolError,
    RemediationToolRequest,
    RemediationToolResult,
    validate_tool_request,
)


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot be executed safely."""


@dataclass(frozen=True)
class ToolRegistry:
    tools: Mapping[str, RemediationTool]

    def resolve(self, name: str) -> RemediationTool:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"tool is not registered: {name}")
        if tool.name != name:
            raise ToolExecutionError(f"registered tool name mismatch: {name}")
        return tool


class PolicyGatedToolExecutor:
    """Execute only explicitly registered requests that pass the central policy."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, request: RemediationToolRequest) -> RemediationToolResult:
        try:
            validate_tool_request(request)
        except RemediationToolError as exc:
            raise ToolExecutionError(str(exc)) from exc

        tool = self._registry.resolve(request.tool)
        try:
            result = tool.invoke(request)
        except Exception as exc:
            raise ToolExecutionError(f"tool execution failed: {request.tool}") from exc

        if result.tool != request.tool:
            raise ToolExecutionError("tool returned a mismatched result")
        if not isinstance(result.output, str):
            raise ToolExecutionError("tool result output must be text")
        return result
