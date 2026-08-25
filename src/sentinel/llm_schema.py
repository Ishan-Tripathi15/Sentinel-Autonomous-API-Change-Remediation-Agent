import json
from typing import Any

from sentinel.llm import LLMProviderError, RemediationPlan


MAX_DIAGNOSIS_CHARS = 4_000
MAX_CHANGE_CHARS = 2_000
MAX_COMMAND_CHARS = 500
MAX_ITEMS = 32


def parse_remediation_plan(raw: str) -> RemediationPlan:
    """Parse only the exact JSON shape Sentinel permits from an LLM."""
    if len(raw.encode("utf-8")) > 64_000:
        raise LLMProviderError("model response exceeds the maximum size")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("model response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LLMProviderError("remediation plan must be a JSON object")
    if set(payload) != {"diagnosis", "changes", "verification_commands", "confidence"}:
        raise LLMProviderError("remediation plan contains unexpected or missing fields")

    diagnosis = _string(payload, "diagnosis", MAX_DIAGNOSIS_CHARS)
    changes = _strings(payload, "changes", MAX_CHANGE_CHARS)
    commands = _strings(payload, "verification_commands", MAX_COMMAND_CHARS)
    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise LLMProviderError("confidence must be a number")

    plan = RemediationPlan(
        diagnosis=diagnosis,
        changes=changes,
        verification_commands=commands,
        confidence=float(confidence),
    )
    plan.validate()
    return plan


def _string(payload: dict[str, Any], key: str, max_chars: int) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise LLMProviderError(f"{key} must be a non-empty string")
    if len(value) > max_chars:
        raise LLMProviderError(f"{key} exceeds the maximum length")
    return value


def _strings(payload: dict[str, Any], key: str, max_chars: int) -> tuple[str, ...]:
    value = payload[key]
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ITEMS:
        raise LLMProviderError(f"{key} must contain between 1 and {MAX_ITEMS} items")
    result = tuple(_item(item, key, max_chars) for item in value)
    return result


def _item(item: Any, key: str, max_chars: int) -> str:
    if not isinstance(item, str) or not item.strip():
        raise LLMProviderError(f"{key} items must be non-empty strings")
    if len(item) > max_chars:
        raise LLMProviderError(f"{key} item exceeds the maximum length")
    return item
