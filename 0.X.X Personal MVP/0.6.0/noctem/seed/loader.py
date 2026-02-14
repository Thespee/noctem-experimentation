"""
Seed data loader for Noctem.
Loads goals, projects, tasks, and calendar URLs from JSON files.
Supports Windows-style conflict resolution (skip/overwrite/rename for each).
"""
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..services import goal_service, project_service, task_service
from ..services.ics_import import save_url

logger = logging.getLogger(__name__)


class ConflictAction(Enum):
    """How to handle conflicts when importing."""
    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"
    SKIP_ALL = "skip_all"
    OVERWRITE_ALL = "overwrite_all"


@dataclass
class ImportStats:
    """Statistics from an import operation."""
    goals_created: int = 0
    goals_skipped: int = 0
    goals_overwritten: int = 0
    projects_created: int = 0
    projects_skipped: int = 0
    projects_overwritten: int = 0
    tasks_created: int = 0
    tasks_skipped: int = 0
    tasks_overwritten: int = 0
    calendars_added: int = 0
    calendars_skipped: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def summary(self) -> str:
        """Return human-readable summary."""
        lines = []
        if self.goals_created or self.goals_skipped or self.goals_overwritten:
            lines.append(f"Goals: {self.goals_created} created, {self.goals_skipped} skipped, {self.goals_overwritten} overwritten")
        if self.projects_created or self.projects_skipped or self.projects_overwritten:
            lines.append(f"Projects: {self.projects_created} created, {self.projects_skipped} skipped, {self.projects_overwritten} overwritten")
        if self.tasks_created or self.tasks_skipped or self.tasks_overwritten:
            lines.append(f"Tasks: {self.tasks_created} created, {self.tasks_skipped} skipped, {self.tasks_overwritten} overwritten")
        if self.calendars_added or self.calendars_skipped:
            lines.append(f"Calendar URLs: {self.calendars_added} added, {self.calendars_skipped} skipped")
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
        return "\n".join(lines) if lines else "Nothing imported"


# Type for conflict resolution callback
# Takes (entity_type, name, existing_id) -> ConflictAction
ConflictResolver = Callable[[str, str, int], ConflictAction]


def _default_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
    """Default resolver - skip all conflicts."""
    return ConflictAction.SKIP


