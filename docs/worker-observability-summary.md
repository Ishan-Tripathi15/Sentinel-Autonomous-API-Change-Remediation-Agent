# Worker observability

The runtime owns thread-safe metrics and lifecycle health state. Metrics distinguish job failures from runtime infrastructure failures. Health distinguishes process readiness from accepting new work and transitions to not accepting work during shutdown.
