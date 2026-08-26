from __future__ import annotations

from importlib.resources import files
from os import environ

import psycopg

_MIGRATIONS_PACKAGE = "sentinel.migrations"


def migrate(database_url: str) -> None:
    """Apply packaged SQL migrations exactly once in filename order."""
    if not database_url.strip():
        raise ValueError("database URL is required")

    migration_files = sorted(
        resource
        for resource in files(_MIGRATIONS_PACKAGE).iterdir()
        if resource.name.endswith(".sql")
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for migration in migration_files:
            version = migration.name
            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if applied:
                continue
            connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )


def main() -> None:
    """CLI entry point for database migration."""
    database_url = environ.get("SENTINEL_DATABASE_URL", "")
    migrate(database_url)


if __name__ == "__main__":
    main()
