from __future__ import annotations

from dataclasses import dataclass, field


class ToolPolicyError(ValueError):
    """Raised when a remediation tool request violates execution policy."""


@dataclass(frozen=True)
class RemediationToolPolicy:
    """Default-deny policy for model-generated remediation tool requests."""

    allowed_tools: frozenset[str] = field(
        default_factory=lambda: frozenset({"read_file", "search_code", "apply_patch"})
    )
    max_arguments: int = 8
    max_argument_length: int = 8_192

    def authorize(self, tool: str, arguments: tuple[str, ...]) -> None:
        if tool not in self.allowed_tools:
            raise ToolPolicyError(f"tool is not permitted: {tool}")
        if len(arguments) > self.max_arguments:
            raise ToolPolicyError("too many tool arguments")
        for argument in arguments:
            if "\x00" in argument:
                raise ToolPolicyError("tool arguments must not contain null bytes")
            if not argument.strip():
                raise ToolPolicyError("tool arguments must not be empty")
            if len(argument) > self.max_argument_length:
                raise ToolPolicyError("tool argument exceeds the maximum length")


DEFAULT_TOOL_POLICY = RemediationToolPolicy()
