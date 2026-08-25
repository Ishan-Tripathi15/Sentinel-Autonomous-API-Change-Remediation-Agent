import pytest

from sentinel.llm import RemediationPlan
from sentinel.tool_requests import ToolRequestCompilationError, compile_tool_requests


def plan(*changes: str) -> RemediationPlan:
    return RemediationPlan(
        diagnosis="API contract changed",
        changes=changes,
        verification_commands=("pytest -q",),
        confidence=0.9,
    )


def test_compile_supported_change_directives() -> None:
    batch = compile_tool_requests(
        plan("read_file: src/app.py", "search_code: response.status")
    )
    assert [request.tool for request in batch.requests] == ["read_file", "search_code"]


def test_compile_apply_patch_as_declarative_request() -> None:
    batch = compile_tool_requests(plan("apply_patch: update response parser"))
    assert batch.requests[0].tool == "apply_patch"


def test_compile_rejects_natural_language_as_implicit_execution() -> None:
    with pytest.raises(ToolRequestCompilationError, match="unsupported change directive"):
        compile_tool_requests(plan("edit the parser and run the tests"))
