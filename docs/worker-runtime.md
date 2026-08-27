# Worker service runtime

Sentinel's remediation worker can run as a long-lived process through `sentinel.worker_service`.

The runtime is intentionally separate from dependency construction: deployments call `run_worker(factory)` with a fully configured `RemediationWorker`. This keeps credentials, database connections, and GitHub clients out of module-level globals and makes startup testable.

## Environment

- `SENTINEL_WORKER_LEASE_SECONDS`: lease duration, 1–3600 seconds, default `300`.
- `SENTINEL_WORKER_POLL_INTERVAL_SECONDS`: idle queue polling interval, default `1.0` seconds.
- `SENTINEL_WORKER_ERROR_BACKOFF_SECONDS`: initial runtime error backoff, default `1.0` seconds.
- `SENTINEL_WORKER_MAX_ERROR_BACKOFF_SECONDS`: maximum runtime error backoff, default `30.0` seconds.

Invalid or non-positive values fail startup rather than silently accepting unsafe configuration. Runtime-level backoff is capped to prevent an unbounded sleep loop.

## Shutdown

The service handles `SIGTERM` and `SIGINT` by requesting a graceful stop. The runtime uses an interruptible event wait, so an idle worker does not need to wait for the full polling interval before exiting.

The worker state machine remains responsible for job ownership and lifecycle transitions. The service process only supervises the loop; it does not execute customer code or perform repository writes itself.
