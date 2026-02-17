"""
Data models for Noctem entities.
"""
from dataclasses import dataclass, field
from datetime import date, time, datetime
from typing import Optional
import json


@dataclass
class Goal:
    id: Optional[int] = None
    name: str = ""
    type: str = "bigger_goal"  # bigger_goal | daily_goal
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    archived: bool = False

    @classmethod
    def from_row(cls, row) -> "Goal":
        if row is None:
            return None
        return cls(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            description=row["description"],
            created_at=row["created_at"],
            archived=bool(row["archived"]),
        )


@dataclass
class Project:
    id: Optional[int] = None
    name: str = ""
    goal_id: Optional[int] = None
    status: str = "in_progress"  # backburner | in_progress | done | canceled
    summary: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: Optional[datetime] = None
    # v0.6.0: AI suggestions
    next_action_suggestion: Optional[str] = None
    suggestion_generated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "Project":
        if row is None:
            return None
        # Safely get suggestion fields (may not exist in older DBs)
        next_action = row["next_action_suggestion"] if "next_action_suggestion" in row.keys() else None
        suggestion_at = row["suggestion_generated_at"] if "suggestion_generated_at" in row.keys() else None
        return cls(
            id=row["id"],
            name=row["name"],
            goal_id=row["goal_id"],
            status=row["status"],
            summary=row["summary"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            created_at=row["created_at"],
            next_action_suggestion=next_action,
            suggestion_generated_at=suggestion_at,
        )


@dataclass
class Task:
    id: Optional[int] = None
    name: str = ""
    project_id: Optional[int] = None
    status: str = "not_started"  # not_started | in_progress | done | canceled
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    importance: float = 0.5  # 0-1 scale: 1=important, 0.5=medium, 0=not important
    tags: list[str] = field(default_factory=list)
    recurrence_rule: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # v0.6.0: AI suggestions
    computer_help_suggestion: Optional[str] = None
    suggestion_generated_at: Optional[datetime] = None
    # v0.6.0 Polish: Duration for context-aware suggestions
    duration_minutes: Optional[int] = None

    @property
    def title(self) -> str:
        """Alias for name (for consistency)."""
        return self.name

    @property
    def urgency(self) -> float:
        """Calculate urgency score (0-1) based on due date. Higher = more urgent."""
        if self.due_date is None:
            return 0.0  # No due date = not urgent
        
        today = date.today()
        days_until = (self.due_date - today).days
        
        if days_until < 0:  # Overdue
            return 1.0
        elif days_until == 0:  # Due today
            return 1.0
        elif days_until == 1:  # Due tomorrow
            return 0.9
        elif days_until <= 3:  # Due within 3 days
            return 0.7
        elif days_until <= 7:  # Due within a week
            return 0.5
        elif days_until <= 14:  # Due within 2 weeks
            return 0.3
        elif days_until <= 30:  # Due within a month
            return 0.1
        else:
            return 0.0

    @property
    def priority_score(self) -> float:
        """Calculate priority score (0-1) from importance and urgency."""
        # Weighted combination: importance matters more but urgency boosts it
        return (self.importance * 0.6) + (self.urgency * 0.4)

    @classmethod
    def from_row(cls, row) -> "Task":
        if row is None:
            return None
        tags = []
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except json.JSONDecodeError:
                tags = []
        
        # Parse due_date if it's a string
        due_date_val = row["due_date"]
        if isinstance(due_date_val, str):
            due_date_val = date.fromisoformat(due_date_val)
        
        # Parse due_time if it's a string
        due_time_val = row["due_time"]
        if isinstance(due_time_val, str):
            due_time_val = time.fromisoformat(due_time_val)
        
        # Get importance, default to 0.5 if not present or None
        importance_val = row.get("importance") if hasattr(row, 'get') else row["importance"]
        if importance_val is None:
            importance_val = 0.5
        
        # Safely get suggestion fields (may not exist in older DBs)
        computer_help = row["computer_help_suggestion"] if "computer_help_suggestion" in row.keys() else None
        suggestion_at = row["suggestion_generated_at"] if "suggestion_generated_at" in row.keys() else None
        duration = row["duration_minutes"] if "duration_minutes" in row.keys() else None
        
        return cls(
            id=row["id"],
            name=row["name"],
            project_id=row["project_id"],
            status=row["status"],
            due_date=due_date_val,
            due_time=due_time_val,
            importance=importance_val,
            tags=tags,
            recurrence_rule=row["recurrence_rule"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            computer_help_suggestion=computer_help,
            suggestion_generated_at=suggestion_at,
            duration_minutes=duration,
        )

    def tags_json(self) -> str:
        """Return tags as JSON string for DB storage."""
        return json.dumps(self.tags) if self.tags else None


@dataclass
class TimeBlock:
    id: Optional[int] = None
    title: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    source: str = "manual"  # manual | gcal | ics
    gcal_event_id: Optional[str] = None
    block_type: str = "other"  # meeting | focus | personal | other
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "TimeBlock":
        if row is None:
            return None
        
        # Parse datetime strings from SQLite
        start_time = row["start_time"]
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time)
            except ValueError:
                pass
        
        end_time = row["end_time"]
        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time)
            except ValueError:
                pass
        
        return cls(
            id=row["id"],
            title=row["title"],
            start_time=start_time,
            end_time=end_time,
            source=row["source"],
            gcal_event_id=row["gcal_event_id"],
            block_type=row["block_type"],
            created_at=row["created_at"],
        )


