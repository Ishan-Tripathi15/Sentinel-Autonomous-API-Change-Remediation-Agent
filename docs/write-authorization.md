# Repository-write authorization

Repository writes are fail-closed behind a typed `RepositoryWriteAuthorization` record.

## Invariants

1. An authorization is bound to one remediation job, organization, installation, repository, and base branch.
2. Authorizations have a policy version, authorizer identity, activation timestamp, and bounded expiry.
3. Missing, expired, revoked, or mismatched authorization denies repository writes.
4. Authorization activation is the only boundary that can turn a dry-run remediation job into a write-enabled job.
5. Human approval is independent: approval makes a held job eligible for workflow execution but does not grant repository-write authority.
6. GitHub delivery still requires a verified, non-dry-run job and continues through durable idempotency and reconciliation.

The durable store uses `remediation_write_authorizations` and defaults to no authorization when no active record exists.
