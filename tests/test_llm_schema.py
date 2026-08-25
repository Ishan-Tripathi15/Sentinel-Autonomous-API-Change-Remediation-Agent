import json

import pytest

from sentinel.llm import LLMProviderError
from sentinel.llm_schema import parse_remediation_plan


def valid_payload() -> dict[str, object]:
    return {
        "diagnosis": "API response shape changed",
        "changes": ["update response parsing"],
        "verification_commands": ["pytest -q"],
        "confidence": 0.9,
    }


def test_parser_accepts_exact_schema() -> None:
    plan = parse_remediation_plan(json.dumps(valid_payload()))
    assert plan.confidence == 0.9
    assert plan.changes == ("update response parsing",)


@pytest.mark.parametrize("field", ["diagnosis", "changes", "verification_commands", "confidence"])
def test_parser_rejects_missing_field(field: str) -> None:
    payload = valid_payload()
    del payload[field]
    with pytest.raises(LLMProviderError):
        parse_remediation_plan(json.dumps(payload))


def test_parser_rejects_extra_field() -> None:
    payload = valid_payload()
    payload["tool"] = "shell"
    with pytest.raises(LLMProviderError):
        parse_remediation_plan(json.dumps(payload))


def test_parser_rejects_malformed_json() -> None:
    with pytest.raises(LLMProviderError):
        parse_remediation_plan("not-json")


def test_parser_rejects_boolean_confidence() -> None:
    payload = valid_payload()
    payload["confidence"] = True
    with pytest.raises(LLMProviderError):
        parse_remediation_plan(json.dumps(payload))


def test_parser_rejects_oversized_response() -> None:
    with pytest.raises(LLMProviderError):
        parse_remediation_plan("x" * 64_001)
