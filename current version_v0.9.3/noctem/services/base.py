"""
Base service utilities including action logging.
"""
import json
from typing import Any, Optional
from ..db import get_db


def log_action(
    action_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> int:
    """
    Log an action to the action_log table.
    Returns the log entry ID.
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO action_log (action_type, entity_type, entity_id, details)
            VALUES (?, ?, ?, ?)
            """,
            (
                action_type,
                entity_type,
                entity_id,
                json.dumps(details) if details else None,
            ),
        )
        return cursor.lastrowid


def get_action_logs(
    action_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve action logs with optional filtering."""
    query = "SELECT * FROM action_log WHERE 1=1"
    params = []

    if action_type:
        query += " AND action_type = ?"
        params.append(action_type)
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
