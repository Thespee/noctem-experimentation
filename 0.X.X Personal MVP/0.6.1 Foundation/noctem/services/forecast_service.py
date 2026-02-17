"""
Forecast service for Noctem v0.6.0 Final Polish.

Provides 14-day forecast functionality:
- Daily density calculations (busyness level)
- Free time blocks
- Butler day briefs
"""
import logging
from datetime import datetime, date, timedelta, time
from typing import Optional
from dataclasses import dataclass, field

from ..db import get_db
from . import task_service
from .briefing import get_time_blocks_for_date
from .suggestion_service import get_calendar_gaps, TimeGap

logger = logging.getLogger(__name__)


@dataclass
class DayForecast:
    """Forecast data for a single day."""
    date: date
    day_name: str
    is_today: bool = False
    is_weekend: bool = False
    
    # Counts
    task_count: int = 0
    event_count: int = 0
    overdue_count: int = 0
    high_priority_count: int = 0
    
    # Density (0-1 scale)
    density: float = 0.0
    density_label: str = "free"  # 'free', 'light', 'moderate', 'busy', 'packed'
    
    # Time data
    blocked_hours: float = 0.0
    free_hours: float = 0.0
    free_blocks: list[TimeGap] = field(default_factory=list)
    
    # Butler brief
    brief: str = ""
    recommendations: list[str] = field(default_factory=list)


def get_14_day_forecast(start_date: Optional[date] = None) -> list[DayForecast]:
    """
    Get 14-day forecast from start date.
    
    Args:
        start_date: First day of forecast (default: today)
    
    Returns:
        List of DayForecast objects
    """
    if start_date is None:
        start_date = date.today()
    
    forecasts = []
    today = date.today()
    
    for i in range(14):
        day = start_date + timedelta(days=i)
        forecast = _build_day_forecast(day, today)
        forecasts.append(forecast)
    
    return forecasts


def _build_day_forecast(target_date: date, today: date) -> DayForecast:
    """Build forecast for a single day."""
    forecast = DayForecast(
        date=target_date,
        day_name=target_date.strftime("%a"),
        is_today=(target_date == today),
        is_weekend=(target_date.weekday() >= 5),
    )
    
    # Get tasks due on this day
    tasks = task_service.get_tasks_due_on(target_date)
    forecast.task_count = len(tasks)
    forecast.high_priority_count = len([t for t in tasks if t.importance >= 0.8])
    
    # Get overdue count (only for today)
    if target_date == today:
        overdue = task_service.get_overdue_tasks()
        forecast.overdue_count = len(overdue)
    
    # Get calendar events
    events = get_time_blocks_for_date(target_date)
    forecast.event_count = len(events)
    
    # Calculate blocked hours
    forecast.blocked_hours = _calculate_blocked_hours(events)
    
    # Calculate free blocks (only for today and future)
    if target_date >= today:
        forecast.free_blocks = get_calendar_gaps(target_date)
        forecast.free_hours = sum(g.duration_minutes for g in forecast.free_blocks) / 60.0
    else:
        forecast.free_hours = max(0, 9 - forecast.blocked_hours)  # Assume 9hr workday
    
    # Calculate density
    forecast.density = calculate_density(
        task_count=forecast.task_count,
        event_count=forecast.event_count,
        blocked_hours=forecast.blocked_hours,
        overdue_count=forecast.overdue_count,
    )
    forecast.density_label = _density_to_label(forecast.density)
    
    # Generate brief
    forecast.brief = generate_day_brief(forecast)
    forecast.recommendations = _generate_recommendations(forecast)
    
    return forecast


def calculate_density(
    task_count: int,
    event_count: int,
    blocked_hours: float,
    overdue_count: int = 0,
) -> float:
    """
    Calculate busyness density for a day (0-1 scale).
    
    Considers:
    - Number of tasks
    - Number of events
    - Hours blocked
    - Overdue items
    """
    # Base density from tasks (each task ~0.1, max contribution 0.4)
    task_density = min(0.4, task_count * 0.1)
    
    # Event density (each event ~0.1, max contribution 0.3)
    event_density = min(0.3, event_count * 0.1)
    
    # Blocked hours density (9hr day assumed, max contribution 0.3)
    hours_density = min(0.3, blocked_hours / 9.0 * 0.3)
    
    # Overdue penalty (adds urgency)
    overdue_density = min(0.2, overdue_count * 0.05)
    
    total = task_density + event_density + hours_density + overdue_density
    return min(1.0, total)


def _density_to_label(density: float) -> str:
    """Convert density float to human-readable label."""
    if density < 0.2:
        return "free"
    elif density < 0.4:
        return "light"
    elif density < 0.6:
        return "moderate"
    elif density < 0.8:
        return "busy"
    else:
        return "packed"


def _calculate_blocked_hours(events: list) -> float:
    """Calculate total hours blocked by events."""
    total_minutes = 0
    
    for event in events:
        start = event.start_time
        end = event.end_time
        
        # Parse if strings
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        
        if start and end:
            duration = (end - start).total_seconds() / 60.0
            total_minutes += max(0, duration)
    
    return total_minutes / 60.0


