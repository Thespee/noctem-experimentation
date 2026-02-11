#!/usr/bin/env python3
"""
Signal notifications for birth process.
Sends progress updates, errors, and help requests via Signal.
"""

import json
import socket
import subprocess
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger("noctem.birth.notify")

# Signal daemon settings (same as main Noctem)
SIGNAL_DAEMON_HOST = "127.0.0.1"
SIGNAL_DAEMON_PORT = 7583

# Fallback to signal-cli direct if daemon not available
SIGNAL_CLI_PATH = "signal-cli"

# Configured phone numbers
_signal_number: Optional[str] = None  # Noctem's number (sender)
_recipient_number: Optional[str] = None  # User's number (receiver)


def configure(signal_number: str, recipient_number: Optional[str] = None):
    """Configure Signal numbers for notifications."""
    global _signal_number, _recipient_number
    _signal_number = signal_number
    _recipient_number = recipient_number or signal_number


def _send_via_daemon(message: str, recipient: str) -> bool:
    """Send message via signal-cli JSON-RPC daemon."""
    try:
        request = {
            "jsonrpc": "2.0",
            "method": "send",
            "params": {
                "recipient": [recipient],
                "message": message
            },
            "id": 1
        }
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((SIGNAL_DAEMON_HOST, SIGNAL_DAEMON_PORT))
        sock.sendall((json.dumps(request) + "\n").encode())
        
        # Read response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk or b"\n" in response:
                break
            response += chunk
        sock.close()
        
        result = json.loads(response.decode().strip())
        return "error" not in result
        
    except (ConnectionRefusedError, socket.timeout, Exception) as e:
        logger.debug(f"Daemon send failed: {e}")
        return False


def _send_via_cli(message: str, recipient: str) -> bool:
    """Send message via signal-cli command line."""
    if not _signal_number:
        return False
    
    try:
        result = subprocess.run(
            [SIGNAL_CLI_PATH, "-u", _signal_number, "send", "-m", message, recipient],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"CLI send failed: {e}")
        return False


def send_signal(message: str, recipient: Optional[str] = None) -> bool:
    """
    Send a Signal message.
    Tries daemon first, falls back to CLI.
    """
    target = recipient or _recipient_number or _signal_number
    
    if not target:
        logger.warning("No recipient configured for Signal notification")
        print(f"[SIGNAL NOT CONFIGURED] {message}")
        return False
    
    # Truncate long messages
    if len(message) > 2000:
        message = message[:1997] + "..."
    
    # Try daemon first (faster, more reliable)
    if _send_via_daemon(message, target):
        return True
    
    # Fall back to CLI
    return _send_via_cli(message, target)


def notify_progress(stage: str, message: str, emoji: str = "🔧"):
    """Send progress notification."""
    from .state import get_birth_state
    
    state = get_birth_state()
    progress = state.progress_percent if state else 0
    
    full_message = f"{emoji} Birth [{stage}] ({progress}%): {message}"
    
    # Also print locally
    print(full_message)
    logger.info(full_message)
    
    send_signal(full_message)


def notify_error(stage: str, error: str, request_help: bool = True):
    """Send error notification."""
    msg = f"🚨 Birth ERROR [{stage}]: {error}"
    
    if request_help:
        msg += "\n\nReply with:\n"
        msg += "  /umb connect <relay> - Get remote help\n"
        msg += "  /umb retry - Retry this stage\n"
        msg += "  /umb skip - Skip this stage\n"
        msg += "  /umb abort - Cancel birth"
    
    print(msg)
    logger.error(msg)
    send_signal(msg)


def notify_complete():
    """Send completion notification."""
    msg = """🌙 Noctem birth complete!

✓ All systems configured
✓ Auto-start enabled
✓ Ready to receive messages

Send me a message to begin!"""
    
    print(msg)
    logger.info("Birth complete")
    send_signal(msg)


def notify_waiting(reason: str):
    """Notify that birth is waiting for something."""
    msg = f"⏳ Birth waiting: {reason}"
    print(msg)
    logger.info(msg)
    send_signal(msg)


def notify_resume(stage: str):
    """Notify that birth is resuming."""
    msg = f"▶️ Birth resuming from stage: {stage}"
    print(msg)
    logger.info(msg)
    send_signal(msg)
