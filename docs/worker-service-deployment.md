# Worker service deployment boundary

The worker runtime is ready to be hosted as a separate long-lived process, but dependency construction remains explicit. A deployment must provide a configured `RemediationWorker` to `run_worker(factory)`.

The module entrypoint intentionally fails closed when no dependency factory is supplied. This prevents a container from appearing healthy while silently running without a queue, audit sink, or credentials.

Runtime controls are supplied through the `SENTINEL_WORKER_*` environment variables described in `docs/worker-runtime.md`.
