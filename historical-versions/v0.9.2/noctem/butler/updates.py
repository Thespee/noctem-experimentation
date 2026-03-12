"""
Butler Updates - Generate status update messages for Noctem v0.6.0.

Update messages summarize system state using templates (no LLM).
Sent on scheduled days (default: Mon/Wed/Fri at 9am).
"""
from datetime import date, timedelta
from typing import List, Optional
import logging

from ..db import get_db
from ..services import task_service, project_service

logger = logging.getLogger(__name__)


def get_overdue_tasks() -> List[dict]:
    """Get tasks that are overdue."""
    today = date.today()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, due_date, importance
            FROM tasks
            WHERE status NOT IN ('done', 'canceled')
              AND due_date < ?
            ORDER BY due_date ASC, importance DESC
        """, (today.isoformat(),)).fetchall()
        return [dict(row) for row in rows]


def get_tasks_due_today() -> List[dict]:
    """Get tasks due today."""
    today = date.today()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, due_time, importance
            FROM tasks
            WHERE status NOT IN ('done', 'canceled')
              AND due_date = ?
            ORDER BY due_time ASC NULLS LAST, importance DESC
        """, (today.isoformat(),)).fetchall()
        return [dict(row) for row in rows]


def get_tasks_due_this_week() -> List[dict]:
    """Get tasks due this week (excluding today)."""
    today = date.today()
    week_end = today + timedelta(days=(6 - today.weekday()))  # End of week (Sunday)
    
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, due_date, importance
            FROM tasks
            WHERE status NOT IN ('done', 'canceled')
              AND due_date > ?
              AND due_date <= ?
            ORDER BY due_date ASC, importance DESC
        """, (today.isoformat(), week_end.isoformat())).fetchall()
        return [dict(row) for row in rows]


def get_stale_projects(days_inactive: int = 7) -> List[dict]:
    """Get projects with no task activity in N days."""
    cutoff = date.today() - timedelta(days=days_inactive)
    
    with get_db() as conn:
        # Projects where no tasks were completed or created recently
        rows = conn.execute("""
            SELECT p.id, p.name, 
                   COUNT(t.id) as task_count,
                   MAX(t.completed_at) as last_activity
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE p.status = 'in_progress'
            GROUP BY p.id
            HAVING last_activity IS NULL 
               OR date(last_activity) < ?
               OR task_count = 0
            ORDER BY last_activity ASC NULLS FIRST
        """, (cutoff.isoformat(),)).fetchall()
        return [dict(row) for row in rows]


def get_unclear_tasks_count() -> int:
    """Count tasks tagged as unclear."""
    with get_db() as conn:
        # Tags are stored as JSON array string
        count = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE status NOT IN ('done', 'canceled')
              AND tags LIKE '%"unclear"%'
        """).fetchone()[0]
        return count


def generate_update_message() -> str:
    """
    Generate a template-based status update message.
    
    Includes:
    - Overdue tasks (urgent)
    - Tasks due today
    - Tasks due this week
    - Stale projects
    - Unclear items needing review
    
    No LLM required - pure data aggregation.
    """
    lines = []
    today = date.today()
    day_name = today.strftime("%A")
    
    lines.append(f"📋 **{day_name} Update**")
    lines.append("")
    
    # === OVERDUE (most important) ===
    overdue = get_overdue_tasks()
    if overdue:
        lines.append(f"🚨 **OVERDUE** ({len(overdue)} items)")
        for task in overdue[:5]:  # Show max 5
            days_late = (today - date.fromisoformat(task["due_date"])).days
            lines.append(f"  • {task['name']} ({days_late}d late)")
        if len(overdue) > 5:
            lines.append(f"  _...and {len(overdue) - 5} more_")
        lines.append("")
    
    # === TODAY ===
    due_today = get_tasks_due_today()
    if due_today:
        lines.append(f"📌 **Today** ({len(due_today)} tasks)")
        for task in due_today[:5]:
            time_str = f" at {task['due_time']}" if task.get("due_time") else ""
            lines.append(f"  • {task['name']}{time_str}")
        if len(due_today) > 5:
            lines.append(f"  _...and {len(due_today) - 5} more_")
        lines.append("")
    else:
        lines.append("📌 **Today**: No tasks due")
        lines.append("")
    
    # === THIS WEEK ===
    due_week = get_tasks_due_this_week()
    if due_week:
        lines.append(f"📅 **This Week** ({len(due_week)} tasks)")
        for task in due_week[:3]:  # Show max 3
            due = date.fromisoformat(task["due_date"])
            day = due.strftime("%a")
            lines.append(f"  • {task['name']} ({day})")
        if len(due_week) > 3:
            lines.append(f"  _...and {len(due_week) - 3} more_")
        lines.append("")
    
    # === STALE PROJECTS ===
    stale = get_stale_projects()
    if stale:
        lines.append(f"💤 **Stale Projects** ({len(stale)} need attention)")
        for proj in stale[:3]:
            lines.append(f"  • {proj['name']}")
        lines.append("")
    
    # === UNCLEAR ITEMS ===
    unclear_count = get_unclear_tasks_count()
    if unclear_count > 0:
        lines.append(f"❓ **{unclear_count} unclear items** awaiting review")
        lines.append("")
    
    # === FOOTER ===
    lines.append("_Reply anytime to add tasks or ask questions._")
    
    return "\n".join(lines)


def generate_brief_update() -> str:
    """Generate a shorter update for less busy days."""
    overdue = get_overdue_tasks()
    due_today = get_tasks_due_today()
    
    parts = []
    
    if overdue:
        parts.append(f"🚨 {len(overdue)} overdue")
    
    if due_today:
        parts.append(f"📌 {len(due_today)} due today")
    else:
        parts.append("📌 Nothing due today")
    
    return " • ".join(parts)
