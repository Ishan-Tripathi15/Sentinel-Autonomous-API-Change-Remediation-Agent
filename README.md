# Sentinel

**Autonomous API-Change Remediation Agent**

Sentinel watches APIs and SDKs a codebase depends on, detects changes that matter to that codebase, and prepares a validated remediation workflow before a developer has to read a changelog.

This repository starts with the MVP described in the build brief: Stripe/OpenAPI change ingestion, deterministic change classification, TypeScript/JavaScript call-site matching, isolated remediation boundaries, verification, and dry-run delivery.

## MVP principles

- **Deterministic first:** OpenAPI diffing and static matching do not depend on an LLM.
- **Safe by default:** MVP delivery is dry-run only; no auto-merge.
- **Least privilege:** GitHub integration is designed around a GitHub App, not personal tokens.
- **Auditable:** jobs carry tenant, source, model/prompt versions, and verification metadata.
- **Extensible:** vendors implement a common ingestion interface so Stripe is not hard-coded into the engine.

## Local development

```bash
docker compose up --build
```

The local stack starts PostgreSQL, applies database migrations, and then starts the API.

API health: `http://localhost:8000/health`

Run tests locally:

```bash
python -m pip install -e '.[dev]'
pytest
```

For database-backed tests, set `SENTINEL_DATABASE_URL` to a reachable PostgreSQL database.

## Persistent audit storage

Production audit records are stored in PostgreSQL through `PostgresAuditSink`. The storage boundary remains behind the existing `AuditSink` protocol, so the remediation domain does not depend on PostgreSQL-specific types.

Migrations are packaged under `src/sentinel/migrations` and applied with:

```bash
SENTINEL_DATABASE_URL=postgresql://... python -m sentinel.migrate
```

The migration runner records applied migration filenames in `schema_migrations` and is safe to execute repeatedly.

## Architecture

```text
Vendor/OpenAPI source
        |
        v
 Ingestion + diffing ---> Change event store
        |                       |
        +-----------------------v
                        Matching engine
                             |
                        Blast radius
                             |
                    Remediation workflow
                     /       |        \
                 patch     verify     audit
                     \       |        /
                          Delivery
                       dry-run / PR

Audit boundary
      |
      +---- In-memory sink  -> tests/dev
      |
      +---- PostgreSQL sink -> production
```

See `docs/architecture.md` and `docs/mvp.md` for implementation boundaries.

## Security boundary

Customer repositories and generated patches must never be executed in the API process. The remediation runner is an explicit sandbox interface. The initial implementation provides a safe local adapter for development; production deployment must replace it with Firecracker/gVisor-class isolation before customer code execution is enabled.
