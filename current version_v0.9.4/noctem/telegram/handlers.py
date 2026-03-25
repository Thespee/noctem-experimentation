"""Telegram handlers for Noctem v0.9.4."""
from __future__ import annotations
import asyncio

import logging
import subprocess

from telegram import Update
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from ..config import Config
from ..mcp import get_mcp_server
from ..mcp.resolver import resolve_task_target
from ..parser.command import CommandType, parse_command
from ..parser.task_parser import parse_task
from ..scheduler.jobs import record_user_activity
from ..seed.loader import ConflictAction, load_seed_data
from ..seed.text_parser import is_natural_seed_format, parse_natural_seed_text
from ..services import goal_service, project_service, task_service
from ..services.message_logger import MessageLog
from ..voice.journals import save_voice_journal

logger = logging.getLogger(__name__)
_TELEGRAM_REPLY_RETRIES = 3
_TELEGRAM_REPLY_TIMEOUT_SECONDS = 10


def _touch_activity(update: Update | None = None):
    try:
        record_user_activity(source="telegram")
    except Exception as exc:
        logger.debug("Failed to record scheduler activity heartbeat: %s", exc)
    try:
        if update and update.effective_chat and update.effective_chat.id is not None:
            resolved_chat_id = str(update.effective_chat.id).strip()
            if resolved_chat_id and Config.telegram_chat_id() != resolved_chat_id:
                Config.set("telegram_chat_id", resolved_chat_id)
    except Exception as exc:
        logger.debug("Failed to update telegram_chat_id from inbound update: %s", exc)


def _resolve_task_id(parsed) -> int | None:
    if parsed.target_id:
        return int(parsed.target_id)
    if parsed.target_name:
        resolution = resolve_task_target(parsed.target_name, include_done=True)
        selected = resolution.get("selected_task")
        if selected and getattr(selected, "id", None):
            return int(selected.id)
    return None


def _normalize_reply_text(text: str) -> str:
    resolved = str(text or "").strip()
    if resolved:
        return resolved
    return "Done."


async def _safe_reply_text(update: Update, text: str, *, parse_mode: str | None = None) -> bool:
    message = update.message if update else None
    if message is None:
        return False
    payload = _normalize_reply_text(text)
    last_error: Exception | None = None
    for attempt in range(_TELEGRAM_REPLY_RETRIES):
        try:
            await message.reply_text(
                payload,
                parse_mode=parse_mode,
                read_timeout=_TELEGRAM_REPLY_TIMEOUT_SECONDS,
                write_timeout=_TELEGRAM_REPLY_TIMEOUT_SECONDS,
                connect_timeout=8,
                pool_timeout=8,
            )
            return True
        except RetryAfter as exc:
            last_error = exc
            retry_after = float(getattr(exc, "retry_after", 1.0) or 1.0)
            if attempt < (_TELEGRAM_REPLY_RETRIES - 1):
                await asyncio.sleep(min(max(retry_after, 0.2), 3.0))
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            if attempt < (_TELEGRAM_REPLY_RETRIES - 1):
                await asyncio.sleep(0.4 * (attempt + 1))
        except Exception as exc:
            last_error = exc
            break
    logger.debug("Telegram inline reply failed after retries: %s", last_error)
    return False


async def _fast_feedback(update: Update, text: str):
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith(".f"):
        stripped = stripped[2:].strip()
    elif lowered.startswith("/f"):
        stripped = stripped[2:].strip()
    if not stripped:
        await update.message.reply_text("❌ Please provide feedback text after .f")
        return
    from ..services.feedback_service import prepend_feedback
    result = prepend_feedback(stripped, source="telegram.fast_path")
    if not result.get("ok"):
        await update.message.reply_text("❌ Unable to save feedback.")
        return
    await update.message.reply_text("✓ Feedback captured.")


async def _fast_create_task(update: Update, text: str):
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith(".t "):
        stripped = stripped[3:].strip()
    elif lowered.startswith("/t "):
        stripped = stripped[3:].strip()
    parsed = parse_task(stripped)
    name = (parsed.name or "").strip()
    if not name:
        await update.message.reply_text("❌ Please provide a task description after .t")
        return
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
        context={"source": "telegram.fast_path"},
    )
    if not result.get("ok"):
        await update.message.reply_text("❌ Unable to create task right now.")
        return
    task_payload = (result.get("result") or {}).get("task") or {}
    await update.message.reply_text(f"✓ Created task #{task_payload.get('id')}: {task_payload.get('name', name)}")


async def _fast_complete_or_skip(update: Update, parsed, *, op: str):
    task_id = _resolve_task_id(parsed)
    if task_id is None:
        await update.message.reply_text(f"❌ Could not resolve task target for {op}.")
        return
    tool = "tasks.complete" if op == "complete" else "tasks.skip"
    result = get_mcp_server().call_tool(tool, {"task_id": task_id}, context={"source": "telegram.fast_path"})
    if not result.get("ok"):
        await update.message.reply_text(f"❌ {op.capitalize()} failed.")
        return
    payload = result.get("result") or {}
    task_payload = payload.get("task") or {}
    if op == "complete":
        await update.message.reply_text(f"✓ Completed: {task_payload.get('name', f'task #{task_id}')}")
    else:
        await update.message.reply_text(f"⏭️ Skipped: {task_payload.get('name', f'task #{task_id}')}")


