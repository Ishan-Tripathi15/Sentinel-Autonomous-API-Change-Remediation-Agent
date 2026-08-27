CREATE TABLE IF NOT EXISTS remediation_write_authorizations (
    authorization_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES remediation_jobs(job_id),
    organization_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    authorized_by TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    authorized_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (job_id, repository, base_branch)
);

CREATE INDEX IF NOT EXISTS idx_write_authorizations_active
    ON remediation_write_authorizations (job_id, repository, base_branch, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_write_authorizations_tenant
    ON remediation_write_authorizations (organization_id, installation_id, created_at DESC);
