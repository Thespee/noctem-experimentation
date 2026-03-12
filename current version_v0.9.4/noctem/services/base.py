"""Base service utilities including lightweight action logging."""
from __future__ import annotations

import logging
from datetime import datetime
from itertools import count
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

_ACTION_LOG_LOCK = Lock()
_ACTION_LOG_COUNTER = count(start=1)
_ACTION_LOG_BUFFER: list[dict] = []
_ACTION_LOG_BUFFER_MAX = 500


def log_action(
    action_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> int:
    """Log an action in process memory and structured runtime logs."""
    event = {
        "id": next(_ACTION_LOG_COUNTER),
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "created_at": datetime.utcnow().isoformat(),
    }
    with _ACTION_LOG_LOCK:
        _ACTION_LOG_BUFFER.append(event)
        if len(_ACTION_LOG_BUFFER) > _ACTION_LOG_BUFFER_MAX:
            del _ACTION_LOG_BUFFER[: len(_ACTION_LOG_BUFFER) - _ACTION_LOG_BUFFER_MAX]
    logger.info(
        "action_event type=%s entity=%s entity_id=%s details=%s",
        action_type,
        entity_type,
        entity_id,
        event["details"],
    )
    return int(event["id"])


def get_action_logs(
    action_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve recent in-memory action logs with optional filtering."""
    with _ACTION_LOG_LOCK:
        rows = list(_ACTION_LOG_BUFFER)
    if action_type:
        rows = [row for row in rows if row.get("action_type") == action_type]
    if entity_type:
        rows = [row for row in rows if row.get("entity_type") == entity_type]
    if entity_id is not None:
        rows = [row for row in rows if row.get("entity_id") == entity_id]
    rows = list(reversed(rows))
    return rows[: max(0, int(limit))]
