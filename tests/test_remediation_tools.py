import pytest

from sentinel.remediation_tools import (
    RemediationToolError,
    RemediationToolRequest,
    validate_tool_request,
)


def test_allowed_tool_request_is_valid() -> None:
    validate_tool_request(RemediationToolRequest(tool="read_file", arguments=("src/app.ts",)))


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(RemediationToolError):
        validate_tool_request(RemediationToolRequest(tool="shell", arguments=("rm -rf",)))


def test_null_byte_is_rejected() -> None:
    with pytest.raises(RemediationToolError):
        validate_tool_request(RemediationToolRequest(tool="read_file", arguments=("a\x00b",)))


def test_empty_argument_is_rejected() -> None:
    with pytest.raises(RemediationToolError):
        validate_tool_request(RemediationToolRequest(tool="apply_patch", arguments=("",)))
