#!/usr/bin/env python3
"""
Noctem Signal Receiver
Monitors Signal for incoming messages and routes them appropriately.
Uses signal-cli daemon mode via JSON-RPC for reliable send/receive.
"""

import json
import socket
import subprocess
import threading
import logging
import time
from typing import Optional, Callable
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

import state
from daemon import get_daemon, quick_chat
from skill_runner import load_config, run_skill

logger = logging.getLogger("noctem.signal")

# JSON-RPC connection settings
SIGNAL_DAEMON_HOST = "127.0.0.1"
SIGNAL_DAEMON_PORT = 7583

# Action words that suggest a task rather than quick chat
# These should be imperative verbs at the START of the message
ACTION_WORDS = [
    "find", "search", "create", "write", "build", "make", "generate",
    "analyze", "summarize", "fetch", "get", "download", "scrape",
    "send", "email", "schedule", "remind", "set up", "configure",
    "install", "run", "execute", "debug", "fix", "refactor", "check"
]

# Question starters - these are quick chats
QUESTION_WORDS = [
    "what", "how", "why", "when", "where", "who", "which",
    "is", "are", "do", "does", "can", "could", "would", "will"
]


class SignalReceiver:
    """Receives and processes Signal messages."""
    
    def __init__(self):
        self.config = load_config()
        self.running = False
        self._thread = None
        self.phone = self.config.get("signal_phone")
    
    def is_quick_chat(self, message: str) -> bool:
        """Determine if a message should be handled as quick chat vs queued task."""
        # Commands are always quick
        if message.startswith('/'):
            return True
        
        msg_lower = message.lower().strip()
        first_word = msg_lower.split()[0] if msg_lower else ""
        
        # Questions are quick chats (unless very long)
        if first_word in QUESTION_WORDS or msg_lower.endswith('?'):
            return len(message) < 200  # Only queue very long questions
        
        # Short messages without action words at the START are quick
        max_len = self.config.get("quick_chat_max_length", 80)
        if len(message) < max_len:
            # Check if message STARTS with an action word (imperative)
            if first_word not in ACTION_WORDS:
                return True
        
        return False
    
    def handle_command(self, command: str) -> str:
        """Handle a /command."""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Handle /parent commands via parent module
        if cmd == "/parent":
            from parent.child_handler import handle_parent_message
            response = handle_parent_message(command)
            if response:
                return response
            return "Invalid parent command. Use: /parent <status|history|health|logs|report>"
        
        if cmd == "/status":
            daemon = get_daemon()
            status = daemon.get_status()
            running = state.get_running_tasks()
            pending = state.get_pending_tasks()
            
            lines = [f"Noctem {'running' if status['running'] else 'stopped'}"]
            if running:
                lines.append(f"Current: {running[0]['input'][:30]}...")
            lines.append(f"Queue: {len(pending)} pending")
            return "\n".join(lines)
        
        elif cmd == "/queue":
            pending = state.get_pending_tasks()
            if not pending:
                return "Queue empty"
            lines = [f"Queue ({len(pending)}):"]
            for task in pending[:5]:
                lines.append(f"  [{task['id']}] p{task['priority']} \"{task['input'][:30]}\"")
            if len(pending) > 5:
                lines.append(f"  ...and {len(pending)-5} more")
            return "\n".join(lines)
        
        elif cmd == "/cancel":
            if not args:
                return "Usage: /cancel <task_id>"
            try:
                task_id = int(args[0])
                if state.cancel_task(task_id):
                    return f"Cancelled task {task_id}"
                else:
                    return f"Could not cancel task {task_id} (not found or not pending)"
            except ValueError:
                return "Invalid task ID"
        
        elif cmd == "/priority":
            if len(args) < 2:
                return "Usage: /priority <task_id> <1-10>"
            try:
                task_id = int(args[0])
                priority = int(args[1])
                if state.set_task_priority(task_id, priority):
                    return f"Set task {task_id} priority to {priority}"
                else:
                    return f"Could not change priority (invalid ID or priority)"
            except ValueError:
                return "Invalid task ID or priority"
        
        elif cmd == "/echo" or cmd.startswith("/echo "):
            # Simple echo test - no LLM, just repeat back
            text = command[6:].strip() if len(command) > 6 else "(empty)"
            return f"Echo: {text}"
        
        elif cmd == "/ping":
            # Even simpler - just respond
            return "pong"
        
        elif cmd == "/last":
            last_msg = state.get_state("last_signal_message")
            if last_msg:
                return f"Last message: \"{last_msg.get('text', '')[:50]}\"\nStatus: {last_msg.get('status')}\nTime: {last_msg.get('time')}"
            return "No messages received yet"
        
        elif cmd == "/report":
            # Generate daily report (no send)
            try:
                from skills.daily_report import generate_report
                report, stats = generate_report(period_hours=24)
                # Truncate for Signal
                if len(report) > 1500:
                    report = report[:1500] + "\n...truncated"
                return report
            except Exception as e:
                return f"Report error: {e}"
        
        elif cmd == "/email":
            return self.handle_email_command(" ".join(args))
        
        elif cmd == "/tasks":
            from skills.task_manager import handle_tasks_command
            return handle_tasks_command(args)
        
        elif cmd == "/add":
            from skills.task_manager import handle_add_command
            return handle_add_command(args)
        
        elif cmd == "/done":
            from skills.task_manager import handle_done_command
            return handle_done_command(args)
        
        elif cmd == "/morning":
            try:
                from utils.morning_report import generate_morning_report
                return generate_morning_report()
            except Exception as e:
                return f"Error generating report: {e}"
        
        elif cmd == "/help":
            return """Commands:
/ping - Test (responds 'pong')
/tasks - List pending tasks
/add <title> - Add task (/add Buy milk in Shopping)
/done <id> - Complete a task
/morning - Morning briefing
/status - System status
/report - Generate daily report
/help - This message"""
        
        else:
            return f"Unknown command: {cmd}. Try /help"
    
    def handle_email_command(self, args_str: str) -> str:
        """Handle /email subcommands."""
        args = args_str.strip().split() if args_str.strip() else []
        
        if not args:
            return """Email commands:
/email status - Check email config
/email test - Send test email
/email check - Check inbox
/email report - Send daily report now"""
        
        subcmd = args[0].lower()
        
        if subcmd == "status":
            try:
                from utils.vault import get_vault
                vault = get_vault()
                status = vault.status()
                user = vault.get("email_user") if vault.has("email_user") else None
                recipient = vault.get("email_recipient") if vault.has("email_recipient") else None
                
                if not user:
                    return "❌ Email not configured\nRun: python utils/vault.py"
                
                return f"""📧 Email Status:
  From: {user}
  To: {recipient or user}
  Backend: {status['backend']}
  Keys: {', '.join(status['configured_keys'])}"""
            except Exception as e:
                return f"Error: {e}"
        
        elif subcmd == "test":
            try:
                from skills.email_send import test_smtp_connection, send_email_smtp
                from utils.vault import get_credential
                
                # Test connection first
                success, msg = test_smtp_connection()
                if not success:
                    return f"❌ SMTP test failed: {msg}"
                
                # Send test email
                recipient = get_credential("email_recipient") or get_credential("email_user")
                success, msg = send_email_smtp(
                    to=recipient,
                    subject="🌙 Noctem Test Email",
                    body="This is a test email from Noctem.\n\nIf you received this, email is working!"
                )
                
                if success:
                    return f"✅ Test email sent to {recipient}"
                return f"❌ Send failed: {msg}"
            except Exception as e:
                return f"Error: {e}"
        
        elif subcmd == "check":
            try:
                from skills.email_fetch import fetch_emails
                emails, error = fetch_emails(limit=5, unread_only=True, since_hours=24)
                
                if error:
                    return f"❌ {error}"
                
                if not emails:
                    return "📭 No new emails"
                
                lines = [f"📬 {len(emails)} email(s):"]
                for e in emails[:5]:
                    subj = e['subject'][:35] + "..." if len(e['subject']) > 35 else e['subject']
                    lines.append(f"  • {subj}")
                    lines.append(f"    {e['from']['address']}")
                return "\n".join(lines)
            except Exception as e:
                return f"Error: {e}"
        
        elif subcmd == "report":
            try:
                from skills.daily_report import send_daily_report
                success, msg, stats = send_daily_report()
                
                if success:
                    return f"✅ Report sent!\nTasks: {stats['tasks_completed']} done, {stats['tasks_failed']} failed\nIncidents: {stats['incidents_count']}"
                return f"❌ {msg}"
            except Exception as e:
                return f"Error: {e}"
        
        else:
            return f"Unknown email command: {subcmd}\nTry: /email status, test, check, report"
    
    def send_response(self, message: str, recipient: Optional[str] = None):
        """Send a response via Signal using JSON-RPC daemon."""
        phone = recipient or self.phone
        if not phone:
            logger.error("No phone number configured")
            return
        
        # Truncate long messages
        if len(message) > 2000:
            message = message[:1997] + "..."
        
        print(f"   → Sending via daemon...")
        
        try:
            # JSON-RPC request to daemon
            request = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    "recipient": [phone],
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
                if not chunk:
                    break
                response += chunk
                if b"\n" in response:
                    break
            sock.close()
            
            result = json.loads(response.decode().strip())
            if "error" in result:
                print(f"   ✗ Send error: {result['error']}")
                logger.error(f"Signal send error: {result['error']}")
            else:
                print(f"   ✓ Sent")
                
        except ConnectionRefusedError:
            print(f"   ✗ Daemon not running! Start with: signal-cli -a {phone} daemon --tcp")
            logger.error("signal-cli daemon not running")
        except Exception as e:
            print(f"   ✗ Send failed: {e}")
            logger.error(f"Failed to send Signal message: {e}")
    
    def process_message(self, sender: str, message: str):
        """Process an incoming message."""
        from datetime import datetime
        
        # Visible console output
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n📱 [{timestamp}] Signal message from {sender}:")
        print(f"   \"{message[:80]}{'...' if len(message) > 80 else ''}\"")
        
        # Store in state for visibility
        state.set_state("last_signal_message", {
            "from": sender,
            "text": message[:100],
            "time": datetime.now().isoformat(),
            "status": "received"
        })
        
        logger.info(f"Message from {sender}: {message[:50]}...")
        
        # Only respond to allowed number
        if self.phone and sender != self.phone:
            print(f"   ⚠ BLOCKED (not from {self.phone})")
            logger.warning(f"Blocked message from unauthorized sender: {sender}")
            state.set_state("last_signal_message", {
                "from": sender,
                "text": message[:100],
                "time": datetime.now().isoformat(),
                "status": "blocked"
            })
            return
        
        # Handle commands
        if message.startswith('/'):
            print(f"   → Handling command...")
            response = self.handle_command(message)
            self.send_response(response)
            print(f"   ✓ Response sent")
            state.set_state("last_signal_message", {
                "from": sender,
                "text": message[:100],
                "time": datetime.now().isoformat(),
                "status": "replied"
            })
            return
        
        # Quick chat vs task
        if self.is_quick_chat(message):
            print(f"   → Quick chat, calling LLM...")
            state.set_state("last_signal_message", {
                "from": sender,
                "text": message[:100],
                "time": datetime.now().isoformat(),
                "status": "processing"
            })
            response = quick_chat(message)
            print(f"   → Sending response ({len(response)} chars)...")
            self.send_response(response)
            print(f"   ✓ Done")
            state.set_state("last_signal_message", {
                "from": sender,
                "text": message[:100],
                "time": datetime.now().isoformat(),
                "status": "replied"
            })
        else:
            # Queue as task
            print(f"   → Queueing as background task...")
            task_id = state.create_task(message, source="signal", priority=4)
            self.send_response(f"Queued as task #{task_id}. I'll message you when done.")
            print(f"   ✓ Queued as task #{task_id}")
            state.set_state("last_signal_message", {
                "from": sender,
                "text": message[:100],
                "time": datetime.now().isoformat(),
                "status": f"queued #{task_id}"
            })
            
            # If daemon is running, the task will be processed
            # Otherwise, we process it directly
            daemon = get_daemon()
            if not daemon.running:
                result = daemon.execute_task(state.get_task(task_id))
                self.send_response(result)
    
    def listen(self):
        """Listen for incoming Signal messages via JSON-RPC daemon."""
        if not self.phone:
            logger.error("No signal_phone configured")
            return
        
        print(f"📱 Signal receiver connecting to daemon on port {SIGNAL_DAEMON_PORT}...")
        logger.info(f"Connecting to signal-cli daemon for {self.phone}")
        
        while self.running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                sock.connect((SIGNAL_DAEMON_HOST, SIGNAL_DAEMON_PORT))
                
                # Subscribe to receive messages (required for newer signal-cli versions)
                subscribe_request = {
                    "jsonrpc": "2.0",
                    "method": "subscribeReceive",
                    "params": {"account": self.phone},
                    "id": 1
                }
                sock.sendall((json.dumps(subscribe_request) + "\n").encode())
                # Read subscription response
                sub_response = sock.recv(4096).decode()
                print(f"📱 Subscribed to messages: {sub_response[:100]}...")
                
                print(f"📱 Connected! Waiting for messages...")
                
                sock.settimeout(None)  # Block forever waiting for messages
                buffer = ""
                
                while self.running:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            print("📱 Daemon connection closed, reconnecting...")
                            break
                        
                        buffer += chunk.decode()
                        
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            
                            try:
                                data = json.loads(line)
                                
                                # Try multiple possible structures
                                envelope = None
                                
                                # Structure 1: {"envelope": {...}}
                                if "envelope" in data:
                                    envelope = data["envelope"]
                                # Structure 2: {"params": {"envelope": {...}}}
                                elif "params" in data and "envelope" in data.get("params", {}):
                                    envelope = data["params"]["envelope"]
                                # Structure 3: {"method": "receive", "params": {...}}
                                elif "method" in data:
                                    params = data.get("params", {})
                                    if "envelope" in params:
                                        envelope = params["envelope"]
                                
                                if envelope:
                                    source = envelope.get("sourceNumber") or envelope.get("source")
                                    message = None
                                    
                                    # Try dataMessage first (messages from others)
                                    data_message = envelope.get("dataMessage", {})
                                    if data_message:
                                        message = data_message.get("message")
                                    
                                    # Try syncMessage (messages synced from your own phone)
                                    if not message:
                                        sync_message = envelope.get("syncMessage", {})
                                        sent = sync_message.get("sentMessage", {})
                                        if sent:
                                            message = sent.get("message")
                                            # For sent messages, destination is more relevant
                                            dest = sent.get("destinationNumber") or sent.get("destination")
                                            if dest:
                                                source = dest
                                    
                                    if source and message:
                                        self.process_message(source, message)
                                    
                            except json.JSONDecodeError:
                                continue
                                
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Receive error: {e}")
                        break
                
                sock.close()
                
            except ConnectionRefusedError:
                print(f"📱 Daemon not running. Start with: signal-cli -a {self.phone} daemon --tcp 127.0.0.1:{SIGNAL_DAEMON_PORT}")
                time.sleep(5)
            except Exception as e:
                print(f"📱 Connection error: {e}")
                logger.error(f"Signal connection error: {e}")
                time.sleep(5)
    
    def start(self):
        """Start the Signal receiver in a background thread."""
        if self.running:
            return
        
        if not self.phone:
            logger.warning("No signal_phone configured, skipping Signal receiver")
            return
        
        self.running = True
        self._thread = threading.Thread(target=self.listen, daemon=True)
        self._thread.start()
        logger.info("Signal receiver started")
    
    def stop(self):
        """Stop the Signal receiver."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Signal receiver stopped")


# Global receiver instance
_receiver: Optional[SignalReceiver] = None


def get_receiver() -> SignalReceiver:
    """Get or create the global receiver instance."""
    global _receiver
    if _receiver is None:
        _receiver = SignalReceiver()
    return _receiver


if __name__ == "__main__":
    # Test
    receiver = get_receiver()
    
    print("Testing quick chat detection:")
    print(f"  'hello' -> quick: {receiver.is_quick_chat('hello')}")
    print(f"  'find the weather' -> quick: {receiver.is_quick_chat('find the weather')}")
    print(f"  '/status' -> quick: {receiver.is_quick_chat('/status')}")
    
    print("\nTesting command handling:")
    print(f"  /help -> {receiver.handle_command('/help')}")
