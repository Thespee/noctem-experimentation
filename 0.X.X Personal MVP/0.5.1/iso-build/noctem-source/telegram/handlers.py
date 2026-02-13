"""
Telegram message handlers.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..parser.command import parse_command, CommandType
from ..parser.task_parser import parse_task, format_task_confirmation
from ..services import task_service, habit_service, project_service, goal_service
from ..services.briefing import generate_morning_briefing, generate_today_view, generate_week_view
from ..session import get_session, SessionMode
from ..handlers.interactive import (
    start_prioritize_mode, handle_prioritize_input,
    start_update_mode, handle_update_input,
    handle_correction,
)
from . import formatter

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
• `habit done exercise` - log habit

**Commands:**
• /today - Today's briefing
• /week - This week's view
• /projects - List projects
• /habits - Habit status
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
• /habits - Habit status
• /goals - Your goals
• `web` - Dashboard link

**Create:**
• /project <name> - New project
• /habit <name> <freq> - New habit
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
• `habit done <name>`

**Settings:**
• /settings - View/change config"""
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


async def cmd_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /habits command."""
    stats = habit_service.get_all_habits_stats()
    
    if not stats:
        await update.message.reply_text("No habits yet. Create one with /habit <name> <frequency>")
        return
    
    lines = ["🔄 **Habits**\n"]
    for s in stats:
        done = "✓" if s["done_today"] else "○"
        streak = f"🔥{s['streak']}" if s["streak"] > 0 else ""
        week = f"({s['completions_this_week']}/{s['target_this_week']} this week)"
        lines.append(f"{done} **{s['name']}** {week} {streak}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /habit <name> <frequency> command - create new habit."""
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /habit <name> [daily|weekly]")
        return
    
    # Parse frequency from args
    freq = "daily"
    name_parts = []
    for arg in context.args:
        if arg.lower() in ("daily", "weekly", "custom"):
            freq = arg.lower()
        else:
            name_parts.append(arg)
    
    if not name_parts:
        await update.message.reply_text("Please provide a habit name")
        return
    
    name = " ".join(name_parts)
    habit = habit_service.create_habit(name, frequency=freq)
    await update.message.reply_text(
        f"✓ Created habit: **{habit.name}** ({habit.frequency})", 
        parse_mode="Markdown"
    )


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
• Morning briefing: {config.get('morning_message_time')}
• Calendar sync: every {config.get('gcal_sync_interval_minutes')} min

_Configure via web dashboard or CLI_"""
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages (tasks and quick actions)."""
    text = update.message.text
    session = get_session()
    
    # Handle interactive modes first
    if session.mode == SessionMode.PRIORITIZE:
        response, exited = handle_prioritize_input(text)
        await update.message.reply_text(response)
        return
    
    if session.mode == SessionMode.UPDATE:
        response, exited = handle_update_input(text)
        await update.message.reply_text(response)
        return
    
    cmd = parse_command(text)
    
    if cmd.type == CommandType.CORRECT:
        correction_text = cmd.args[0] if cmd.args else ""
        response = handle_correction(correction_text)
        await update.message.reply_text(response)
    elif cmd.type == CommandType.PRIORITIZE:
        count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
        response = start_prioritize_mode(count)
        await update.message.reply_text(response)
    elif cmd.type == CommandType.UPDATE:
        count = int(cmd.args[0]) if cmd.args and cmd.args[0].isdigit() else 5
        response = start_update_mode(count)
        await update.message.reply_text(response)
    elif cmd.type == CommandType.DONE:
        await handle_done(update, cmd)
    elif cmd.type == CommandType.SKIP:
        await handle_skip(update, cmd)
    elif cmd.type == CommandType.DELETE:
        await handle_delete(update, cmd)
    elif cmd.type == CommandType.HABIT_DONE:
        await handle_habit_done(update, cmd)
    elif cmd.type == CommandType.TODAY:
        await cmd_today(update, context)
    elif cmd.type == CommandType.WEEK:
        await cmd_week(update, context)
    elif cmd.type == CommandType.PROJECTS:
        await cmd_projects(update, context)
    elif cmd.type == CommandType.HABITS:
        await cmd_habits(update, context)
    elif cmd.type == CommandType.GOALS:
        await cmd_goals(update, context)
    elif cmd.type == CommandType.WEB:
        await cmd_web(update, context)
    else:
        # Treat as new task
        await handle_new_task(update, text, session)


async def handle_new_task(update: Update, text: str, session=None):
    """Parse and create a new task from natural language."""
    parsed = parse_task(text)
    
    if not parsed.name:
        await update.message.reply_text("Couldn't parse task name. Please try again.")
        return
    
    # Look up project if specified
    project_id = None
    if parsed.project_name:
        project = project_service.get_project_by_name(parsed.project_name)
        if project:
            project_id = project.id
    
    # Create the task
    task = task_service.create_task(
        name=parsed.name,
        project_id=project_id,
        due_date=parsed.due_date,
        due_time=parsed.due_time,
        importance=parsed.importance,
        tags=parsed.tags,
        recurrence_rule=parsed.recurrence_rule,
    )
    
    # Track for correction
    if session:
        session.set_last_entity("task", task.id)
    
    confirmation = format_task_confirmation(parsed)
    await update.message.reply_text(confirmation)


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
        return
    
    task_service.complete_task(task.id)
    await update.message.reply_text(f"✓ Completed: {task.name}")


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
        return
    
    updated = task_service.skip_task(task.id)
    await update.message.reply_text(f"⏭️ Deferred to tomorrow: {task.name}")


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
        return
    
    task_service.delete_task(task.id)
    await update.message.reply_text(f"🗑️ Deleted: {task.name}")


async def handle_habit_done(update: Update, cmd):
    """Log a habit completion."""
    habit = habit_service.get_habit_by_name(cmd.target_name)
    
    if not habit:
        await update.message.reply_text("❌ Habit not found")
        return
    
    habit_service.log_habit(habit.id)
    stats = habit_service.get_habit_stats(habit.id)
    
    streak_msg = f"🔥 {stats['streak']} day streak!" if stats['streak'] > 0 else ""
    await update.message.reply_text(f"✓ Logged: {habit.name} {streak_msg}")