def generate_day_brief(forecast: DayForecast) -> str:
    """
    Generate a butler's brief for a day.
    
    Args:
        forecast: The DayForecast object
    
    Returns:
        Brief summary string
    """
    parts = []
    
    # Opening
    if forecast.is_today:
        parts.append("Today:")
    else:
        parts.append(f"{forecast.day_name}:")
    
    # Density summary
    if forecast.density_label == "free":
        parts.append("clear schedule")
    elif forecast.density_label == "light":
        parts.append("light day")
    elif forecast.density_label == "moderate":
        parts.append("moderate load")
    elif forecast.density_label == "busy":
        parts.append("busy day")
    else:
        parts.append("packed day")
    
    # Specifics
    details = []
    if forecast.task_count > 0:
        details.append(f"{forecast.task_count} task{'s' if forecast.task_count != 1 else ''}")
    if forecast.event_count > 0:
        details.append(f"{forecast.event_count} event{'s' if forecast.event_count != 1 else ''}")
    if forecast.overdue_count > 0:
        details.append(f"{forecast.overdue_count} overdue")
    
    if details:
        parts.append(f"({', '.join(details)})")
    
    return " ".join(parts)


def _generate_recommendations(forecast: DayForecast) -> list[str]:
    """Generate butler recommendations for a day."""
    recommendations = []
    
    if forecast.overdue_count > 0:
        recommendations.append(f"Clear {forecast.overdue_count} overdue item{'s' if forecast.overdue_count != 1 else ''}")
    
    if forecast.density_label == "free" and not forecast.is_weekend:
        recommendations.append("Good day for deep work or catch-up")
    
    if forecast.high_priority_count > 2:
        recommendations.append("Many high-priority tasks - consider rescheduling")
    
    if forecast.blocked_hours > 6:
        recommendations.append("Heavy meeting day - protect focus time")
    
    if forecast.free_hours > 4 and forecast.task_count == 0 and not forecast.is_weekend:
        recommendations.append("Consider planning ahead")
    
    return recommendations


def get_free_blocks(target_date: Optional[date] = None) -> list[TimeGap]:
    """
    Get free time blocks for a date.
    
    Args:
        target_date: Date to check (default: today)
    
    Returns:
        List of TimeGap objects
    """
    if target_date is None:
        target_date = date.today()
    
    return get_calendar_gaps(target_date)


def get_week_summary(start_date: Optional[date] = None) -> dict:
    """
    Get a summary for a week.
    
    Args:
        start_date: First day of week (default: this Monday)
    
    Returns:
        Dict with week statistics
    """
    if start_date is None:
        today = date.today()
        # Go back to Monday
        start_date = today - timedelta(days=today.weekday())
    
    forecasts = [_build_day_forecast(start_date + timedelta(days=i), date.today()) for i in range(7)]
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(days=6)).isoformat(),
        "total_tasks": sum(f.task_count for f in forecasts),
        "total_events": sum(f.event_count for f in forecasts),
        "avg_density": sum(f.density for f in forecasts) / 7,
        "busiest_day": max(forecasts, key=lambda f: f.density).day_name,
        "freest_day": min(forecasts, key=lambda f: f.density).day_name,
        "days": [
            {
                "date": f.date.isoformat(),
                "day_name": f.day_name,
                "density": f.density,
                "density_label": f.density_label,
                "task_count": f.task_count,
                "event_count": f.event_count,
            }
            for f in forecasts
        ],
    }


def get_7_day_table_data(start_date: Optional[date] = None) -> list[dict]:
    """
    Get data for the 7-day table view (Mon-Sun).
    
    Returns list of dicts with comprehensive day data.
    """
    if start_date is None:
        today = date.today()
        # Go to Monday of this week
        start_date = today - timedelta(days=today.weekday())
    
    result = []
    today = date.today()
    
    for i in range(7):
        day = start_date + timedelta(days=i)
        forecast = _build_day_forecast(day, today)
        
        # Get tasks with details
        tasks = task_service.get_tasks_due_on(day)
        events = get_time_blocks_for_date(day)
        
        result.append({
            "date": day.isoformat(),
            "date_display": day.strftime("%d"),
            "day_name": day.strftime("%a"),
            "is_today": day == today,
            "is_weekend": day.weekday() >= 5,
            "density": forecast.density,
            "density_label": forecast.density_label,
            "brief": forecast.brief,
            "recommendations": forecast.recommendations,
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "importance": t.importance,
                    "status": t.status,
                    "due_time": str(t.due_time) if t.due_time else None,
                }
                for t in tasks
            ],
            "events": [
                {
                    "title": e.title,
                    "start_time": e.start_time.strftime("%H:%M") if hasattr(e.start_time, 'strftime') else str(e.start_time)[:5] if e.start_time else None,
                    "end_time": e.end_time.strftime("%H:%M") if hasattr(e.end_time, 'strftime') else str(e.end_time)[:5] if e.end_time else None,
                }
                for e in events
            ],
        })
    
    return result
