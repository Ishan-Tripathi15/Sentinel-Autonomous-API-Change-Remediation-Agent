# Worker health and metrics

The long-lived remediation worker exposes two process-local observability objects:

- `WorkerMetrics` tracks completed jobs, failed jobs, runtime errors, in-progress jobs, uptime, and last activity.
- `WorkerHealth` tracks readiness, whether the worker is accepting work, last activity, and runtime errors.

The runtime owns both objects and updates them at the worker lifecycle boundary. They are intentionally dependency-injected so a deployment can expose them through its metrics/health adapter without coupling the remediation state machine to a specific telemetry vendor.

## Readiness semantics

A worker starts **not ready**. Once the runtime begins processing, it becomes ready and accepts work. A requested shutdown immediately stops accepting work. The runtime also marks the worker as stopping when its loop exits.

This distinction lets a load balancer or orchestrator remove a worker from service before process termination.

## Metrics semantics

Counters are protected by a lock and can safely be read from another thread. Runtime-level errors are separate from individual job failures: a queue/database failure increments `runtime_errors`, while a successfully claimed job that reaches the worker's failure path increments `jobs_failed`.
