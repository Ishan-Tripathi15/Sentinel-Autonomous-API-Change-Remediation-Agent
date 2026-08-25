import pytest

from sentinel.tool_policy import RemediationToolPolicy, ToolPolicyError


def test_default_policy_allows_declared_tool() -> None:
    RemediationToolPolicy().authorize("read_file", ("src/app.py",))


def test_default_policy_denies_unknown_tool() -> None:
    with pytest.raises(ToolPolicyError, match="not permitted"):
        RemediationToolPolicy().authorize("shell", ("pytest",))


def test_policy_rejects_too_many_arguments() -> None:
    policy = RemediationToolPolicy(max_arguments=2)
    with pytest.raises(ToolPolicyError, match="too many"):
        policy.authorize("search_code", ("a", "b", "c"))


def test_policy_rejects_oversized_argument() -> None:
    policy = RemediationToolPolicy(max_argument_length=4)
    with pytest.raises(ToolPolicyError, match="maximum length"):
        policy.authorize("read_file", ("abcde",))


def test_policy_rejects_null_bytes() -> None:
    with pytest.raises(ToolPolicyError, match="null bytes"):
        RemediationToolPolicy().authorize("read_file", ("a\x00b",))


def test_policy_rejects_empty_arguments() -> None:
    with pytest.raises(ToolPolicyError, match="empty"):
        RemediationToolPolicy().authorize("apply_patch", ("   ",))
