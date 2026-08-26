from unittest.mock import Mock

import pytest

from sentinel.llm import RemediationContext, RemediationPlan
from sentinel.remediation_orchestrator import (
    RemediationOrchestrationError,
    RemediationOrchestrator,
)
from sentinel.remediation_tools import RemediationToolRequest, RemediationToolResult
from sentinel.tool_executor import PolicyGatedToolExecutor, ToolRegistry


class ReadTool:
    name = "read_file"

    def invoke(self, request: RemediationToolRequest) -> RemediationToolResult:
        return RemediationToolResult("read_file", True, "content")


def make_context() -> RemediationContext:
    return RemediationContext(
        change_summary="API response parser changed",
        affected_files=("src/app.py",),
        evidence=("test-api is failing",),
    )


def test_orchestrator_executes_compiled_requests() -> None:
    llm = Mock()
    llm.generate_plan.return_value = RemediationPlan(
        diagnosis="inspect changed parser",
        changes=("read_file: src/app.py",),
        verification_commands=("pytest -q",),
        confidence=0.9,
    )
    executor = PolicyGatedToolExecutor(ToolRegistry({"read_file": ReadTool()}))

    result = RemediationOrchestrator(llm, executor).remediate(make_context())

    assert result.executed_tools == ("read_file",)
    assert result.verification_commands == ("pytest -q",)


def test_orchestrator_fails_closed_on_unsupported_change() -> None:
    llm = Mock()
    llm.generate_plan.return_value = RemediationPlan(
        diagnosis="unsafe instruction",
        changes=("run shell command",),
        verification_commands=("pytest -q",),
        confidence=0.9,
    )
    executor = PolicyGatedToolExecutor(ToolRegistry({}))

    with pytest.raises(RemediationOrchestrationError, match="stopped safely"):
        RemediationOrchestrator(llm, executor).remediate(make_context())
