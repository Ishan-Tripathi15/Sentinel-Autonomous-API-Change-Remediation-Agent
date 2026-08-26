from __future__ import annotations

import json
from datetime import datetime
from os import environ
from typing import Any

from psycopg import Error, OperationalError
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from sentinel.audit import AuditError, AuditSink, RemediationAuditEvent, RemediationAuditRecord

_INSERT_SQL = """
INSERT INTO remediation_audit (
    audit_id, recorded_at, organization_id, installation_id, job_id, change_event_id,
    source_vendor, source_url, source_version, change_type, change_severity,
    change_summary, status, model_version, prompt_version, patch_diff,
    verification, delivery_outcome
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
)
"""

_INSERT_EVENT_SQL = """
INSERT INTO remediation_audit_events (
    audit_event_id, recorded_at, organization_id, installation_id, job_id,
    change_event_id, event_type, from_status, to_status, metadata
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
"""

_SELECT_COLUMNS = """
    audit_id, recorded_at, organization_id, installation_id, job_id, change_event_id,
    source_vendor, source_url, source_version, change_type, change_severity,
    change_summary, status, model_version, prompt_version, patch_diff,
    verification, delivery_outcome
"""


class PostgresAuditSink(AuditSink):
    """Durable PostgreSQL audit sink with bounded connection pooling."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        if not database_url.strip():
            raise AuditError("database URL is required")
        if min_size < 1 or max_size < min_size:
            raise AuditError("invalid database pool size")
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": tuple_row},
            open=True,
        )

    @classmethod
    def from_env(cls) -> PostgresAuditSink:
        """Build a production sink from SENTINEL_DATABASE_URL."""
        database_url = environ.get("SENTINEL_DATABASE_URL", "")
        if not database_url:
            raise AuditError("SENTINEL_DATABASE_URL is required")
        return cls(database_url)

    def append(self, record: RemediationAuditRecord) -> None:
        """Persist an immutable audit record or fail closed."""
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    _INSERT_SQL,
                    (
                        record.audit_id, _parse_recorded_at(record.recorded_at),
                        record.organization_id, record.installation_id, record.job_id,
                        record.change_event_id, record.source_vendor, record.source_url,
                        record.source_version, record.change_type, record.change_severity,
                        record.change_summary, record.status, record.model_version,
                        record.prompt_version, record.patch_diff,
                        json.dumps([dict(item) for item in record.verification]),
                        json.dumps(dict(record.delivery_outcome)),
                    ),
                )
        except Error as exc:
            if _is_unique_violation(exc):
                raise AuditError("audit_id must be unique") from exc
            raise AuditError("audit persistence failed") from exc

    def append_event(self, event: RemediationAuditEvent) -> None:
        """Persist one append-only lifecycle event."""
        try:
            with self._pool.connection() as connection:
                connection.execute(
                    _INSERT_EVENT_SQL,
                    (
                        event.audit_event_id, _parse_recorded_at(event.recorded_at),
                        event.organization_id, event.installation_id, event.job_id,
                        event.change_event_id, event.event_type, event.from_status,
                        event.to_status, json.dumps(dict(event.metadata)),
                    ),
                )
        except Error as exc:
            if _is_unique_violation(exc):
                raise AuditError("audit_event_id must be unique") from exc
            raise AuditError("audit event persistence failed") from exc

    def list(
        self,
        *,
        organization_id: str | None = None,
        installation_id: str | None = None,
        job_id: str | None = None,
        limit: int = 100,
    ) -> tuple[RemediationAuditRecord, ...]:
        """Return recent audit records with optional identity filters."""
        if limit < 1 or limit > 1000:
            raise AuditError("audit query limit must be between 1 and 1000")

        conditions: list[str] = []
        parameters: list[Any] = []
        if organization_id is not None:
            conditions.append("organization_id = %s")
            parameters.append(organization_id)
        if installation_id is not None:
            conditions.append("installation_id = %s")
            parameters.append(installation_id)
        if job_id is not None:
            conditions.append("job_id = %s")
            parameters.append(job_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM remediation_audit
            {where}
            ORDER BY recorded_at DESC, audit_id DESC
            LIMIT %s
        """
        parameters.append(limit)

        try:
            with self._pool.connection() as connection:
                rows = connection.execute(query, parameters).fetchall()
        except OperationalError as exc:
            raise AuditError("audit storage is unavailable") from exc
        except Error as exc:
            raise AuditError("audit query failed") from exc

        return tuple(_record_from_row(row) for row in rows)

    def list_events(self, *, job_id: str | None = None, limit: int = 100) -> tuple[RemediationAuditEvent, ...]:
        """Return an append-only lifecycle timeline in chronological order."""
        if limit < 1 or limit > 1000:
            raise AuditError("audit event query limit must be between 1 and 1000")
        where = "WHERE job_id = %s" if job_id is not None else ""
        parameters: list[Any] = [job_id] if job_id is not None else []
        parameters.append(limit)
        query = f"""
            SELECT audit_event_id, recorded_at, organization_id, installation_id,
                   job_id, change_event_id, event_type, from_status, to_status, metadata
            FROM remediation_audit_events
            {where}
            ORDER BY recorded_at ASC, audit_event_id ASC
            LIMIT %s
        """
        try:
            with self._pool.connection() as connection:
                rows = connection.execute(query, parameters).fetchall()
        except OperationalError as exc:
            raise AuditError("audit storage is unavailable") from exc
        except Error as exc:
            raise AuditError("audit event query failed") from exc
        return tuple(_event_from_row(row) for row in rows)

    def close(self) -> None:
        self._pool.close()


def _parse_recorded_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuditError("recorded_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AuditError("recorded_at must include a timezone")
    return parsed


def _is_unique_violation(exc: Error) -> bool:
    return getattr(exc, "sqlstate", None) == "23505"


def _record_from_row(row: tuple[Any, ...]) -> RemediationAuditRecord:
    return RemediationAuditRecord(
        audit_id=row[0], recorded_at=row[1].isoformat(), organization_id=row[2],
        installation_id=row[3], job_id=row[4], change_event_id=row[5], source_vendor=row[6],
        source_url=row[7], source_version=row[8], change_type=row[9], change_severity=row[10],
        change_summary=row[11], status=row[12], model_version=row[13], prompt_version=row[14],
        patch_diff=row[15], verification=tuple(row[16]), delivery_outcome=dict(row[17]),
    )


def _event_from_row(row: tuple[Any, ...]) -> RemediationAuditEvent:
    return RemediationAuditEvent(
        audit_event_id=row[0], recorded_at=row[1].isoformat(), organization_id=row[2],
        installation_id=row[3], job_id=row[4], change_event_id=row[5], event_type=row[6],
        from_status=row[7], to_status=row[8], metadata=dict(row[9]),
    )
