"""Audit logging for agent workflow actions."""
import json
from typing import Any

from ..db import get_db
from .models import AgentAction


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def log_agent_action(
    workflow_id: int,
    action_type: str,
    input_data: Any = None,
    output_data: Any = None,
    decision_reasoning: str | None = None,
) -> int:
    """Persist a workflow action record."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_actions (workflow_id, action_type, input_data, output_data, decision_reasoning)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                action_type,
                _json(input_data),
                _json(output_data),
                decision_reasoning,
            ),
        )
        return cursor.lastrowid


def get_agent_actions(workflow_id: int, limit: int = 200) -> list[dict]:
    """Return workflow actions ordered by creation time."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM agent_actions
            WHERE workflow_id = ?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (workflow_id, limit),
        ).fetchall()
    return [AgentAction.from_row(row).to_dict() for row in rows]
