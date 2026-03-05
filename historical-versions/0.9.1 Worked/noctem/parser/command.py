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
    GOAL = "goal"  # /goal <name> - create goal
    SETTINGS = "settings"
    PRIORITIZE = "prioritize"  # /prioritize n - reorder top n tasks
    UPDATE = "update"  # /update n - fill in missing info
    WEB = "web"  # Send dashboard link
    
    # Quick actions
    DONE = "done"
    SKIP = "skip"
    DELETE = "delete"
    CORRECT = "correct"  # * prefix to update last entity
    
    # v0.9.1: New command types
    WIKI = "wiki"  # wiki subcommands
    SESSION = "session"  # feedback session
    SUMMON = "summon"  # direct butler contact
    
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
    
    # v0.9.1: Dot-prefix shortcuts (primary, phone-friendly)
    # Also accepts / as fallback — both route to the same CommandType
    if text.startswith('.') or text.startswith('/'):
        prefix_char = text[0]
        rest = text[1:]
        parts = rest.split(maxsplit=1)
        if not parts:
            # Bare . or / — treat as new task
            return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)
        
        cmd = parts[0].lower()
        raw_args = parts[1] if len(parts) > 1 else ""
        args = raw_args.split() if raw_args else []
        
        # Shorthand map (single-letter shortcuts)
        shorthand_map = {
            't': CommandType.NEW_TASK,
            'p': CommandType.PROJECT,
            'g': CommandType.GOAL,
            'd': CommandType.DONE,
            's': CommandType.SKIP,
            'w': CommandType.WIKI,
        }
        
        # Full command name map
        cmd_map = {
            'start': CommandType.START,
            'help': CommandType.HELP,
            'today': CommandType.TODAY,
            'week': CommandType.WEEK,
            'projects': CommandType.PROJECTS,
            'project': CommandType.PROJECT,
            'goals': CommandType.GOALS,
            'goal': CommandType.GOAL,
            'settings': CommandType.SETTINGS,
            'prioritize': CommandType.PRIORITIZE,
            'update': CommandType.UPDATE,
            'wiki': CommandType.WIKI,
            'session': CommandType.SESSION,
            'summon': CommandType.SUMMON,
            'web': CommandType.WEB,
            'done': CommandType.DONE,
            'skip': CommandType.SKIP,
            'delete': CommandType.DELETE,
        }
        
        # Try shorthand first (single letter), then full name
        cmd_type = shorthand_map.get(cmd) or cmd_map.get(cmd)
        
        if cmd_type:
            # For done/skip/delete, parse target_id/target_name
            target_id = None
            target_name = None
            if cmd_type in (CommandType.DONE, CommandType.SKIP, CommandType.DELETE) and raw_args:
                target = raw_args.strip()
                if target.isdigit():
                    target_id = int(target)
                else:
                    target_name = target.lower()
            
            return ParsedCommand(
                type=cmd_type,
                args=args,
                raw_text=text,
                target_id=target_id,
                target_name=target_name,
            )
        
        # Unknown command after . or / — treat as new task
        return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)
    
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
