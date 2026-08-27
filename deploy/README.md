# Worker container

`worker.Dockerfile` packages the long-lived remediation worker separately from the HTTP API.

The image expects deployment code to provide a configured worker factory to `sentinel.worker_service.run_worker`. The default module entrypoint intentionally fails closed until dependencies are wired by the deployment layer.

Runtime configuration is supplied through the `SENTINEL_WORKER_*` environment variables documented in `docs/worker-runtime.md`.
