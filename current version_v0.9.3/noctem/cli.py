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
  
  status          Show lean runtime status
  suggest         Legacy command (removed in v0.9.3)
  slow            Legacy command (removed in v0.9.3)
  /summon <msg>   Legacy command (removed in v0.9.3)
  maintenance ... Legacy commands (removed in v0.9.3)
  skill ...       Legacy commands (removed in v0.9.3)
  
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
    
    # v0.9.3: Status command
    if text_lower == 'status':
        if log:
            log.set_parsed("STATUS", {})
            log.set_action("show_status")
            log.set_result(True)
        
        today_tasks = task_service.get_tasks_due_today()
        overdue_tasks = task_service.get_overdue_tasks()
        inbox_tasks = task_service.get_inbox_tasks()
        print("\n🤖 Noctem v0.9.3 Status\n")
        print(f"  • Due today: {len(today_tasks)}")
        print(f"  • Overdue: {len(overdue_tasks)}")
        print(f"  • Inbox: {len(inbox_tasks)}")
        print("  • Voice transcription: enabled")
        print("\n  Legacy butler/slow/skills runtimes are removed in v0.9.3.")
        return True
    
    # v0.9.3: Suggest command (legacy)
    if text_lower == 'suggest':
        if log:
            log.set_parsed("SUGGEST", {})
            log.set_action("show_suggestions")
            log.set_result(True)
        print("\n⚠️ suggest is removed in v0.9.3.")
        print("Legacy AI suggestion surfaces were stripped from active runtime.")
        return True
    
    # v0.9.1: Wiki commands (via 'wiki ...' or '.w ...' or '/wiki ...')
    if text_lower.startswith('wiki '):
        return handle_wiki_command(text[5:].strip(), log)
    
    # v0.9.3: Skill commands (legacy)
    if text_lower.startswith('skill '):
        if log:
            log.set_parsed("SKILL", {"raw": text})
            log.set_action("skill_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ skill commands are removed in v0.9.3.")
        return True
    
    # v0.9.3: Slow mode commands (legacy)
    if text_lower == 'slow' or text_lower == 'slow status':
        if log:
            log.set_parsed("SLOW_STATUS", {})
            log.set_action("slow_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ slow mode processing was removed from active runtime in v0.9.3.")
        return True
    
    if text_lower == 'slow process':
        if log:
            log.set_parsed("SLOW_PROCESS", {})
            log.set_action("slow_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ slow process is removed in v0.9.3.")
        return True
    
    # v0.6.1: Summon command (legacy location — now handled above via parse_command routing)
    
    # v0.9.3: Maintenance commands (legacy)
    if text_lower.startswith('maintenance'):
        if log:
            log.set_parsed("MAINTENANCE", {"raw": text})
            log.set_action("maintenance_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ maintenance commands are removed in v0.9.3.")
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
    
    # v0.6.1: Summon command (handle before parse_command to preserve raw text)
    if text_lower.startswith('/summon') or text_lower.startswith('summon ') or text_lower.startswith('.summon'):
        if log:
            log.set_parsed("SUMMON", {"raw": text})
            log.set_action("summon_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ summon is removed in v0.9.3.")
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
    
    elif cmd.type in (CommandType.DONE, CommandType.SKIP, CommandType.DELETE, CommandType.NEW_TASK):
        from .agent.chat_orchestrator import process_chat_message

        chat_result = process_chat_message(text, source="cli")
        if log:
            log.set_action("chat_orchestrator")
            log.set_result(
                True,
                {
                    "mode": chat_result.get("mode"),
                    "thread_id": chat_result.get("thread_id"),
                    "workflow_id": chat_result.get("workflow_id"),
                    "status": chat_result.get("status"),
                    "intent": chat_result.get("intent"),
                    "intent_classifier": chat_result.get("intent_classifier"),
                    "intent_confidence": chat_result.get("intent_confidence"),
                },
            )
        print(chat_result.get("response", "✓ Done"))
    
    elif cmd.type == CommandType.WIKI:
        # Route to wiki handler (args already parsed by parse_command)
        wiki_args = " ".join(cmd.args) if cmd.args else ""
        return handle_wiki_command(wiki_args, log)
    
    elif cmd.type == CommandType.GOAL:
        if cmd.args:
            goal = goal_service.create_goal(" ".join(cmd.args))
            if log:
                log.set_action("create_goal")
                log.set_result(True, {"goal_id": goal.id})
            print(f"✓ Created goal: {goal.name}")
        else:
            print("Usage: .g <name> or /goal <name>")
    
    elif cmd.type == CommandType.SESSION:
        return handle_session_command(log)
    
    elif cmd.type == CommandType.SUMMON:
        if log:
            log.set_parsed("SUMMON", {"args": cmd.args})
            log.set_action("summon_removed")
            log.set_result(False, {"error": "removed_in_v093"})
        print("⚠️ summon is removed in v0.9.3.")
    
    return True


