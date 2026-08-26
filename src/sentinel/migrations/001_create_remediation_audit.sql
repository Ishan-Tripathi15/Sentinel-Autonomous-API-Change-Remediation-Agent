CREATE TABLE IF NOT EXISTS remediation_audit (
    audit_id TEXT PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL,
    organization_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    change_event_id TEXT NOT NULL,
    source_vendor TEXT NOT NULL,
    source_url TEXT,
    source_version TEXT,
    change_type TEXT NOT NULL,
    change_severity TEXT NOT NULL,
    change_summary TEXT NOT NULL,
    status TEXT NOT NULL,
    model_version TEXT,
    prompt_version TEXT,
    patch_diff TEXT,
    verification JSONB NOT NULL DEFAULT '[]'::jsonb,
    delivery_outcome JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_remediation_audit_org_installation
    ON remediation_audit (organization_id, installation_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_remediation_audit_job
    ON remediation_audit (job_id);

CREATE INDEX IF NOT EXISTS idx_remediation_audit_change_event
    ON remediation_audit (change_event_id);
