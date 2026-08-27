# Worker lease renewal

A claimed remediation job has a PostgreSQL lease that prevents another worker from reclaiming it while the owner is still making progress.

## Contract

`PostgresJobQueue.renew_lease()` extends the lease only when all of the following are true:

- the job ID is present;
- the worker ID is present;
- the requested lease is within the same bounded range as job claims;
- the job is still `running`;
- the durable `worker_id` matches the renewing worker; and
- the existing lease has not already expired.

Renewal changes only lease metadata. It does not alter the remediation workflow status or payload checkpoint.

## Recovery

An expired lease remains reclaimable by the normal `claim()` path. A worker that loses its lease cannot renew, checkpoint, or safely complete the job after another worker has become eligible to claim it.

The next worker-runtime integration step will call lease renewal during long-running stages. The renewal mechanism intentionally remains in the durable queue boundary so ownership checks stay authoritative and cannot be bypassed by the worker runtime.
