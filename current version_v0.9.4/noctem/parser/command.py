"""
Command parser for v0.9.4 active command surface.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandType(Enum):
    """Supported command types in active v0.9.4 scope."""

    START = "start"
    HELP = "help"
    PROJECTS = "projects"
    PROJECT = "project"
    GOALS = "goals"
    GOAL = "goal"
    SETTINGS = "settings"
    WEB = "web"
    DONE = "done"
    SKIP = "skip"
    DELETE = "delete"
    NEW_TASK = "new_task"


@dataclass
class ParsedCommand:
    type: CommandType
    args: list[str]
    raw_text: str
    target_id: Optional[int] = None
    target_name: Optional[str] = None


def _build_target(raw: str) -> tuple[Optional[int], Optional[str]]:
    target = (raw or "").strip()
    if not target:
        return None, None
    if target.isdigit():
        return int(target), None
    return None, target.lower()


def parse_command(text: str) -> ParsedCommand:
    text = (text or "").strip()
    text_lower = text.lower()

    if not text:
        return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)

    if text.startswith(".") or text.startswith("/"):
        rest = text[1:].strip()
        if not rest:
            return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)

        parts = rest.split(maxsplit=1)
        cmd = parts[0].lower()
        raw_args = parts[1] if len(parts) > 1 else ""
        args = raw_args.split() if raw_args else []

        shorthand_map = {
            "t": CommandType.NEW_TASK,
            "p": CommandType.PROJECT,
            "g": CommandType.GOAL,
            "d": CommandType.DONE,
            "s": CommandType.SKIP,
        }
        cmd_map = {
            "start": CommandType.START,
            "help": CommandType.HELP,
            "projects": CommandType.PROJECTS,
            "project": CommandType.PROJECT,
            "goals": CommandType.GOALS,
            "goal": CommandType.GOAL,
            "settings": CommandType.SETTINGS,
            "web": CommandType.WEB,
            "done": CommandType.DONE,
            "skip": CommandType.SKIP,
            "delete": CommandType.DELETE,
        }

        cmd_type = shorthand_map.get(cmd) or cmd_map.get(cmd)
        if not cmd_type:
            return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)

        target_id = None
        target_name = None
        if cmd_type in (CommandType.DONE, CommandType.SKIP, CommandType.DELETE):
            target_id, target_name = _build_target(raw_args)

        return ParsedCommand(
            type=cmd_type,
            args=args,
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )

    match = re.match(r"^(?:done|complete|completed)\s+(.+)$", text_lower)
    if match:
        target = match.group(1).strip()
        target_id, target_name = _build_target(target)
        return ParsedCommand(
            type=CommandType.DONE,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )

    match = re.match(r"^skip\s+(.+)$", text_lower)
    if match:
        target = match.group(1).strip()
        target_id, target_name = _build_target(target)
        return ParsedCommand(
            type=CommandType.SKIP,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )

    match = re.match(r"^(?:delete|remove)\s+(.+)$", text_lower)
    if match:
        target = match.group(1).strip()
        target_id, target_name = _build_target(target)
        return ParsedCommand(
            type=CommandType.DELETE,
            args=[target],
            raw_text=text,
            target_id=target_id,
            target_name=target_name,
        )

    if text_lower == "projects":
        return ParsedCommand(type=CommandType.PROJECTS, args=[], raw_text=text)
    if text_lower == "goals":
        return ParsedCommand(type=CommandType.GOALS, args=[], raw_text=text)
    if text_lower == "web":
        return ParsedCommand(type=CommandType.WEB, args=[], raw_text=text)

    return ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text=text)


def is_command(text: str) -> bool:
    return parse_command(text).type != CommandType.NEW_TASK
