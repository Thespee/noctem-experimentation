"""
Scheduled jobs using APScheduler.
Handles morning briefing, Google Calendar sync, and butler contacts (v0.6.0).
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config
from ..services.briefing import generate_morning_briefing
from ..services.calendar_sync import sync_calendar, is_gcal_configured
from ..butler.protocol import ButlerProtocol
from ..butler.updates import generate_update_message
from ..butler.clarifications import ClarificationQueue, generate_clarification_message

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

# Telegram bot application (set from main.py)
_bot_app = None


def set_bot_app(app):
    """Set the Telegram bot application for sending messages."""
    global _bot_app
    _bot_app = app


async def send_morning_briefing():
    """Send the morning briefing via Telegram."""
    logger.info("Running morning briefing job")
    
    if _bot_app is None:
        logger.warning("Bot app not configured, skipping morning briefing")
        return
    
    chat_id = Config.telegram_chat_id()
    if not chat_id:
        logger.warning("Telegram chat ID not configured")
        return
    
    try:
        briefing = generate_morning_briefing()
        await _bot_app.bot.send_message(chat_id=chat_id, text=briefing)
        logger.info("Morning briefing sent")
    except Exception as e:
        logger.error(f"Failed to send morning briefing: {e}")


async def run_calendar_sync():
    """Sync Google Calendar events."""
    logger.info("Running calendar sync job")
    
    if not is_gcal_configured():
        logger.debug("Google Calendar not configured, skipping sync")
        return
    
    try:
        result = sync_calendar()
        logger.info(f"Calendar sync complete: {result}")
    except Exception as e:
        logger.error(f"Calendar sync failed: {e}")


# === v0.6.0: Butler Contact Jobs ===

async def send_butler_update():
    """
    Send a butler update message (Mon/Wed/Fri by default).
    Respects the 5 contacts/week budget.
    """
    logger.info("Running butler update job")
    
    if _bot_app is None:
        logger.warning("Bot app not configured, skipping butler update")
        return
    
    chat_id = Config.telegram_chat_id()
    if not chat_id:
        logger.warning("Telegram chat ID not configured")
        return
    
    # Check budget before sending
    if not ButlerProtocol.can_contact("update"):
        logger.info("Butler update budget exhausted for this week")
        return
    
    try:
        message = generate_update_message()
        await _bot_app.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        
        # Record the contact
        ButlerProtocol.record_contact("update", message[:500])  # Truncate for storage
        logger.info("Butler update sent")
    except Exception as e:
        logger.error(f"Failed to send butler update: {e}")


async def send_butler_clarification():
    """
    Send clarification questions (Tue/Thu by default).
    Only sends if there are pending questions and budget allows.
    """
    logger.info("Running butler clarification job")
    
    if _bot_app is None:
        logger.warning("Bot app not configured, skipping clarification")
        return
    
    chat_id = Config.telegram_chat_id()
    if not chat_id:
        logger.warning("Telegram chat ID not configured")
        return
    
    # Check if there are pending questions
    if not ClarificationQueue.has_pending_questions():
        logger.info("No pending clarification questions")
        return
    
    # Check budget before sending
    if not ButlerProtocol.can_contact("clarification"):
        logger.info("Butler clarification budget exhausted for this week")
        return
    
    try:
        message = generate_clarification_message()
        if message:
            await _bot_app.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
            
            # Record the contact
            ButlerProtocol.record_contact("clarification", message[:500])
            logger.info("Butler clarification sent")
    except Exception as e:
        logger.error(f"Failed to send butler clarification: {e}")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the scheduler."""
    global scheduler
    
    scheduler = AsyncIOScheduler()
    
    # Morning briefing job
    morning_time = Config.morning_time()  # e.g., "07:00"
    try:
        hour, minute = map(int, morning_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 7, 0
    
    scheduler.add_job(
        send_morning_briefing,
        CronTrigger(hour=hour, minute=minute),
        id="morning_briefing",
        name="Morning Briefing",
        replace_existing=True,
    )
    logger.info(f"Morning briefing scheduled for {hour:02d}:{minute:02d}")
    
    # Calendar sync job
    sync_interval = Config.get("gcal_sync_interval_minutes", 15)
    scheduler.add_job(
        run_calendar_sync,
        "interval",
        minutes=sync_interval,
        id="calendar_sync",
        name="Calendar Sync",
        replace_existing=True,
    )
    logger.info(f"Calendar sync scheduled every {sync_interval} minutes")
    
    # v0.6.0: Butler contact jobs
    _schedule_butler_contacts(scheduler)
    
    return scheduler


def _schedule_butler_contacts(scheduler: AsyncIOScheduler):
    """Schedule butler update and clarification jobs based on config."""
    
    # Get configured days and times
    update_days = Config.get("butler_update_days", ["monday", "wednesday", "friday"])
    update_time = Config.get("butler_update_time", "09:00")
    clarification_days = Config.get("butler_clarification_days", ["tuesday", "thursday"])
    clarification_time = Config.get("butler_clarification_time", "09:00")
    
    # Parse times
    try:
        update_hour, update_minute = map(int, update_time.split(":"))
    except (ValueError, AttributeError):
        update_hour, update_minute = 9, 0
    
    try:
        clarification_hour, clarification_minute = map(int, clarification_time.split(":"))
    except (ValueError, AttributeError):
        clarification_hour, clarification_minute = 9, 0
    
    # Map day names to cron day-of-week
    day_map = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed",
        "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun"
    }
    
    # Schedule update jobs
    update_dow = ",".join([day_map.get(d.lower(), d[:3]) for d in update_days])
    scheduler.add_job(
        send_butler_update,
        CronTrigger(day_of_week=update_dow, hour=update_hour, minute=update_minute),
        id="butler_update",
        name="Butler Update",
        replace_existing=True,
    )
    logger.info(f"Butler updates scheduled for {update_days} at {update_time}")
    
    # Schedule clarification jobs
    clarification_dow = ",".join([day_map.get(d.lower(), d[:3]) for d in clarification_days])
    scheduler.add_job(
        send_butler_clarification,
        CronTrigger(day_of_week=clarification_dow, hour=clarification_hour, minute=clarification_minute),
        id="butler_clarification",
        name="Butler Clarification",
        replace_existing=True,
    )
    logger.info(f"Butler clarifications scheduled for {clarification_days} at {clarification_time}")


def start_scheduler():
    """Start the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def update_morning_time(new_time: str):
    """Update the morning briefing time."""
    Config.set("morning_message_time", new_time)
    
    if scheduler:
        try:
            hour, minute = map(int, new_time.split(":"))
            scheduler.reschedule_job(
                "morning_briefing",
                trigger=CronTrigger(hour=hour, minute=minute),
            )
            logger.info(f"Morning briefing rescheduled to {hour:02d}:{minute:02d}")
        except Exception as e:
            logger.error(f"Failed to reschedule morning briefing: {e}")


def trigger_briefing_now():
    """Manually trigger the morning briefing (for testing)."""
    import asyncio
    asyncio.create_task(send_morning_briefing())


def trigger_sync_now():
    """Manually trigger calendar sync (for testing)."""
    import asyncio
    asyncio.create_task(run_calendar_sync())


def trigger_butler_update_now():
    """Manually trigger butler update (for testing)."""
    import asyncio
    asyncio.create_task(send_butler_update())


def trigger_butler_clarification_now():
    """Manually trigger butler clarification (for testing)."""
    import asyncio
    asyncio.create_task(send_butler_clarification())
