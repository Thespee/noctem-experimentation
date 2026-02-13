#!/usr/bin/env python3
"""
CLI interface for Noctem - for testing without Telegram.
"""
import sys
import readline
from datetime import date

from .db import init_db
from .config import Config
from .parser.task_parser import parse_task, format_task_confirmation
from .parser.command import parse_command, CommandType
from .services import task_service, habit_service, project_service, goal_service
from .services.briefing import generate_morning_briefing, generate_today_view, generate_week_view
from .services.message_logger import MessageLog
from .session import get_session, SessionMode
from .handlers.interactive import (
    start_prioritize_mode, handle_prioritize_input,
    start_update_mode, handle_update_input,
    handle_correction,
)


def print_help():
    print("""
Noctem CLI

Commands:
  today           Show morning briefing
  week            Show week view
  projects        List projects
  habits          Show habit status
  goals           List goals
  
  done <n|name>   Mark task done
  skip <n|name>   Defer to tomorrow
  delete <name>   Delete task (or 'remove')
  habit done <n>  Log habit
  
  /project <name> Create project
  /habit <name>   Create habit
  /goal <name>    Create goal
  /prioritize <n> Reorder top n tasks
  /update <n>     Fill in missing info for n items
  
  * <update>      Update last created item (e.g., '* tomorrow !1')
  
  config          Show config
  set <key> <val> Set config
  
  help            This help
  quit            Exit
""")


