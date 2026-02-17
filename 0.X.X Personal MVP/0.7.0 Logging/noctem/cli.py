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
from .services import task_service, project_service, goal_service
from .services.briefing import generate_morning_briefing, generate_today_view, generate_week_view
from .services.message_logger import MessageLog
from .session import get_session, SessionMode
from .handlers.interactive import (
    start_prioritize_mode, handle_prioritize_input,
    start_update_mode, handle_update_input,
    handle_correction,
)
from .fast.capture import process_input, get_pending_voice_confirmations
from .fast.classifier import ThoughtKind


def print_help():
    print("""
Noctem CLI v0.6.1

Commands:
  today           Show morning briefing
  week            Show week view
  projects        List projects
  goals           List goals
  
  done <n|name>   Mark task done
  skip <n|name>   Defer to tomorrow
  delete <name>   Delete task (or 'remove')
  
  /project <name> Create project
  /goal <name>    Create goal
  /prioritize <n> Reorder top n tasks
  /update <n>     Fill in missing info for n items
  
  * <update>      Update last created item (e.g., '* tomorrow !1')
  
  status          Show system status (butler, slow mode, LLM)
  suggest         Show AI suggestions for tasks/projects
  slow            Show slow mode queue status
  slow process    Force process slow mode queue
  
  /summon <msg>   Talk directly to Butler (bypasses fast mode)
  
  maintenance models    Discover and benchmark available models
  maintenance scan      Run full maintenance scan
  maintenance insights  View pending insights
  maintenance report    Preview maintenance report
  
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
    
    # v0.6.1: Summon command
    if text_lower.startswith('/summon') or text_lower.startswith('summon '):
        from .butler.summon import handle_summon
        
        # Extract message after /summon or summon
        if text_lower.startswith('/summon'):
            message = text[7:].strip()
        else:
            message = text[7:].strip()
        
        if log:
            log.set_parsed("SUMMON", {"message": message})
            log.set_action("summon")
        
        response, metadata = handle_summon(message, source="cli")
        print(response)
        
        if log:
            log.set_result(True, metadata)
        return True
    
    # v0.6.1: Maintenance commands
    if text_lower.startswith('maintenance'):
        from .maintenance.scanner import (
            run_maintenance_scan, preview_maintenance_report, 
            get_scanner, get_maintenance_summary
        )
        from .slow.model_registry import get_registry, get_current_model_status
        
        parts = text_lower.split()
        subcommand = parts[1] if len(parts) > 1 else "help"
        
        if log:
            log.set_parsed("MAINTENANCE", {"subcommand": subcommand})
            log.set_action(f"maintenance_{subcommand}")
        
        if subcommand == "models":
            print("\n🔍 Discovering and benchmarking models...")
            registry = get_registry()
            
            # Check if Ollama is available
            from .slow.ollama import OllamaClient
            client = OllamaClient()
            if not client.check_health():
                print("❌ Ollama not available. Start with: ollama serve")
                if log:
                    log.set_result(False, {"error": "ollama_unavailable"})
                return True
            
            models = registry.discover_models()
            print(f"Found {len(models)} models\n")
            
            for model in models:
                print(f"Benchmarking {model.name}...")
                info = registry.benchmark_and_save(model.name, model.backend)
                if info:
                    status_emoji = "✅" if info.health == "ok" else "🐢" if info.health == "slow" else "❌"
                    print(f"  {status_emoji} {info.name}: {info.tokens_per_sec or '?'} tok/s")
                    if info.family:
                        print(f"     Family: {info.family}, Size: {info.parameter_size or '?'}")
            
            print("\n✓ Model registry updated")
            if log:
                log.set_result(True, {"models_found": len(models)})
        
        elif subcommand == "scan":
            print("\n🔧 Running full maintenance scan...")
            insights = run_maintenance_scan("full")
            print(f"\n✓ Scan complete: {len(insights)} insights generated")
            
            if insights:
                print("\nInsights:")
                for i in insights:
                    priority_emoji = "⚠️" if i.priority >= 4 else "💡"
                    print(f"  {priority_emoji} [{i.insight_type}] {i.title}")
            if log:
                log.set_result(True, {"insights": len(insights)})
        
        elif subcommand == "insights":
            scanner = get_scanner()
            insights = scanner.get_pending_insights()
            
            if not insights:
                print("\n✅ No pending insights")
            else:
                print(f"\n📋 Pending Insights ({len(insights)})\n")
                for i in insights:
                    priority_emoji = "⚠️" if i.priority >= 4 else "💡" if i.priority >= 2 else "📝"
                    print(f"  {priority_emoji} #{i.id}: {i.title}")
                    print(f"     Type: {i.insight_type}, Source: {i.source}")
            if log:
                log.set_result(True, {"pending": len(insights)})
        
        elif subcommand == "report":
            print("\n" + preview_maintenance_report())
            if log:
                log.set_result(True)
        
        else:
            print("""
🔧 Maintenance Commands

  maintenance models    Discover and benchmark available models
  maintenance scan      Run full maintenance scan
  maintenance insights  View pending insights
  maintenance report    Preview maintenance report (without sending)
""")
            if log:
                log.set_result(True)
        
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
    
    elif cmd.type == CommandType.NEW_TASK:
        # Use thoughts-first capture system (royal scribe pattern)
        result = process_input(text, source="cli")
        
        if log:
            log.set_action(f"capture_{result.kind.value}")
            log.set_result(True, {
                "thought_id": result.thought_id,
                "kind": result.kind.value,
                "confidence": result.confidence,
                "task_id": result.task.id if result.task else None,
            })
        
        print(result.response)
    
    return True


def show_thinking_feed(limit: int = 10):
    """Display recent thinking feed entries."""
    try:
        from .services.conversation_service import get_thinking_feed
        entries = get_thinking_feed(limit=limit, level_filter='activity')
        
        if not entries:
            print("  No recent system activity")
            return
        
        for e in reversed(entries):  # Show oldest first
            timestamp = e.created_at.strftime("%H:%M:%S") if e.created_at else "--:--:--"
            level_marker = "🔸" if e.thinking_level == "decision" else "  "
            source = e.source or "system"
            summary = e.thinking_summary or e.content or ""
            print(f"  {level_marker}[{timestamp}] {source}: {summary[:60]}")
    except Exception as ex:
        print(f"  (thinking feed unavailable: {ex})")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Noctem CLI v0.6.0")
    parser.add_argument('mode', nargs='?', default='normal', 
                        help="Mode: 'all' for verbose output, 'quiet' for minimal")
    args = parser.parse_args()
    
    verbose = args.mode.lower() == 'all'
    quiet = args.mode.lower() == 'quiet'
    
    if not quiet:
        print("🌙 Noctem CLI v0.6.0")
        if verbose:
            print("  Verbose mode enabled - showing system thinking")
        print("Type 'help' for commands, 'quit' to exit.\n")
    
    init_db()
    
    if not quiet:
        print(generate_today_view())
        print()
    
    # Show thinking feed on verbose startup
    if verbose:
        print("\n🧠 Recent System Activity:")
        show_thinking_feed(limit=15)
        print()
    
    while True:
        try:
            prompt = "noctem> " if not quiet else "> "
            text = input(prompt)
            with MessageLog(text, source="cli") as log:
                if not handle_input(text, log):
                    if not quiet:
                        print("Goodbye!")
                    break
                
                # Show thinking update in verbose mode
                if verbose and text.strip():
                    print("  🧠 thinking...")
                    show_thinking_feed(limit=3)
        except (KeyboardInterrupt, EOFError):
            if not quiet:
                print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
