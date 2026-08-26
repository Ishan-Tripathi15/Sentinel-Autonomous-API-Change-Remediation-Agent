from __future__ import annotations

from os import environ
from threading import Lock

from .job_queue import PostgresJobQueue

_lock = Lock()
_queue: PostgresJobQueue | None = None


def get_job_queue() -> PostgresJobQueue:
    """Return the process queue configured by SENTINEL_DATABASE_URL."""
    global _queue
    with _lock:
        if _queue is None:
            database_url = environ.get("SENTINEL_DATABASE_URL", "")
            if not database_url:
                raise RuntimeError("SENTINEL_DATABASE_URL is required for persistent job queue")
            _queue = PostgresJobQueue(database_url)
        return _queue


def reset_job_queue() -> None:
    """Close and reset the singleton for tests or worker lifecycle shutdown."""
    global _queue
    with _lock:
        current = _queue
        _queue = None
        if current is not None:
            current.close()