async def _fast_delete(update: Update, parsed):
    task_id = _resolve_task_id(parsed)
    if task_id is None:
        await update.message.reply_text("❌ Could not resolve task target for delete.")
        return
    server = get_mcp_server()
    preview = server.call_tool("tasks.preview_delete", {"task_id": task_id}, context={"source": "telegram.fast_path"})
    if not preview.get("ok"):
        await update.message.reply_text("❌ Unable to preview delete.")
        return
    preview_id = (preview.get("result") or {}).get("preview_id")
    commit = server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview_id, "approved": True},
        context={"source": "telegram.fast_path"},
    )
    if not commit.get("ok"):
        await update.message.reply_text("❌ Delete failed.")
        return
    await update.message.reply_text(f"🗑️ Deleted task #{task_id}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    chat_id = update.effective_chat.id
    if not Config.telegram_chat_id():
        Config.set("telegram_chat_id", str(chat_id))
    await update.message.reply_text(
        "👋 Noctem v0.9.4 is ready.\n\nUse `.t buy milk tomorrow`, `done 1`, `skip 1`, `delete 1`, `.p Project`, `.g Goal`."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    await update.message.reply_text(
        "Commands:\n"
        "• /projects, /project <name>\n"
        "• /goals\n"
        "• /settings\n"
        "• /web\n"
        "• /status\n"
        "Fast path: .t/.d/skip/delete\n"
        "Anything else routes to the agent runtime."
    )


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    projects = project_service.get_active_projects()
    if not projects:
        await update.message.reply_text("No active projects.")
        return
    lines = ["📁 Active Projects\n"]
    for p in projects:
        lines.append(f"• {p.name}")
    await update.message.reply_text("\n".join(lines))


async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    if not context.args:
        await update.message.reply_text("Usage: /project <name>")
        return
    name = " ".join(context.args).strip()
    project = project_service.create_project(name)
    await update.message.reply_text(f"✓ Created project: {project.name}")


async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    goals = goal_service.get_all_goals()
    if not goals:
        await update.message.reply_text("No goals yet.")
        return
    lines = ["🎯 Goals\n"]
    for g in goals:
        lines.append(f"• {g.name}")
    await update.message.reply_text("\n".join(lines))


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    cfg = Config.get_all()
    await update.message.reply_text(
        f"⚙️ Settings\n\n• Timezone: {cfg.get('timezone')}\n• Calendar import: ICS feeds (manual refresh)"
    )


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    host = Config.web_host() or "localhost"
    port = int(Config.web_port() or 5000)
    await update.message.reply_text(f"🌐 Web dashboard: http://{host}:{port}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    await update.message.reply_text(
        "🤖 Noctem v0.9.4 Status\n\n"
        f"• Due today: {len(task_service.get_tasks_due_today())}\n"
        f"• Overdue: {len(task_service.get_overdue_tasks())}\n"
        f"• Inbox: {len(task_service.get_inbox_tasks())}\n"
        "• Voice processing: transcription-only"
    )

async def cmd_t(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    if not context.args:
        await update.message.reply_text("Usage: /t <task text>")
        return
    text = "/t " + " ".join(context.args)
    await _fast_create_task(update, text)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Usage: /done <task_id_or_name>")
        return
    parsed = parse_command(f"/done {raw}")
    await _fast_complete_or_skip(update, parsed, op="complete")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Usage: /skip <task_id_or_name>")
        return
    parsed = parse_command(f"/skip {raw}")
    await _fast_complete_or_skip(update, parsed, op="skip")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Usage: /delete <task_id_or_name>")
        return
    parsed = parse_command(f"/delete {raw}")
    await _fast_delete(update, parsed)


async def cmd_suggest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    await update.message.reply_text("⚠️ `suggest` is removed in v0.9.4.")


async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    await update.message.reply_text("Send natural seed text in the next message and I will import it.")


async def cmd_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    try:
        result = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5, check=False)
        tailscale_ip = (result.stdout or "").strip()
        if result.returncode == 0 and tailscale_ip:
            await update.message.reply_text(f"🔒 Tailscale IP: `{tailscale_ip}`", parse_mode="Markdown")
            return
        await update.message.reply_text("❌ Tailscale not connected.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error checking access endpoint: {exc}")


async def handle_seed_text(update: Update, text: str):
    parsed = parse_natural_seed_text(text)
    if not parsed:
        await update.message.reply_text("❌ Could not parse seed text.")
        return
    stats = load_seed_data(parsed, conflict_resolver=lambda *_: ConflictAction.SKIP)
    await update.message.reply_text(f"✅ Seed import complete: {stats.summary()}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    text = (update.message.text or "").strip()
    with MessageLog(text, source="telegram") as log:
        parsed = parse_command(text)
        log.set_parsed(parsed.type.name, {"target_id": parsed.target_id, "target_name": parsed.target_name, "args": parsed.args})

        if parsed.type == CommandType.PROJECT:
            name = " ".join(parsed.args).strip()
            if not name:
                await update.message.reply_text("Usage: .p <name>")
                log.set_action("create_project")
                log.set_result(False, {"error": "missing_project_name"})
                return
            project = project_service.create_project(name)
            await update.message.reply_text(f"✓ Created project: {project.name}")
            log.set_action("create_project")
            log.set_result(True, {"project_id": project.id})
            return

        if parsed.type == CommandType.GOAL:
            name = " ".join(parsed.args).strip()
            if not name:
                await update.message.reply_text("Usage: .g <name>")
                log.set_action("create_goal")
                log.set_result(False, {"error": "missing_goal_name"})
                return
            goal = goal_service.create_goal(name)
            await update.message.reply_text(f"✓ Created goal: {goal.name}")
            log.set_action("create_goal")
            log.set_result(True, {"goal_id": goal.id})
            return

        if parsed.type == CommandType.PROJECTS:
            await cmd_projects(update, context)
            log.set_action("list_projects")
            log.set_result(True)
            return
        if parsed.type == CommandType.GOALS:
            await cmd_goals(update, context)
            log.set_action("list_goals")
            log.set_result(True)
            return
        if parsed.type == CommandType.START:
            await cmd_start(update, context)
            log.set_action("start")
            log.set_result(True)
            return
        if parsed.type == CommandType.HELP:
            await cmd_help(update, context)
            log.set_action("help")
            log.set_result(True)
            return
        if parsed.type == CommandType.SETTINGS:
            await cmd_settings(update, context)
            log.set_action("settings")
            log.set_result(True)
            return
        if parsed.type == CommandType.STATUS:
            await cmd_status(update, context)
            log.set_action("status")
            log.set_result(True)
            return
        if parsed.type == CommandType.ACCESS:
            await cmd_access(update, context)
            log.set_action("access")
            log.set_result(True)
            return
        if parsed.type == CommandType.WEB:
            await cmd_web(update, context)
            log.set_action("web_link")
            log.set_result(True)
            return

        if parsed.type == CommandType.DONE:
            await _fast_complete_or_skip(update, parsed, op="complete")
            log.set_action("fast_complete")
            log.set_result(True)
            return
        if parsed.type == CommandType.SKIP:
            await _fast_complete_or_skip(update, parsed, op="skip")
            log.set_action("fast_skip")
            log.set_result(True)
            return
        if parsed.type == CommandType.DELETE:
            await _fast_delete(update, parsed)
            log.set_action("fast_delete")
            log.set_result(True)
            return
        if parsed.type == CommandType.FEEDBACK:
            await _fast_feedback(update, text)
            log.set_action("fast_feedback")
            log.set_result(True)
            return
        if parsed.type == CommandType.NEW_TASK and (text.lower().startswith(".t ") or text.lower().startswith("/t ")):
            await _fast_create_task(update, text)
            log.set_action("fast_create")
            log.set_result(True)
            return

        if is_natural_seed_format(text):
            await handle_seed_text(update, text)
            log.set_action("seed_import")
            log.set_result(True)
            return

        from ..agent.execution_queue_runtime import process_chat_message_via_queue
        try:
            chat_result = process_chat_message_via_queue(text, source="telegram")
        except Exception as exc:
            logger.exception("Telegram queued chat processing failed")
            await _safe_reply_text(update, "Sorry, I hit an error while processing that.")
            log.set_action("chat_orchestrator")
            log.set_result(False, {"error": str(exc)})
            return

        deliveries = chat_result.get("deliveries") if isinstance(chat_result.get("deliveries"), list) else []
        telegram_delivered = any(
            str(item.get("channel") or "").strip().lower() == "telegram"
            and str(item.get("status") or "").strip().lower() == "delivered"
            for item in deliveries
            if isinstance(item, dict)
        )
        if not telegram_delivered:
            await _safe_reply_text(update, chat_result.get("response", "Done."))
        await update.message.reply_text(chat_result.get("response", "✓ Done"))
        log.set_action("chat_orchestrator")
        log.set_result(True, {"workflow_id": chat_result.get("workflow_id"), "status": chat_result.get("status")})


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _touch_activity(update)
    voice = update.message.voice
    if voice is None:
        await update.message.reply_text("❌ No voice payload.")
        return
    file = await context.bot.get_file(voice.file_id)
    payload = await file.download_as_bytearray()
    journal_id = save_voice_journal(
        audio_data=bytes(payload),
        source="telegram",
        original_filename=f"{voice.file_id}.ogg",
        metadata={"telegram_file_id": voice.file_id, "duration": voice.duration},
    )
    await update.message.reply_text(f"🎙️ Saved voice memo #{journal_id}. It will be transcribed during background processing.")