def handle_skill_command(args: str, log) -> bool:
    """
    Handle skill subcommands.
    
    Commands:
        list              - List all skills
        info <name>       - Show skill details
        run <name>        - Run a skill
        enable <name>     - Enable a skill
        disable <name>    - Disable a skill
        create <name>     - Create a new skill (interactive)
        validate <path>   - Validate a skill directory
    """
    if log:
        log.set_parsed("SKILL", {"raw": args})
        log.set_action("skill_removed")
        log.set_result(False, {"error": "removed_in_v093"})
    print("⚠️ skill commands are removed in v0.9.3.")
    return True
    
    # Initialize if needed
    if not service._initialized:
        service.initialize()
    
    if log:
        log.set_parsed("SKILL", {"subcommand": subcommand, "arg": skill_arg})
    
    if subcommand == "list":
        skills = service.list_skills(enabled_only=False)
        if log:
            log.set_action("skill_list")
            log.set_result(True, {"count": len(skills)})
        
        if not skills:
            print("\n🔧 No skills registered.")
            print("Use 'skill create <name>' to create one.")
            return True
        
        print("\n🔧 Skills\n")
        for s in skills:
            status = "✓" if s.enabled else "○"
            approval = " ⚠️" if s.requires_approval else ""
            uses = f" ({s.use_count} uses)" if s.use_count > 0 else ""
            print(f"  {status} {s.name}{approval} - {s.description[:40]}...{uses}")
        print(f"\n  Total: {len(skills)} skills")
        return True
    
    elif subcommand == "info":
        if not skill_arg:
            print("❌ Usage: skill info <name>")
            return True
        
        info = service.get_skill_info(skill_arg)
        if log:
            log.set_action("skill_info")
            log.set_result(info is not None, {"name": skill_arg})
        
        if not info:
            print(f"❌ Skill '{skill_arg}' not found")
            return True
        
        print(f"\n🔧 {info['name']} v{info['version']}")
        print(f"   Source: {info['source']}")
        print(f"   Enabled: {info['enabled']}")
        print(f"   Requires approval: {info['requires_approval']}")
        print(f"   Description: {info['description']}")
        print("   Triggers:")
        for t in info['triggers']:
            print(f"     • \"{t['pattern']}\" (threshold: {t['confidence_threshold']})")
        print(f"   Stats: {info['stats']['use_count']} uses, {info['stats']['success_rate']:.0f}% success" if info['stats']['success_rate'] else "   Stats: No usage yet")
        return True
    
    elif subcommand == "run":
        if not skill_arg:
            print("❌ Usage: skill run <name>")
            return True
        
        success, message = service.run_skill(skill_arg)
        if log:
            log.set_action("skill_run")
            log.set_result(success, {"name": skill_arg})
        
        if success:
            print(f"\n🔧 Running skill: {skill_arg}\n")
            print(message[:500])  # Show first 500 chars
            if len(message) > 500:
                print("\n... (truncated)")
        else:
            print(f"❌ {message}")
        return True
    
    elif subcommand == "enable":
        if not skill_arg:
            print("❌ Usage: skill enable <name>")
            return True
        
        success = service.enable_skill(skill_arg)
        if log:
            log.set_action("skill_enable")
            log.set_result(success, {"name": skill_arg})
        
        if success:
            print(f"✓ Enabled skill: {skill_arg}")
        else:
            print(f"❌ Skill '{skill_arg}' not found")
        return True
    
    elif subcommand == "disable":
        if not skill_arg:
            print("❌ Usage: skill disable <name>")
            return True
        
        success = service.disable_skill(skill_arg)
        if log:
            log.set_action("skill_disable")
            log.set_result(success, {"name": skill_arg})
        
        if success:
            print(f"✓ Disabled skill: {skill_arg}")
        else:
            print(f"❌ Skill '{skill_arg}' not found")
        return True
    
    elif subcommand == "create":
        if not skill_arg:
            print("❌ Usage: skill create <name>")
            return True
        
        # Interactive skill creation
        print(f"\n🔧 Creating skill: {skill_arg}\n")
        
        try:
            description = input("Description: ")
            instructions = input("Instructions (one line, or leave blank): ")
            if not instructions:
                instructions = f"Instructions for {skill_arg}"
            
            skill = service.create_skill(
                name=skill_arg,
                description=description,
                instructions=instructions,
            )
            
            if log:
                log.set_action("skill_create")
                log.set_result(skill is not None, {"name": skill_arg})
            
            if skill:
                print(f"\n✓ Created skill: {skill.name}")
                print(f"   Path: {skill.skill_path}")
                print("   Edit instructions.md to customize.")
            else:
                print("❌ Failed to create skill")
        except ValueError as e:
            print(f"❌ {e}")
        except (KeyboardInterrupt, EOFError):
            print("\n  Canceled")
        return True
    
    elif subcommand == "validate":
        if not skill_arg:
            print("❌ Usage: skill validate <path>")
            return True
        
        skill_path = Path(skill_arg)
        is_valid, errors = service.validate_skill(skill_path)
        
        if log:
            log.set_action("skill_validate")
            log.set_result(is_valid, {"path": skill_arg, "errors": errors})
        
        if is_valid:
            print(f"✓ Skill at '{skill_arg}' is valid")
        else:
            print(f"❌ Skill validation failed:")
            for e in errors:
                print(f"   • {e}")
        return True
    
    else:
        print(f"❌ Unknown skill command: {subcommand}")
        print("   Commands: list, info, run, enable, disable, create, validate")
        return True


