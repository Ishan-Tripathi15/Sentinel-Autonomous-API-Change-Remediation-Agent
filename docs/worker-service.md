# Worker deployment

The worker runtime is separated from dependency construction. Deployments should provide a configured `RemediationWorker` to `run_worker(factory)` and keep credentials and database clients outside module-level state.

The service accepts bounded environment configuration for lease duration, polling, and runtime error backoff. Invalid values fail startup.

The runtime handles `SIGTERM` and `SIGINT` through an interruptible stop event for graceful container shutdown.
