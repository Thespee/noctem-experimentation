"""
Scheduled jobs using APScheduler.
Handles morning briefing and Google Calendar sync.
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config
from ..services.briefing import generate_morning_briefing
from ..services.calendar_sync import sync_calendar, is_gcal_configured

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
    
    return scheduler


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
