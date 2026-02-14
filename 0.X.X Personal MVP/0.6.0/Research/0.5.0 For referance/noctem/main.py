#!/usr/bin/env python3
"""
Noctem v0.5 - Executive Assistant System
Main entry point.
"""
import argparse
import asyncio
import logging
import threading
import sys
import socket
import os

from .db import init_db
from .config import Config

# Will be configured later based on mode
logger = logging.getLogger(__name__)


def setup_logging(quiet: bool = False):
    """Configure logging - file only if quiet, else also console."""
    from pathlib import Path
    
    log_dir = Path(__file__).parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "noctem.log"
    
    handlers = [
        logging.FileHandler(log_file),
    ]
    
    if not quiet:
        handlers.append(logging.StreamHandler())
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    
    # Suppress noisy loggers when quiet
    if quiet:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)


def get_local_ip() -> str:
    """Get the local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def show_qr_code(url: str):
    """Display a QR code in the terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Clear screen
        os.system('clear' if os.name != 'nt' else 'cls')
        
        # Print header
        print("\n" + "="*50)
        print("  \033[1;36mNOCTEM v0.5\033[0m - Executive Assistant")
        print("="*50)
        print(f"\n  \033[1;32m{url}\033[0m\n")
        
        # Print QR code
        qr.print_ascii(invert=True)
        
        print("\n" + "-"*50)
        print("  Scan QR code to open dashboard on your phone")
        print("  Press Ctrl+C to stop")
        print("-"*50 + "\n")
        
    except ImportError:
        print(f"\n  Dashboard: {url}")
        print("  (Install 'qrcode' for QR display)\n")


def run_web_server():
    """Run the Flask web dashboard in a thread."""
    from .web.app import create_app
    app = create_app()
    app.run(
        host=Config.web_host(),
        port=Config.web_port(),
        debug=False,
        use_reloader=False,
    )


def run_cli():
    """Run the CLI interface."""
    from .cli import main as cli_main
    cli_main()


async def run_bot_async():
    """Run the Telegram bot with scheduler."""
    from .telegram.bot import create_bot
    from .scheduler.jobs import create_scheduler, set_bot_app
    
    # Create bot
    app = create_bot()
    set_bot_app(app)
    
    # Create and start scheduler
    scheduler = create_scheduler()
    scheduler.start()
    
    logger.info("Starting Telegram bot...")
    
    # Run bot
    async with app:
        await app.start()
        await app.updater.start_polling()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await app.updater.stop()
            await app.stop()
            scheduler.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Noctem v0.5 Executive Assistant")
    parser.add_argument(
        "mode",
        choices=["bot", "web", "cli", "all", "init"],
        default="cli",
        nargs="?",
        help="Run mode: bot (Telegram), web (dashboard), cli (terminal), all, or init (setup DB)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Web server port (overrides config)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress console output, logs to file only (shows QR code in 'all' mode)",
    )
    args = parser.parse_args()
    
    # Setup logging based on quiet flag
    setup_logging(quiet=args.quiet)
    
    # Initialize database
    init_db()
    
    if args.mode == "init":
        Config.init_defaults()
        print("Database and config initialized.")
        print(f"Database at: {Config.get('db_path', 'noctem/data/noctem.db')}")
        print("\nNext steps:")
        print("1. Set Telegram token: python -m noctem.cli, then: set telegram_bot_token YOUR_TOKEN")
        print("2. Run CLI: python -m noctem cli")
        print("3. Run web: python -m noctem web")
        return
    
    if args.port:
        Config.set("web_port", args.port)
    
    if args.mode == "cli":
        run_cli()
    
    elif args.mode == "web":
        if not args.quiet:
            logger.info(f"Starting web dashboard on http://{Config.web_host()}:{Config.web_port()}")
        run_web_server()
    
    elif args.mode == "bot":
        token = Config.telegram_token()
        if not token:
            print("Error: Telegram bot token not configured.")
            print("Set it with: python -m noctem cli, then: set telegram_bot_token YOUR_TOKEN")
            sys.exit(1)
        asyncio.run(run_bot_async())
    
    elif args.mode == "all":
        # Run web in thread first
        web_thread = threading.Thread(target=run_web_server, daemon=True)
        web_thread.start()
        
        # Show QR code if quiet mode (before bot connects)
        ip = get_local_ip()
        port = Config.web_port()
        url = f"http://{ip}:{port}/"
        
        if args.quiet:
            show_qr_code(url)
        else:
            logger.info(f"Web dashboard started on {url}")
        
        # Try to run bot
        token = Config.telegram_token()
        if not token:
            if not args.quiet:
                print("Telegram bot not configured. Running web only.")
                print("Set token with: python -m noctem cli, then: set telegram_bot_token YOUR_TOKEN")
            # Keep running for web
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            try:
                asyncio.run(run_bot_async())
            except Exception as e:
                if not args.quiet:
                    print(f"\nBot connection failed: {e}")
                    print("Running web dashboard only. Press Ctrl+C to stop.")
                else:
                    # Re-show QR since error may have messed up display
                    show_qr_code(url)
                    print("  ⚠️  Telegram bot offline (network issue)")
                    print("-"*50 + "\n")
                # Keep running for web
                try:
                    while True:
                        import time
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass


if __name__ == "__main__":
    main()
