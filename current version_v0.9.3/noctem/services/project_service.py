"""
Project service - CRUD operations for projects.
"""
from typing import Optional
from datetime import date
from ..db import get_db
from ..models import Project
from .base import log_action


def create_project(
    name: str,
    goal_id: Optional[int] = None,
    summary: Optional[str] = None,
    status: str = "in_progress",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Project:
    """Create a new project."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (name, goal_id, status, summary, start_date, end_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, goal_id, status, summary, start_date, end_date),
        )
        project_id = cursor.lastrowid

    log_action("project_created", "project", project_id, {"name": name, "goal_id": goal_id})
    return get_project(project_id)


def get_project(project_id: int) -> Optional[Project]:
    """Get a project by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return Project.from_row(row)


def get_project_by_name(name: str) -> Optional[Project]:
    """Get a project by name (case-insensitive partial match)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE LOWER(name) LIKE LOWER(?) ORDER BY created_at DESC LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        return Project.from_row(row)


def get_all_projects(
    status: Optional[str] = None,
    goal_id: Optional[int] = None,
) -> list[Project]:
    """Get all projects with optional filtering."""
    query = "SELECT * FROM projects WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if goal_id:
        query += " AND goal_id = ?"
        params.append(goal_id)

    query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [Project.from_row(row) for row in rows]


def get_active_projects() -> list[Project]:
    """Get all in-progress projects."""
    return get_all_projects(status="in_progress")


def update_project(
    project_id: int,
    name: Optional[str] = None,
    goal_id: Optional[int] = None,
    status: Optional[str] = None,
    summary: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Optional[Project]:
    """Update a project."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if goal_id is not None:
        updates.append("goal_id = ?")
        params.append(goal_id)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if summary is not None:
        updates.append("summary = ?")
        params.append(summary)
    if start_date is not None:
        updates.append("start_date = ?")
        params.append(start_date)
    if end_date is not None:
        updates.append("end_date = ?")
        params.append(end_date)

    if not updates:
        return get_project(project_id)

    params.append(project_id)
    query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"

    with get_db() as conn:
        conn.execute(query, params)

    log_action("project_updated", "project", project_id, {"updates": updates})
    return get_project(project_id)


def complete_project(project_id: int) -> Optional[Project]:
    """Mark a project as done."""
    return update_project(project_id, status="done")


def delete_project(project_id: int) -> bool:
    """Delete a project. Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        deleted = cursor.rowcount > 0

    if deleted:
        log_action("project_deleted", "project", project_id)
    return deleted


def get_projects_with_suggestions(limit: int = 3) -> list[Project]:
    """Get projects that have AI suggestions (v0.6.0)."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM projects 
            WHERE next_action_suggestion IS NOT NULL 
            AND status = 'in_progress'
            ORDER BY suggestion_generated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [Project.from_row(row) for row in rows]
