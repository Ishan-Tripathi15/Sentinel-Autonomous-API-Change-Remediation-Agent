from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sentinel.github_delivery import GitHubDeliveryClient, GitHubDeliveryError, GitHubFileChange
from sentinel.models import RemediationJob
from sentinel.orchestrator import RemediationStatus
from sentinel.write_authorization import RepositoryWriteAuthorization

REPOSITORY = "acme/service"


def make_job(*, status: str = RemediationStatus.VERIFIED.value, dry_run: bool = False) -> RemediationJob:
    return RemediationJob(
        job_id="job-123",
        organization_id="org-1",
        installation_id="installation-1",
        change_event_id="event-1",
        status=status,
        dry_run=dry_run,
    )


def make_authorization(job: RemediationJob | None = None) -> RepositoryWriteAuthorization:
    return RepositoryWriteAuthorization.issue(
        job or make_job(),
        repository=REPOSITORY,
        base_branch="main",
        authorized_by="policy-engine",
        authorized_at=datetime(2026, 8, 28, 12, tzinfo=UTC),
    )


def make_client(handler) -> GitHubDeliveryClient:
    client = GitHubDeliveryClient("token")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    return client


def test_delivery_requires_repository_write_authorization() -> None:
    client = GitHubDeliveryClient("token")
    try:
        with pytest.raises(GitHubDeliveryError, match="authorization is required"):
            client.deliver(
                make_job(),
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[GitHubFileChange("src/client.py", "updated")],
                authorization=None,
            )
    finally:
        client.close()


def test_delivery_rejects_dry_run_authorization() -> None:
    client = GitHubDeliveryClient("token")
    try:
        with pytest.raises(GitHubDeliveryError, match="dry-run"):
            client.deliver(
                make_job(dry_run=True),
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[GitHubFileChange("src/client.py", "updated")],
                authorization=make_authorization(make_job(dry_run=True)),
            )
    finally:
        client.close()


def test_delivery_rejects_unverified_job() -> None:
    client = GitHubDeliveryClient("token")
    job = make_job(status=RemediationStatus.FAILED.value)
    try:
        with pytest.raises(GitHubDeliveryError, match="verified"):
            client.deliver(
                job,
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[GitHubFileChange("src/client.py", "updated")],
                authorization=make_authorization(job),
            )
    finally:
        client.close()


def test_delivery_builds_one_commit_and_pull_request() -> None:
    calls: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.content.decode() if request.content else None
        calls.append((request.method, request.url.path, payload))
        if request.method == "GET" and request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "base-sha"}})
        if request.method == "GET" and request.url.path.endswith("/git/commits/base-sha"):
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if request.method == "GET" and "/git/ref/heads/sentinel/remediation/" in request.url.path:
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob-sha"})
        if request.method == "POST" and request.url.path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "tree-sha"})
        if request.method == "POST" and request.url.path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "commit-sha"})
        if request.method == "POST" and request.url.path.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/sentinel/remediation/job-123"})
        if request.method == "POST" and request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"number": 42, "html_url": "https://github.com/acme/service/pull/42"})
        return httpx.Response(500, json={"message": "unexpected request"})

    client = make_client(handler)
    try:
        result = client.deliver(
            make_job(),
            repository=REPOSITORY,
            base_branch="main",
            title="chore: remediate",
            body="Sentinel remediation",
            changes=[GitHubFileChange("src/client.py", "updated")],
            authorization=make_authorization(),
        )
    finally:
        client.close()

    assert result.number == 42
    assert result.branch_name == "sentinel/remediation/job-123"
    assert result.commit_sha == "commit-sha"
    assert [method for method, _, _ in calls] == ["GET", "GET", "GET", "POST", "POST", "POST", "POST", "POST"]


def test_delivery_rejects_mismatched_authorization_before_remote_write() -> None:
    client = GitHubDeliveryClient("token")
    try:
        with pytest.raises(GitHubDeliveryError, match="does not belong"):
            client.deliver(
                make_job(),
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[GitHubFileChange("src/client.py", "updated")],
                authorization=make_authorization(make_job().model_copy(update={"job_id": "other-job"})),
            )
    finally:
        client.close()


def test_delivery_rejects_existing_branch_before_creating_blobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "base-sha"}})
        if request.method == "GET" and request.url.path.endswith("/git/commits/base-sha"):
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if request.method == "GET":
            return httpx.Response(200, json={"object": {"sha": "existing"}})
        return httpx.Response(500)

    client = make_client(handler)
    try:
        with pytest.raises(GitHubDeliveryError, match="already exists"):
            client.deliver(
                make_job(),
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[GitHubFileChange("src/client.py", "updated")],
                authorization=make_authorization(),
            )
    finally:
        client.close()


@pytest.mark.parametrize(
    "change",
    [
        GitHubFileChange("../secret", "x"),
        GitHubFileChange("/absolute", "x"),
        GitHubFileChange("src\\client.py", "x"),
        GitHubFileChange("src/client.py", "\x00"),
    ],
)
def test_delivery_rejects_unsafe_file_changes(change: GitHubFileChange) -> None:
    client = GitHubDeliveryClient("token")
    try:
        with pytest.raises(GitHubDeliveryError):
            client.deliver(
                make_job(),
                repository=REPOSITORY,
                base_branch="main",
                title="chore: remediate",
                body="body",
                changes=[change],
                authorization=make_authorization(),
            )
    finally:
        client.close()
