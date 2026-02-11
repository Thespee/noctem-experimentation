#!/usr/bin/env python3
"""
Birth process state machine.
Tracks progress through stages and persists state to disk.
"""

import json
import os
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


class BirthStage(Enum):
    """Birth process stages in order."""
    INIT = auto()
    DETECT = auto()
    NETWORK = auto()
    SYSTEM_DEPS = auto()
    PYTHON_DEPS = auto()
    OLLAMA = auto()
    SIGNAL_CLI = auto()
    NOCTEM_INIT = auto()
    TEST_SKILLS = auto()
    AUTOSTART = auto()
    CLEANUP = auto()
    COMPLETE = auto()
    ERROR = auto()
    UMBILICAL = auto()  # Special state when waiting for remote help


# Stage order for iteration
STAGE_ORDER = [
    BirthStage.DETECT,
    BirthStage.NETWORK,
    BirthStage.SYSTEM_DEPS,
    BirthStage.PYTHON_DEPS,
    BirthStage.OLLAMA,
    BirthStage.SIGNAL_CLI,
    BirthStage.NOCTEM_INIT,
    BirthStage.TEST_SKILLS,
    BirthStage.AUTOSTART,
    BirthStage.CLEANUP,
]


@dataclass
class BirthState:
    """Current state of the birth process."""
    stage: BirthStage = BirthStage.INIT
    started_at: str = ""
    updated_at: str = ""
    completed_stages: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    current_task: str = ""
    progress_percent: int = 0
    umbilical_active: bool = False
    config: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "stage": self.stage.name,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_stages": self.completed_stages,
            "errors": self.errors,
            "current_task": self.current_task,
            "progress_percent": self.progress_percent,
            "umbilical_active": self.umbilical_active,
            "config": self.config,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BirthState":
        """Create from dictionary."""
        stage = BirthStage[data.get("stage", "INIT")]
        return cls(
            stage=stage,
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            completed_stages=data.get("completed_stages", []),
            errors=data.get("errors", []),
            current_task=data.get("current_task", ""),
            progress_percent=data.get("progress_percent", 0),
            umbilical_active=data.get("umbilical_active", False),
            config=data.get("config", {}),
        )
    
    def mark_stage_complete(self, stage: BirthStage):
        """Mark a stage as complete."""
        if stage.name not in self.completed_stages:
            self.completed_stages.append(stage.name)
        self._update_progress()
        self.updated_at = datetime.now().isoformat()
    
    def add_error(self, stage: BirthStage, error: str, recoverable: bool = True):
        """Add an error to the log."""
        self.errors.append({
            "stage": stage.name,
            "error": error,
            "time": datetime.now().isoformat(),
            "recoverable": recoverable,
        })
        if not recoverable:
            self.stage = BirthStage.ERROR
        self.updated_at = datetime.now().isoformat()
    
    def _update_progress(self):
        """Update progress percentage based on completed stages."""
        total = len(STAGE_ORDER)
        completed = len([s for s in self.completed_stages if s in [st.name for st in STAGE_ORDER]])
        self.progress_percent = int((completed / total) * 100)
    
    def get_next_stage(self) -> Optional[BirthStage]:
        """Get the next stage to execute."""
        for stage in STAGE_ORDER:
            if stage.name not in self.completed_stages:
                return stage
        return None
    
    def is_complete(self) -> bool:
        """Check if birth process is complete."""
        return all(stage.name in self.completed_stages for stage in STAGE_ORDER)


# State file location
STATE_FILE = Path(__file__).parent.parent / "data" / ".birth_state.json"


def _ensure_data_dir():
    """Ensure data directory exists."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def save_state(state: BirthState):
    """Save birth state to disk."""
    _ensure_data_dir()
    STATE_FILE.write_text(json.dumps(state.to_dict(), indent=2))


def load_state() -> Optional[BirthState]:
    """Load birth state from disk."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return BirthState.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def clear_state():
    """Remove birth state file."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


# Global state instance
_birth_state: Optional[BirthState] = None


def get_birth_state() -> Optional[BirthState]:
    """Get the current birth state."""
    global _birth_state
    return _birth_state


def init_birth_state(resume: bool = True) -> BirthState:
    """Initialize or resume birth state."""
    global _birth_state
    
    if resume:
        _birth_state = load_state()
    
    if _birth_state is None:
        _birth_state = BirthState()
        save_state(_birth_state)
    
    return _birth_state


def update_birth_state(**kwargs):
    """Update birth state fields and persist."""
    global _birth_state
    if _birth_state is None:
        return
    
    for key, value in kwargs.items():
        if hasattr(_birth_state, key):
            setattr(_birth_state, key, value)
    
    _birth_state.updated_at = datetime.now().isoformat()
    save_state(_birth_state)
