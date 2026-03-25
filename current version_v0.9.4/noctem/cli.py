#!/usr/bin/env python3
"""CLI interface for Noctem v0.9.4."""
from __future__ import annotations

import argparse
import json

from .config import Config
from .db import init_db
from .mcp import get_mcp_server
from .mcp.resolver import resolve_task_target
from .parser.command import CommandType, parse_command
from .parser.task_parser import parse_task
from .services import goal_service, project_service, task_service
from .services.feedback_service import prepend_feedback
from .services.message_logger import MessageLog


def _print_help():
    print(
        """
Noctem CLI v0.9.4

Active commands:
  .t <task> or /t <task>     Fast-path task capture (MCP)
  .d <target> or done <x>    Fast-path complete (MCP)
  skip <target>              Fast-path skip/defer (MCP)
  delete <target>            Fast-path delete (MCP, preview+commit)
  .f <text>                   Fast-path feedback capture
  .p <name>                  Create project
  .g <name>                  Create goal
  projects                   List projects
  goals                      List goals
  status                     Show task counts
  config                     Show settings
  set <key> <value>          Update config
  help                       Show this help
  quit                       Exit

Natural language goes through the agentic runtime.
"""
    )


def _fast_feedback(input_text: str) -> str:
    stripped = (input_text or "").strip()
    lowered = stripped.lower()
    if lowered.startswith(".f"):
        stripped = stripped[2:].strip()
    elif lowered.startswith("/f"):
        stripped = stripped[2:].strip()
    if not stripped:
        return "❌ Please provide feedback text after .f"
    result = prepend_feedback(stripped, source="cli.fast_path")
    if not result.get("ok"):
        return "❌ Unable to save feedback."
    return "✓ Feedback captured."


def _fast_create_task(input_text: str) -> str:
    # remove explicit .t / /t prefix if present
    stripped = (input_text or "").strip()
    lowered = stripped.lower()
    if lowered.startswith(".t "):
        stripped = stripped[3:].strip()
    elif lowered.startswith("/t "):
        stripped = stripped[3:].strip()
    parsed = parse_task(stripped)
    name = (parsed.name or "").strip()
    if not name:
        return "❌ Please provide a task description after .t"
    result = get_mcp_server().call_tool(
        "tasks.create",
        {
            "name": name,
            "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
            "due_time": parsed.due_time.isoformat() if parsed.due_time else None,
            "importance": parsed.importance,
            "tags": parsed.tags,
            "recurrence_rule": parsed.recurrence_rule,
        },
        context={"source": "cli.fast_path"},
    )
    if not result.get("ok"):
        return "❌ Unable to create task."
    task_payload = (result.get("result") or {}).get("task") or {}
    return f"✓ Created task #{task_payload.get('id')}: {task_payload.get('name', name)}"


def _resolve_task_id(parsed) -> int | None:
    if parsed.target_id:
        return int(parsed.target_id)
    if parsed.target_name:
        resolution = resolve_task_target(parsed.target_name, include_done=True)
        selected = resolution.get("selected_task")
        if selected and getattr(selected, "id", None):
            return int(selected.id)
    return None


def _fast_complete_or_skip(parsed, *, op: str) -> str:
    task_id = _resolve_task_id(parsed)
    if task_id is None:
        return f"❌ Could not resolve task target for {op}."
    tool = "tasks.complete" if op == "complete" else "tasks.skip"
    result = get_mcp_server().call_tool(tool, {"task_id": task_id}, context={"source": "cli.fast_path"})
    if not result.get("ok"):
        return f"❌ {op.capitalize()} failed."
    payload = result.get("result") or {}
    task_payload = payload.get("task") or {}
    if op == "complete":
        return f"✓ Completed: {task_payload.get('name', f'task #{task_id}')}"
    return f"⏭️ Skipped: {task_payload.get('name', f'task #{task_id}')}"


def _fast_delete(parsed) -> str:
    task_id = _resolve_task_id(parsed)
    if task_id is None:
        return "❌ Could not resolve task target for delete."
    server = get_mcp_server()
    preview = server.call_tool("tasks.preview_delete", {"task_id": task_id}, context={"source": "cli.fast_path"})
    if not preview.get("ok"):
        return "❌ Unable to preview delete."
    preview_id = (preview.get("result") or {}).get("preview_id")
    commit = server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview_id, "approved": True},
        context={"source": "cli.fast_path"},
    )
    if not commit.get("ok"):
        return "❌ Delete failed."
    return f"🗑️ Deleted task #{task_id}"


def _agentic_fallback(text: str) -> str:
    from .agent.chat_orchestrator import process_chat_message

    result = process_chat_message(text, source="cli")
    return str(result.get("response") or "✓ Done")


