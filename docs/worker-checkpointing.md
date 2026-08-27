# Durable worker checkpoints

The remediation worker persists each successfully completed workflow stage in the PostgreSQL job payload while the worker lease is active.

## Recovery behavior

A worker crash after a checkpoint leaves the job leased until the lease expires. A later worker can reclaim the row and resume from the persisted workflow status instead of restarting already-completed stages.

The persisted stages are:

- `ready-for-remediation`
- `patch-generated`
- `verification-pending`
- `verified`
- `dry-run-complete`

A checkpoint is accepted only from the worker that owns the active lease, while the lease is still valid, and only when the payload identity matches the durable job ID.

## Safety

Checkpointing does not skip workflow transitions or authorization gates. Approval remains required where the job was created in `awaiting-approval`, verification remains mandatory before `verified`, and repository-write authorization remains outside the worker checkpoint mechanism.

The queue's authoritative `status` column remains `running` during processing; the JSON payload records the last successfully completed workflow stage. This separation lets lease recovery identify an abandoned worker while preserving its last safe progress point.
