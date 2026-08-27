# Worker deployment contract

The worker runtime is intentionally not self-configuring. Production deployment must construct `RemediationWorker` with its queue, audit sink, and stage handlers, then call `run_worker(factory)`.

This prevents a process from starting without durable dependencies and keeps credentials out of module-level globals.

Use the `SENTINEL_WORKER_*` environment variables to tune lease, polling, and bounded error backoff behavior.
