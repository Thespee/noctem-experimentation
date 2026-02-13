"""
Goal service - CRUD operations for goals.
"""
from typing import Optional
from ..db import get_db
from ..models import Goal
from .base import log_action


def create_goal(
    name: str,
    goal_type: str = "bigger_goal",
    description: Optional[str] = None,
) -> Goal:
    """Create a new goal."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO goals (name, type, description)
            VALUES (?, ?, ?)
            """,
            (name, goal_type, description),
        )
        goal_id = cursor.lastrowid

    log_action("goal_created", "goal", goal_id, {"name": name, "type": goal_type})
    return get_goal(goal_id)


def get_goal(goal_id: int) -> Optional[Goal]:
    """Get a goal by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        return Goal.from_row(row)


def get_all_goals(include_archived: bool = False) -> list[Goal]:
    """Get all goals."""
    query = "SELECT * FROM goals"
    if not include_archived:
        query += " WHERE archived = 0"
    query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query).fetchall()
        return [Goal.from_row(row) for row in rows]


def update_goal(
    goal_id: int,
    name: Optional[str] = None,
    goal_type: Optional[str] = None,
    description: Optional[str] = None,
    archived: Optional[bool] = None,
) -> Optional[Goal]:
    """Update a goal."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if goal_type is not None:
        updates.append("type = ?")
        params.append(goal_type)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if archived is not None:
        updates.append("archived = ?")
        params.append(int(archived))

    if not updates:
        return get_goal(goal_id)

    params.append(goal_id)
    query = f"UPDATE goals SET {', '.join(updates)} WHERE id = ?"

    with get_db() as conn:
        conn.execute(query, params)

    log_action("goal_updated", "goal", goal_id, {"updates": updates})
    return get_goal(goal_id)


def archive_goal(goal_id: int) -> Optional[Goal]:
    """Archive a goal."""
    return update_goal(goal_id, archived=True)


def delete_goal(goal_id: int) -> bool:
    """Delete a goal. Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        deleted = cursor.rowcount > 0

    if deleted:
        log_action("goal_deleted", "goal", goal_id)
    return deleted
