"""
Scheduled jobs using APScheduler.
Lean v0.9.3 scheduler: voice processing only.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..voice.processing import process_pending_voice_journals

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


async def process_voice_queue():
    """Process pending voice journals."""
    try:
        processed = process_pending_voice_journals(max_items=2)
        if processed:
            logger.info(f"Processed {processed} voice journal(s)")
    except Exception as e:
        logger.error(f"Voice processing failed: {e}")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the scheduler."""
    global scheduler

    scheduler = AsyncIOScheduler()
    
    # Voice transcription processing job
    scheduler.add_job(
        process_voice_queue,
        "interval",
        minutes=1,
        id="voice_processing",
        name="Voice Processing",
        replace_existing=True,
    )
    logger.info("Voice processing scheduled every 1 minute")

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


def trigger_butler_update_now():
    """Compatibility stub - Butler runtime has been removed in v0.9.3."""
    logger.info("Butler update trigger ignored: Butler runtime removed in v0.9.3")


def trigger_butler_clarification_now():
    """Compatibility stub - Butler runtime has been removed in v0.9.3."""
    logger.info("Butler clarification trigger ignored: Butler runtime removed in v0.9.3")