@dataclass
class ActionLog:
    id: Optional[int] = None
    action_type: str = ""  # task_created, task_completed, etc.
    entity_type: Optional[str] = None  # task, project, goal, etc.
    entity_id: Optional[int] = None
    details: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "ActionLog":
        if row is None:
            return None
        details = {}
        if row["details"]:
            try:
                details = json.loads(row["details"])
            except json.JSONDecodeError:
                details = {}
        return cls(
            id=row["id"],
            action_type=row["action_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            details=details,
            created_at=row["created_at"],
        )

    def details_json(self) -> str:
        """Return details as JSON string for DB storage."""
        return json.dumps(self.details) if self.details else None


@dataclass
class Thought:
    """Universal capture for all inputs (royal scribe pattern)."""
    id: Optional[int] = None
    source: str = "cli"  # 'telegram', 'cli', 'web', 'voice'
    raw_text: str = ""
    kind: Optional[str] = None  # 'actionable', 'note', 'ambiguous'
    ambiguity_reason: Optional[str] = None  # 'scope', 'timing', 'intent'
    confidence: Optional[float] = None  # 0.0-1.0 classifier confidence
    linked_task_id: Optional[int] = None
    linked_project_id: Optional[int] = None
    voice_journal_id: Optional[int] = None
    status: str = "pending"  # 'pending', 'processed', 'clarified'
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "Thought":
        if row is None:
            return None
        return cls(
            id=row["id"],
            source=row["source"],
            raw_text=row["raw_text"],
            kind=row["kind"],
            ambiguity_reason=row["ambiguity_reason"] if "ambiguity_reason" in row.keys() else None,
            confidence=row["confidence"],
            linked_task_id=row["linked_task_id"],
            linked_project_id=row["linked_project_id"],
            voice_journal_id=row["voice_journal_id"] if "voice_journal_id" in row.keys() else None,
            status=row["status"],
            created_at=row["created_at"],
            processed_at=row["processed_at"],
        )


@dataclass
class Conversation:
    """Unified conversation log across web/CLI/Telegram."""
    id: Optional[int] = None
    session_id: Optional[str] = None
    source: str = "cli"  # 'web', 'cli', 'telegram'
    role: str = "user"  # 'user', 'assistant', 'system'
    content: str = ""
    thinking_summary: Optional[str] = None
    thinking_level: Optional[str] = None  # 'decision', 'activity', 'debug'
    metadata: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "Conversation":
        if row is None:
            return None
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        # Parse created_at if it's a string
        created_at_val = row["created_at"]
        if isinstance(created_at_val, str):
            try:
                created_at_val = datetime.fromisoformat(created_at_val)
            except ValueError:
                pass
        
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            source=row["source"],
            role=row["role"],
            content=row["content"],
            thinking_summary=row["thinking_summary"],
            thinking_level=row["thinking_level"],
            metadata=metadata,
            created_at=created_at_val,
        )

    def metadata_json(self) -> str:
        """Return metadata as JSON string for DB storage."""
        return json.dumps(self.metadata) if self.metadata else None


@dataclass
class PromptTemplate:
    """LLM prompt template with versioning."""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    current_version: int = 1
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "PromptTemplate":
        if row is None:
            return None
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            current_version=row["current_version"],
            created_at=row["created_at"],
        )


@dataclass
class PromptVersion:
    """A specific version of a prompt template."""
    id: Optional[int] = None
    template_id: int = 0
    version: int = 1
    prompt_text: str = ""
    variables: list[str] = field(default_factory=list)  # ['task_name', 'project_context']
    created_at: Optional[datetime] = None
    created_by: str = "system"  # 'system', 'user'

    @classmethod
    def from_row(cls, row) -> "PromptVersion":
        if row is None:
            return None
        variables = []
        if row["variables"]:
            try:
                variables = json.loads(row["variables"])
            except json.JSONDecodeError:
                variables = []
        return cls(
            id=row["id"],
            template_id=row["template_id"],
            version=row["version"],
            prompt_text=row["prompt_text"],
            variables=variables,
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def variables_json(self) -> str:
        """Return variables as JSON string for DB storage."""
        return json.dumps(self.variables) if self.variables else None
