from __future__ import annotations

from dataclasses import dataclass

from sentinel.llm import LLMProviderError, RemediationPlan
from sentinel.remediation_tools import RemediationToolRequest, validate_tool_request


class ToolRequestCompilationError(LLMProviderError):
    """Raised when a model plan cannot be safely converted to tool requests."""


@dataclass(frozen=True)
class ToolRequestBatch:
    requests: tuple[RemediationToolRequest, ...]


def compile_tool_requests(plan: RemediationPlan) -> ToolRequestBatch:
    """Translate only the declarative change portion of a plan into requests.

    The compiler never executes tools. Every generated request is validated by
    the centralized default-deny policy before it is returned to the caller.
    """
    plan.validate()
    requests: list[RemediationToolRequest] = []
    for change in plan.changes:
        request = _compile_change(change)
        try:
            validate_tool_request(request)
        except Exception as exc:
            raise ToolRequestCompilationError(str(exc)) from exc
        requests.append(request)
    return ToolRequestBatch(tuple(requests))


def _compile_change(change: str) -> RemediationToolRequest:
    text = change.strip()
    if not text:
        raise ToolRequestCompilationError("change must not be empty")

    # Keep the compiler deliberately conservative. Natural-language model
    # output is treated as a request to inspect code, not as executable input.
    if text.startswith("read_file:"):
        path = text.partition(":")[2].strip()
        return RemediationToolRequest("read_file", (path,))
    if text.startswith("search_code:"):
        query = text.partition(":")[2].strip()
        return RemediationToolRequest("search_code", (query,))
    if text.startswith("apply_patch:"):
        patch = text.partition(":")[2].strip()
        return RemediationToolRequest("apply_patch", (patch,))
    raise ToolRequestCompilationError(
        "unsupported change directive; expected read_file:, search_code:, or apply_patch:"
    )
