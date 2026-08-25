import pytest

from sentinel.llm import LLMProviderError, RemediationContext
from sentinel.llm_provider import ProviderConfig, StructuredLLMAdapter


class FakeClient:
    def complete(self, *, system: str, user: str) -> str:
        assert "Return only a JSON remediation plan" in system
        assert "src/app.ts" in user
        return (
            '{"diagnosis":"payment field removed",'
            '"changes":["update response mapping"],'
            '"verification_commands":["pytest tests/test_payments.py"],'
            '"confidence":0.92}'
        )


class InvalidClient(FakeClient):
    def complete(self, *, system: str, user: str) -> str:
        super().complete(system=system, user=user)
        return "not-json"


def test_provider_config_rejects_empty_model() -> None:
    with pytest.raises(LLMProviderError):
        ProviderConfig(model="").validate()


def test_adapter_returns_strictly_parsed_plan() -> None:
    adapter = StructuredLLMAdapter(
        FakeClient(),
        ProviderConfig(model="test-model", max_output_tokens=100),
    )
    context = RemediationContext(
        change_summary="API response changed",
        affected_files=("src/app.ts",),
        evidence=("response field removed",),
    )

    plan = adapter.generate_plan(context)

    assert plan.diagnosis == "payment field removed"
    assert plan.changes == ("update response mapping",)
    assert plan.verification_commands == ("pytest tests/test_payments.py",)
    assert plan.confidence == 0.92


def test_adapter_fails_closed_on_invalid_model_output() -> None:
    adapter = StructuredLLMAdapter(
        InvalidClient(),
        ProviderConfig(model="test-model", max_output_tokens=100),
    )
    context = RemediationContext(
        change_summary="API response changed",
        affected_files=("src/app.ts",),
    )

    with pytest.raises(LLMProviderError, match="valid JSON"):
        adapter.generate_plan(context)
