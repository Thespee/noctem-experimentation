"""
Telegram message handlers.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..parser.command import parse_command, CommandType
from ..parser.task_parser import parse_task, format_task_confirmation
from ..services import task_service, project_service, goal_service
from ..services.briefing import generate_morning_briefing, generate_today_view, generate_week_view
from ..services.message_logger import MessageLog
from ..session import get_session, SessionMode
from ..handlers.interactive import (
    start_prioritize_mode, handle_prioritize_input,
    start_update_mode, handle_update_input,
    handle_correction,
)
from ..voice.journals import save_voice_journal
from ..seed.text_parser import parse_natural_seed_text, is_natural_seed_format
from ..seed.loader import load_seed_data, ConflictAction
from ..mcp import get_mcp_server
from . import formatter
import subprocess

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    chat_id = update.effective_chat.id
    
    # Save chat ID if not already set
    from ..config import Config
    if not Config.telegram_chat_id():
        Config.set("telegram_chat_id", str(chat_id))
        logger.info(f"Saved chat ID: {chat_id}")
    
    msg = f"""👋 Welcome to Noctem!

✅ Your chat ID: `{chat_id}` (saved)

I'm your executive assistant. Here's how to use me:

**Add tasks** - Just type naturally:
• `buy groceries tomorrow`
• `call mom friday 3pm`
• `finish report by feb 20 !1`

**Quick actions:**
• `done 1` - complete task #1
• `skip 2` - defer task to tomorrow

**Commands:**
• /today - Today's briefing
• /week - This week's view
• /projects - List projects
• /help - Full command list

Let's get started! Try adding a task."""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    msg = """📚 **Noctem Commands**

**View:**
• /today - Today's briefing
• /week - Week ahead
• /projects - Active projects
• /goals - Your goals
• `web` - Dashboard link

**Create:**
• /project <name> - New project
• Any text → New task

**Task format:**
`task name [date] [time] [!priority] [#tags] [/project]`

Examples:
• `meeting notes tomorrow 2pm`
• `submit report feb 15 !1 #work`
• `review PR next week /backend`

**Quick actions:**
• `done 1` or `done <task name>`
• `skip 1` - Defer to tomorrow
• `delete <task>`

**Settings:**
• /settings - View/change config
• /access - Remote access URL (Tailscale)"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /today command."""
    briefing = generate_morning_briefing()
    await update.message.reply_text(briefing)


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /week command."""
    view = generate_week_view()
    await update.message.reply_text(view, parse_mode="Markdown")


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /projects command."""
    projects = project_service.get_active_projects()
    
    if not projects:
        await update.message.reply_text("No active projects. Create one with /project <name>")
        return
    
    lines = ["📁 **Active Projects**\n"]
    for p in projects:
        task_count = len(task_service.get_project_tasks(p.id))
        lines.append(f"• **{p.name}** ({task_count} tasks)")
        if p.summary:
            lines.append(f"  _{p.summary}_")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /project <name> command - create new project."""
    if not context.args:
        await update.message.reply_text("Usage: /project <name>")
        return
    
    name = " ".join(context.args)
    project = project_service.create_project(name)
    await update.message.reply_text(f"✓ Created project: **{project.name}**", parse_mode="Markdown")


async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /goals command."""
    goals = goal_service.get_all_goals()
    
    if not goals:
        await update.message.reply_text("No goals yet.")
        return
    
    lines = ["🎯 **Goals**\n"]
    for g in goals:
        projects = project_service.get_all_projects(goal_id=g.id)
        lines.append(f"• **{g.name}** ({len(projects)} projects)")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command."""
    from ..config import Config
    
    config = Config.get_all()
    msg = f"""⚙️ **Settings**

• Timezone: {config.get('timezone')}
• Calendar import: ICS feeds (manual refresh)

