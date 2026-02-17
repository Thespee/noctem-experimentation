"""
Command parser - detects and routes user commands.
Distinguishes between slash commands, quick actions, and new tasks.
"""
import re
from dataclasses import dataclass
from typing import Optional, Any
from enum import Enum


class CommandType(Enum):
    """Types of commands the bot can handle."""
    # Slash commands
    START = "start"
    HELP = "help"
    TODAY = "today"
    WEEK = "week"
    PROJECTS = "projects"
    PROJECT = "project"  # /project <name> - create project
    GOALS = "goals"
    SETTINGS = "settings"
    PRIORITIZE = "prioritize"  # /prioritize n - reorder top n tasks
    UPDATE = "update"  # /update n - fill in missing info
    WEB = "web"  # Send dashboard link
    
    # Quick actions
    DONE = "done"
    SKIP = "skip"
    DELETE = "delete"
    CORRECT = "correct"  # * prefix to update last entity
    
    # Default: new task
    NEW_TASK = "new_task"


@dataclass
class ParsedCommand:
    """Result of parsing a command."""
    type: CommandType
    args: list[str]
    raw_text: str
    target_id: Optional[int] = None  # For done/skip/delete by ID
    target_name: Optional[str] = None  # For done/skip/delete by name


def parse_command(text: str) -> ParsedCommand:
    """
    Parse user input and determine the command type.
    
    Examples:
    - "/start" -> START
    - "/today" -> TODAY
    - "done 1" -> DONE with target_id=1
    - "done buy milk" -> DONE with target_name="buy milk"
    - "skip 2" -> SKIP with target_id=2
    - "buy groceries tomorrow" -> NEW_TASK
    - "* !1 tomorrow" -> CORRECT (update last entity)
    - "/prioritize 5" -> PRIORITIZE with count=5
    - "/update 3" -> UPDATE with count=3
    """
    text = text.strip()
    text_lower = text.lower()
    
    # Correction command: starts with *
    if text.startswith('*'):
        correction_text = text[1:].strip()
        return ParsedCommand(
            type=CommandType.CORRECT,
            args=[correction_text],
            raw_text=text,
        )
    
    # Slash commands
    if text.startswith('/'):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []
        
        cmd_map = {
            'start': CommandType.START,
            'help': CommandType.HELP,
            'today': CommandType.TODAY,
            'week': CommandType.WEEK,
            'projects': CommandType.PROJECTS,
            'project': CommandType.PROJECT,
            'goals': CommandType.GOALS,
            'settings': CommandType.SETTINGS,
            'prioritize': CommandType.PRIORITIZE,
            'update': CommandType.UPDATE,
        }
        
        cmd_type = cmd_map.get(cmd, CommandType.NEW_TASK)
        return ParsedCommand(
            type=cmd_type,
            args=args,
            raw_text=text,
        )
    
    # Quick actions: done
    match = re.match(r'^done\s+(.+)$', text_lower)
    if match:
        target = match.group(1).strip()
        target_id = None
        target_name = None
        
        # Check if target is a number
        if target.isdigit():
            target_id = int(target)
        else:
            target_name = target
        
        return ParsedCommand(
            type=CommandType.DONE,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )
    
    # Quick actions: skip
    match = re.match(r'^skip\s+(.+)$', text_lower)
    if match:
        target = match.group(1).strip()
        target_id = None
        target_name = None
        
        if target.isdigit():
            target_id = int(target)
        else:
            target_name = target
        
        return ParsedCommand(
            type=CommandType.SKIP,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )
    
    # Quick actions: delete or remove
    match = re.match(r'^(?:delete|remove)\s+(.+)$', text_lower)
    if match:
        target = match.group(1).strip()
        target_id = None
        target_name = None
        
        if target.isdigit():
            target_id = int(target)
        else:
            target_name = target
        
        return ParsedCommand(
            type=CommandType.DELETE,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )
    
    # Just "today" or "week" without slash
    if text_lower == 'today':
        return ParsedCommand(type=CommandType.TODAY, args=[], raw_text=text)
    if text_lower == 'week':
        return ParsedCommand(type=CommandType.WEEK, args=[], raw_text=text)
    if text_lower == 'projects':
        return ParsedCommand(type=CommandType.PROJECTS, args=[], raw_text=text)
    if text_lower == 'goals':
        return ParsedCommand(type=CommandType.GOALS, args=[], raw_text=text)
    if text_lower == 'web':
        return ParsedCommand(type=CommandType.WEB, args=[], raw_text=text)
    
    # Default: treat as new task
    return ParsedCommand(
        type=CommandType.NEW_TASK,
        args=[],
        raw_text=text,
    )


def is_command(text: str) -> bool:
    """Check if text is a command (not a new task)."""
    parsed = parse_command(text)
    return parsed.type != CommandType.NEW_TASK
