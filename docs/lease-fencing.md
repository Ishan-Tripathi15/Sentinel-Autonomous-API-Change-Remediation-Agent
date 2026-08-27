# Durable lease fencing

The PostgreSQL queue is the authoritative ownership boundary for remediation jobs.

A worker may checkpoint or complete a job only while it still owns a valid lease. The ownership predicate includes the job ID, worker ID, `running` status, and an unexpired `lease_until` timestamp.

## Required invariant

**No valid lease → no checkpoint → no completion.**

The heartbeat is a liveness mechanism. It reduces avoidable lease expiry during long-running stages, but it does not create ownership. The database remains authoritative.

## Stale-worker recovery

If a worker's lease expires, another worker can reclaim the job. The original worker's later checkpoint or completion operation must be rejected by the database ownership predicate.
