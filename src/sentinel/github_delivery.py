from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus

_MAX_FILES = 32
_MAX_FILE_CHARS = 64_000
_MAX_REPOSITORY_CHARS = 256
_MAX_BRANCH_CHARS = 128
_REPOSITORY_RE = re.compile(r"^[^/\\\x00]+/[^/\\\x00]+$")


class GitHubDeliveryError(ValueError):
    """Raised when a GitHub PR delivery cannot safely be completed."""


@dataclass(frozen=True)
class GitHubFileChange:
    """A complete file replacement to include in a Git tree."""

    path: str
    content: str


@dataclass(frozen=True)
class GitHubPullRequest:
    """The provider-side result of a successful delivery."""

    number: int
    url: str
    branch_name: str
    commit_sha: str


class GitHubDeliveryClient:
    """Create one GitHub PR from a verified remediation using the Git Data API.

    The client accepts an installation access token rather than generating or
    storing credentials. It constructs one tree and one commit before creating
    the branch, so repository contents are never mutated file-by-file.
    """

    def __init__(
        self,
        access_token: str,
        *,
        api_base_url: str = "https://api.github.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        if not access_token.strip():
            raise GitHubDeliveryError("GitHub access token is required")
        if not 0 < timeout_seconds <= 60:
            raise GitHubDeliveryError("GitHub delivery timeout must be between 0 and 60 seconds")
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

    def __enter__(self) -> GitHubDeliveryClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def deliver(
        self,
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        title: str,
        body: str,
        changes: list[GitHubFileChange],
        allow_write: bool,
    ) -> GitHubPullRequest:
        """Create a branch and PR only after all write gates have passed."""
        self._validate_request(
            job,
            repository=repository,
            base_branch=base_branch,
            title=title,
            body=body,
            changes=changes,
            allow_write=allow_write,
        )

        owner, repo = repository.split("/", 1)
        base_ref = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(base_branch, safe='')}")
        base_sha = self._string_field(base_ref, "object.sha")
        base_commit = self._request("GET", f"/repos/{owner}/{repo}/git/commits/{base_sha}")
        base_tree_sha = self._string_field(base_commit, "tree.sha")

        branch_name = f"sentinel/remediation/{job.job_id}"
        branch_path = f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch_name, safe='')}"
        branch_exists = self._request_optional("GET", branch_path)
        if branch_exists is not None:
            raise GitHubDeliveryError("remediation branch already exists")

        tree_entries: list[dict[str, str]] = []
        for change in changes:
            blob = self._request(
                "POST",
                f"/repos/{owner}/{repo}/git/blobs",
                json={"content": change.content, "encoding": "utf-8"},
            )
            tree_entries.append(
                {
                    "path": change.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": self._string_field(blob, "sha"),
                }
            )

        tree = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        tree_sha = self._string_field(tree, "sha")
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json={
                "message": title,
                "tree": tree_sha,
                "parents": [base_sha],
            },
        )
        commit_sha = self._string_field(commit, "sha")
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
        )
        pull = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": branch_name,
                "base": base_branch,
            },
        )
        number = pull.get("number")
        url = pull.get("html_url")
        if not isinstance(number, int) or not isinstance(url, str):
            raise GitHubDeliveryError("GitHub returned an invalid pull request response")
        return GitHubPullRequest(
            number=number,
            url=url,
            branch_name=branch_name,
            commit_sha=commit_sha,
        )

    @staticmethod
    def _validate_request(
        job: RemediationJob,
        *,
        repository: str,
        base_branch: str,
        title: str,
        body: str,
        changes: list[GitHubFileChange],
        allow_write: bool,
    ) -> None:
        if not allow_write:
            raise GitHubDeliveryError("GitHub repository writes require explicit allow_write=true")
        if job.status != RemediationStatus.VERIFIED.value:
            raise GitHubDeliveryError("only verified remediation jobs can be delivered")
        if job.dry_run:
            raise GitHubDeliveryError("dry-run remediation jobs cannot perform GitHub writes")
        if len(repository) > _MAX_REPOSITORY_CHARS or not _REPOSITORY_RE.fullmatch(repository):
            raise GitHubDeliveryError("repository must be an owner/name pair")
        if not _valid_branch(base_branch) or len(base_branch) > _MAX_BRANCH_CHARS:
            raise GitHubDeliveryError("base branch is invalid")
        if not title.strip() or not body.strip():
            raise GitHubDeliveryError("pull request title and body are required")
        if any("\x00" in value for value in (repository, base_branch, title, body)):
            raise GitHubDeliveryError("GitHub delivery fields must not contain null bytes")
        if not 1 <= len(changes) <= _MAX_FILES:
            raise GitHubDeliveryError(f"delivery must contain 1-{_MAX_FILES} file changes")
        paths = set()
        for change in changes:
            if not _valid_path(change.path):
                raise GitHubDeliveryError("file change path is invalid")
            if change.path in paths:
                raise GitHubDeliveryError("file change paths must be unique")
            paths.add(change.path)
            if not change.content or len(change.content) > _MAX_FILE_CHARS:
                raise GitHubDeliveryError("file content is empty or exceeds the size limit")
            if "\x00" in change.content:
                raise GitHubDeliveryError("file content must not contain null bytes")

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=json)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubDeliveryError("GitHub API request failed") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubDeliveryError("GitHub API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubDeliveryError("GitHub API returned an invalid response")
        return payload

    def _request_optional(self, method: str, path: str) -> dict[str, Any] | None:
        try:
            response = self._client.request(method, path)
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubDeliveryError("GitHub API request failed") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubDeliveryError("GitHub API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubDeliveryError("GitHub API returned an invalid response")
        return payload

    @staticmethod
    def _string_field(payload: dict[str, Any], field_path: str) -> str:
        value: Any = payload
        for field in field_path.split("."):
            if not isinstance(value, dict):
                raise GitHubDeliveryError("GitHub API response is missing required fields")
            value = value.get(field)
        if not isinstance(value, str) or not value:
            raise GitHubDeliveryError("GitHub API response is missing required fields")
        return value


def _valid_branch(value: str) -> bool:
    return bool(value.strip()) and "\x00" not in value and not value.startswith("/") and ".." not in value


def _valid_path(value: str) -> bool:
    if not value or "\x00" in value or "\\" in value:
        return False
    if value.startswith("/"):
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)