def validate_seed_data(data: dict) -> List[str]:
    """
    Validate seed data structure.
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    if not isinstance(data, dict):
        return ["Seed data must be a JSON object"]
    
    # Check goals
    if "goals" in data:
        if not isinstance(data["goals"], list):
            errors.append("'goals' must be an array")
        else:
            for i, goal in enumerate(data["goals"]):
                if not isinstance(goal, dict):
                    errors.append(f"Goal {i}: must be an object")
                elif "name" not in goal:
                    errors.append(f"Goal {i}: missing 'name'")
    
    # Check projects
    if "projects" in data:
        if not isinstance(data["projects"], list):
            errors.append("'projects' must be an array")
        else:
            for i, proj in enumerate(data["projects"]):
                if not isinstance(proj, dict):
                    errors.append(f"Project {i}: must be an object")
                elif "name" not in proj:
                    errors.append(f"Project {i}: missing 'name'")
    
    # Check tasks
    if "tasks" in data:
        if not isinstance(data["tasks"], list):
            errors.append("'tasks' must be an array")
        else:
            for i, task in enumerate(data["tasks"]):
                if not isinstance(task, dict):
                    errors.append(f"Task {i}: must be an object")
                elif "name" not in task:
                    errors.append(f"Task {i}: missing 'name'")
    
    # Check calendar_urls
    if "calendar_urls" in data:
        if not isinstance(data["calendar_urls"], list):
            errors.append("'calendar_urls' must be an array")
        else:
            for i, cal in enumerate(data["calendar_urls"]):
                if not isinstance(cal, dict):
                    errors.append(f"Calendar URL {i}: must be an object")
                elif "url" not in cal:
                    errors.append(f"Calendar URL {i}: missing 'url'")
    
    return errors


def load_seed_file(path: str) -> dict:
    """Load and parse a seed data JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_seed_data(
    data: dict,
    conflict_resolver: ConflictResolver = None,
) -> ImportStats:
    """
    Load seed data into the database.
    
    Args:
        data: Parsed seed data dictionary
        conflict_resolver: Callback for handling conflicts.
                          Takes (entity_type, name, existing_id) -> ConflictAction
    
    Returns:
        ImportStats with counts and errors
    """
    if conflict_resolver is None:
        conflict_resolver = _default_resolver
    
    stats = ImportStats()
    
    # Validate first
    errors = validate_seed_data(data)
    if errors:
        stats.errors.extend(errors)
        return stats
    
    # Track global skip/overwrite all decisions
    skip_all = {"goals": False, "projects": False, "tasks": False}
    overwrite_all = {"goals": False, "projects": False, "tasks": False}
    
    # Helper to resolve with skip_all/overwrite_all support
    def resolve(entity_type: str, name: str, existing_id: int) -> ConflictAction:
        if skip_all.get(entity_type):
            return ConflictAction.SKIP
        if overwrite_all.get(entity_type):
            return ConflictAction.OVERWRITE
        
        action = conflict_resolver(entity_type, name, existing_id)
        
        if action == ConflictAction.SKIP_ALL:
            skip_all[entity_type] = True
            return ConflictAction.SKIP
        elif action == ConflictAction.OVERWRITE_ALL:
            overwrite_all[entity_type] = True
            return ConflictAction.OVERWRITE
        
        return action
    
    # Maps for name -> id lookups (for linking)
    goal_map = {}  # goal_name -> goal_id
    project_map = {}  # project_name -> project_id
    
    # 1. Load goals first (no dependencies)
    for goal_data in data.get("goals", []):
        try:
            name = goal_data["name"]
            existing = goal_service.get_goal_by_name(name)
            
            if existing:
                action = resolve("goal", name, existing.id)
                
                if action == ConflictAction.SKIP:
                    stats.goals_skipped += 1
                    goal_map[name] = existing.id
                    continue
                elif action == ConflictAction.OVERWRITE:
                    # Update existing goal
                    goal_service.update_goal(
                        existing.id,
                        name=name,
                        goal_type=goal_data.get("type", "bigger_goal"),
                        description=goal_data.get("description"),
                    )
                    stats.goals_overwritten += 1
                    goal_map[name] = existing.id
                    continue
                elif action == ConflictAction.RENAME:
                    # Create with modified name
                    name = f"{name} (imported)"
            
            # Create new goal
            goal = goal_service.create_goal(
                name=name,
                goal_type=goal_data.get("type", "bigger_goal"),
                description=goal_data.get("description"),
            )
            stats.goals_created += 1
            goal_map[goal_data["name"]] = goal.id
            
        except Exception as e:
            stats.errors.append(f"Goal '{goal_data.get('name', '?')}': {e}")
    
    # 2. Load projects (may reference goals)
    for proj_data in data.get("projects", []):
        try:
            name = proj_data["name"]
            existing = project_service.get_project_by_name(name)
            
            # Resolve goal reference
            goal_id = None
            if "goal" in proj_data:
                goal_id = goal_map.get(proj_data["goal"])
                if not goal_id:
                    # Try to find existing goal
                    existing_goal = goal_service.get_goal_by_name(proj_data["goal"])
                    if existing_goal:
                        goal_id = existing_goal.id
            
            if existing:
                action = resolve("project", name, existing.id)
                
                if action == ConflictAction.SKIP:
                    stats.projects_skipped += 1
                    project_map[name] = existing.id
                    continue
                elif action == ConflictAction.OVERWRITE:
                    project_service.update_project(
                        existing.id,
                        name=name,
                        goal_id=goal_id,
                        summary=proj_data.get("summary"),
                        status=proj_data.get("status", "in_progress"),
                    )
                    stats.projects_overwritten += 1
                    project_map[name] = existing.id
                    continue
                elif action == ConflictAction.RENAME:
                    name = f"{name} (imported)"
            
            # Create new project
            project = project_service.create_project(
                name=name,
                goal_id=goal_id,
                summary=proj_data.get("summary"),
            )
            if proj_data.get("status"):
                project_service.update_project(project.id, status=proj_data["status"])
            
            stats.projects_created += 1
            project_map[proj_data["name"]] = project.id
            
        except Exception as e:
            stats.errors.append(f"Project '{proj_data.get('name', '?')}': {e}")
    
    # 3. Load tasks (may reference projects)
    for task_data in data.get("tasks", []):
        try:
            name = task_data["name"]
            existing = task_service.get_task_by_name(name)
            
            # Resolve project reference
            project_id = None
            if "project" in task_data:
                project_id = project_map.get(task_data["project"])
                if not project_id:
                    existing_proj = project_service.get_project_by_name(task_data["project"])
                    if existing_proj:
                        project_id = existing_proj.id
            
            # Parse due_date if provided
            due_date = None
            if "due_date" in task_data:
                due_date = date.fromisoformat(task_data["due_date"])
            
            if existing:
                action = resolve("task", name, existing.id)
                
                if action == ConflictAction.SKIP:
                    stats.tasks_skipped += 1
                    continue
                elif action == ConflictAction.OVERWRITE:
                    task_service.update_task(
                        existing.id,
                        name=name,
                        project_id=project_id,
                        due_date=due_date,
                        importance=task_data.get("importance", 0.5),
                        tags=task_data.get("tags"),
                    )
                    stats.tasks_overwritten += 1
                    continue
                elif action == ConflictAction.RENAME:
                    name = f"{name} (imported)"
            
            # Create new task
            task_service.create_task(
                name=name,
                project_id=project_id,
                due_date=due_date,
                importance=task_data.get("importance", 0.5),
                tags=task_data.get("tags"),
                recurrence_rule=task_data.get("recurrence"),
            )
            stats.tasks_created += 1
            
        except Exception as e:
            stats.errors.append(f"Task '{task_data.get('name', '?')}': {e}")
    
    # 4. Load calendar URLs
    for cal_data in data.get("calendar_urls", []):
        try:
            url = cal_data["url"]
            cal_name = cal_data.get("name", url[:50])
            
            # Check if URL already exists
            from ..services.ics_import import get_saved_urls
            existing_urls = [u["url"] for u in get_saved_urls()]
            
            if url in existing_urls:
                stats.calendars_skipped += 1
                continue
            
            # Save and sync the URL
            save_url(url, cal_name)
            stats.calendars_added += 1
            
        except Exception as e:
            stats.errors.append(f"Calendar URL '{cal_data.get('url', '?')}': {e}")
    
    return stats


