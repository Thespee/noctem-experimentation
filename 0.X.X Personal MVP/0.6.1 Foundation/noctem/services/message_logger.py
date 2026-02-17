"""
Verbose message logging for Noctem.
Logs all incoming messages, parsed intent, actions taken, and results.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from ..db import get_db

# File logger setup
LOG_DIR = Path(__file__).parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(LOG_DIR / "noctem.log")
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

logger = logging.getLogger("noctem")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)


class MessageLog:
    """Context manager for logging a complete message interaction."""
    
    def __init__(self, raw_message: str, source: str = "cli"):
        self.raw_message = raw_message
        self.source = source
        self.parsed_command: Optional[str] = None
        self.parsed_data: dict = {}
        self.action_taken: Optional[str] = None
        self.result: str = "pending"
        self.result_details: dict = {}
        self._log_id: Optional[int] = None
    
    def set_parsed(self, command_type: str, data: dict = None):
        """Record what we parsed from the message."""
        self.parsed_command = command_type
        self.parsed_data = data or {}
        logger.debug(f"PARSED: {command_type} | {json.dumps(data or {})}")
    
    def set_action(self, action: str):
        """Record what action we're taking."""
        self.action_taken = action
        logger.debug(f"ACTION: {action}")
    
    def set_result(self, success: bool, details: dict = None):
        """Record the result."""
        self.result = "success" if success else "error"
        self.result_details = details or {}
        level = logging.INFO if success else logging.WARNING
        logger.log(level, f"RESULT: {self.result} | {json.dumps(details or {})}")
    
    def save(self):
        """Save the log entry to database."""
        with get_db() as conn:
            # Check if source column exists
            cursor = conn.execute("PRAGMA table_info(message_log)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'source' in columns:
                conn.execute("""
                    INSERT INTO message_log 
                    (raw_message, parsed_command, parsed_data, action_taken, result, result_details, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.raw_message,
                    self.parsed_command,
                    json.dumps(self.parsed_data),
                    self.action_taken,
                    self.result,
                    json.dumps(self.result_details),
                    self.source,
                ))
            else:
                conn.execute("""
                    INSERT INTO message_log 
                    (raw_message, parsed_command, parsed_data, action_taken, result, result_details)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    self.raw_message,
                    self.parsed_command,
                    json.dumps(self.parsed_data),
                    self.action_taken,
                    self.result,
                    json.dumps(self.result_details),
                ))
            self._log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Also log full entry to file
        logger.info(
            f"[{self.source}] \"{self.raw_message}\" -> {self.parsed_command} "
            f"-> {self.action_taken} -> {self.result}"
        )
    
    def __enter__(self):
        logger.debug(f"INPUT [{self.source}]: {self.raw_message}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.set_result(False, {"error": str(exc_val)})
        self.save()
        return False


def log_simple(message: str, level: str = "info"):
    """Simple logging without full context."""
    getattr(logger, level)(message)


def get_recent_logs(limit: int = 50) -> list[dict]:
    """Get recent message logs from database."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, raw_message, parsed_command, action_taken, result, created_at
            FROM message_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_last_entity_created() -> Optional[dict]:
    """Get the last created entity for correction feature."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT parsed_command, parsed_data, result_details
            FROM message_log
            WHERE result = 'success' 
              AND parsed_command IN ('NEW_TASK', 'PROJECT', 'HABIT', 'GOAL')
            ORDER BY created_at DESC
            LIMIT 1
        """).fetchone()
        if row:
            return {
                "type": row["parsed_command"],
                "parsed": json.loads(row["parsed_data"]) if row["parsed_data"] else {},
                "details": json.loads(row["result_details"]) if row["result_details"] else {}
            }
        return None
