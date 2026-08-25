import hashlib
import hmac
import json

import pytest
from sentinel.github_app import (
    WebhookVerificationError,
    parse_installation_event,
    verify_webhook_signature,
)


PAYLOAD = json.dumps(
    {
        "action": "created",
        "installation": {"id": 123},
        "repositories": [
            {"id": 456, "full_name": "acme/payments", "default_branch": "main"},
        ],
    }
).encode()


def test_valid_github_signature_is_accepted() -> None:
    secret = "test-secret"
    digest = hmac.new(secret.encode(), PAYLOAD, hashlib.sha256).hexdigest()
    verify_webhook_signature(PAYLOAD, f"sha256={digest}", secret)


def test_invalid_github_signature_is_rejected() -> None:
    with pytest.raises(WebhookVerificationError, match="invalid webhook signature"):
        verify_webhook_signature(PAYLOAD, "sha256=invalid", "test-secret")


def test_installation_event_is_normalized() -> None:
    installation_id, action, repositories = parse_installation_event(PAYLOAD)
    assert installation_id == 123
    assert action == "created"
    assert repositories[0].full_name == "acme/payments"
    assert repositories[0].default_branch == "main"
