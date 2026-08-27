# Worker observability integration

The runtime now owns `WorkerMetrics` and `WorkerHealth` instances. Deployment code can read `runtime.metrics.snapshot()` and `runtime.health.snapshot()` and expose those values through the application's preferred monitoring adapter.

Readiness is false before the runtime starts, true while it is accepting work, and false again during shutdown. Runtime infrastructure failures are counted separately from individual job failures.
