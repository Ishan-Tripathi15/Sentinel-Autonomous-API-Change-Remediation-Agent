CREATE TABLE IF NOT EXISTS remediation_audit_events (
    audit_event_id TEXT PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL,
    organization_id TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    change_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_remediation_audit_events_job_time
    ON remediation_audit_events (job_id, recorded_at ASC, audit_event_id ASC);

CREATE INDEX IF NOT EXISTS idx_remediation_audit_events_org_time
    ON remediation_audit_events (organization_id, installation_id, recorded_at DESC);
