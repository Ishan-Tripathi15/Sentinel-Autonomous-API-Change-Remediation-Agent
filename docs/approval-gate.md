# Remediation approval gate

Jobs classified as `awaiting-approval` require an explicit human approval before they return to the remediation queue.

`approve_remediation()` validates the approver and timestamp, creates an immutable approval record, and releases the job to `queued`.

Approval is **not** a repository-write permission. Repository writes remain independently gated by the existing verified-job, dry-run, and explicit `allow_write` checks in the delivery layer.

The approval record includes the job, organization, installation, approver, and timezone-aware timestamp so callers can persist it alongside the append-only remediation audit trail.
