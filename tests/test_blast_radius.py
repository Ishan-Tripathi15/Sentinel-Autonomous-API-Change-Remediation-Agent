from sentinel.blast_radius import build_blast_radius
from sentinel.models import ChangeEvent, ChangeSeverity, ChangeType


def _event() -> ChangeEvent:
    return ChangeEvent(
        vendor="stripe",
        version="2026-08-01",
        change_type=ChangeType.BREAKING,
        severity=ChangeSeverity.HIGH,
        summary="Payment endpoint changed",
        affected_endpoints=["/v1/payments"],
        affected_fields=["/paths//v1/payments/post/requestBody"],
        confidence=0.98,
        event_id="evt-123",
        detected_at="2026-08-25T00:00:00Z",
    )


def test_build_blast_radius_returns_deterministic_ranked_sites() -> None:
    files = {
        "src/payments.ts": 'import Stripe from "stripe";\nclient.post("/v1/payments", body);\n',
        "src/unrelated.ts": "export const value = 1;\n",
        "README.md": "/v1/payments is documented here\n",
    }

    report = build_blast_radius(change_event=_event(), repository="acme/payments", files=files)

    assert report.repository == "acme/payments"
    assert report.affected_files == ["src/payments.ts"]
    assert len(report.call_sites) == 1
    assert report.call_sites[0].endpoint == "/v1/payments"
    assert report.call_sites[0].line == 2
    assert report.call_sites[0].confidence >= 0.8


def test_blast_radius_never_executes_or_scans_unsupported_files() -> None:
    files = {
        "scripts/build.py": 'raise RuntimeError("must not execute")\n',
        "docs/example.md": 'client.post("/v1/payments")\n',
    }

    report = build_blast_radius(change_event=_event(), repository="acme/payments", files=files)

    assert report.call_sites == []
    assert report.affected_files == []
    assert report.confidence == 0.0
