"""
Project Analyzer for Noctem v0.6.0 slow mode.

Analyzes projects to suggest what the user should do next.
Uses prompt_service for editable/versioned prompts.
"""
import logging
from typing import Optional, List

from ..db import get_db
from ..models import Project
from ..services import project_service, task_service
from ..services.prompt_service import render_prompt
from .ollama import llm_generate

logger = logging.getLogger(__name__)


def analyze_project_for_next_action(project: Project) -> Optional[str]:
    """
    Analyze a project to suggest what the user should do next.
    
    Args:
        project: The project to analyze
        
    Returns:
        Next action suggestion, or None if analysis failed
    """
    # Get tasks for this project
    tasks = task_service.get_project_tasks(project.id)
    
    # Format task list
    if tasks:
        task_lines = []
        for t in tasks[:10]:  # Limit to 10 tasks
            status_emoji = {
                "not_started": "○",
                "in_progress": "◐",
                "done": "✓",
                "canceled": "✗"
            }.get(t.status, "?")
            
            due_str = f" (due: {t.due_date})" if t.due_date else ""
            task_lines.append(f"  {status_emoji} {t.name}{due_str}")
        
        task_list = "\n".join(task_lines)
        if len(tasks) > 10:
            task_list += f"\n  ...and {len(tasks) - 10} more tasks"
    else:
        task_list = "  (No tasks yet)"
    
    # Use prompt service for editable prompts
    system_prompt = render_prompt("project_analyzer_system")
    user_prompt = render_prompt("project_analyzer_user", {
        "name": project.name,
        "summary": project.summary or "No summary",
        "status": project.status,
        "task_list": task_list,
    })
    
    suggestion = llm_generate(user_prompt, system=system_prompt)
    
    if suggestion:
        logger.info(f"Generated next action suggestion for project {project.id}")
    else:
        logger.warning(f"Failed to generate suggestion for project {project.id}")
    
    return suggestion


def save_project_suggestion(project_id: int, suggestion: str):
    """Save a next action suggestion to the project record."""
    with get_db() as conn:
        conn.execute("""
            UPDATE projects
            SET next_action_suggestion = ?,
                suggestion_generated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (suggestion, project_id))
    
    logger.debug(f"Saved suggestion for project {project_id}")


def get_projects_needing_analysis(limit: int = 5) -> List[Project]:
    """Get projects that haven't been analyzed yet or need re-analysis."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id
            FROM projects
            WHERE status = 'in_progress'
              AND (next_action_suggestion IS NULL
                   OR suggestion_generated_at < datetime('now', '-7 days'))
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        
        return [project_service.get_project(row["id"]) for row in rows]


def analyze_and_save(project: Project) -> bool:
    """Analyze a project and save the suggestion. Returns True if successful."""
    suggestion = analyze_project_for_next_action(project)
    
    if suggestion:
        save_project_suggestion(project.id, suggestion)
        return True
    
    return False


def get_project_suggestion(project_id: int) -> Optional[str]:
    """Get the next action suggestion for a project."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT next_action_suggestion
            FROM projects
            WHERE id = ?
        """, (project_id,)).fetchone()
        
        if row:
            return row["next_action_suggestion"]
        return None


def clear_project_suggestion(project_id: int):
    """Clear the suggestion for a project (e.g., to re-analyze)."""
    with get_db() as conn:
        conn.execute("""
            UPDATE projects
            SET next_action_suggestion = NULL,
                suggestion_generated_at = NULL
            WHERE id = ?
        """, (project_id,))
