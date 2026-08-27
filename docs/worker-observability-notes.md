# Worker observability notes

Health and metrics remain separate from remediation state transitions. The runtime updates both at process boundaries, while deployment code remains responsible for adapting snapshots to the chosen telemetry or health-check system.