_Configure via web dashboard or CLI_"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - lean v0.9.3 system status."""
    today_tasks = task_service.get_tasks_due_today()
    overdue_tasks = task_service.get_overdue_tasks()
    inbox_tasks = task_service.get_inbox_tasks()
    mcp_phase = "unknown"
    mcp_tools = "unknown"
    mcp_contract = "unknown"
    try:
        mcp_server = get_mcp_server()
        tools_listing = mcp_server.tools_list(context={"source": "telegram.handlers"})
        if tools_listing.get("ok"):
            listed_tools = tools_listing["result"].get("tools") or []
            mcp_tools = str(tools_listing["result"].get("tool_count", len(listed_tools)))
        version_result = mcp_server.call_tool(
            "ops.version",
            {},
            context={"source": "telegram.handlers"},
        )
        if version_result.get("ok"):
            payload = version_result.get("result") or {}
            mcp_phase = str(payload.get("mcp_phase") or mcp_phase)
            mcp_contract = str(payload.get("tool_contract_version") or mcp_contract)
    except Exception as exc:
        logger.debug("Status MCP metadata lookup failed: %s", exc)
    lines = [
        "🤖 **Noctem v0.9.3 Status**\n",
        f"• Due today: {len(today_tasks)}",
        f"• Overdue: {len(overdue_tasks)}",
        f"• Inbox: {len(inbox_tasks)}",
        f"• MCP phase: {mcp_phase}",
        f"• MCP tools: {mcp_tools}",
        f"• MCP contract: {mcp_contract}",
        "• Voice transcription: enabled",
        "",
        "_Legacy butler/slow/skills surfaces are removed in this version._",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /suggest command - legacy AI suggestion surface removed in v0.9.3."""
    await update.message.reply_text(
        "⚠️ `suggest` is no longer available in v0.9.3.\n\n"
        "Legacy AI suggestion surfaces were removed from active runtime.",
        parse_mode="Markdown",
    )


async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /seed command - prompt user to send seed data.
    v0.6.0: Natural language seed data loading.
    """
    msg = """📝 **Load Seed Data**

Send your seed data in this format:

```
Goals:
-Goal 1
-Goal 2

Projects by goal:
-Goal 1
---- Project A
---- Project B

Tasks by Project:
- Project A
---- Task 1
---- Task 2; due date

Links to calendars:
name:
url
```

Or just paste your seed data text directly and I'll detect it automatically!"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle web command - send dashboard link."""
    import socket
    from ..config import Config
    
    # Get local IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    
    port = Config.web_port()
    url = f"http://{local_ip}:{port}/"
    
    await update.message.reply_text(f"🌐 Dashboard: {url}")


async def cmd_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /access command - send Tailscale IP for remote access."""
    from ..config import Config
    
    try:
        # Get Tailscale IP
        result = subprocess.run(
            [r"C:\Program Files\Tailscale\tailscale.exe", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            tailscale_ip = result.stdout.strip()
            port = Config.web_port()
            
            msg = f"""🔐 **Remote Access (Tailscale)**

**Dashboard:** `http://{tailscale_ip}:{port}/`

**Tailscale IP:** `{tailscale_ip}`

_Make sure Tailscale is running on your device._"""
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            await update.message.reply_text(
                f"❌ Tailscale not connected\n\n_{error_msg}_",
                parse_mode="Markdown"
            )
            
    except FileNotFoundError:
        await update.message.reply_text(
            "❌ Tailscale not installed\n\n"
            "_Install from: https://tailscale.com/download_",
            parse_mode="Markdown"
        )
    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Tailscale command timed out")
    except Exception as e:
        logger.error(f"Failed to get Tailscale IP: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_prioritize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /prioritize command."""
    count = 5
    if context.args and context.args[0].isdigit():
        count = int(context.args[0])
    
    response = start_prioritize_mode(count)
    await update.message.reply_text(response)


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /update command."""
    count = 5
    if context.args and context.args[0].isdigit():
        count = int(context.args[0])
    
    response = start_update_mode(count)
    await update.message.reply_text(response)


async def cmd_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /skill command - removed from active runtime in v0.9.3."""
    await update.message.reply_text(
        "⚠️ `/skill` is removed in v0.9.3.\n\n"
        "Legacy skills runtime is now archived for reference only.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages (tasks and quick actions)."""
    text = update.message.text
    session = get_session()
    
    # Record EVERY interaction for v0.6.0
    with MessageLog(text, source="telegram") as log:
        # Handle interactive modes first
        if session.mode == SessionMode.PRIORITIZE:
            log.set_parsed("INTERACTIVE_PRIORITIZE", {})
            response, exited = handle_prioritize_input(text)
            log.set_action("prioritize_input")
            log.set_result(True, {"response": response[:100], "exited": exited})
            await update.message.reply_text(response)
            return
        
        if session.mode == SessionMode.UPDATE:
            log.set_parsed("INTERACTIVE_UPDATE", {})
            response, exited = handle_update_input(text)
            log.set_action("update_input")
            log.set_result(True, {"response": response[:100], "exited": exited})
            await update.message.reply_text(response)
            return
        
        cmd = parse_command(text)
        log.set_parsed(cmd.type.name, {
            "target_id": cmd.target_id,
            "target_name": cmd.target_name,
            "args": cmd.args
        })
        
        if cmd.type == CommandType.CORRECT:
            correction_text = cmd.args[0] if cmd.args else ""
            log.set_action("correction")
            response = handle_correction(correction_text)
            log.set_result(True, {"response": response[:100]})
            await update.message.reply_text(response)
        elif cmd.type == CommandType.PRIORITIZE:
            count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
            log.set_action("start_prioritize")
            response = start_prioritize_mode(count)
            log.set_result(True, {"count": count})
            await update.message.reply_text(response)
        elif cmd.type == CommandType.UPDATE:
            count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
            log.set_action("start_update")
            response = start_update_mode(count)
            log.set_result(True, {"count": count})
            await update.message.reply_text(response)
        elif cmd.type in (CommandType.DONE, CommandType.SKIP, CommandType.DELETE):
            from ..agent.chat_orchestrator import process_chat_message

            chat_result = process_chat_message(text, source="telegram")
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
            await update.message.reply_text(chat_result.get("response", "✓ Done"))
        elif cmd.type == CommandType.TODAY:
            log.set_action("view_today")
            await cmd_today(update, context)
            log.set_result(True, {})
        elif cmd.type == CommandType.WEEK:
            log.set_action("view_week")
            await cmd_week(update, context)
            log.set_result(True, {})
        elif cmd.type == CommandType.PROJECTS:
            log.set_action("view_projects")
            await cmd_projects(update, context)
            log.set_result(True, {})
        elif cmd.type == CommandType.GOALS:
            log.set_action("view_goals")
            await cmd_goals(update, context)
            log.set_result(True, {})
        elif cmd.type == CommandType.WEB:
            log.set_action("get_web_link")
            await cmd_web(update, context)
            log.set_result(True, {})
        else:
            # Check if it's natural language seed data
            if is_natural_seed_format(text):
                log.set_action("load_seed_text")
                await handle_seed_text(update, text)
                log.set_result(True, {"type": "seed_data"})
            else:
                from ..agent.chat_orchestrator import process_chat_message

                chat_result = process_chat_message(text, source="telegram")
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
                await update.message.reply_text(chat_result.get("response", "✓ Done"))


async def handle_new_task(update: Update, text: str, session=None, log=None):
    """Parse and create a new task from natural language."""
    mcp_server = get_mcp_server()
    parsed = parse_task(text)
    
    # v0.6.0: Handle unclear input gracefully - never lose data
    if not parsed.name or len(parsed.name.strip()) < 2:
        # Still record it, but as unclear
        create_result = mcp_server.call_tool(
            "tasks.create",
            {
                "name": text,
                "tags": ["unclear"],
            },
            context={"source": "telegram.handlers"},
        )
        if not create_result.get("ok"):
            await update.message.reply_text("❌ Unable to save that note as a task right now.")
            return None
        task_payload = create_result["result"].get("task")
        if not isinstance(task_payload, dict) or task_payload.get("id") is None:
            await update.message.reply_text("❌ Unable to verify task creation.")
            return None
        if session:
            session.set_last_entity("task", int(task_payload["id"]))
        
        await update.message.reply_text(
            f"✉️ Filed: \"{text}\"\n_I'll review this later._",
            parse_mode="Markdown"
        )
        return int(task_payload["id"])
    
    # Look up project if specified
    project_id = None
    if parsed.project_name:
        project = project_service.get_project_by_name(parsed.project_name)
        if project:
            project_id = project.id
    
    # Create the task
    create_result = mcp_server.call_tool(
        "tasks.create",
        {
            "name": parsed.name,
            "project_id": project_id,
            "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
            "due_time": parsed.due_time.isoformat() if parsed.due_time else None,
            "importance": parsed.importance,
            "tags": parsed.tags,
            "recurrence_rule": parsed.recurrence_rule,
        },
        context={"source": "telegram.handlers"},
    )
    if not create_result.get("ok"):
        await update.message.reply_text("❌ Unable to create task right now.")
        return None
    task_payload = create_result["result"].get("task")
    if not isinstance(task_payload, dict) or task_payload.get("id") is None:
        await update.message.reply_text("❌ Unable to verify task creation.")
        return None
    
    # Track for correction
    if session:
        session.set_last_entity("task", int(task_payload["id"]))
    
    confirmation = format_task_confirmation(parsed)
    await update.message.reply_text(confirmation)
    return int(task_payload["id"])


async def handle_done(update: Update, cmd):
    """Mark a task as done."""
    task = None
    
    if cmd.target_id:
        # Get task by position in today's priority list
        tasks = task_service.get_priority_tasks(10)
        if 1 <= cmd.target_id <= len(tasks):
            task = tasks[cmd.target_id - 1]
    elif cmd.target_name:
        task = task_service.get_task_by_name(cmd.target_name)
    
    if not task:
        await update.message.reply_text("❌ Task not found")
        return False
    
    complete_result = get_mcp_server().call_tool(
        "tasks.complete",
        {"task_id": task.id},
        context={"source": "telegram.handlers"},
    )
    if not complete_result.get("ok"):
        await update.message.reply_text("❌ Unable to complete that task right now")
        return False
    await update.message.reply_text(f"✓ Completed: {task.name}")
    return True


async def handle_skip(update: Update, cmd):
    """Defer a task to tomorrow."""
    task = None
    
    if cmd.target_id:
        tasks = task_service.get_priority_tasks(10)
        if 1 <= cmd.target_id <= len(tasks):
            task = tasks[cmd.target_id - 1]
    elif cmd.target_name:
        task = task_service.get_task_by_name(cmd.target_name)
    
    if not task:
        await update.message.reply_text("❌ Task not found")
        return False
    
    skip_result = get_mcp_server().call_tool(
        "tasks.skip",
        {"task_id": task.id},
        context={"source": "telegram.handlers"},
    )
    if not skip_result.get("ok"):
        await update.message.reply_text("❌ Unable to defer that task right now")
        return False
    await update.message.reply_text(f"⏭️ Deferred to tomorrow: {task.name}")
    return True


async def handle_delete(update: Update, cmd):
    """Delete a task."""
    task = None
    
    if cmd.target_id:
        tasks = task_service.get_priority_tasks(10)
        if 1 <= cmd.target_id <= len(tasks):
            task = tasks[cmd.target_id - 1]
    elif cmd.target_name:
        task = task_service.get_task_by_name(cmd.target_name)
    
    if not task:
        await update.message.reply_text("❌ Task not found")
        return False
    
    mcp_server = get_mcp_server()
    preview_result = mcp_server.call_tool(
        "tasks.preview_delete",
        {"task_id": task.id},
        context={"source": "telegram.handlers"},
    )
    if not preview_result.get("ok"):
        await update.message.reply_text("❌ Unable to prepare task deletion")
        return False
    preview_id = preview_result["result"].get("preview_id")
    commit_result = mcp_server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview_id, "approved": True, "idempotency_key": f"telegram-delete-{task.id}"},
        context={"source": "telegram.handlers"},
    )
    if not commit_result.get("ok"):
        await update.message.reply_text("❌ Unable to delete that task right now")
        return False
    await update.message.reply_text(f"🗑️ Deleted: {task.name}")
    return True


