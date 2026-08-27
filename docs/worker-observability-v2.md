# Worker observability contract

The worker runtime owns process-local health and metrics state.

- Metrics: completed jobs, failed jobs, runtime errors, in-progress jobs, uptime, and last activity.
- Health: readiness, accepting-work state, last activity, and runtime errors.

The runtime becomes ready before polling begins and stops accepting work during shutdown. Snapshots are safe to read concurrently and can be adapted by deployment-specific telemetry integrations.
