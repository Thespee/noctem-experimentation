"""
Task parser - parses natural language task input into Task objects.
Extracts priority, tags, project, date, time, recurrence from free-form text.
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, time

from .natural_date import parse_datetime


@dataclass
class ParsedTask:
    """Result of parsing a task string."""
    name: str = ""
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    importance: Optional[float] = None  # 1.0=important, 0.5=medium, 0.0=not important
    tags: list[str] = field(default_factory=list)
    project_name: Optional[str] = None
    recurrence_rule: Optional[str] = None


# Importance mapping: !1 = important (1.0), !2 = medium (0.5), !3 = not important (0.0)
IMPORTANCE_MAP = {1: 1.0, 2: 0.5, 3: 0.0}


def parse_importance(text: str) -> tuple[Optional[float], str]:
    """
    Extract importance from text.
    Supports: !1, !2, !3 (maps to 1.0, 0.5, 0.0)
    Returns (importance, remaining_text).
    """
    # Match !1, !2, !3 (no word boundary before ! since it's not a word char)
    match = re.search(r'!([1-3])(?:\b|$)', text)
    if match:
        level = int(match.group(1))
        importance = IMPORTANCE_MAP.get(level, 0.5)
        remaining = re.sub(r'![1-3](?:\b|$)', '', text).strip()
        return importance, remaining
    
    return None, text


def parse_tags(text: str) -> tuple[list[str], str]:
    """
    Extract tags from text.
    Supports: #tag, #work, #personal
    Returns (tags_list, remaining_text).
    """
    tags = re.findall(r'#(\w+)', text)
    remaining = re.sub(r'#\w+', '', text).strip()
    return tags, remaining


def parse_project(text: str) -> tuple[Optional[str], str]:
    """
    Extract project name from text.
    Supports: /project, +project
    Returns (project_name, remaining_text).
    """
    match = re.search(r'[/+](\w+)', text)
    if match:
        project = match.group(1)
        remaining = re.sub(r'[/+]\w+', '', text).strip()
        return project, remaining
    return None, text


def parse_task(text: str) -> ParsedTask:
    """
    Parse a complete task string into components.
    
    Examples:
    - "buy groceries tomorrow" -> name="buy groceries", due_date=tomorrow
    - "call mom friday 3pm" -> name="call mom", due_date=friday, due_time=15:00
    - "pay rent every 1st" -> name="pay rent", recurrence=monthly
    - "finish report by feb 20 !1" -> name="finish report", due_date=feb 20, importance=1.0
    - "email john next week #work" -> name="email john", due_date=next week, tags=[work]
    """
    remaining = text.strip()
    
    # Step 1: Extract importance (!1, !2, !3)
    importance, remaining = parse_importance(remaining)
    
    # Step 2: Extract tags
    tags, remaining = parse_tags(remaining)
    
    # Step 3: Extract project
    project_name, remaining = parse_project(remaining)
    
    # Step 4: Extract date, time, recurrence
    parsed_dt = parse_datetime(remaining)
    
    # Step 5: Clean up the remaining text as the task name
    name = parsed_dt.remaining_text.strip()
    
    # Remove common filler words at boundaries
    name = re.sub(r'^(to|the|a|an)\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(by|on|at|for)$', '', name, flags=re.IGNORECASE)
    
    # Capitalize first letter
    if name:
        name = name[0].upper() + name[1:] if len(name) > 1 else name.upper()
    
    return ParsedTask(
        name=name,
        due_date=parsed_dt.date,
        due_time=parsed_dt.time,
        importance=importance,
        tags=tags,
        project_name=project_name,
        recurrence_rule=parsed_dt.recurrence,
    )


# Reverse mapping for display
IMPORTANCE_DISPLAY = {1.0: "!1 (important)", 0.5: "!2 (medium)", 0.0: "!3 (low)"}


def format_task_confirmation(parsed: ParsedTask) -> str:
    """Format a confirmation message for a parsed task."""
    parts = [f'✓ Added: "{parsed.name}"']
    
    if parsed.due_date:
        date_str = parsed.due_date.strftime("%a %b %d")
        parts.append(f"due {date_str}")
    
    if parsed.due_time:
        time_str = parsed.due_time.strftime("%H:%M")
        parts.append(f"at {time_str}")
    
    if parsed.importance is not None:
        imp_str = IMPORTANCE_DISPLAY.get(parsed.importance, f"importance={parsed.importance}")
        parts.append(imp_str)
    
    if parsed.tags:
        parts.append(" ".join(f"#{t}" for t in parsed.tags))
    
    if parsed.project_name:
        parts.append(f"/{parsed.project_name}")
    
    if parsed.recurrence_rule:
        # Simple human-readable recurrence
        if "DAILY" in parsed.recurrence_rule:
            parts.append("(repeats daily)")
        elif "WEEKLY" in parsed.recurrence_rule:
            parts.append("(repeats weekly)")
        elif "MONTHLY" in parsed.recurrence_rule:
            parts.append("(repeats monthly)")
    
    return " ".join(parts)
