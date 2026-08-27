# Worker observability

Worker runtime health and metrics are process-local and dependency-injected. Use `runtime.metrics.snapshot()` for counters and `runtime.health.snapshot()` for readiness state. Readiness becomes active only after runtime startup and accepting work is disabled during shutdown.
