from __future__ import annotations

from os import environ
from threading import Lock

from .audit import AuditSink, InMemoryAuditSink
from .audit_storage import PostgresAuditSink

_lock = Lock()
_sink: AuditSink | None = None


def get_audit_sink() -> AuditSink:
    """Return the process audit sink selected by runtime configuration.

    Production deployments use PostgreSQL when SENTINEL_DATABASE_URL is set.
    Local/test deployments without a database URL retain the deterministic
    in-memory sink.
    """
    global _sink
    with _lock:
        if _sink is None:
            database_url = environ.get("SENTINEL_DATABASE_URL", "")
            _sink = PostgresAuditSink(database_url) if database_url else InMemoryAuditSink()
        return _sink


def set_audit_sink(sink: AuditSink) -> None:
    """Override the runtime sink for tests or an explicitly managed worker."""
    global _sink
    with _lock:
        _sink = sink


def reset_audit_sink() -> None:
    """Drop the runtime singleton; the next access rebuilds it from the environment."""
    global _sink
    with _lock:
        current = _sink
        _sink = None
        if isinstance(current, PostgresAuditSink):
            current.close()
