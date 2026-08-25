from __future__ import annotations

from dataclasses import dataclass

from sentinel.llm import RemediationContext, StructuredLLMAdapter
from sentinel.tool_executor import PolicyGatedToolExecutor, ToolExecutionError
from sentinel.tool_requests import ToolRequestCompilationError, compile_tool_requests


class RemediationOrchestrationError(RuntimeError):
    """Raised when a remediation run cannot complete safely."""


@dataclass(frozen=True)
class RemediationRunResult:
    diagnosis: str
    executed_tools: tuple[str, ...]
    verification_commands: tuple[str, ...]
    confidence: float


class RemediationOrchestrator:
    """Run diagnosis through approved tools without executing verification commands."""

    def __init__(self, llm: StructuredLLMAdapter, executor: PolicyGatedToolExecutor) -> None:
        self._llm = llm
        self._executor = executor

    def remediate(self, context: RemediationContext) -> RemediationRunResult:
        try:
            plan = self._llm.propose(context)
            batch = compile_tool_requests(plan)
            executed: list[str] = []
            for request in batch.requests:
                self._executor.execute(request)
                executed.append(request.tool)
        except (ToolRequestCompilationError, ToolExecutionError) as exc:
            raise RemediationOrchestrationError("remediation stopped safely") from exc

        return RemediationRunResult(
            diagnosis=plan.diagnosis,
            executed_tools=tuple(executed),
            verification_commands=plan.verification_commands,
            confidence=plan.confidence,
        )
