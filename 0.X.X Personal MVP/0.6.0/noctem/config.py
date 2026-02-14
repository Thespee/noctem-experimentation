"""
Configuration management for Noctem.
Loads/saves config from the database config table.
"""
import json
from typing import Any, Optional
from .db import get_db

# Default configuration
DEFAULTS = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "timezone": "America/Vancouver",
    "morning_message_time": "07:00",
    "gcal_sync_interval_minutes": 15,
    "gcal_calendar_ids": ["primary"],
    "web_port": 5000,
    "web_host": "0.0.0.0",
    
    # v0.6.0: Butler protocol
    "butler_contacts_per_week": 5,
    "butler_update_days": ["monday", "wednesday", "friday"],
    "butler_update_time": "09:00",
    "butler_clarification_days": ["tuesday", "thursday"],
    "butler_clarification_time": "09:00",
    
    # v0.6.0: Slow mode
    "slow_mode_enabled": True,
    "slow_model": "qwen2.5:7b-instruct-q4_K_M",
    "ollama_host": "http://localhost:11434",
    "slow_idle_minutes": 5,  # Wait this long after last message before processing
}


class Config:
    """Configuration manager that reads/writes to the database."""

    _cache: dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a config value. Returns default if not set."""
        # Check cache first
        if key in cls._cache:
            return cls._cache[key]

        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()

            if row is None:
                # Return from DEFAULTS if available, else provided default
                value = DEFAULTS.get(key, default)
            else:
                try:
                    value = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    value = row["value"]

            cls._cache[key] = value
            return value

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """Set a config value."""
        json_value = json.dumps(value)
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json_value),
            )
        cls._cache[key] = value

    @classmethod
    def get_all(cls) -> dict[str, Any]:
        """Get all config values, merged with defaults."""
        result = dict(DEFAULTS)
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            for row in rows:
                try:
                    result[row["key"]] = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    result[row["key"]] = row["value"]
        return result

    @classmethod
    def init_defaults(cls) -> None:
        """Initialize config table with default values if not present."""
        with get_db() as conn:
            for key, value in DEFAULTS.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)
                    """,
                    (key, json.dumps(value)),
                )
        cls._cache.clear()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the config cache."""
        cls._cache.clear()

    # Convenience properties for common config values
    @classmethod
    def telegram_token(cls) -> str:
        return cls.get("telegram_bot_token", "")

    @classmethod
    def telegram_chat_id(cls) -> str:
        return cls.get("telegram_chat_id", "")

    @classmethod
    def timezone(cls) -> str:
        return cls.get("timezone", "America/Vancouver")

    @classmethod
    def morning_time(cls) -> str:
        return cls.get("morning_message_time", "07:00")

    @classmethod
    def web_port(cls) -> int:
        return cls.get("web_port", 5000)

    @classmethod
    def web_host(cls) -> str:
        return cls.get("web_host", "0.0.0.0")
