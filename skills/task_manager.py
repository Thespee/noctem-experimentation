#!/usr/bin/env python3
"""
Noctem Task Manager Skill
Personal task tracking with goal → project → task hierarchy.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.base import Skill, SkillResult, SkillContext, register_skill
import state


@register_skill
class TaskManagerSkill(Skill):
    """Manage personal tasks, projects, and goals."""
    
    name = "task_manager"
    description = "Manage personal tasks with goal/project hierarchy"
    parameters = {
        "action": "list|add|done|goals|projects",
        "title": "Task/project/goal title (for add)",
        "task_id": "Task ID (for done)",
        "project": "Project name to link task to (optional)",
    }
    
    def run(self, params: dict, context: SkillContext) -> SkillResult:
        action = params.get("action", "list")
        
        try:
            if action == "list":
                return self._list_tasks()
            elif action == "add":
                return self._add_task(params)
            elif action == "done":
                return self._complete_task(params)
            elif action == "goals":
                return self._list_goals()
            elif action == "projects":
                return self._list_projects()
            else:
                return SkillResult(success=False, output="", error=f"Unknown action: {action}")
        except Exception as e:
            return SkillResult(success=False, output="", error=str(e))
    
    def _list_tasks(self) -> SkillResult:
        """List pending tasks."""
        tasks = state.get_user_tasks(status="pending")
        if not tasks:
            return SkillResult(success=True, output="No pending tasks! 🎉")
        
        lines = [f"📋 Pending Tasks ({len(tasks)}):"]
        for t in tasks[:10]:
            project = f" [{t['project_name']}]" if t.get('project_name') else ""
            due = f" (due {t['due_date']})" if t.get('due_date') else ""
            lines.append(f"  {t['id']}. {t['title']}{project}{due}")
        
        if len(tasks) > 10:
            lines.append(f"  ...and {len(tasks) - 10} more")
        
        return SkillResult(success=True, output="\n".join(lines), data={"tasks": tasks})
    
    def _add_task(self, params: dict) -> SkillResult:
        """Add a new task."""
        title = params.get("title", "").strip()
        if not title:
            return SkillResult(success=False, output="", error="Task title required")
        
        # Find or create project if specified
        project_id = None
        project_name = params.get("project", "").strip()
        if project_name:
            projects = state.get_projects()
            for p in projects:
                if p['name'].lower() == project_name.lower():
                    project_id = p['id']
                    break
            if not project_id:
                # Create new project
                project_id = state.create_project(project_name)
        
        # Parse priority from title (e.g., "!!" for high, "!" for medium)
        priority = 5
        if title.startswith("!!!"):
            priority = 1
            title = title[3:].strip()
        elif title.startswith("!!"):
            priority = 2
            title = title[2:].strip()
        elif title.startswith("!"):
            priority = 3
            title = title[1:].strip()
        
        task_id = state.create_user_task(
            title=title,
            project_id=project_id,
            priority=priority
        )
        
        project_note = f" in {project_name}" if project_name else ""
        return SkillResult(
            success=True, 
            output=f"✅ Added task #{task_id}: {title}{project_note}",
            data={"task_id": task_id}
        )
    
    def _complete_task(self, params: dict) -> SkillResult:
        """Mark a task as done."""
        task_id = params.get("task_id")
        if not task_id:
            return SkillResult(success=False, output="", error="Task ID required")
        
        try:
            task_id = int(task_id)
        except ValueError:
            return SkillResult(success=False, output="", error="Invalid task ID")
        
        task = state.get_user_task(task_id)
        if not task:
            return SkillResult(success=False, output="", error=f"Task #{task_id} not found")
        
        if state.complete_user_task(task_id):
            return SkillResult(
                success=True,
                output=f"✅ Completed: {task['title']}",
                data={"task": task}
            )
        return SkillResult(success=False, output="", error="Failed to complete task")
    
    def _list_goals(self) -> SkillResult:
        """List active goals."""
        goals = state.get_goals()
        if not goals:
            return SkillResult(success=True, output="No goals set. Use /goal <name> to create one.")
        
        lines = ["🎯 Goals:"]
        for g in goals:
            projects = state.get_projects(goal_id=g['id'])
            lines.append(f"  {g['id']}. {g['name']} ({len(projects)} projects)")
        
        return SkillResult(success=True, output="\n".join(lines), data={"goals": goals})
    
    def _list_projects(self) -> SkillResult:
        """List active projects."""
        projects = state.get_projects()
        if not projects:
            return SkillResult(success=True, output="No projects. Tasks will be added without a project.")
        
        lines = ["📁 Projects:"]
        for p in projects:
            tasks = state.get_user_tasks(project_id=p['id'])
            lines.append(f"  {p['id']}. {p['name']} ({len(tasks)} tasks)")
        
        return SkillResult(success=True, output="\n".join(lines), data={"projects": projects})


# Signal command handlers - these will be called from signal_receiver.py
def handle_tasks_command(args: list) -> str:
    """Handle /tasks command."""
    skill = TaskManagerSkill()
    ctx = SkillContext()
    
    if not args:
        result = skill.run({"action": "list"}, ctx)
    elif args[0] == "done" and len(args) > 1:
        result = skill.run({"action": "done", "task_id": args[1]}, ctx)
    elif args[0] == "goals":
        result = skill.run({"action": "goals"}, ctx)
    elif args[0] == "projects":
        result = skill.run({"action": "projects"}, ctx)
    else:
        # Treat as task title to add
        title = " ".join(args)
        result = skill.run({"action": "add", "title": title}, ctx)
    
    return result.output if result.success else f"Error: {result.error}"


def handle_add_command(args: list) -> str:
    """Handle /add command."""
    if not args:
        return "Usage: /add <task title>"
    
    skill = TaskManagerSkill()
    ctx = SkillContext()
    
    # Check for "in <project>" syntax
    title_parts = []
    project = None
    i = 0
    while i < len(args):
        if args[i].lower() == "in" and i + 1 < len(args):
            project = " ".join(args[i+1:])
            break
        title_parts.append(args[i])
        i += 1
    
    title = " ".join(title_parts)
    params = {"action": "add", "title": title}
    if project:
        params["project"] = project
    
    result = skill.run(params, ctx)
    return result.output if result.success else f"Error: {result.error}"


def handle_done_command(args: list) -> str:
    """Handle /done command."""
    if not args:
        return "Usage: /done <task_id>"
    
    skill = TaskManagerSkill()
    ctx = SkillContext()
    result = skill.run({"action": "done", "task_id": args[0]}, ctx)
    return result.output if result.success else f"Error: {result.error}"
