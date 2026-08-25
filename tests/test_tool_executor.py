import pytest

from sentinel.remediation_tools import RemediationToolRequest, RemediationToolResult
from sentinel.tool_executor import PolicyGatedToolExecutor, ToolExecutionError, ToolRegistry


class FakeTool:
    name = "read_file"

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        return RemediationToolResult(request.tool, True, "file contents")


class MismatchedTool:
    name = "read_file"

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        return RemediationToolResult("search_code", True, "wrong")


def test_executor_validates_policy_and_invokes_registered_tool() -> None:
    executor = PolicyGatedToolExecutor(ToolRegistry({"read_file": FakeTool()}))
    result = executor.execute(RemediationToolRequest("read_file", ("src/app.py",)))
    assert result.success is True
    assert result.output == "file contents"


def test_executor_denies_unknown_tool() -> None:
    executor = PolicyGatedToolExecutor(ToolRegistry({}))
    with pytest.raises(ToolExecutionError, match="not permitted: shell"):
        executor.execute(RemediationToolRequest("shell", ("rm -rf /",)))


def test_executor_rejects_mismatched_result() -> None:
    executor = PolicyGatedToolExecutor(ToolRegistry({"read_file": MismatchedTool()}))
    with pytest.raises(ToolExecutionError, match="mismatched result"):
        executor.execute(RemediationToolRequest("read_file", ("src/app.py",)))
