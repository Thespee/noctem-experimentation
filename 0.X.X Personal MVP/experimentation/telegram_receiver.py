#!/usr/bin/env python3
"""
Noctem Telegram Receiver
Monitors Telegram for incoming messages via Bot API (HTTP long polling).
No external dependencies - uses only standard library.
"""

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Callable
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

import state
from skill_runner import load_config

logger = logging.getLogger("noctem.telegram")

# Singleton instance
_receiver = None


def get_telegram_receiver():
    """Get the global TelegramReceiver instance."""
    global _receiver
    if _receiver is None:
        _receiver = TelegramReceiver()
    return _receiver


class TelegramReceiver:
    """Receives and processes Telegram messages via Bot API."""
    
    def __init__(self):
        self.config = load_config()
        self.running = False
        self._thread = None
        self.token = self.config.get("telegram_token")
        self.chat_id = self.config.get("telegram_chat_id")
        self._last_update_id = 0
    
    def _api_call(self, method: str, params: dict = None) -> Optional[dict]:
        """Make a Telegram Bot API call."""
        if not self.token:
            return None
        
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        
        try:
            if params:
                data = json.dumps(params).encode('utf-8')
                req = urllib.request.Request(
                    url, 
                    data=data,
                    headers={'Content-Type': 'application/json'}
                )
            else:
                req = urllib.request.Request(url)
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result if result.get("ok") else None
        except urllib.error.URLError as e:
            logger.error(f"Telegram API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Telegram API exception: {e}")
            return None
    
    def send_message(self, text: str, chat_id: str = None) -> bool:
        """Send a message to Telegram."""
        target_chat = chat_id or self.chat_id
        if not target_chat:
            logger.error("No chat_id configured")
            return False
        
        # Telegram has a 4096 char limit per message
        if len(text) > 4000:
            text = text[:4000] + "\n...truncated"
        
        result = self._api_call("sendMessage", {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "Markdown"
        })
        
        # If markdown fails, try plain text
        if not result:
            result = self._api_call("sendMessage", {
                "chat_id": target_chat,
                "text": text
            })
        
        return result is not None
    
    def get_updates(self, timeout: int = 30) -> list:
        """Get new messages using long polling."""
        result = self._api_call("getUpdates", {
            "offset": self._last_update_id + 1,
            "timeout": timeout,
            "allowed_updates": ["message"]
        })
        
        if result and result.get("result"):
            updates = result["result"]
            if updates:
                self._last_update_id = updates[-1]["update_id"]
            return updates
        return []
    
    def handle_command(self, command: str) -> str:
        """Handle a /command - delegates to existing handlers."""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == "/ping":
            return "pong"
        
        elif cmd == "/status":
            from daemon import get_daemon
            daemon = get_daemon()
            status = daemon.get_status()
            pending = state.get_pending_tasks()
            return f"Noctem {'running' if status['running'] else 'stopped'}\nQueue: {len(pending)} pending"
        
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
            return """📋 *Noctem Commands*
            
/ping - Test (responds 'pong')
/tasks - List pending tasks
/add <title> - Add task
/add <title> in <project> - Add to project
/done <id> - Complete a task
/morning - Morning briefing
/status - System status
/help - This message

*Natural language:*
"Buy milk tomorrow at 4pm"
"Call mom on Friday"
"!!! Urgent task" (high priority)"""
        
        else:
            return f"Unknown command: {cmd}\nTry /help"
    
    def handle_message(self, text: str, chat_id: str) -> Optional[str]:
        """Process an incoming message and return response."""
        # Only respond to configured chat
        if self.chat_id and str(chat_id) != str(self.chat_id):
            logger.warning(f"Ignoring message from unauthorized chat: {chat_id}")
            return None
        
        # Log the message
        state.log_message(
            source="telegram",
            sender=str(chat_id),
            text=text
        )
        
        text = text.strip()
        
        # Commands start with /
        if text.startswith('/'):
            return self.handle_command(text)
        
        # Natural language task - try to parse it
        return self.handle_natural_language(text)
    
    def handle_natural_language(self, text: str) -> str:
        """Parse natural language input as a task (no AI)."""
        from utils.nl_task_parser import parse_task
        
        parsed = parse_task(text)
        
        if parsed:
            from skills.task_manager import TaskManagerSkill
            from skills.base import SkillContext
            
            skill = TaskManagerSkill()
            ctx = SkillContext()
            
            params = {"action": "add", "title": parsed["title"]}
            if parsed.get("project"):
                params["project"] = parsed["project"]
            # TODO: Handle due_date when we add that to state.py
            
            result = skill.run(params, ctx)
            
            response = result.output if result.success else f"Error: {result.error}"
            
            # Add parsed info
            if parsed.get("due_date"):
                response += f"\n📅 Due: {parsed['due_date']}"
            
            return response
        
        # Fallback - just add as task
        from skills.task_manager import handle_add_command
        return handle_add_command(text.split())
    
    def _poll_loop(self):
        """Main polling loop - runs in background thread."""
        logger.info("Telegram polling started")
        
        while self.running:
            try:
                updates = self.get_updates(timeout=30)
                
                for update in updates:
                    message = update.get("message", {})
                    text = message.get("text", "")
                    chat_id = message.get("chat", {}).get("id")
                    
                    if text and chat_id:
                        response = self.handle_message(text, chat_id)
                        if response:
                            self.send_message(response, str(chat_id))
            
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)  # Back off on error
    
    def start(self):
        """Start the Telegram receiver."""
        if not self.token:
            logger.error("No telegram_token configured")
            return False
        
        if self.running:
            return True
        
        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram receiver started")
        return True
    
    def stop(self):
        """Stop the Telegram receiver."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Telegram receiver stopped")
