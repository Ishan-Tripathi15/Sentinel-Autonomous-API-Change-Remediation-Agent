import pytest

from sentinel.llm import (
    LLMProviderError,
    RemediationContext,
    RemediationPlan,
    UnconfiguredLLMProvider,
)


def valid_plan() -> RemediationPlan:
    return RemediationPlan(
        diagnosis="API response shape changed",
        changes=("update response parsing",),
        verification_commands=("pytest -q",),
        confidence=0.9,
    )


def test_plan_validation_accepts_structured_output() -> None:
    valid_plan().validate()


def test_plan_validation_rejects_invalid_confidence() -> None:
    plan = RemediationPlan("x", ("y",), ("pytest",), 1.1)
    with pytest.raises(LLMProviderError):
        plan.validate()


def test_unconfigured_provider_fails_closed() -> None:
    provider = UnconfiguredLLMProvider()
    context = RemediationContext(change_summary="changed", affected_files=("src/app.ts",))
    with pytest.raises(LLMProviderError):
        provider.generate_plan(context)
