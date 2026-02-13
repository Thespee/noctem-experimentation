#!/usr/bin/env python3
"""
Umbilical cord - secure remote assistance during birth.
Provides reverse SSH tunnel for remote debugging when birth gets stuck.
"""

import subprocess
import socket
import secrets
import threading
import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger("noctem.birth.umbilical")

# Connection timeout (30 minutes)
UMBILICAL_TIMEOUT = 1800


@dataclass
class UmbilicalConnection:
    """Active umbilical connection info."""
    connection_id: str
    relay_host: str
    remote_port: int
    started_at: float
    process: Optional[subprocess.Popen] = None


# Active connection (only one at a time)
_connection: Optional[UmbilicalConnection] = None
_timeout_thread: Optional[threading.Thread] = None


def generate_connection_id() -> str:
    """Generate a random connection ID."""
    return secrets.token_hex(4)


def find_free_port() -> int:
    """Find a free port for the tunnel."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def start_tunnel(relay_host: str) -> Tuple[bool, str]:
    """
    Start a reverse SSH tunnel to allow remote access.
    
    The tunnel allows someone on the relay host to SSH back into this machine.
    
    Args:
        relay_host: SSH destination (user@host or just host)
    
    Returns:
        (success, message)
    """
    global _connection, _timeout_thread
    
    if _connection is not None:
        return False, f"Umbilical already active (ID: {_connection.connection_id})"
    
    # Generate connection details
    connection_id = generate_connection_id()
    remote_port = find_free_port()
    local_port = 22  # Local SSH
    
    # Build reverse tunnel command
    # -R binds remote_port on relay to local_port here
    # -N = no command execution
    # -o options for reliability
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-N",
        "-R", f"{remote_port}:localhost:{local_port}",
        relay_host
    ]
    
    logger.info(f"Starting umbilical tunnel: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give it time to connect
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            logger.error(f"Tunnel failed to start: {stderr}")
            return False, f"Tunnel failed: {stderr[:100]}"
        
        _connection = UmbilicalConnection(
            connection_id=connection_id,
            relay_host=relay_host,
            remote_port=remote_port,
            started_at=time.time(),
            process=process
        )
        
        # Start timeout monitor
        _timeout_thread = threading.Thread(target=_timeout_monitor, daemon=True)
        _timeout_thread.start()
        
        msg = (
            f"🔗 Umbilical active!\n"
            f"ID: {connection_id}\n"
            f"Connect from relay with:\n"
            f"  ssh -p {remote_port} localhost"
        )
        
        logger.info(f"Umbilical established: {connection_id} on port {remote_port}")
        return True, msg
        
    except FileNotFoundError:
        return False, "SSH not installed. Install with: sudo apt install openssh-client"
    except Exception as e:
        logger.error(f"Tunnel error: {e}")
        return False, f"Tunnel error: {e}"


def _timeout_monitor():
    """Monitor connection and close after timeout."""
    global _connection
    
    while _connection is not None:
        elapsed = time.time() - _connection.started_at
        
        if elapsed > UMBILICAL_TIMEOUT:
            from .notify import send_signal
            close_tunnel()
            send_signal("⏱️ Umbilical timed out (30 min). Reply /umb connect <relay> to reconnect.")
            break
        
        # Also check if tunnel process died
        if _connection.process and _connection.process.poll() is not None:
            from .notify import send_signal
            _connection = None
            send_signal("⚠️ Umbilical connection lost. Reply /umb connect <relay> to reconnect.")
            break
        
        time.sleep(30)


def close_tunnel() -> Tuple[bool, str]:
    """Close the umbilical connection."""
    global _connection
    
    if _connection is None:
        return False, "No active umbilical"
    
    conn_id = _connection.connection_id
    
    try:
        if _connection.process:
            _connection.process.terminate()
            _connection.process.wait(timeout=5)
    except Exception:
        pass
    
    _connection = None
    logger.info(f"Umbilical {conn_id} closed")
    return True, f"Umbilical {conn_id} closed"


def get_status() -> Optional[dict]:
    """Get current umbilical status."""
    if _connection is None:
        return None
    
    elapsed = time.time() - _connection.started_at
    remaining = UMBILICAL_TIMEOUT - elapsed
    
    return {
        "connection_id": _connection.connection_id,
        "relay_host": _connection.relay_host,
        "remote_port": _connection.remote_port,
        "uptime_seconds": int(elapsed),
        "timeout_remaining": int(remaining),
        "active": _connection.process.poll() is None if _connection.process else False
    }


def handle_umb_command(command: str) -> str:
    """
    Handle /umb commands.
    
    Commands:
        /umb connect <relay_host> - Start umbilical tunnel
        /umb status               - Get connection status
        /umb close                - Close umbilical
        /umb retry                - Retry current birth stage
        /umb skip                 - Skip current birth stage
        /umb abort                - Abort birth entirely
    """
    parts = command.strip().split(maxsplit=2)
    
    if len(parts) < 2:
        return (
            "Umbilical commands:\n"
            "  /umb connect <relay> - Start tunnel\n"
            "  /umb status - Connection status\n"
            "  /umb close - Close tunnel\n"
            "  /umb retry - Retry current stage\n"
            "  /umb skip - Skip current stage\n"
            "  /umb abort - Cancel birth"
        )
    
    action = parts[1].lower()
    
    if action == "connect":
        if len(parts) < 3:
            return "Usage: /umb connect <relay_host>\nExample: /umb connect user@myserver.com"
        
        relay = parts[2]
        success, message = start_tunnel(relay)
        return message
    
    elif action == "status":
        status = get_status()
        if status:
            return (
                f"🔗 Umbilical active\n"
                f"ID: {status['connection_id']}\n"
                f"Relay: {status['relay_host']}\n"
                f"Port: {status['remote_port']}\n"
                f"Uptime: {status['uptime_seconds']}s\n"
                f"Timeout in: {status['timeout_remaining']}s"
            )
        return "No active umbilical connection"
    
    elif action == "close":
        success, message = close_tunnel()
        return message
    
    elif action == "retry":
        from .state import get_birth_state, BirthStage, save_state
        state = get_birth_state()
        if state and state.stage == BirthStage.ERROR:
            # Clear error state and allow retry
            state.stage = BirthStage.INIT  # Will resume from last incomplete
            save_state(state)
            return "🔄 Retrying birth from last checkpoint..."
        return "Birth not in error state"
    
    elif action == "skip":
        from .state import get_birth_state, save_state
        state = get_birth_state()
        if state:
            next_stage = state.get_next_stage()
            if next_stage:
                state.mark_stage_complete(next_stage)
                save_state(state)
                return f"⏭️ Skipped stage: {next_stage.name}"
        return "No stage to skip"
    
    elif action == "abort":
        close_tunnel()
        from .state import get_birth_state, BirthStage, clear_state
        state = get_birth_state()
        if state:
            clear_state()
        return "🛑 Birth aborted. Run manually with: python3 birth/run.py"
    
    else:
        return f"Unknown command: {action}. Try /umb for help."
