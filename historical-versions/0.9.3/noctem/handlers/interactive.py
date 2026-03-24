"""
Handlers for interactive modes: /prioritize, /update, and * correction.
"""
from typing import Optional, Tuple
from datetime import date, time
from ..session import get_session, SessionMode, UpdateItem
from ..services import task_service, project_service, goal_service
from ..parser.task_parser import parse_task
from ..mcp import get_mcp_server


def _mcp_update_task(task_id: int, **updates):
    payload = {"task_id": task_id}
    for key, value in updates.items():
        if key == "due_date" and isinstance(value, date):
            payload[key] = value.isoformat()
        elif key == "due_time" and isinstance(value, time):
            payload[key] = value.isoformat()
        else:
            payload[key] = value

    result = get_mcp_server().call_tool(
        "tasks.update_fields",
        payload,
        context={"source": "handlers.interactive"},
    )
    if not result.get("ok"):
        return None
    task_payload = result["result"].get("task")
    if not isinstance(task_payload, dict) or task_payload.get("id") is None:
        return None
    return task_service.get_task(int(task_payload["id"]))


def _mcp_create_task(**kwargs):
    result = get_mcp_server().call_tool(
        "tasks.create",
        {
            "name": kwargs.get("name"),
            "project_id": kwargs.get("project_id"),
            "due_date": kwargs.get("due_date").isoformat() if kwargs.get("due_date") else None,
            "due_time": kwargs.get("due_time").isoformat() if kwargs.get("due_time") else None,
            "importance": kwargs.get("importance"),
            "tags": kwargs.get("tags"),
            "recurrence_rule": kwargs.get("recurrence_rule"),
        },
        context={"source": "handlers.interactive"},
    )
    if not result.get("ok"):
        return None
    task_payload = result["result"].get("task")
    if not isinstance(task_payload, dict) or task_payload.get("id") is None:
        return None
    return task_service.get_task(int(task_payload["id"]))


def start_prioritize_mode(count: int) -> str:
    """
    Enter prioritize mode to reorder top n tasks.
    Returns the list display.
    """
    session = get_session()
    tasks = task_service.get_priority_tasks(count)
    
    if not tasks:
        return "No tasks to prioritize."
    
    session.mode = SessionMode.PRIORITIZE
    session.prioritize_tasks = tasks
    session.prioritize_count = len(tasks)
    
    return format_prioritize_list(tasks)


def format_prioritize_list(tasks) -> str:
    """Format the prioritize list display."""
    lines = ["⚡ Top Priority Tasks (reply with number to bump to top):"]
    for i, task in enumerate(tasks, 1):
        due = f" (due {task.due_date})" if task.due_date else ""
        score = f" [{task.priority_score:.0%}]"
        lines.append(f"{i}. {task.name}{due}{score}")
    lines.append("")
    lines.append("Reply: '2' to make #2 top priority, 'done' to exit")
    return "\n".join(lines)


def handle_prioritize_input(text: str) -> Tuple[str, bool]:
    """
    Handle input during prioritize mode.
    Returns (response, should_exit_mode).
    """
    session = get_session()
    text = text.strip().lower()
    
    if text in ('done', 'exit', 'quit', 'q'):
        session.reset()
        return "✓ Exited prioritize mode.", True
    
    # Parse "n. command" format for updating specific items
    # Or just "n" to bump to top
    if text.isdigit():
        idx = int(text)
        if 1 <= idx <= len(session.prioritize_tasks):
            # Move task to highest importance
            task = session.prioritize_tasks[idx - 1]
            _mcp_update_task(task.id, importance=1.0)
            
            # Refresh list
            tasks = task_service.get_priority_tasks(session.prioritize_count)
            session.prioritize_tasks = tasks
            
            return f"✓ Bumped '{task.name}' to top priority.\n\n{format_prioritize_list(tasks)}", False
        else:
            return f"Invalid number. Choose 1-{len(session.prioritize_tasks)}.", False
    
    return "Reply with a number (1-{}) or 'done' to exit.".format(len(session.prioritize_tasks)), False


