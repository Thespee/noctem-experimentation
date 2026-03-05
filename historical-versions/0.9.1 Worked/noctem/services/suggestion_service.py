"""
Context-aware suggestion service for Noctem v0.6.0 Polish.

Provides smart task suggestions that consider:
- Calendar gaps (free time between meetings)
- Task duration estimates
- Current time of day
- Task priorities
"""
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import List, Optional, Tuple

from ..db import get_db
from ..models import Task, TimeBlock
from . import task_service
from .briefing import get_time_blocks_for_date


@dataclass
class TimeGap:
    """A gap of free time in the calendar."""
    start: datetime
    end: datetime
    duration_minutes: int
    
    @property
    def description(self) -> str:
        """Human-readable description of the gap."""
        start_str = self.start.strftime("%H:%M")
        end_str = self.end.strftime("%H:%M")
        return f"{start_str}-{end_str} ({self.duration_minutes} min)"


@dataclass
class TaskSuggestion:
    """A suggested task with context about why it fits."""
    task: Task
    suggested_gap: Optional[TimeGap] = None
    fit_reason: str = ""
    score: float = 0.0  # Combined score for ranking
    
    @property
    def summary(self) -> str:
        """One-line summary of the suggestion."""
        if self.suggested_gap:
            return f"{self.task.name} — fits {self.suggested_gap.description}"
        return f"{self.task.name} — {self.fit_reason}"


# Default work hours for gap detection
DEFAULT_WORK_START = time(9, 0)
DEFAULT_WORK_END = time(18, 0)

# Minimum gap size to consider (minutes)
MIN_GAP_MINUTES = 15

# Default task duration if not specified (minutes)
DEFAULT_TASK_DURATION = 30


