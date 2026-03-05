"""
Telegram message formatting utilities.
"""
from datetime import date, datetime
from typing import Optional
from ..models import Task


def format_task(task: Task, index: Optional[int] = None) -> str:
    """Format a single task for display."""
    parts = []
    
    if index is not None:
        parts.append(f"{index}.")
    
    if task.priority:
        parts.append(f"[!{task.priority}]")
    
    parts.append(task.name)
    
    if task.due_date:
        if task.due_date == date.today():
            parts.append("(today)")
        else:
            parts.append(f"(due {task.due_date.strftime('%b %d')})")
    
    if task.due_time:
        parts.append(f"at {task.due_time.strftime('%H:%M')}")
    
    return " ".join(parts)


def format_task_list(tasks: list[Task], title: str = "Tasks") -> str:
    """Format a list of tasks."""
    if not tasks:
        return f"No {title.lower()}"
    
    lines = [f"**{title}**"]
    for i, task in enumerate(tasks, 1):
        lines.append(format_task(task, i))
    
    return "\n".join(lines)


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram Markdown."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
