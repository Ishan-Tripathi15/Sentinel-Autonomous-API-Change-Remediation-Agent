# Worker deployment contract

The worker runtime is intentionally separate from dependency construction. A production process should construct a configured `RemediationWorker` and pass it to `run_worker(factory)`.

The module-level CLI entrypoint fails closed when dependencies are absent. This is deliberate: starting a worker without a durable queue, audit sink, or required credentials must not look healthy.

Configure lease, polling, and bounded error backoff through the `SENTINEL_WORKER_*` environment variables documented in `docs/worker-runtime.md`.