def start_update_mode(count: int) -> str:
    """
    Enter update mode to fill in missing info.
    Gathers items that need: due_date, importance, project assignment,
    projects without goals, projects without tasks.
    Returns the list display.
    """
    session = get_session()
    items = []
    idx = 1
    
    # Tasks missing due date
    all_tasks = task_service.get_all_tasks(include_done=False)
    for task in all_tasks:
        missing = []
        if task.due_date is None:
            missing.append("due_date")
        if task.importance == 0.5:  # Default, never set explicitly
            missing.append("importance")
        if task.project_id is None:
            missing.append("project")
        
        if missing and idx <= count:
            items.append(UpdateItem(
                index=idx,
                entity_type="task",
                entity_id=task.id,
                name=task.name,
                missing=missing
            ))
            idx += 1
    
    # Projects without goals
    projects = project_service.get_active_projects()
    for project in projects:
        missing = []
        if project.goal_id is None:
            missing.append("goal")
        
        # Check if project has any active tasks
        project_tasks = task_service.get_project_tasks(project.id)
        active_tasks = [t for t in project_tasks if t.status not in ('done', 'canceled')]
        if not active_tasks:
            missing.append("tasks")
        
        if missing and idx <= count:
            items.append(UpdateItem(
                index=idx,
                entity_type="project",
                entity_id=project.id,
                name=project.name,
                missing=missing
            ))
            idx += 1
    
    if not items:
        return "✓ Everything looks complete! No items need updating."
    
    session.mode = SessionMode.UPDATE
    session.update_items = items[:count]
    session.update_index = 0
    
    return format_update_list(items[:count])


def format_update_list(items: list[UpdateItem]) -> str:
    """Format the update list display."""
    lines = ["📝 Items needing info:"]
    for item in items:
        missing_str = ", ".join(item.missing)
        icon = "📋" if item.entity_type == "task" else "📁"
        lines.append(f"{item.index}. {icon} {item.name} — needs: {missing_str}")
    
    lines.append("")
    lines.append("Reply: '1. tomorrow !1' to update #1, 'done' to exit")
    return "\n".join(lines)


def handle_update_input(text: str) -> Tuple[str, bool]:
    """
    Handle input during update mode.
    Format: "n. <update info>" or just "done" to exit.
    Returns (response, should_exit_mode).
    """
    session = get_session()
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    
    if text_lower in ('done', 'exit', 'quit', 'q'):
        session.reset()
        return "✓ Exited update mode.", True
    
    # Parse "n. <command>" format
    import re
    match = re.match(r'^(\d+)\.\s*(.+)$', text_stripped)
    if not match:
        return "Format: '<number>. <update>' (e.g., '1. tomorrow !1')", False
    
    idx = int(match.group(1))
    update_text = match.group(2).strip()
    
    # Find the item
    item = None
    for i in session.update_items:
        if i.index == idx:
            item = i
            break
    
    if not item:
        return f"Invalid number. Choose from the list.", False
    
    if item.entity_type == "task":
        return handle_task_update(item, update_text)
    elif item.entity_type == "project":
        return handle_project_update(item, update_text)
    
    return "Unknown item type.", False


def handle_task_update(item: UpdateItem, update_text: str) -> Tuple[str, bool]:
    """Apply update to a task."""
    session = get_session()
    
    # Parse the update text for date, importance, project
    parsed = parse_task(update_text)
    
    updates = {}
    update_parts = []
    
    if parsed.due_date and "due_date" in item.missing:
        updates["due_date"] = parsed.due_date
        update_parts.append(f"due {parsed.due_date}")
    
    if parsed.importance is not None and "importance" in item.missing:
        updates["importance"] = parsed.importance
        imp_label = {1.0: "!1", 0.5: "!2", 0.0: "!3"}.get(parsed.importance, str(parsed.importance))
        update_parts.append(f"importance {imp_label}")
    
    if parsed.project_name and "project" in item.missing:
        project = project_service.get_project_by_name(parsed.project_name)
        if project:
            updates["project_id"] = project.id
            update_parts.append(f"project /{project.name}")
    
    if updates:
        updated_task = _mcp_update_task(item.entity_id, **updates)
        if updated_task is None:
            return f"Failed to update '{item.name}'.", False
        
        # Remove from update list or mark as done
        session.update_items = [i for i in session.update_items if i.index != item.index]
        
        response = f"✓ Updated '{item.name}': {', '.join(update_parts)}"
        
        if session.update_items:
            response += f"\n\n{format_update_list(session.update_items)}"
            return response, False
        else:
            session.reset()
            return response + "\n\n✓ All items updated!", True
    
    return f"Couldn't parse update. Try: 'tomorrow !1' or '/projectname'", False


