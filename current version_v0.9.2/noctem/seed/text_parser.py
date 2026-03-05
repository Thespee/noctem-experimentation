"""
Natural language seed data parser for Noctem.
Parses human-readable text format into seed data JSON.

Supported format:
```
Goals:
-Goal Name 1
-Goal Name 2

Projects by goal:
-Goal Name 1
---- Project 1
---- Project 2
-Goal Name 2
---- Project 3

Tasks by Project:
- Project 1
---- Task 1
---- Task 2; due date
---- Task 3

Links to calendars:
name:
url

name2:
url2
```
"""
import re
from datetime import date, datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


def parse_date_hint(text: str) -> Optional[str]:
    """
    Try to extract a date from text hints like "jan 20th 2026", "feb 11th", "asap".
    Returns ISO format date string or None.
    """
    text_lower = text.lower().strip()
    
    # Handle "asap" - set to today
    if text_lower in ('asap', 'now', 'today'):
        return date.today().isoformat()
    
    # Handle "tomorrow"
    if text_lower == 'tomorrow':
        from datetime import timedelta
        return (date.today() + timedelta(days=1)).isoformat()
    
    # Try to parse common date formats
    # "jan 20th 2026", "feb 11th", "march 4th"
    month_map = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12,
    }
    
    # Pattern: "jan 20th 2026" or "jan 20 2026" or "jan 20th"
    pattern = r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?'
    match = re.search(pattern, text_lower)
    
    if match:
        month_str, day_str, year_str = match.groups()
        month = month_map.get(month_str)
        if month:
            day = int(day_str)
            year = int(year_str) if year_str else date.today().year
            # If date is in the past and no year specified, assume next year
            if not year_str:
                potential_date = date(year, month, day)
                if potential_date < date.today():
                    year += 1
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass  # Invalid date
    
    return None


def parse_natural_seed_text(text: str) -> Dict[str, Any]:
    """
    Parse natural language seed data format into JSON structure.
    
    Args:
        text: Human-readable seed data text
        
    Returns:
        Dict in seed data JSON format
    """
    result = {
        "goals": [],
        "projects": [],
        "tasks": [],
        "calendar_urls": [],
    }
    
    # Normalize line endings and split
    lines = text.replace('\r\n', '\n').split('\n')
    
    # Track current section and context
    current_section = None
    current_goal = None
    current_project = None
    
    # Maps for tracking
    goal_names = set()
    project_to_goal = {}  # project_name -> goal_name
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        line_lower = line.lower().strip()
        
        # Detect section headers
        if line_lower.startswith('goals:'):
            current_section = 'goals'
            current_goal = None
            current_project = None
            i += 1
            continue
        
        if line_lower.startswith('projects by goal:') or line_lower.startswith('projects:'):
            current_section = 'projects'
            current_goal = None
            current_project = None
            i += 1
            continue
        
        if line_lower.startswith('tasks by project:') or line_lower.startswith('tasks:'):
            current_section = 'tasks'
            current_goal = None
            current_project = None
            i += 1
            continue
        
        if 'calendar' in line_lower and ':' in line_lower:
            current_section = 'calendars'
            current_goal = None
            current_project = None
            i += 1
            continue
        
        # Skip empty lines
        if not line.strip():
            i += 1
            continue
        
        # Process based on current section
        if current_section == 'goals':
            # Goals are simple list items: -Goal Name or - Goal Name
            if line.strip().startswith('-'):
                goal_name = line.strip().lstrip('-').strip()
                if goal_name and goal_name not in goal_names:
                    result["goals"].append({
                        "name": goal_name,
                        "type": "bigger_goal",
                    })
                    goal_names.add(goal_name)
        
        elif current_section == 'projects':
            stripped = line.strip()
            
            # Check if it's a goal header (single dash, not four dashes)
            if stripped.startswith('-') and not stripped.startswith('----'):
                # This is a goal reference
                current_goal = stripped.lstrip('-').strip()
                # Add goal if not already added
                if current_goal and current_goal not in goal_names:
                    result["goals"].append({
                        "name": current_goal,
                        "type": "bigger_goal",
                    })
                    goal_names.add(current_goal)
            
            # Check if it's a project (four dashes)
            elif stripped.startswith('----'):
                project_name = stripped.lstrip('-').strip()
                if project_name:
                    project_data = {"name": project_name}
                    if current_goal:
                        project_data["goal"] = current_goal
                        project_to_goal[project_name.lower()] = current_goal
                    result["projects"].append(project_data)
        
        elif current_section == 'tasks':
            stripped = line.strip()
            
            # Check if it's a project header (single dash, not four dashes)
            if stripped.startswith('-') and not stripped.startswith('----'):
                current_project = stripped.lstrip('-').strip()
                # Add project if not already added
                existing_projects = [p["name"].lower() for p in result["projects"]]
                if current_project and current_project.lower() not in existing_projects:
                    result["projects"].append({"name": current_project})
            
            # Check if it's a task (four dashes)
            elif stripped.startswith('----'):
                task_text = stripped.lstrip('-').strip()
                if task_text:
                    task_data = {"name": task_text}
                    
                    # Check for date hint after semicolon
                    if ';' in task_text:
                        parts = task_text.split(';', 1)
                        task_name = parts[0].strip()
                        date_hint = parts[1].strip()
                        
                        task_data["name"] = task_name
                        parsed_date = parse_date_hint(date_hint)
                        if parsed_date:
                            task_data["due_date"] = parsed_date
                    
                    # Link to project if we have context
                    if current_project:
                        task_data["project"] = current_project
                    
                    result["tasks"].append(task_data)
        
        elif current_section == 'calendars':
            stripped = line.strip()
            
            # Calendar format: either "name:\nurl" or just a URL
            if stripped.endswith(':') and not stripped.startswith('http'):
                # This is a calendar name, next line should be URL
                cal_name = stripped.rstrip(':').strip()
                i += 1
                # Look for URL on next non-empty line
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line:
                        if next_line.startswith('http'):
                            result["calendar_urls"].append({
                                "name": cal_name,
                                "url": next_line,
                            })
                        break
                    i += 1
            elif stripped.startswith('http'):
                # Just a URL without a name
                result["calendar_urls"].append({
                    "name": "Calendar",
                    "url": stripped,
                })
        
        i += 1
    
    return result


def is_natural_seed_format(text: str) -> bool:
    """
    Check if text looks like natural seed data format.
    Returns True if it contains section headers.
    """
    text_lower = text.lower()
    return (
        'goals:' in text_lower or
        'projects by goal:' in text_lower or
        'tasks by project:' in text_lower or
        ('projects:' in text_lower and 'tasks:' in text_lower)
    )
