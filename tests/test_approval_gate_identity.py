from datetime import UTC, datetime

import pytest

from sentinel.approval_gate import ApprovalError, RemediationApproval


def test_approval_record_requires_identity() -> None:
    timestamp = datetime(2026, 8, 27, tzinfo=UTC)
    with pytest.raises(ApprovalError, match="job_id"):
        RemediationApproval(" ", "org-1", "install-1", "operator-1", timestamp)
    with pytest.raises(ApprovalError, match="organization_id"):
        RemediationApproval("job-1", " ", "install-1", "operator-1", timestamp)
    with pytest.raises(ApprovalError, match="installation_id"):
        RemediationApproval("job-1", "org-1", " ", "operator-1", timestamp)
