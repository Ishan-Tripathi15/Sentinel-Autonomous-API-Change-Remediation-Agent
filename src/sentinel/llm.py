from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot produce a valid response."""


@dataclass(frozen=True)
class RemediationContext:
    change_summary: str
    affected_files: tuple[str, ...]
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemediationPlan:
    diagnosis: str
    changes: tuple[str, ...]
    verification_commands: tuple[str, ...]
    confidence: float

    def validate(self) -> None:
        if not self.diagnosis.strip():
            raise LLMProviderError("diagnosis is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise LLMProviderError("confidence must be between 0 and 1")
        if not self.changes:
            raise LLMProviderError("at least one proposed change is required")
        if not self.verification_commands:
            raise LLMProviderError("at least one verification command is required")


class LLMProvider(Protocol):
    """Provider-neutral interface for structured remediation planning."""

    def generate_plan(self, context: RemediationContext) -> RemediationPlan:
        """Generate a structured plan without directly executing tools."""


class UnconfiguredLLMProvider:
    """Safe default until an explicitly configured provider is supplied."""

    def generate_plan(self, context: RemediationContext) -> RemediationPlan:
        raise LLMProviderError("no LLM provider is configured")