def get_calendar_gaps(
    target_date: date = None,
    work_start: time = DEFAULT_WORK_START,
    work_end: time = DEFAULT_WORK_END,
) -> List[TimeGap]:
    """
    Find gaps of free time in the calendar for a given date.
    
    Args:
        target_date: Date to check (default: today)
        work_start: Start of work hours
        work_end: End of work hours
    
    Returns:
        List of TimeGap objects representing free time
    """
    if target_date is None:
        target_date = date.today()
    
    # Get all time blocks for the date
    blocks = get_time_blocks_for_date(target_date)
    
    # Convert work hours to datetime
    day_start = datetime.combine(target_date, work_start)
    day_end = datetime.combine(target_date, work_end)
    
    # Sort blocks by start time
    sorted_blocks = sorted(blocks, key=lambda b: b.start_time if b.start_time else day_start)
    
    gaps = []
    current_time = day_start
    
    # If checking today, start from now (not day_start)
    now = datetime.now()
    if target_date == date.today() and now > current_time:
        # Round up to next 15-minute boundary
        minutes = (now.minute // 15 + 1) * 15
        if minutes >= 60:
            # Use timedelta to properly handle hour rollover (e.g., 23:45 -> 00:00)
            current_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            current_time = now.replace(minute=minutes, second=0, microsecond=0)
    
    for block in sorted_blocks:
        block_start = block.start_time
        block_end = block.end_time
        
        # Parse if strings
        if isinstance(block_start, str):
            block_start = datetime.fromisoformat(block_start)
        if isinstance(block_end, str):
            block_end = datetime.fromisoformat(block_end)
        
        # Skip blocks outside work hours
        if block_end < current_time or block_start > day_end:
            continue
        
        # If there's a gap before this block
        if block_start > current_time:
            gap_end = min(block_start, day_end)
            gap_minutes = int((gap_end - current_time).total_seconds() / 60)
            
            if gap_minutes >= MIN_GAP_MINUTES:
                gaps.append(TimeGap(
                    start=current_time,
                    end=gap_end,
                    duration_minutes=gap_minutes,
                ))
        
        # Move current time past this block
        current_time = max(current_time, block_end)
    
    # Check for gap after last block
    if current_time < day_end:
        gap_minutes = int((day_end - current_time).total_seconds() / 60)
        if gap_minutes >= MIN_GAP_MINUTES:
            gaps.append(TimeGap(
                start=current_time,
                end=day_end,
                duration_minutes=gap_minutes,
            ))
    
    return gaps


def get_tasks_for_gap(gap: TimeGap, max_count: int = 5) -> List[Task]:
    """
    Get tasks that would fit in a given time gap.
    
    Args:
        gap: The time gap to fill
        max_count: Maximum tasks to return
    
    Returns:
        List of tasks sorted by fit (best first)
    """
    # Get all active tasks
    all_tasks = task_service.get_all_tasks(include_done=False)
    
    fitting_tasks = []
    for task in all_tasks:
        duration = task.duration_minutes or DEFAULT_TASK_DURATION
        
        # Task fits if its duration is <= gap duration
        if duration <= gap.duration_minutes:
            fitting_tasks.append(task)
    
    # Sort by priority score (highest first)
    fitting_tasks.sort(key=lambda t: t.priority_score, reverse=True)
    
    return fitting_tasks[:max_count]


def get_fitting_tasks(gap: TimeGap) -> List[Task]:
    """Alias for get_tasks_for_gap."""
    return get_tasks_for_gap(gap)


def _calculate_suggestion_score(task: Task, gap: Optional[TimeGap], now: datetime) -> float:
    """
    Calculate a score for how good a suggestion is.
    Higher score = better suggestion.
    """
    score = task.priority_score * 0.5  # Base from task priority
    
    # Bonus for having a duration estimate
    if task.duration_minutes:
        score += 0.1
    
    # Bonus for fitting in a gap
    if gap:
        duration = task.duration_minutes or DEFAULT_TASK_DURATION
        # Perfect fit bonus
        if gap.duration_minutes - duration < 15:
            score += 0.2
        else:
            score += 0.1
    
    # Time-of-day considerations
    hour = now.hour
    
    # Morning (9-12): Prefer important tasks
    if 9 <= hour < 12:
        if task.importance >= 0.8:
            score += 0.1
    
    # Afternoon (12-17): Prefer medium tasks
    elif 12 <= hour < 17:
        pass  # No adjustment
    
    # Evening (17+): Prefer quick/easy tasks
    else:
        if task.duration_minutes and task.duration_minutes <= 15:
            score += 0.1
    
    return min(1.0, score)


def get_contextual_suggestions(
    max_count: int = 5,
    target_date: date = None,
) -> List[TaskSuggestion]:
    """
    Get context-aware task suggestions.
    
    Considers:
    - Current calendar gaps
    - Task durations
    - Task priorities
    - Time of day
    
    Args:
        max_count: Maximum suggestions to return
        target_date: Date to suggest for (default: today)
    
    Returns:
        List of TaskSuggestion objects, best first
    """
    if target_date is None:
        target_date = date.today()
    
    now = datetime.now()
    
    # Get calendar gaps
    gaps = get_calendar_gaps(target_date)
    
    # Get priority tasks
    priority_tasks = task_service.get_priority_tasks(max_count * 2)
    
    suggestions = []
    used_task_ids = set()
    
    # First pass: Match tasks to gaps
    for gap in gaps:
        fitting = get_tasks_for_gap(gap, max_count=3)
        for task in fitting:
            if task.id in used_task_ids:
                continue
            
            score = _calculate_suggestion_score(task, gap, now)
            suggestions.append(TaskSuggestion(
                task=task,
                suggested_gap=gap,
                fit_reason=f"fits your {gap.start.strftime('%H:%M')}-{gap.end.strftime('%H:%M')} gap",
                score=score,
            ))
            used_task_ids.add(task.id)
    
    # Second pass: Add high-priority tasks without gaps
    for task in priority_tasks:
        if task.id in used_task_ids:
            continue
        
        score = _calculate_suggestion_score(task, None, now)
        
        # Determine fit reason based on task properties
        if task.due_date == target_date:
            fit_reason = "due today"
        elif task.due_date and task.due_date < target_date:
            fit_reason = "overdue"
        elif task.importance >= 0.8:
            fit_reason = "high priority"
        else:
            fit_reason = "good next action"
        
        suggestions.append(TaskSuggestion(
            task=task,
            suggested_gap=None,
            fit_reason=fit_reason,
            score=score,
        ))
        used_task_ids.add(task.id)
    
    # Sort by score and return top N
    suggestions.sort(key=lambda s: s.score, reverse=True)
    return suggestions[:max_count]


def format_suggestions_message(suggestions: List[TaskSuggestion]) -> str:
    """
    Format suggestions into a human-readable message.
    """
    if not suggestions:
        return "No task suggestions right now."
    
    lines = ["💡 **Suggested Next Actions**", ""]
    
    for i, s in enumerate(suggestions, 1):
        duration_str = f" ({s.task.duration_minutes}m)" if s.task.duration_minutes else ""
        lines.append(f"{i}. {s.task.name}{duration_str}")
        lines.append(f"   _{s.fit_reason}_")
    
    return "\n".join(lines)


def get_current_gap() -> Optional[TimeGap]:
    """
    Get the current or next available time gap.
    Returns None if no gaps available today.
    """
    gaps = get_calendar_gaps()
    now = datetime.now()
    
    for gap in gaps:
        # Return first gap that hasn't ended
        if gap.end > now:
            return gap
    
    return None


def get_quick_suggestion() -> Optional[TaskSuggestion]:
    """
    Get a single quick suggestion for "what should I do next?"
    """
    suggestions = get_contextual_suggestions(max_count=1)
    return suggestions[0] if suggestions else None