def handle_input(text: str, log: MessageLog = None) -> bool:
    text = text.strip()
    if not text:
        return True
    
    session = get_session()
    text_lower = text.lower()
    
    # Handle interactive modes first
    if session.mode == SessionMode.PRIORITIZE:
        response, exited = handle_prioritize_input(text)
        print(response)
        if log:
            log.set_parsed("PRIORITIZE_INPUT", {"input": text})
            log.set_action("prioritize_mode")
            log.set_result(True)
        return True
    
    if session.mode == SessionMode.UPDATE:
        response, exited = handle_update_input(text)
        print(response)
        if log:
            log.set_parsed("UPDATE_INPUT", {"input": text})
            log.set_action("update_mode")
            log.set_result(True)
        return True
    
    if text_lower in ('quit', 'exit', 'q'):
        if log:
            log.set_parsed("QUIT", {})
            log.set_action("exit")
            log.set_result(True)
        return False
    
    if text_lower == 'help':
        if log:
            log.set_parsed("HELP", {})
            log.set_action("show_help")
            log.set_result(True)
        print_help()
        return True
    
    if text_lower == 'config':
        if log:
            log.set_parsed("CONFIG", {})
            log.set_action("show_config")
            log.set_result(True)
        for k, v in Config.get_all().items():
            print(f"  {k}: {v}")
        return True
    
    if text_lower.startswith('set '):
        parts = text[4:].split(maxsplit=1)
        if len(parts) == 2:
            import json
            try:
                val = json.loads(parts[1])
            except:
                val = parts[1]
            Config.set(parts[0], val)
            if log:
                log.set_parsed("SET_CONFIG", {"key": parts[0], "value": val})
                log.set_action(f"set_config:{parts[0]}")
                log.set_result(True)
            print(f"✓ Set {parts[0]}")
        return True
    
    if text_lower.startswith('/goal '):
        name = text[6:].strip()
        if name:
            goal = goal_service.create_goal(name)
            if log:
                log.set_parsed("GOAL", {"name": name})
                log.set_action("create_goal")
                log.set_result(True, {"goal_id": goal.id})
            print(f"✓ Created goal: {goal.name}")
        return True
    
    cmd = parse_command(text)
    if log:
        log.set_parsed(cmd.type.name, {
            "target_id": cmd.target_id,
            "target_name": cmd.target_name,
            "args": cmd.args
        })
    
    if cmd.type == CommandType.TODAY:
        if log:
            log.set_action("show_today")
            log.set_result(True)
        print(generate_morning_briefing())
    
    elif cmd.type == CommandType.WEEK:
        if log:
            log.set_action("show_week")
            log.set_result(True)
        print(generate_week_view())
    
    elif cmd.type == CommandType.PROJECTS:
        if log:
            log.set_action("list_projects")
            log.set_result(True)
        projects = project_service.get_active_projects()
        if not projects:
            print("No projects. Create with: /project <name>")
        else:
            for p in projects:
                tasks = task_service.get_project_tasks(p.id)
                print(f"  • {p.name} ({len(tasks)} tasks)")
    
    elif cmd.type == CommandType.HABITS:
        if log:
            log.set_action("list_habits")
            log.set_result(True)
        stats = habit_service.get_all_habits_stats()
        if not stats:
            print("No habits. Create with: /habit <name>")
        else:
            for s in stats:
                done = "✓" if s["done_today"] else "○"
                streak = f"🔥{s['streak']}" if s["streak"] > 0 else ""
                print(f"  {done} {s['name']} ({s['completions_this_week']}/{s['target_this_week']}) {streak}")
    
    elif cmd.type == CommandType.GOALS:
        if log:
            log.set_action("list_goals")
            log.set_result(True)
        goals = goal_service.get_all_goals()
        if not goals:
            print("No goals.")
        else:
            for g in goals:
                print(f"  • {g.name}")
    
    elif cmd.type == CommandType.PROJECT:
        if cmd.args:
            project = project_service.create_project(" ".join(cmd.args))
            if log:
                log.set_action("create_project")
                log.set_result(True, {"project_id": project.id})
            print(f"✓ Created project: {project.name}")
        else:
            print("Usage: /project <name>")
    
    elif cmd.type == CommandType.HABIT:
        if cmd.args:
            habit = habit_service.create_habit(" ".join(cmd.args))
            if log:
                log.set_action("create_habit")
                log.set_result(True, {"habit_id": habit.id})
            session.set_last_entity("habit", habit.id)
            print(f"✓ Created habit: {habit.name}")
        else:
            print("Usage: /habit <name>")
    
    elif cmd.type == CommandType.PRIORITIZE:
        count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
        response = start_prioritize_mode(count)
        if log:
            log.set_action("start_prioritize")
            log.set_result(True, {"count": count})
        print(response)
    
    elif cmd.type == CommandType.UPDATE:
        count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
        response = start_update_mode(count)
        if log:
            log.set_action("start_update")
            log.set_result(True, {"count": count})
        print(response)
    
    elif cmd.type == CommandType.CORRECT:
        correction_text = cmd.args[0] if cmd.args else ""
        response = handle_correction(correction_text)
        if log:
            log.set_action("correct_last")
            log.set_result("✓" in response, {"correction": correction_text})
        print(response)
    
    elif cmd.type == CommandType.DONE:
        task = None
        if cmd.target_id:
            tasks = task_service.get_priority_tasks(10)
            if 1 <= cmd.target_id <= len(tasks):
                task = tasks[cmd.target_id - 1]
        elif cmd.target_name:
            task = task_service.get_task_by_name(cmd.target_name)
        
        if task:
            task_service.complete_task(task.id)
            if log:
                log.set_action("complete_task")
                log.set_result(True, {"task_id": task.id, "name": task.name})
            print(f"✓ Completed: {task.name}")
        else:
            if log:
                log.set_action("complete_task")
                log.set_result(False, {"error": "task_not_found"})
            print("❌ Task not found")
    
    elif cmd.type == CommandType.SKIP:
        task = None
        if cmd.target_id:
            tasks = task_service.get_priority_tasks(10)
            if 1 <= cmd.target_id <= len(tasks):
                task = tasks[cmd.target_id - 1]
        elif cmd.target_name:
            task = task_service.get_task_by_name(cmd.target_name)
        
        if task:
            task_service.skip_task(task.id)
            if log:
                log.set_action("skip_task")
                log.set_result(True, {"task_id": task.id, "name": task.name})
            print(f"⏭️ Skipped: {task.name}")
        else:
            if log:
                log.set_action("skip_task")
                log.set_result(False, {"error": "task_not_found"})
            print("❌ Task not found")
    
    elif cmd.type == CommandType.DELETE:
        task = task_service.get_task_by_name(cmd.target_name) if cmd.target_name else None
        if task:
            task_service.delete_task(task.id)
            if log:
                log.set_action("delete_task")
                log.set_result(True, {"task_id": task.id, "name": task.name})
            print(f"🗑️ Deleted: {task.name}")
        else:
            if log:
                log.set_action("delete_task")
                log.set_result(False, {"error": "task_not_found"})
            print("❌ Task not found")
    
    elif cmd.type == CommandType.HABIT_DONE:
        habit = habit_service.get_habit_by_name(cmd.target_name)
        if habit:
            habit_service.log_habit(habit.id)
            stats = habit_service.get_habit_stats(habit.id)
            if log:
                log.set_action("log_habit")
                log.set_result(True, {"habit_id": habit.id, "name": habit.name})
            streak = f"🔥 {stats['streak']}!" if stats['streak'] > 0 else ""
            print(f"✓ Logged: {habit.name} {streak}")
        else:
            if log:
                log.set_action("log_habit")
                log.set_result(False, {"error": "habit_not_found"})
            print("❌ Habit not found")
    
    elif cmd.type == CommandType.NEW_TASK:
        parsed = parse_task(text)
        if not parsed.name:
            if log:
                log.set_action("create_task")
                log.set_result(False, {"error": "parse_failed"})
            print("Couldn't parse task.")
            return True
        
        project_id = None
        if parsed.project_name:
            project = project_service.get_project_by_name(parsed.project_name)
            if project:
                project_id = project.id
        
        task = task_service.create_task(
            name=parsed.name,
            project_id=project_id,
            due_date=parsed.due_date,
            due_time=parsed.due_time,
            importance=parsed.importance,
            tags=parsed.tags,
            recurrence_rule=parsed.recurrence_rule,
        )
        session.set_last_entity("task", task.id)
        if log:
            log.set_action("create_task")
            log.set_result(True, {
                "task_id": task.id,
                "name": task.name,
                "due_date": str(parsed.due_date) if parsed.due_date else None,
                "importance": parsed.importance,
                "project": parsed.project_name
            })
        print(format_task_confirmation(parsed))
    
    return True


def main():
    print("🌙 Noctem CLI v0.5")
    print("Type 'help' for commands, 'quit' to exit.\n")
    
    init_db()
    print(generate_today_view())
    print()
    
    while True:
        try:
            text = input("noctem> ")
            with MessageLog(text, source="cli") as log:
                if not handle_input(text, log):
                    print("Goodbye!")
                    break
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
