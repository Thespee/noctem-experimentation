"""
Session state management for interactive modes.
Handles /prioritize, /update, and * correction.
"""
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class SessionMode(Enum):
    NORMAL = "normal"
    PRIORITIZE = "prioritize"  # Reordering top n tasks
    UPDATE = "update"  # Filling in missing info


@dataclass
class UpdateItem:
    """An item that needs updating."""
    index: int
    entity_type: str  # "task", "project"
    entity_id: int
    name: str
    missing: list[str]  # What's missing: "due_date", "importance", "project", "goal", "tasks"


@dataclass
class Session:
    """Session state for a user interaction."""
    mode: SessionMode = SessionMode.NORMAL
    
    # For /prioritize mode
    prioritize_tasks: list[Any] = field(default_factory=list)
    prioritize_count: int = 0
    
    # For /update mode
    update_items: list[UpdateItem] = field(default_factory=list)
    update_index: int = 0
    
    # For * correction
    last_entity_type: Optional[str] = None  # "task", "habit", "project", "goal"
    last_entity_id: Optional[int] = None
    
    def reset(self):
        """Reset to normal mode."""
        self.mode = SessionMode.NORMAL
        self.prioritize_tasks = []
        self.prioritize_count = 0
        self.update_items = []
        self.update_index = 0
    
    def set_last_entity(self, entity_type: str, entity_id: int):
        """Track the last created/modified entity for correction."""
        self.last_entity_type = entity_type
        self.last_entity_id = entity_id


# Global session (will be per-user in Telegram)
_session = Session()


def get_session() -> Session:
    """Get the current session."""
    return _session


def reset_session():
    """Reset the session to normal mode."""
    _session.reset()
