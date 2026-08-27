from __future__ import annotations

from os import environ
from threading import Lock
from typing import Any

from psycopg_pool import ConnectionPool

from .delivery_idempotency import DeliveryAttemptStore

_lock = Lock()
_pool: ConnectionPool[Any] | None = None


def get_delivery_attempt_store() -> DeliveryAttemptStore:
    """Return the durable delivery-attempt store configured by the environment."""
    global _pool
    with _lock:
        if _pool is None:
            database_url = environ.get("SENTINEL_DATABASE_URL", "")
            if not database_url:
                raise RuntimeError("SENTINEL_DATABASE_URL is required for durable delivery")
            _pool = ConnectionPool(database_url, min_size=1, max_size=4, open=True)
        return DeliveryAttemptStore(_pool)


def reset_delivery_attempt_store() -> None:
    """Close and reset the delivery store singleton for tests or shutdown."""
    global _pool
    with _lock:
        current = _pool
        _pool = None
        if current is not None:
            current.close()
