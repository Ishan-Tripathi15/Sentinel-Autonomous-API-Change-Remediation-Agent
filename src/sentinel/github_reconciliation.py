from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .delivery_reconciliation import RemoteDelivery


class GitHubReconciliationError(RuntimeError):
    """Raised when GitHub state cannot be safely inspected."""


class GitHubDeliveryReconciliationProvider:
    """Discover an existing Sentinel delivery without creating remote state."""

    def __init__(
        self,
        access_token: str,
        *,
        api_base_url: str = "https://api.github.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        if not access_token.strip():
            raise GitHubReconciliationError("GitHub access token is required")
        self._client = httpx.Client(
            base_url=api_base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def close(self) -> None:
        self._client.close()

    def find_delivery(
        self, *, repository: str, branch_name: str, base_branch: str
    ) -> RemoteDelivery | None:
        owner, repo = self._split_repository(repository)
        branch_path = f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch_name, safe='')}"
        try:
            branch = self._client.get(branch_path)
            if branch.status_code == 404:
                return None
            branch.raise_for_status()
            branch_payload = self._json_object(branch)
            commit_sha = self._string(branch_payload, "object.sha")

            pulls = self._client.get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": "open", "head": f"{owner}:{branch_name}", "base": base_branch},
            )
            pulls.raise_for_status()
            payload = pulls.json()
            if not isinstance(payload, list):
                raise GitHubReconciliationError("GitHub returned an invalid pull request list")
            for pull in payload:
                if not isinstance(pull, dict):
                    continue
                number = pull.get("number")
                url = pull.get("html_url")
                if isinstance(number, int) and isinstance(url, str) and url:
                    return RemoteDelivery(number, url, branch_name, commit_sha)
            return None
        except httpx.HTTPError as exc:
            raise GitHubReconciliationError("GitHub reconciliation request failed") from exc

    @staticmethod
    def _split_repository(repository: str) -> tuple[str, str]:
        parts = repository.split("/", 1)
        if len(parts) != 2 or not all(parts):
            raise GitHubReconciliationError("repository must be an owner/name pair")
        return parts[0], parts[1]

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubReconciliationError("GitHub returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubReconciliationError("GitHub returned an invalid response")
        return payload

    @staticmethod
    def _string(payload: dict[str, Any], field_path: str) -> str:
        value: Any = payload
        for field in field_path.split("."):
            if not isinstance(value, dict):
                raise GitHubReconciliationError("GitHub response is missing required fields")
            value = value.get(field)
        if not isinstance(value, str) or not value:
            raise GitHubReconciliationError("GitHub response is missing required fields")
        return value
