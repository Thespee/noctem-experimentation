"""Interrupt management for v0.9.3 agent workflows."""
import json
from typing import Any

from ..db import get_db
from .models import AgentInterrupt


def create_interrupt(
    workflow_id: int,
    interrupt_type: str,
    question: str,
    options: Any = None,
    context: Any = None,
) -> int:
    """Create a pending interrupt and return its ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_interrupts (workflow_id, interrupt_type, question, options, context)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                interrupt_type,
                question,
                json.dumps(options, ensure_ascii=False) if options is not None else None,
                json.dumps(context, ensure_ascii=False) if context is not None else None,
            ),
        )
        return cursor.lastrowid


def resolve_interrupt(interrupt_id: int, resolution: str) -> bool:
    """Resolve a pending interrupt."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE agent_interrupts
            SET resolution = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ? AND resolved_at IS NULL
            """,
            (resolution, interrupt_id),
        )
        return cursor.rowcount > 0


def get_pending_interrupts(workflow_id: int | None = None) -> list[dict]:
    """Get unresolved interrupts (optionally for a single workflow)."""
    query = """
        SELECT * FROM agent_interrupts
        WHERE resolved_at IS NULL
    """
    params: list[Any] = []
    if workflow_id is not None:
        query += " AND workflow_id = ?"
        params.append(workflow_id)
    query += " ORDER BY created_at ASC, id ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [AgentInterrupt.from_row(row).to_dict() for row in rows]
