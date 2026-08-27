CREATE TABLE IF NOT EXISTS remediation_delivery_attempts (
    delivery_key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES remediation_jobs(job_id),
    organization_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'succeeded', 'failed')),
    provider TEXT NOT NULL,
    delivery_owner TEXT,
    lease_until TIMESTAMPTZ,
    pull_request_number INTEGER,
    pull_request_url TEXT,
    commit_sha TEXT,
    error_type TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (job_id, delivery_key)
);

CREATE INDEX IF NOT EXISTS idx_delivery_attempts_job
    ON remediation_delivery_attempts (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_delivery_attempts_status
    ON remediation_delivery_attempts (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_delivery_attempts_lease
    ON remediation_delivery_attempts (status, lease_until)
    WHERE status = 'in_progress';
