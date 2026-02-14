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

    @classmethod
    def from_row(cls, row) -> "Project":
        if row is None:
            return None
        return cls(
            id=row["id"],
            name=row["name"],
            goal_id=row["goal_id"],
            status=row["status"],
            summary=row["summary"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            created_at=row["created_at"],
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
        )

    def tags_json(self) -> str:
        """Return tags as JSON string for DB storage."""
        return json.dumps(self.tags) if self.tags else None


@dataclass
class Habit:
    id: Optional[int] = None
    name: str = ""
    goal_id: Optional[int] = None
    frequency: str = "daily"  # daily | weekly | custom
    target_count: int = 1
    custom_days: list[str] = field(default_factory=list)  # e.g., ["mon", "wed", "fri"]
    time_preference: str = "anytime"  # morning | afternoon | evening | anytime
    duration_minutes: Optional[int] = None
    active: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> "Habit":
        if row is None:
            return None
        custom_days = []
        if row["custom_days"]:
            try:
                custom_days = json.loads(row["custom_days"])
            except json.JSONDecodeError:
                custom_days = []
        return cls(
            id=row["id"],
            name=row["name"],
            goal_id=row["goal_id"],
            frequency=row["frequency"],
            target_count=row["target_count"],
            custom_days=custom_days,
            time_preference=row["time_preference"],
            duration_minutes=row["duration_minutes"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    def custom_days_json(self) -> str:
        """Return custom_days as JSON string for DB storage."""
        return json.dumps(self.custom_days) if self.custom_days else None


@dataclass
class HabitLog:
    id: Optional[int] = None
    habit_id: int = 0
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "HabitLog":
        if row is None:
            return None
        return cls(
            id=row["id"],
            habit_id=row["habit_id"],
            completed_at=row["completed_at"],
            notes=row["notes"],
        )


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
    action_type: str = ""  # task_created, task_completed, habit_logged, etc.
    entity_type: Optional[str] = None  # task, habit, project, etc.
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