def handle_wiki_command(args: str, log) -> bool:
    """
    Handle wiki subcommands.
    
    Commands:
        ingest [file]     - Ingest new sources (or specific file)
        search "query"    - Semantic search
        ask "question"    - Q&A with citations
        sources           - List indexed sources
        status            - Show wiki stats
        verify            - Check for changed source files
    """
    from pathlib import Path
    from .wiki.ingestion import (
        discover_new_sources, create_source, extract_text,
        update_source_status, list_sources, verify_source, get_source_by_path,
    )
    from .wiki.chunking import chunk_text, save_chunks
    from .wiki.embeddings import add_chunks_to_vectorstore, check_ollama_available
    from .wiki.retrieval import get_wiki_stats
    from .wiki.query import ask, simple_search, check_wiki_ready
    from .wiki import SOURCES_DIR
    
    parts = args.split(None, 1)
    subcommand = parts[0] if parts else "help"
    sub_arg = parts[1] if len(parts) > 1 else None
    
    if log:
        log.set_parsed("WIKI", {"subcommand": subcommand, "arg": sub_arg})
    
    if subcommand == "ingest":
        if log:
            log.set_action("wiki_ingest")
        
        # Check Ollama first
        ollama_ok, ollama_msg = check_ollama_available()
        if not ollama_ok:
            print(f"\n❌ {ollama_msg}")
            if log:
                log.set_result(False, {"error": "ollama_unavailable"})
            return True
        
        if sub_arg:
            # Ingest specific file
            file_path = Path(sub_arg).resolve()
            if not file_path.exists():
                # Try relative to sources dir
                file_path = SOURCES_DIR / sub_arg
            if not file_path.exists():
                print(f"❌ File not found: {sub_arg}")
                if log:
                    log.set_result(False, {"error": "file_not_found"})
                return True
            files_to_ingest = [file_path]
        else:
            # Discover all new files
            files_to_ingest = discover_new_sources()
            if not files_to_ingest:
                print("\n✅ No new files to ingest.")
                print(f"   Put files in: {SOURCES_DIR}")
                if log:
                    log.set_result(True, {"files": 0})
                return True
        
        print(f"\n📚 Ingesting {len(files_to_ingest)} file(s)...\n")
        success_count = 0
        
        for file_path in files_to_ingest:
            try:
                print(f"  Processing: {file_path.name}")
                
                # Check if already tracked
                existing = get_source_by_path(str(file_path.resolve()))
                if existing and existing.status == 'indexed':
                    print(f"    → Already indexed (skipping)")
                    continue
                
                # Create source record
                if not existing:
                    source = create_source(file_path)
                else:
                    source = existing
                
                # Extract text
                update_source_status(source.id, 'processing')
                text, metadata = extract_text(file_path)
                
                if not text.strip():
                    update_source_status(source.id, 'failed', error_message="No text extracted")
                    print(f"    → No text extracted (skipping)")
                    continue
                
                # Chunk text
                file_type = source.file_type or 'txt'
                chunks = chunk_text(text, file_type=file_type)
                
                if not chunks:
                    update_source_status(source.id, 'failed', error_message="No chunks generated")
                    print(f"    → No chunks generated (skipping)")
                    continue
                
                # Save chunks to DB
                db_chunks = save_chunks(source.id, chunks)
                
                # Add to vector store
                added = add_chunks_to_vectorstore(db_chunks)
                
                # Update source status
                update_source_status(source.id, 'indexed', chunk_count=len(db_chunks))
                
                print(f"    ✓ {len(db_chunks)} chunks indexed")
                success_count += 1
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
                try:
                    update_source_status(source.id, 'failed', error_message=str(e))
                except Exception:
                    pass
        
        print(f"\n✓ Ingested {success_count}/{len(files_to_ingest)} files")
        if log:
            log.set_result(True, {"files": success_count})
    
    elif subcommand == "search":
        if not sub_arg:
            print("Usage: wiki search \"your query\"")
            return True
        
        if log:
            log.set_action("wiki_search")
        
        query = sub_arg.strip('"').strip("'")
        print(f"\n🔍 Searching: {query}\n")
        
        try:
            results = simple_search(query)
            if not results:
                print("  No results found.")
                if log:
                    log.set_result(True, {"results": 0})
                return True
            
            for i, (content, citation, score) in enumerate(results, 1):
                print(f"  [{i}] {citation} (similarity: {score:.2f})")
                # Show first 200 chars of content
                snippet = content[:200].replace('\n', ' ')
                print(f"      {snippet}..." if len(content) > 200 else f"      {snippet}")
                print()
            
            if log:
                log.set_result(True, {"results": len(results)})
        except Exception as e:
            print(f"❌ Search error: {e}")
            if log:
                log.set_result(False, {"error": str(e)})
    
    elif subcommand == "ask":
        if not sub_arg:
            print("Usage: wiki ask \"your question\"")
            return True
        
        if log:
            log.set_action("wiki_ask")
        
        question = sub_arg.strip('"').strip("'")
        print(f"\n🤔 Asking: {question}\n")
        
        try:
            answer = ask(question)
            print(answer.formatted())
            print()
            
            if log:
                log.set_result(True, {
                    "has_answer": answer.has_answer,
                    "sources_used": len(answer.sources_used),
                    "model": answer.model_used,
                })
        except Exception as e:
            print(f"❌ Error: {e}")
            if log:
                log.set_result(False, {"error": str(e)})
    
    elif subcommand == "sources":
        if log:
            log.set_action("wiki_sources")
        
        trust_filter = None
        if sub_arg:
            # Parse --trust N
            try:
                trust_filter = int(sub_arg.replace('--trust', '').strip())
            except ValueError:
                pass
        
        sources = list_sources(trust_level=trust_filter)
        
        if not sources:
            print("\n📚 No sources indexed yet.")
            print(f"   Put files in: {SOURCES_DIR}")
            print("   Then run: wiki ingest")
        else:
            print(f"\n📚 Wiki Sources ({len(sources)})\n")
            trust_labels = {1: "personal", 2: "curated", 3: "web"}
            for s in sources:
                status_emoji = "✅" if s.status == 'indexed' else "⏳" if s.status == 'pending' else "❌"
                trust = trust_labels.get(s.trust_level, "?")
                chunks = f"{s.chunk_count} chunks" if s.chunk_count else "no chunks"
                print(f"  {status_emoji} {s.title or s.file_name} [{trust}] ({chunks})")
        
        if log:
            log.set_result(True, {"count": len(sources)})
    
    elif subcommand == "status":
        if log:
            log.set_action("wiki_status")
        
        stats = get_wiki_stats()
        ready, msg = check_wiki_ready()
        
        print(f"\n📊 Wiki Status\n")
        print(f"  {msg}\n")
        
        status_counts = stats.get("sources_by_status", {})
        if status_counts:
            print("  Sources:")
            for status, count in status_counts.items():
                emoji = "✅" if status == 'indexed' else "⏳" if status == 'pending' else "🔄" if status == 'changed' else "❌"
                print(f"    {emoji} {status}: {count}")
        
        print(f"\n  Total chunks: {stats.get('total_chunks', 0)}")
        
        trust_counts = stats.get("sources_by_trust", {})
        if trust_counts:
            trust_labels = {1: "personal", 2: "curated", 3: "web"}
            print("\n  By trust level:")
            for level, count in trust_counts.items():
                print(f"    {trust_labels.get(level, '?')}: {count}")
        
        if log:
            log.set_result(True, stats)
    
    elif subcommand == "verify":
        if log:
            log.set_action("wiki_verify")
        
        sources = list_sources(status='indexed')
        if not sources:
            print("\n✅ No indexed sources to verify.")
            if log:
                log.set_result(True, {"verified": 0})
            return True
        
        print(f"\n🔍 Verifying {len(sources)} source(s)...\n")
        changed = 0
        
        for source in sources:
            unchanged = verify_source(source)
            if unchanged:
                print(f"  ✅ {source.title or source.file_name}: unchanged")
            else:
                print(f"  ⚠️  {source.title or source.file_name}: CHANGED (re-ingest needed)")
                changed += 1
        
        if changed:
            print(f"\n⚠️  {changed} source(s) changed. Run 'wiki ingest' to re-index.")
        else:
            print(f"\n✅ All sources verified.")
        
        if log:
            log.set_result(True, {"verified": len(sources), "changed": changed})
    
    else:
        print("""
📚 Wiki Commands

  wiki ingest [file]     Ingest sources from data/sources/
  wiki search "query"    Semantic search across knowledge base
  wiki ask "question"    Ask a question (LLM-powered with citations)
  wiki sources           List all indexed sources
  wiki status            Show wiki statistics
  wiki verify            Check if source files have changed

Shortcut: .w <subcommand>
""")
        if log:
            log.set_action("wiki_help")
            log.set_result(True)
    
    return True


def handle_session_command(log) -> bool:
    """
    Handle feedback session initiation.
    Placeholder until feedback module is implemented.
    """
    if log:
        log.set_parsed("SESSION", {})
        log.set_action("session_removed")
        log.set_result(False, {"error": "removed_in_v093"})
    print("\n⏳ Feedback sessions are removed in v0.9.3.")
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
