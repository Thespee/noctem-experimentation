#!/usr/bin/env python3
"""
CLI interface for Noctem - for testing without Telegram.
"""
import sys
from datetime import date

# readline for command history (optional on Windows)
try:
    import readline
except ImportError:
    # Windows doesn't have readline, try pyreadline3 or skip
    try:
        import pyreadline3 as readline
    except ImportError:
        pass  # No readline support, but CLI still works

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
Noctem CLI v0.6.0

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
  
  status          Show system status (butler, slow mode, LLM)
  suggest         Show AI suggestions for tasks/projects
  slow            Show slow mode queue status
  slow process    Force process slow mode queue
  
  load <file>     Load seed data from JSON file
  export [file]   Export data to JSON (default: stdout)
  seed            Paste natural language seed data (interactive)
  
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
    
    # v0.6.0: Status command
    if text_lower == 'status':
        from .slow.loop import get_slow_mode_status_message
        from .butler.protocol import get_butler_status
        from .slow.ollama import OllamaClient
        
        if log:
            log.set_parsed("STATUS", {})
            log.set_action("show_status")
            log.set_result(True)
        
        print("\n🤖 Noctem v0.6.0 Status\n")
        
        # Butler status
        butler = get_butler_status()
        print("Butler Protocol:")
        print(f"  • Contacts remaining: {butler['remaining']}/{butler['budget']} this week")
        print(f"  • Update contacts: {butler['updates_remaining']}")
        print(f"  • Clarification contacts: {butler['clarifications_remaining']}")
        print()
        
        # Slow mode status
        print("Slow Mode:")
        print(f"  {get_slow_mode_status_message()}")
        print()
        
        # Ollama status
        client = OllamaClient()
        healthy, msg = client.health_check()
        status_emoji = "✅" if healthy else "❌"
        print(f"Ollama LLM: {status_emoji} {msg}")
        return True
    
    # v0.6.0: Suggest command
    if text_lower == 'suggest':
        if log:
            log.set_parsed("SUGGEST", {})
            log.set_action("show_suggestions")
            log.set_result(True)
        
        tasks = task_service.get_tasks_with_suggestions(limit=5)
        projects = project_service.get_projects_with_suggestions(limit=3)
        
        if not tasks and not projects:
            print("\n💡 No suggestions yet.")
            print("Suggestions are generated in the background when Ollama is available.")
            return True
        
        print("\n💡 AI Suggestions\n")
        
        if tasks:
            print("Tasks - What could a computer help with?")
            for t in tasks:
                print(f"  • {t.name}")
                print(f"    → {t.computer_help_suggestion}")
            print()
        
        if projects:
            print("Projects - What should you do next?")
            for p in projects:
                print(f"  • {p.name}")
                print(f"    → {p.next_action_suggestion}")
        return True
    
    # v0.6.0: Slow mode commands
    if text_lower == 'slow' or text_lower == 'slow status':
        from .slow.queue import SlowWorkQueue
        from .slow.loop import get_slow_mode_status_message
        
        if log:
            log.set_parsed("SLOW_STATUS", {})
            log.set_action("show_slow_status")
            log.set_result(True)
        
        print("\n⏳ Slow Mode Queue\n")
        print(get_slow_mode_status_message())
        
        queue = SlowWorkQueue()
        pending = queue.get_pending_items(limit=10)
        
        if pending:
            print(f"\nPending items ({len(pending)}):")
            for item in pending:
                print(f"  • [{item['work_type']}] {item['entity_type']} #{item['entity_id']}")
        else:
            print("\nQueue is empty.")
        return True
    
    if text_lower == 'slow process':
        from .slow.loop import SlowModeLoop
        from .slow.ollama import OllamaClient
        
        if log:
            log.set_parsed("SLOW_PROCESS", {})
            log.set_action("force_slow_process")
        
        client = OllamaClient()
        healthy, msg = client.health_check()
        
        if not healthy:
            print(f"❌ Cannot process: Ollama unavailable - {msg}")
            if log:
                log.set_result(False, {"error": "ollama_unavailable"})
            return True
        
        print("⏳ Processing slow mode queue...")
        loop = SlowModeLoop()
        count = loop.process_queue_once()
        print(f"✓ Processed {count} items")
        if log:
            log.set_result(True, {"processed": count})
        return True
    
    # Seed data: load command
    if text_lower.startswith('load '):
        from .seed.loader import load_seed_file, load_seed_data, ConflictAction
        import json
        
        filepath = text[5:].strip().strip('"').strip("'")
        if not filepath:
            print("Usage: load <file.json>")
            return True
        
        if log:
            log.set_parsed("LOAD_SEED", {"file": filepath})
            log.set_action("load_seed_data")
        
        try:
            data = load_seed_file(filepath)
        except FileNotFoundError:
            print(f"❌ File not found: {filepath}")
            if log:
                log.set_result(False, {"error": "file_not_found"})
            return True
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            if log:
                log.set_result(False, {"error": "invalid_json"})
            return True
        
        # Windows-style conflict resolver
        def cli_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
            print(f"\n⚠️  Conflict: {entity_type} '{name}' already exists (id={existing_id})")
            print("  [S]kip  [O]verwrite  [R]ename  [A]ll skip  [W]rite all")
            while True:
                choice = input("  Choice: ").strip().lower()
                if choice in ('s', 'skip'):
                    return ConflictAction.SKIP
                elif choice in ('o', 'overwrite'):
                    return ConflictAction.OVERWRITE
                elif choice in ('r', 'rename'):
                    return ConflictAction.RENAME
                elif choice in ('a', 'all skip'):
                    return ConflictAction.SKIP_ALL
                elif choice in ('w', 'write all'):
                    return ConflictAction.OVERWRITE_ALL
                print("  Invalid choice. Try: s/o/r/a/w")
        
        print(f"\n📦 Loading seed data from: {filepath}")
        stats = load_seed_data(data, conflict_resolver=cli_resolver)
        
        print("\n" + stats.summary())
        if stats.errors:
            print("\nErrors:")
            for err in stats.errors[:5]:
                print(f"  • {err}")
            if len(stats.errors) > 5:
                print(f"  ... and {len(stats.errors) - 5} more")
        
        if log:
            log.set_result(len(stats.errors) == 0, {
                "goals": stats.goals_created,
                "projects": stats.projects_created,
                "tasks": stats.tasks_created,
                "errors": len(stats.errors)
            })
        return True
    
    # Seed data: natural language input
    if text_lower == 'seed':
        from .seed.text_parser import parse_natural_seed_text
        from .seed.loader import load_seed_data, ConflictAction
        
        if log:
            log.set_parsed("SEED_TEXT", {})
            log.set_action("load_seed_text")
        
        print("\n📝 Paste your seed data below (Goals:, Projects by goal:, Tasks by Project:, etc.)")
        print("   End with a blank line followed by 'done' or press Ctrl+C to cancel.\n")
        
        lines = []
        try:
            while True:
                line = input()
                if line.strip().lower() == 'done' and lines and not lines[-1].strip():
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return True
        
        text = '\n'.join(lines)
        if not text.strip():
            print("No data provided.")
            return True
        
        # Parse natural language format
        data = parse_natural_seed_text(text)
        
        print(f"\n📦 Parsed: {len(data['goals'])} goals, {len(data['projects'])} projects, {len(data['tasks'])} tasks, {len(data['calendar_urls'])} calendars")
        
        # Windows-style conflict resolver
        def cli_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
            print(f"\n⚠️  Conflict: {entity_type} '{name}' already exists (id={existing_id})")
            print("  [S]kip  [O]verwrite  [R]ename  [A]ll skip  [W]rite all")
            while True:
                choice = input("  Choice: ").strip().lower()
                if choice in ('s', 'skip'):
                    return ConflictAction.SKIP
                elif choice in ('o', 'overwrite'):
                    return ConflictAction.OVERWRITE
                elif choice in ('r', 'rename'):
                    return ConflictAction.RENAME
                elif choice in ('a', 'all skip'):
                    return ConflictAction.SKIP_ALL
                elif choice in ('w', 'write all'):
                    return ConflictAction.OVERWRITE_ALL
                print("  Invalid choice. Try: s/o/r/a/w")
        
        stats = load_seed_data(data, conflict_resolver=cli_resolver)
        
        print("\n" + stats.summary())
        if stats.errors:
            print("\nErrors:")
            for err in stats.errors[:5]:
                print(f"  • {err}")
        
        if log:
            log.set_result(len(stats.errors) == 0)
        return True
    
    # Seed data: export command
    if text_lower == 'export' or text_lower.startswith('export '):
        from .seed.loader import export_seed_data
        import json
        
        parts = text.split(maxsplit=1)
        filepath = parts[1].strip().strip('"').strip("'") if len(parts) > 1 else None
        
        if log:
            log.set_parsed("EXPORT_SEED", {"file": filepath})
            log.set_action("export_seed_data")
        
        data = export_seed_data(include_tasks=True, include_done_tasks=False)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"✓ Exported to: {filepath}")
            print(f"  {len(data.get('goals', []))} goals, {len(data.get('projects', []))} projects, {len(data.get('tasks', []))} tasks")
        else:
            print(json_str)
        
        if log:
            log.set_result(True, {"goals": len(data.get('goals', [])), "projects": len(data.get('projects', [])), "tasks": len(data.get('tasks', []))})
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
    print("🌙 Noctem CLI v0.6.0")
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
