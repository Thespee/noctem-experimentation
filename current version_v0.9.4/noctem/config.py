"""
Configuration management for Noctem.
Loads/saves config from the database config table.
"""
import json
import os
from typing import Any, Optional
from .db import get_db

# Default configuration
DEFAULTS = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "timezone": "America/Vancouver",
    "web_port": 5000,
    "web_host": "0.0.0.0",
    "portal_port": 5001,
    "portal_host": "0.0.0.0",
    # v0.9.3: model-first chat defaults
    "chat_assistant_name": "Alfred",
    "chat_model_first_enabled": True,
    "chat_unified_continuity": True,
    "chat_default_thread_id": "alfred-main",
    "chat_ollama_model": "qwen2.5:7b-instruct-q4_K_M",
    "chat_ollama_base_url": "http://localhost:11434",
    "chat_brief_mode": True,
    "scheduler_job_config": {
        "voice_transcription": {"interval_minutes": 1440, "enabled": True},
        "context_doc_refresh": {"interval_minutes": 5, "enabled": True},
        "ics_refresh": {"interval_minutes": 1440, "enabled": True},
        "queue_retry_scan": {"interval_minutes": 240, "enabled": True},
    },
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
    def web_port(cls) -> int:
        return cls.get("web_port", 5000)

    @classmethod
    def web_host(cls) -> str:
        return cls.get("web_host", "0.0.0.0")

    @classmethod
    def portal_port(cls) -> int:
        return cls.get("portal_port", 5001)

    @classmethod
    def portal_host(cls) -> str:
        return cls.get("portal_host", "0.0.0.0")

    @classmethod
    def _env_bool(cls, key: str, default: bool) -> bool:
        raw = os.environ.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def chat_assistant_name(cls) -> str:
        return (
            os.environ.get("NOCTEM_CHAT_ASSISTANT_NAME")
            or cls.get("chat_assistant_name", "Alfred")
            or "Alfred"
        )

    @classmethod
    def chat_model_first_enabled(cls) -> bool:
        return cls._env_bool(
            "NOCTEM_CHAT_MODEL_FIRST",
            bool(cls.get("chat_model_first_enabled", True)),
        )

    @classmethod
    def chat_unified_continuity(cls) -> bool:
        return cls._env_bool(
            "NOCTEM_CHAT_UNIFIED_CONTINUITY",
            bool(cls.get("chat_unified_continuity", True)),
        )

    @classmethod
    def chat_default_thread_id(cls) -> str:
        value = os.environ.get("NOCTEM_CHAT_DEFAULT_THREAD_ID")
        if value is not None and value.strip():
            return value.strip()
        return (cls.get("chat_default_thread_id", "alfred-main") or "alfred-main").strip()

    @classmethod
    def chat_ollama_model(cls) -> str:
        return (
            os.environ.get("NOCTEM_CHAT_OLLAMA_MODEL")
            or cls.get("chat_ollama_model", "qwen2.5:7b-instruct-q4_K_M")
            or "qwen2.5:7b-instruct-q4_K_M"
        )

    @classmethod
    def chat_ollama_base_url(cls) -> str:
        return (
            os.environ.get("NOCTEM_CHAT_OLLAMA_BASE_URL")
            or cls.get("chat_ollama_base_url", "http://localhost:11434")
            or "http://localhost:11434"
        ).rstrip("/")


    @classmethod
    def chat_brief_mode(cls) -> bool:
        return cls._env_bool(
            "NOCTEM_CHAT_BRIEF_MODE",
            bool(cls.get("chat_brief_mode", True)),
        )