async def handle_seed_text(update: Update, text: str):
    """
    Handle natural language seed data from Telegram.
    v0.6.0: Parse and load seed data, skip conflicts by default.
    """
    # Parse the text
    parsed = parse_natural_seed_text(text)
    
    total = len(parsed['goals']) + len(parsed['projects']) + len(parsed['tasks']) + len(parsed['calendar_urls'])
    
    if total == 0:
        await update.message.reply_text(
            "📝 Couldn't parse seed data. Make sure it includes sections like:\n"
            "`Goals:`, `Projects by goal:`, `Tasks by Project:`",
            parse_mode="Markdown"
        )
        return
    
    # Preview what was parsed
    preview = f"""📦 **Parsed Seed Data:**
• {len(parsed['goals'])} goals
• {len(parsed['projects'])} projects
• {len(parsed['tasks'])} tasks
• {len(parsed['calendar_urls'])} calendar URLs

Loading... (skipping conflicts)"""
    await update.message.reply_text(preview, parse_mode="Markdown")
    
    # Load with skip resolver (non-interactive)
    def skip_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
        return ConflictAction.SKIP
    
    stats = load_seed_data(parsed, conflict_resolver=skip_resolver)
    
    # Report results
    lines = ["✅ **Seed Data Loaded**\n"]
    
    if stats.goals_created or stats.goals_skipped:
        lines.append(f"Goals: {stats.goals_created} created, {stats.goals_skipped} skipped")
    if stats.projects_created or stats.projects_skipped:
        lines.append(f"Projects: {stats.projects_created} created, {stats.projects_skipped} skipped")
    if stats.tasks_created or stats.tasks_skipped:
        lines.append(f"Tasks: {stats.tasks_created} created, {stats.tasks_skipped} skipped")
    if stats.calendars_added or stats.calendars_skipped:
        lines.append(f"Calendars: {stats.calendars_added} added, {stats.calendars_skipped} skipped")
    
    if stats.errors:
        lines.append(f"\n⚠️ {len(stats.errors)} errors occurred")
        for err in stats.errors[:3]:
            lines.append(f"  • {err[:50]}..." if len(err) > 50 else f"  • {err}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    logger.info(f"Loaded seed data from Telegram: {stats.summary()}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle voice messages - save for transcription.
    v0.6.0: Voice journals are stored immediately and transcribed in the background.
    """
    voice = update.message.voice
    
    if not voice:
        return
    
    try:
        # Download the voice file
        file = await context.bot.get_file(voice.file_id)
        audio_data = await file.download_as_bytearray()
        
        # Save to voice journals
        metadata = {
            "telegram_file_id": voice.file_id,
            "telegram_message_id": update.message.message_id,
            "duration_seconds": voice.duration,
            "mime_type": voice.mime_type,
        }
        
        journal_id = save_voice_journal(
            audio_data=bytes(audio_data),
            source="telegram",
            original_filename=f"voice_{voice.file_id}.ogg",
            metadata=metadata,
        )
        
        duration_str = f"{voice.duration}s" if voice.duration else "audio"
        await update.message.reply_text(
            f"🎤 Voice memo received ({duration_str})\n"
            f"_Will be transcribed in the background._",
            parse_mode="Markdown"
        )
        
        logger.info(f"Saved voice journal {journal_id} from Telegram")
        
    except Exception as e:
        logger.error(f"Failed to save voice message: {e}")
        await update.message.reply_text(
            "❌ Failed to save voice message. Please try again."
        )
