# Worker lease heartbeat

The remediation worker renews its PostgreSQL lease in the background while each long-running workflow stage executes.

## Contract

- The heartbeat runs only while a stage handler is active.
- Renewal uses the same worker identity and job ID as the original claim.
- The renewal cadence is bounded to a fraction of the configured lease duration.
- Heartbeat activity changes lease metadata only; it does not change workflow state or the durable stage payload.
- If renewal fails, the failure is surfaced at the stage boundary and the existing safe worker failure/requeue path takes over.

## Ownership safety

The PostgreSQL queue remains authoritative. Renewal succeeds only for a running job whose lease is still valid and whose `worker_id` matches the renewing worker. An expired lease cannot be revived by the stale worker.

This means the heartbeat extends an active owner but never creates ownership. A worker that loses ownership cannot checkpoint or complete the job after another worker becomes eligible to reclaim it.

## Runtime behavior

The heartbeat is intentionally scoped around individual remediation stages rather than the process runtime. This keeps ownership semantics close to the stage that needs the lease and avoids changing the long-lived worker supervisor's lifecycle responsibilities.
