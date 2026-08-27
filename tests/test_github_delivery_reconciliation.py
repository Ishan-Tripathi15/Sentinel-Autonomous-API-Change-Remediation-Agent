from __future__ import annotations

import httpx

from sentinel.github_delivery import GitHubDeliveryClient


def test_find_delivery_discovers_matching_open_pull_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/repos/acme/service/pulls"
        assert request.url.params["state"] == "open"
        assert request.url.params["base"] == "main"
        assert request.url.params["head"] == "acme:sentinel/remediation/job-123"
        return httpx.Response(
            200,
            json=[
                {
                    "number": 42,
                    "html_url": "https://github.com/acme/service/pull/42",
                    "head": {"ref": "sentinel/remediation/job-123", "sha": "commit-sha"},
                }
            ],
        )

    client = GitHubDeliveryClient("token")
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )
    try:
        result = client.find_delivery(
            repository="acme/service",
            branch_name="sentinel/remediation/job-123",
            base_branch="main",
        )
    finally:
        client.close()

    assert result is not None
    assert result.pull_request_number == 42
    assert result.pull_request_url.endswith("/42")
    assert result.branch_name == "sentinel/remediation/job-123"
    assert result.commit_sha == "commit-sha"


def test_find_delivery_returns_none_when_no_open_pull_request_matches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = GitHubDeliveryClient("token")
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )
    try:
        result = client.find_delivery(
            repository="acme/service",
            branch_name="sentinel/remediation/job-123",
            base_branch="main",
        )
    finally:
        client.close()

    assert result is None
