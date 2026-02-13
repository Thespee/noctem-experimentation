"""
Task service - CRUD operations for tasks.
"""
from typing import Optional
from datetime import date, time, datetime, timedelta
import json
from ..db import get_db
from ..models import Task
from .base import log_action


def create_task(
    name: str,
    project_id: Optional[int] = None,
    due_date: Optional[date] = None,
    due_time: Optional[time] = None,
    importance: Optional[float] = None,
    tags: Optional[list[str]] = None,
    recurrence_rule: Optional[str] = None,
) -> Task:
    """Create a new task."""
    # Default importance to 0.5 (medium) if not specified
    if importance is None:
        importance = 0.5
    
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (name, project_id, due_date, due_time, importance, tags, recurrence_rule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                project_id,
                due_date,
                due_time,
                importance,
                json.dumps(tags) if tags else None,
                recurrence_rule,
            ),
        )
        task_id = cursor.lastrowid

    log_action(
        "task_created",
        "task",
        task_id,
        {"name": name, "due_date": str(due_date) if due_date else None, "importance": importance},
    )
    return get_task(task_id)


def get_task(task_id: int) -> Optional[Task]:
    """Get a task by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return Task.from_row(row)


def get_task_by_name(name: str) -> Optional[Task]:
    """Get a task by name (case-insensitive partial match, prefer uncompleted)."""
    with get_db() as conn:
        # First try to find an uncompleted task
        row = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE LOWER(name) LIKE LOWER(?) AND status NOT IN ('done', 'canceled')
            ORDER BY created_at DESC LIMIT 1
            """,
            (f"%{name}%",),
        ).fetchone()
        if row:
            return Task.from_row(row)
        
        # Fall back to any task
        row = conn.execute(
            "SELECT * FROM tasks WHERE LOWER(name) LIKE LOWER(?) ORDER BY created_at DESC LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        return Task.from_row(row)


def get_tasks_due_on(target_date: date) -> list[Task]:
    """Get all tasks due on a specific date."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE due_date = ? AND status NOT IN ('done', 'canceled')
            ORDER BY importance DESC NULLS LAST, due_time ASC NULLS LAST
            """,
            (target_date,),
        ).fetchall()
        return [Task.from_row(row) for row in rows]


def get_tasks_due_today() -> list[Task]:
    """Get all tasks due today."""
    return get_tasks_due_on(date.today())


def get_tasks_due_this_week() -> list[Task]:
    """Get all tasks due this week (including today)."""
    today = date.today()
    week_end = today + timedelta(days=7)
    
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE due_date >= ? AND due_date < ? AND status NOT IN ('done', 'canceled')
            ORDER BY due_date ASC, importance DESC NULLS LAST, due_time ASC NULLS LAST
            """,
            (today, week_end),
        ).fetchall()
        return [Task.from_row(row) for row in rows]


def get_overdue_tasks() -> list[Task]:
    """Get all overdue tasks."""
    today = date.today()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE due_date < ? AND status NOT IN ('done', 'canceled')
            ORDER BY due_date ASC, importance DESC NULLS LAST
            """,
            (today,),
        ).fetchall()
        return [Task.from_row(row) for row in rows]


def get_priority_tasks(max_count: int = 5) -> list[Task]:
    """Get top priority tasks sorted by calculated priority_score."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE status NOT IN ('done', 'canceled')
            """,
        ).fetchall()
        tasks = [Task.from_row(row) for row in rows]
    
    # Sort by priority_score (calculated property) descending
    tasks.sort(key=lambda t: t.priority_score, reverse=True)
    return tasks[:max_count]


def get_inbox_tasks() -> list[Task]:
    """Get tasks with no project (inbox/someday)."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE project_id IS NULL AND status NOT IN ('done', 'canceled')
            ORDER BY importance DESC NULLS LAST, created_at DESC
            """
        ).fetchall()
        return [Task.from_row(row) for row in rows]


