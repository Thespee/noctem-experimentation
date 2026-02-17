"""
Task Analyzer for Noctem v0.6.0 slow mode.

Analyzes tasks to suggest what a computer/automation could help with.
Uses prompt_service for editable/versioned prompts.
"""
import logging
from typing import Optional
from datetime import datetime

from ..db import get_db
from ..models import Task
from ..services import task_service
from ..services.prompt_service import render_prompt
from .ollama import OllamaClient, llm_generate

logger = logging.getLogger(__name__)


def analyze_task_for_computer_help(task: Task) -> Optional[str]:
    """
    Analyze a task to suggest what a computer could help with.
    
    Args:
        task: The task to analyze
        
    Returns:
        Suggestion string, or None if analysis failed
    """
    # Get project name if task has a project
    project_name = "No project"
    if task.project_id:
        from ..services import project_service
        project = project_service.get_project(task.project_id)
        if project:
            project_name = project.name
    
    # Format tags
    tags_str = ", ".join(task.tags) if task.tags else "None"
    
    # Format due date
    due_str = str(task.due_date) if task.due_date else "No due date"
    if task.due_time:
        due_str += f" at {task.due_time}"
    
    # Use prompt service for editable prompts
    system_prompt = render_prompt("task_analyzer_system")
    user_prompt = render_prompt("task_analyzer_user", {
        "name": task.name,
        "project": project_name,
        "due_date": due_str,
        "tags": tags_str,
    })
    
    suggestion = llm_generate(user_prompt, system=system_prompt)
    
    if suggestion:
        logger.info(f"Generated computer help suggestion for task {task.id}")
    else:
        logger.warning(f"Failed to generate suggestion for task {task.id}")
    
    return suggestion


def save_task_suggestion(task_id: int, suggestion: str):
    """Save a computer help suggestion to the task record."""
    with get_db() as conn:
        conn.execute("""
            UPDATE tasks
            SET computer_help_suggestion = ?,
                suggestion_generated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (suggestion, task_id))
    
    logger.debug(f"Saved suggestion for task {task_id}")


def get_tasks_needing_analysis(limit: int = 10) -> list:
    """Get tasks that haven't been analyzed yet."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, project_id, due_date, due_time, tags
            FROM tasks
            WHERE status NOT IN ('done', 'canceled')
              AND computer_help_suggestion IS NULL
            ORDER BY 
                CASE WHEN due_date IS NOT NULL THEN 0 ELSE 1 END,
                due_date ASC,
                importance DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        return [task_service.get_task(row["id"]) for row in rows]


def analyze_and_save(task: Task) -> bool:
    """Analyze a task and save the suggestion. Returns True if successful."""
    suggestion = analyze_task_for_computer_help(task)
    
    if suggestion:
        save_task_suggestion(task.id, suggestion)
        return True
    
    return False


def get_task_suggestion(task_id: int) -> Optional[str]:
    """Get the computer help suggestion for a task."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT computer_help_suggestion
            FROM tasks
            WHERE id = ?
        """, (task_id,)).fetchone()
        
        if row:
            return row["computer_help_suggestion"]
        return None


def clear_task_suggestion(task_id: int):
    """Clear the suggestion for a task (e.g., to re-analyze)."""
    with get_db() as conn:
        conn.execute("""
            UPDATE tasks
            SET computer_help_suggestion = NULL,
                suggestion_generated_at = NULL
            WHERE id = ?
        """, (task_id,))
