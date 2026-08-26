# Audit lifecycle

Sentinel records two complementary audit layers:

1. `remediation_audit` stores bounded snapshots of a remediation job.
2. `remediation_audit_events` stores an append-only chronological lifecycle trail.

A job creation writes both a `job_created` event and its initial snapshot. Workers can append subsequent events through the lifecycle audit boundary without mutating historical records.

Lifecycle events contain tenant/install/job/change identities, an event type, optional status transition, and bounded metadata. Secrets, tokens, credentials, and arbitrary customer source are outside this boundary.
