"""
Telegram bot setup and initialization.
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from ..config import Config
from . import handlers

logger = logging.getLogger(__name__)


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    token = Config.telegram_token()
    
    if not token:
        raise ValueError(
            "Telegram bot token not configured. "
            "Set it via: Config.set('telegram_bot_token', 'YOUR_TOKEN')"
        )
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("today", handlers.cmd_today))
    app.add_handler(CommandHandler("week", handlers.cmd_week))
    app.add_handler(CommandHandler("projects", handlers.cmd_projects))
    app.add_handler(CommandHandler("project", handlers.cmd_project))
    app.add_handler(CommandHandler("habits", handlers.cmd_habits))
    app.add_handler(CommandHandler("habit", handlers.cmd_habit))
    app.add_handler(CommandHandler("goals", handlers.cmd_goals))
    app.add_handler(CommandHandler("settings", handlers.cmd_settings))
    app.add_handler(CommandHandler("prioritize", handlers.cmd_prioritize))
    app.add_handler(CommandHandler("update", handlers.cmd_update))
    app.add_handler(CommandHandler("web", handlers.cmd_web))
    
    # Message handler for all other text (tasks and quick actions)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    logger.info("Telegram bot configured")
    return app


async def run_bot():
    """Run the Telegram bot (blocking)."""
    app = create_bot()
    logger.info("Starting Telegram bot...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)
