# Worker observability contract

The remediation worker runtime exposes process-local health and metrics through dependency-injected objects.

- `WorkerMetrics`: completed, failed, runtime-error, in-progress, uptime, and last-activity data.
- `WorkerHealth`: readiness and accepting-work state, plus runtime-error and last-activity data.

A worker is not ready before startup, becomes ready immediately before polling, and stops accepting work during shutdown. This contract is designed to be adapted by deployment-specific health and telemetry integrations.
