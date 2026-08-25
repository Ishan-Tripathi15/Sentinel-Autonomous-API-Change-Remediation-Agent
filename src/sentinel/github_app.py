from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


class WebhookVerificationError(ValueError):
    """Raised when a GitHub webhook cannot be authenticated."""


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> None:
    """Verify GitHub's X-Hub-Signature-256 header in constant time."""
    if not secret:
        raise WebhookVerificationError("webhook secret is not configured")
    if not signature.startswith("sha256="):
        raise WebhookVerificationError("invalid webhook signature format")
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise WebhookVerificationError("invalid webhook signature")


@dataclass(frozen=True)
class InstallationRepository:
    installation_id: int
    repository_id: int
    full_name: str
    default_branch: str


def parse_installation_event(payload: bytes) -> tuple[int, str, list[InstallationRepository]]:
    """Normalize a GitHub App installation event without performing side effects."""
    try:
        data: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WebhookVerificationError("webhook payload is not valid JSON") from exc

    installation = data.get("installation") or {}
    installation_id = installation.get("id")
    action = data.get("action")
    if not isinstance(installation_id, int) or not isinstance(action, str):
        raise WebhookVerificationError("installation event is missing id or action")

    repositories: list[InstallationRepository] = []
    for repository in data.get("repositories", []):
        if not isinstance(repository, dict):
            continue
        repository_id = repository.get("id")
        full_name = repository.get("full_name")
        default_branch = repository.get("default_branch")
        if not isinstance(repository_id, int) or not isinstance(full_name, str):
            continue
        repositories.append(
            InstallationRepository(
                installation_id=installation_id,
                repository_id=repository_id,
                full_name=full_name,
                default_branch=default_branch if isinstance(default_branch, str) else "main",
            )
        )
    return installation_id, action, repositories