def handle_project_update(item: UpdateItem, update_text: str) -> Tuple[str, bool]:
    """Apply update to a project."""
    session = get_session()
    
    update_parts = []
    
    # Check if it's a goal assignment (starts with goal name)
    if "goal" in item.missing:
        goal = goal_service.get_goal_by_name(update_text.strip())
        if goal:
            project_service.update_project(item.entity_id, goal_id=goal.id)
            update_parts.append(f"goal: {goal.name}")
    
    # Check if it's a new task for the project
    if "tasks" in item.missing and not update_parts:
        # Treat the update text as a new task for this project
        parsed = parse_task(update_text)
        if parsed.name:
            created_task = _mcp_create_task(
                name=parsed.name,
                project_id=item.entity_id,
                due_date=parsed.due_date,
                due_time=parsed.due_time,
                importance=parsed.importance,
            )
            if created_task is not None:
                update_parts.append(f"added task: {parsed.name}")
    
    if update_parts:
        session.update_items = [i for i in session.update_items if i.index != item.index]
        
        response = f"✓ Updated '{item.name}': {', '.join(update_parts)}"
        
        if session.update_items:
            response += f"\n\n{format_update_list(session.update_items)}"
            return response, False
        else:
            session.reset()
            return response + "\n\n✓ All items updated!", True
    
    return f"Couldn't parse update. For goals: type goal name. For tasks: type task description.", False


def handle_correction(correction_text: str) -> str:
    """
    Handle * correction - update the last created entity.
    Parses the correction text and applies any found updates.
    """
    session = get_session()
    
    if not session.last_entity_type or not session.last_entity_id:
        return "❌ No recent item to correct."
    
    if session.last_entity_type == "task":
        task = task_service.get_task(session.last_entity_id)
        if not task:
            return "❌ Last task not found."
        
        # Parse correction for updates
        parsed = parse_task(correction_text)
        
        updates = {}
        update_parts = []
        
        if parsed.due_date:
            updates["due_date"] = parsed.due_date
            update_parts.append(f"due {parsed.due_date}")
        
        if parsed.due_time:
            updates["due_time"] = parsed.due_time
            update_parts.append(f"at {parsed.due_time}")
        
        if parsed.importance is not None:
            updates["importance"] = parsed.importance
            imp_label = {1.0: "!1", 0.5: "!2", 0.0: "!3"}.get(parsed.importance, str(parsed.importance))
            update_parts.append(f"importance {imp_label}")
        
        if parsed.project_name:
            project = project_service.get_project_by_name(parsed.project_name)
            if project:
                updates["project_id"] = project.id
                update_parts.append(f"project /{project.name}")
        
        if parsed.tags:
            # Merge with existing tags
            existing_tags = task.tags or []
            new_tags = list(set(existing_tags + parsed.tags))
            updates["tags"] = new_tags
            update_parts.append(f"tags {', '.join(parsed.tags)}")
        
        if updates:
            updated_task = _mcp_update_task(task.id, **updates)
            if updated_task is None:
                return f"❌ Failed to update '{task.name}'."
            return f"✓ Updated '{task.name}': {', '.join(update_parts)}"
        
        return f"❌ Couldn't parse correction. Try: '* tomorrow !1' or '* /project'"
    
    return f"❌ Correction not supported for {session.last_entity_type} yet."
