import pytest

from sentinel.llm import LLMProviderError, RemediationContext
from sentinel.llm_provider import ProviderConfig, StructuredLLMAdapter


class FakeClient:
    def complete(self, *, system: str, user: str) -> str:
        assert "Return only a JSON remediation plan" in system
        assert "src/app.ts" in user
        return "{}"


def test_provider_config_rejects_empty_model() -> None:
    with pytest.raises(LLMProviderError):
        ProviderConfig(model="").validate()


def test_adapter_builds_bounded_prompt_and_fails_closed_on_unparsed_output() -> None:
    adapter = StructuredLLMAdapter(
        FakeClient(),
        ProviderConfig(model="test-model", max_output_tokens=100),
    )
    context = RemediationContext(
        change_summary="API response changed",
        affected_files=("src/app.ts",),
        evidence=("response field removed",),
    )
    with pytest.raises(LLMProviderError, match="JSON schema"):
        adapter.generate_plan(context)
