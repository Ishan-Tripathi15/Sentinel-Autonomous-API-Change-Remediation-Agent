from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.llm import LLMProviderError, RemediationContext, RemediationPlan
from sentinel.llm_schema import parse_remediation_plan


class ChatClient(Protocol):
    def complete(self, *, system: str, user: str) -> str:
        """Return model text for a single structured-planning request."""


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    max_output_tokens: int = 4096

    def validate(self) -> None:
        if not self.model.strip():
            raise LLMProviderError("model is required")
        if not 1 <= self.max_output_tokens <= 16_384:
            raise LLMProviderError("max_output_tokens must be between 1 and 16384")


class StructuredLLMAdapter:
    """Provider-neutral adapter; transport is injected and model output is strictly validated."""

    def __init__(self, client: ChatClient, config: ProviderConfig) -> None:
        config.validate()
        self._client = client
        self._config = config

    def generate_plan(self, context: RemediationContext) -> RemediationPlan:
        if not context.change_summary.strip():
            raise LLMProviderError("change summary is required")
        prompt = self._build_prompt(context)
        raw = self._client.complete(
            system=(
                "Return only a JSON remediation plan with diagnosis, changes, "
                "verification_commands, and confidence. Do not execute tools."
            ),
            user=prompt,
        )
        return parse_remediation_plan(raw)

    def _build_prompt(self, context: RemediationContext) -> str:
        files = "\n".join(f"- {path}" for path in context.affected_files)
        evidence = "\n".join(f"- {item}" for item in context.evidence)
        return (
            f"Model: {self._config.model}\n"
            f"Change: {context.change_summary}\n"
            f"Affected files:\n{files or '- none'}\n"
            f"Evidence:\n{evidence or '- none'}"
        )
