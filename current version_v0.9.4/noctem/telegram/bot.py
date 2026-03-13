"""
Telegram bot setup and initialization.
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from ..config import Config
from . import handlers

logger = logging.getLogger(__name__)

async def _handle_telegram_error(update, context) -> None:
    logger.debug("Telegram update handling error: %s", getattr(context, "error", None))


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
    app.add_handler(CommandHandler("projects", handlers.cmd_projects))
    app.add_handler(CommandHandler("project", handlers.cmd_project))
    app.add_handler(CommandHandler("goals", handlers.cmd_goals))
    app.add_handler(CommandHandler("settings", handlers.cmd_settings))
    app.add_handler(CommandHandler("web", handlers.cmd_web))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("t", handlers.cmd_t))
    app.add_handler(CommandHandler("done", handlers.cmd_done))
    app.add_handler(CommandHandler("skip", handlers.cmd_skip))
    app.add_handler(CommandHandler("delete", handlers.cmd_delete))
    app.add_handler(CommandHandler("suggest", handlers.cmd_suggest))
    app.add_handler(CommandHandler("seed", handlers.cmd_seed))
    app.add_handler(CommandHandler("access", handlers.cmd_access))
    
    # Message handler for all other text (tasks and quick actions)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    # Voice message handler for voice journals
    app.add_handler(MessageHandler(filters.VOICE, handlers.handle_voice))
    app.add_error_handler(_handle_telegram_error)
    
    logger.info("Telegram bot configured")
    return app


async def run_bot():
    """Run the Telegram bot (blocking)."""
    app = create_bot()
    logger.info("Starting Telegram bot...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)
