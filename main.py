#!/usr/bin/env python3
"""
Noctem - Main Entry Point
Starts all services and provides CLI interface.
"""

import argparse
import signal
import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

import state
from daemon import get_daemon, quick_chat
from signal_receiver import get_receiver
from skill_runner import load_config, list_skills


def format_timedelta(td: timedelta) -> str:
    """Format a timedelta as a human-readable string."""
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    
    return " ".join(parts) if parts else "just now"


def boot_message() -> str:
    """Generate boot message with persistence info."""
    boot_info = state.record_boot()
    
    lines = ["Noctem online."]
    
    # Report time since last boot
    if boot_info["previous_boot"]:
        try:
            last_boot = datetime.fromisoformat(boot_info["previous_boot"])
            delta = datetime.now() - last_boot
            lines.append(f"Last active {format_timedelta(delta)} ago")
            
            if boot_info["previous_machine"] != boot_info["current_machine"]:
                lines.append(f"on {boot_info['previous_machine']}")
        except:
            pass
    
    # Check pending tasks
    pending = state.get_pending_tasks()
    if pending:
        lines.append(f"{len(pending)} task(s) pending.")
    
    return " ".join(lines)


def prompt_for_phone(config_path: Path):
    """Prompt user for Signal phone number if not configured."""
    try:
        phone = input("Enter Signal phone number (e.g., +15551234567) or Enter to skip: ").strip()
        if phone:
            import json
            config_file = config_path / "data" / "config.json"
            with open(config_file, 'r') as f:
                config = json.load(f)
            config['signal_phone'] = phone
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"  ✓ Saved: {phone}")
            return phone
    except (EOFError, KeyboardInterrupt):
        pass
    return None


def start_services(headless: bool = False):
    """Start all Noctem services."""
    config = load_config()
    noctem_dir = Path(__file__).parent
    
    # Initialize parent child handler (for /parent commands)
    from parent.child_handler import init_child_handler
    init_child_handler(
        db_path=noctem_dir / "data" / "noctem.db",
        working_dir=noctem_dir
    )
    
    # Check if Signal phone needs configuration
    if not config.get("signal_phone") and not headless:
        print("\n  ⚠ No Signal phone configured")
        phone = prompt_for_phone(noctem_dir)
        if phone:
            config['signal_phone'] = phone
    
    # Print boot message
    msg = boot_message()
    print(f"\n  🌙 {msg}\n")
    
    # Start daemon
    daemon = get_daemon()
    
    # Check Ollama is running
    if daemon.check_ollama():
        print("  ✓ Ollama connected")
    else:
        print("  ⚠ Ollama not reachable - LLM features disabled")
        print("    Start with: ollama serve")
    
    daemon.start()
    
    # Start Signal receiver if configured
    if config.get("signal_phone"):
        receiver = get_receiver()
        receiver.start()
        
        # Send boot notification if enabled
        if config.get("boot_notification"):
            try:
                from skills.signal_send import SignalSendSkill
                skill = SignalSendSkill()
                from skills.base import SkillContext
                ctx = SkillContext(config=config)
                skill.execute({"message": msg}, ctx)
            except Exception as e:
                print(f"Could not send Signal notification: {e}")
            
            # Also send via email if configured
            try:
                from utils.vault import get_credential
                if get_credential("email_user"):
                    from skills.email_send import send_email_smtp
                    recipient = get_credential("email_recipient") or get_credential("email_user")
                    import socket
                    hostname = socket.gethostname()
                    send_email_smtp(
                        to=recipient,
                        subject=f"🌙 Noctem Online - {hostname}",
                        body=f"{msg}\n\n---\nSent from Noctem on {hostname}"
                    )
                    print(f"  ✓ Email notification sent")
            except Exception as e:
                print(f"  ⚠ Could not send email notification: {e}")
    else:
        print("  ⚠ No signal_phone configured - Signal integration disabled")
    
    print(f"  ✓ Daemon running")
    print(f"  ✓ {len(list_skills())} skills loaded")
    print()