def handle_input(text: str, log: MessageLog | None = None) -> bool:
    text = (text or "").strip()
    if not text:
        return True
    lower = text.lower()

    if lower in {"quit", "exit", "q"}:
        if log:
            log.set_parsed("QUIT", {})
            log.set_action("exit")
            log.set_result(True)
        return False
    if lower == "help":
        _print_help()
        if log:
            log.set_parsed("HELP", {})
            log.set_action("show_help")
            log.set_result(True)
        return True
    if lower == "config":
        for k, v in Config.get_all().items():
            print(f"  {k}: {v}")
        if log:
            log.set_parsed("CONFIG", {})
            log.set_action("show_config")
            log.set_result(True)
        return True
    if lower == "status":
        print("\n🤖 Noctem v0.9.4 Status\n")
        print(f"  • Due today: {len(task_service.get_tasks_due_today())}")
        print(f"  • Overdue: {len(task_service.get_overdue_tasks())}")
        print(f"  • Inbox: {len(task_service.get_inbox_tasks())}")
        print("  • Voice processing: transcription-only")
        if log:
            log.set_parsed("STATUS", {})
            log.set_action("show_status")
            log.set_result(True)
        return True
    if lower.startswith("set "):
        parts = text[4:].split(maxsplit=1)
        if len(parts) == 2:
            key = parts[0]
            try:
                val = json.loads(parts[1])
            except Exception:
                val = parts[1]
            Config.set(key, val)
            print(f"✓ Set {key}")
            if log:
                log.set_parsed("SET_CONFIG", {"key": key})
                log.set_action("set_config")
                log.set_result(True)
        return True

    parsed = parse_command(text)
    if log:
        log.set_parsed(parsed.type.name, {"args": parsed.args, "target_id": parsed.target_id, "target_name": parsed.target_name})

    if parsed.type == CommandType.PROJECTS:
        projects = project_service.get_active_projects()
        if not projects:
            print("No projects.")
        else:
            for p in projects:
                print(f"  • {p.name}")
        if log:
            log.set_action("list_projects")
            log.set_result(True)
        return True

    if parsed.type == CommandType.GOALS:
        goals = goal_service.get_all_goals()
        if not goals:
            print("No goals.")
        else:
            for g in goals:
                print(f"  • {g.name}")
        if log:
            log.set_action("list_goals")
            log.set_result(True)
        return True

    if parsed.type == CommandType.PROJECT:
        name = " ".join(parsed.args).strip()
        if not name:
            print("Usage: .p <name> or /project <name>")
            return True
        project = project_service.create_project(name)
        print(f"✓ Created project: {project.name}")
        if log:
            log.set_action("create_project")
            log.set_result(True, {"project_id": project.id})
        return True

    if parsed.type == CommandType.GOAL:
        name = " ".join(parsed.args).strip()
        if not name:
            print("Usage: .g <name> or /goal <name>")
            return True
        goal = goal_service.create_goal(name)
        print(f"✓ Created goal: {goal.name}")
        if log:
            log.set_action("create_goal")
            log.set_result(True, {"goal_id": goal.id})
        return True

    if parsed.type == CommandType.DONE:
        msg = _fast_complete_or_skip(parsed, op="complete")
        print(msg)
        if log:
            log.set_action("fast_complete")
            log.set_result(not msg.startswith("❌"))
        return True
    if parsed.type == CommandType.SKIP:
        msg = _fast_complete_or_skip(parsed, op="skip")
        print(msg)
        if log:
            log.set_action("fast_skip")
            log.set_result(not msg.startswith("❌"))
        return True
    if parsed.type == CommandType.DELETE:
        msg = _fast_delete(parsed)
        print(msg)
        if log:
            log.set_action("fast_delete")
            log.set_result(not msg.startswith("❌"))
        return True

    if parsed.type == CommandType.FEEDBACK:
        msg = _fast_feedback(text)
        print(msg)
        if log:
            log.set_action("fast_feedback")
            log.set_result(not msg.startswith("❌"))
        return True

    # Fast-path .t only; all other NEW_TASK text goes through agentic runtime.
    if parsed.type == CommandType.NEW_TASK and (text.lower().startswith(".t ") or text.lower().startswith("/t ")):
        msg = _fast_create_task(text)
        print(msg)
        if log:
            log.set_action("fast_create")
            log.set_result(not msg.startswith("❌"))
        return True

    response = _agentic_fallback(text)
    print(response)
    if log:
        log.set_action("chat_orchestrator")
        log.set_result(True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Noctem CLI v0.9.4")
    parser.add_argument("mode", nargs="?", default="normal")
    args = parser.parse_args()

    init_db()
    print("🌙 Noctem CLI v0.9.4")
    print("Type 'help' for commands, 'quit' to exit.\n")

    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        with MessageLog(text, source="cli") as log:
            if not handle_input(text, log):
                break


if __name__ == "__main__":
    main()
