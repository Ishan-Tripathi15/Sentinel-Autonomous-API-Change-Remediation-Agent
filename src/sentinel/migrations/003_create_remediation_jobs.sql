CREATE TABLE IF NOT EXISTS remediation_jobs (
    job_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    change_event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    worker_id TEXT,
    lease_until TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_remediation_jobs_claimable
    ON remediation_jobs (available_at, created_at, job_id)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_remediation_jobs_lease
    ON remediation_jobs (lease_until)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_remediation_jobs_tenant
    ON remediation_jobs (organization_id, installation_id, created_at DESC);
