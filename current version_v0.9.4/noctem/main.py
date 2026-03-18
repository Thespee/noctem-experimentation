#!/usr/bin/env python3
"""
Noctem v0.6.0 - Executive Assistant System
"The Graceful Butler: Fast Capture, Slow Reflection"
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

class _NoctemDebugFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.DEBUG:
            return record.name.startswith("noctem")
        return record.levelno != logging.INFO


def startup_health_check(quiet: bool = False) -> bool:
    """Run startup health checks. Returns True if all critical checks pass."""
    all_ok = True
    
    # 1. Check database
    try:
        from .db import get_db
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        if not quiet:
            print("✓ Database OK")
    except Exception as e:
        print(f"✗ Database error: {e}")
        all_ok = False
    
    # 2. Check config
    try:
        from .config import Config
        config = Config.get_all()
        if not quiet:
            print(f"✓ Config loaded ({len(config)} settings)")
    except Exception as e:
        print(f"✗ Config error: {e}")
        all_ok = False
    
    # 3. Check Telegram config (optional)
    token = Config.telegram_token()
    if token:
        if not quiet:
            print("✓ Telegram token configured")
    else:
        if not quiet:
            print("⚠ Telegram token not set (bot will not start)")
    
    return all_ok


def setup_logging(quiet: bool = False, debug: bool = False):
    """Configure logging; debug mode surfaces DEBUG traces while suppressing INFO on console."""
    from noctem.db import DATA_DIR
    
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "noctem.log"
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    handlers = [file_handler]
    
    if not quiet:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        if debug:
            stream_handler.addFilter(_NoctemDebugFilter())
        handlers.append(stream_handler)
    
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    
    # Suppress noisy third-party loggers
    if quiet or debug:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    if debug:
        logging.getLogger(__name__).debug("[RUNTIME_DEBUG] debug mode enabled; INFO hidden on console")


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
        print("  \033[1;36mNOCTEM v0.6.0\033[0m - Executive Assistant")
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
        threaded=True,
    )


def run_cli():
    """Run the CLI interface."""
    from .cli import main as cli_main
    cli_main()


async def run_bot_async():
    """Run the Telegram bot with scheduler."""
    from .telegram.bot import create_bot
    from .scheduler.jobs import create_scheduler
    
    # Create bot
    app = create_bot()
    
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
    parser = argparse.ArgumentParser(description="Noctem v0.6.0 Executive Assistant")
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logs for runtime troubleshooting and suppress INFO noise on console.",
    )
    args = parser.parse_args()
    
    # Setup logging based on quiet flag
    setup_logging(quiet=args.quiet, debug=args.debug)
    
    # Initialize database
    init_db()
    
    # v0.6.0: Startup health check
    if args.mode != "init" and not args.quiet:
        print("\n🌙 Noctem v0.6.0 - Startup Check\n" + "-" * 35)
        startup_health_check(quiet=False)
        print("-" * 35 + "\n")
    
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
            # Keep running for web only
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
                    print("Running web only. Press Ctrl+C to stop.")
                else:
                    # Re-show QR since error may have messed up display
                    show_qr_code(url)
                    print("  ⚠️  Telegram bot offline (network issue)")
                    print("-"*50 + "\n")
                # Keep running for web only
                try:
                    while True:
                        import time
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass


if __name__ == "__main__":
    main()
