"""Message logging helpers for v0.9.4."""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..db import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(LOG_DIR / "noctem.log")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)

logger = logging.getLogger("noctem")
logger.setLevel(logging.DEBUG)
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("noctem.log") for h in logger.handlers):
    logger.addHandler(file_handler)

_RECENT_LOGS: deque[dict] = deque(maxlen=300)


@dataclass
class MessageLog:
    raw_message: str
    source: str = "cli"
    parsed_command: Optional[str] = None
    parsed_data: dict = field(default_factory=dict)
    action_taken: Optional[str] = None
    result: str = "pending"
    result_details: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def set_parsed(self, command_type: str, data: dict | None = None):
        self.parsed_command = command_type
        self.parsed_data = data or {}
        logger.debug(f"PARSED: {command_type} | {json.dumps(self.parsed_data)}")

    def set_action(self, action: str):
        self.action_taken = action
        logger.debug(f"ACTION: {action}")

    def set_result(self, success: bool, details: dict | None = None):
        self.result = "success" if success else "error"
        self.result_details = details or {}
        level = logging.INFO if success else logging.WARNING
        logger.log(level, f"RESULT: {self.result} | {json.dumps(self.result_details)}")

    def save(self):
        entry = {
            "raw_message": self.raw_message,
            "source": self.source,
            "parsed_command": self.parsed_command,
            "parsed_data": dict(self.parsed_data),
            "action_taken": self.action_taken,
            "result": self.result,
            "result_details": dict(self.result_details),
            "created_at": self.created_at.isoformat() + "Z",
        }
        _RECENT_LOGS.appendleft(entry)
        logger.info(
            f"[{self.source}] \"{self.raw_message}\" -> {self.parsed_command} -> {self.action_taken} -> {self.result}"
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
    getattr(logger, level)(message)


def get_recent_logs(limit: int = 50) -> list[dict]:
    return list(_RECENT_LOGS)[: max(0, int(limit))]


def get_last_entity_created() -> Optional[dict]:
    for entry in _RECENT_LOGS:
        if entry.get("result") != "success":
            continue
        cmd = str(entry.get("parsed_command") or "").upper()
        if cmd in {"NEW_TASK", "PROJECT", "GOAL"}:
            return {
                "type": cmd,
                "parsed": dict(entry.get("parsed_data") or {}),
                "details": dict(entry.get("result_details") or {}),
            }
    return None
