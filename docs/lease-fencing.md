# Durable lease fencing

The PostgreSQL queue is the authoritative ownership boundary for remediation jobs.

A worker may checkpoint or complete a job only when all of these conditions hold at the database boundary:

- the job ID matches the operation;
- the worker ID still owns the lease;
- the job is still `running`; and
- the lease has not expired.

Lease renewal uses the same ownership predicate. An expired or stolen lease therefore cannot be revived by a stale worker.

## Required invariant

**No valid lease → no checkpoint → no completion.**

The worker heartbeat reduces avoidable lease expiry during long-running stages, while the queue predicates provide the actual fencing guarantee. This separation is intentional: the heartbeat is liveness support; the database is the authority.

## Recovery

If a worker loses its lease, its subsequent checkpoint/complete operation is rejected. A different worker can reclaim the expired job through `claim()`. The stale worker cannot make durable progress after ownership has changed.