def stop_services():
    """Stop all services gracefully."""
    print("\nShutting down...")
    
    try:
        daemon = get_daemon()
        daemon.stop()
    except:
        pass
    
    try:
        receiver = get_receiver()
        receiver.stop()
    except:
        pass
    
    print("Goodbye! 🌙")


def interactive_mode():
    """Run in interactive CLI mode."""
    print("Noctem Interactive Mode (type 'quit' to exit, 'help' for commands)\n")
    
    daemon = get_daemon()
    
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if not user_input:
            continue
        
        if user_input.lower() in ('quit', 'exit', 'q'):
            break
        
        if user_input.lower() == 'help':
            print("""
Commands:
  quit, exit, q  - Exit interactive mode
  /status        - Show daemon status  
  /queue         - Show task queue
  /last          - Show last Signal message
  /skills        - List available skills
  /task <text>   - Queue a task explicitly
  
Or just type naturally to chat!
""")
            continue
        
        if user_input == '/status':
            status = daemon.get_status()
            print(f"Daemon: {'running' if status['running'] else 'stopped'}")
            print(f"Pending: {status['pending_count']}")
            if status['current_task']:
                print(f"Current: {status['current_task']['input'][:50]}...")
            # Show last Signal message
            last_msg = state.get_state("last_signal_message")
            if last_msg:
                print(f"Last Signal: \"{last_msg.get('text', '')[:40]}...\" [{last_msg.get('status')}]")
            continue
        
        if user_input == '/last':
            last_msg = state.get_state("last_signal_message")
            if last_msg:
                print(f"From: {last_msg.get('from')}")
                print(f"Text: \"{last_msg.get('text')}\"")
                print(f"Time: {last_msg.get('time')}")
                print(f"Status: {last_msg.get('status')}")
            else:
                print("No Signal messages received yet")
            continue
        
        if user_input == '/queue':
            pending = state.get_pending_tasks()
            if not pending:
                print("Queue empty")
            else:
                for task in pending[:10]:
                    print(f"  [{task['id']}] p{task['priority']} \"{task['input'][:40]}\"")
            continue
        
        if user_input == '/skills':
            for name, info in list_skills().items():
                print(f"  {name}: {info['description'][:50]}...")
            continue
        
        if user_input.startswith('/task '):
            task_text = user_input[6:].strip()
            if task_text:
                task_id = state.create_task(task_text, source="cli", priority=5)
                print(f"Queued as task #{task_id}")
            continue
        
        # Regular chat
        print("noctem> ", end="", flush=True)
        response = quick_chat(user_input)
        print(response)
        print()


def main():
    parser = argparse.ArgumentParser(description="Noctem - Your AI Assistant")
    parser.add_argument("--headless", action="store_true", 
                        help="Run without interactive mode (for systemd)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Run in interactive CLI mode")
    parser.add_argument("--task", "-t", type=str,
                        help="Queue a task and exit")
    parser.add_argument("--chat", "-c", type=str,
                        help="Quick chat and exit")
    args = parser.parse_args()
    
    # Handle quick operations
    if args.task:
        task_id = state.create_task(args.task, source="cli", priority=5)
        print(f"Queued as task #{task_id}")
        return
    
    if args.chat:
        print(quick_chat(args.chat))
        return
    
    # Set up signal handlers
    def handle_signal(signum, frame):
        stop_services()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Start services
    start_services(headless=args.headless)
    
    if args.headless:
        # Run forever in headless mode
        print("Running in headless mode. Send SIGTERM to stop.")
        try:
            while True:
                time.sleep(1)
        except:
            pass
    else:
        # Interactive mode
        interactive_mode()
    
    stop_services()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        stop_services()
    except Exception as e:
        import traceback
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        # Try to log the error
        try:
            state.log_incident(
                message=f"Fatal error: {e}",
                severity="critical",
                category="system",
                details=traceback.format_exc()
            )
        except:
            pass
        sys.exit(1)