def get_project_tasks(project_id: int) -> list[Task]:
    """Get all tasks for a project."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks 
            WHERE project_id = ?
            ORDER BY status ASC, importance DESC NULLS LAST, due_date ASC NULLS LAST
            """,
            (project_id,),
        ).fetchall()
        return [Task.from_row(row) for row in rows]


def get_all_tasks(include_done: bool = False) -> list[Task]:
    """Get all tasks."""
    query = "SELECT * FROM tasks"
    if not include_done:
        query += " WHERE status NOT IN ('done', 'canceled')"
    query += " ORDER BY due_date ASC NULLS LAST, importance DESC NULLS LAST"

    with get_db() as conn:
        rows = conn.execute(query).fetchall()
        return [Task.from_row(row) for row in rows]


def update_task(
    task_id: int,
    name: Optional[str] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    due_date: Optional[date] = None,
    due_time: Optional[time] = None,
    importance: Optional[float] = None,
    tags: Optional[list[str]] = None,
    recurrence_rule: Optional[str] = None,
) -> Optional[Task]:
    """Update a task."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if project_id is not None:
        updates.append("project_id = ?")
        params.append(project_id)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        if status == "done":
            updates.append("completed_at = ?")
            params.append(datetime.now())
    if due_date is not None:
        updates.append("due_date = ?")
        params.append(due_date)
    if due_time is not None:
        updates.append("due_time = ?")
        params.append(due_time)
    if importance is not None:
        updates.append("importance = ?")
        params.append(importance)
    if tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(tags))
    if recurrence_rule is not None:
        updates.append("recurrence_rule = ?")
        params.append(recurrence_rule)

    if not updates:
        return get_task(task_id)

    params.append(task_id)
    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"

    with get_db() as conn:
        conn.execute(query, params)

    log_action("task_updated", "task", task_id, {"updates": updates})
    return get_task(task_id)


def complete_task(task_id: int) -> Optional[Task]:
    """Mark a task as done. Handles recurrence if needed."""
    task = get_task(task_id)
    if not task:
        return None

    # Mark current task as done
    updated = update_task(task_id, status="done")
    log_action("task_completed", "task", task_id, {"name": task.name})

    # If recurring, create next instance
    if task.recurrence_rule and task.due_date:
        next_date = _calculate_next_occurrence(task.due_date, task.recurrence_rule)
        if next_date:
            create_task(
                name=task.name,
                project_id=task.project_id,
                due_date=next_date,
                due_time=task.due_time,
                importance=task.importance,
                tags=task.tags,
                recurrence_rule=task.recurrence_rule,
            )

    return updated


def _calculate_next_occurrence(current_date: date, rule: str) -> Optional[date]:
    """Calculate the next occurrence based on recurrence rule."""
    # Simple implementation - can be expanded
    if "FREQ=DAILY" in rule:
        interval = 1
        if "INTERVAL=" in rule:
            for part in rule.split(";"):
                if part.startswith("INTERVAL="):
                    interval = int(part.split("=")[1])
        return current_date + timedelta(days=interval)
    
    elif "FREQ=WEEKLY" in rule:
        return current_date + timedelta(weeks=1)
    
    elif "FREQ=MONTHLY" in rule:
        # Simple: add ~30 days, adjust to same day of month
        next_month = current_date.month + 1
        next_year = current_date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        try:
            return date(next_year, next_month, current_date.day)
        except ValueError:
            # Handle end-of-month edge cases
            return date(next_year, next_month + 1, 1) - timedelta(days=1)
    
    return None


def skip_task(task_id: int) -> Optional[Task]:
    """Defer a task to tomorrow."""
    tomorrow = date.today() + timedelta(days=1)
    log_action("task_skipped", "task", task_id, {"new_date": str(tomorrow)})
    return update_task(task_id, due_date=tomorrow)


def delete_task(task_id: int) -> bool:
    """Delete a task. Returns True if deleted."""
    task = get_task(task_id)
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted = cursor.rowcount > 0

    if deleted and task:
        log_action("task_deleted", "task", task_id, {"name": task.name})
    return deleted