def export_seed_data(
    include_tasks: bool = True,
    include_done_tasks: bool = False,
) -> dict:
    """
    Export current data as seed data format.
    Useful for creating backups or templates.
    """
    data = {
        "_noctem_seed_version": "1.0",
        "_exported_at": datetime.now().isoformat(),
        "goals": [],
        "projects": [],
        "tasks": [],
        "calendar_urls": [],
    }
    
    # Export goals
    for goal in goal_service.get_all_goals():
        data["goals"].append({
            "name": goal.name,
            "type": goal.type,
            "description": goal.description,
        })
    
    # Export projects
    for project in project_service.get_all_projects():
        proj_data = {
            "name": project.name,
            "status": project.status,
        }
        if project.summary:
            proj_data["summary"] = project.summary
        if project.goal_id:
            goal = goal_service.get_goal(project.goal_id)
            if goal:
                proj_data["goal"] = goal.name
        data["projects"].append(proj_data)
    
    # Export tasks
    if include_tasks:
        tasks = task_service.get_all_tasks(include_done=include_done_tasks)
        for task in tasks:
            task_data = {
                "name": task.name,
                "importance": task.importance,
            }
            if task.due_date:
                task_data["due_date"] = task.due_date.isoformat()
            if task.project_id:
                project = project_service.get_project(task.project_id)
                if project:
                    task_data["project"] = project.name
            if task.tags:
                task_data["tags"] = task.tags
            if task.recurrence_rule:
                task_data["recurrence"] = task.recurrence_rule
            data["tasks"].append(task_data)
    
    # Export calendar URLs
    from ..services.ics_import import get_saved_urls
    for url_info in get_saved_urls():
        data["calendar_urls"].append({
            "url": url_info["url"],
            "name": url_info.get("name", ""),
        })
    
    return data
