"""
Briefing service - generates morning briefing content.
"""
from datetime import date, datetime, timedelta
from typing import Optional
from ..db import get_db
from ..models import Task, TimeBlock
from . import task_service, habit_service


def get_time_blocks_for_date(target_date: date) -> list[TimeBlock]:
    """Get all time blocks (calendar events) for a date."""
    # Convert date to datetime range
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM time_blocks 
            WHERE start_time >= ? AND start_time < ?
            ORDER BY start_time ASC
            """,
            (start, end),
        ).fetchall()
        return [TimeBlock.from_row(row) for row in rows]


def generate_morning_briefing(target_date: Optional[date] = None) -> str:
    """Generate the morning briefing message."""
    if target_date is None:
        target_date = date.today()
    
    day_name = target_date.strftime("%A")
    date_str = target_date.strftime("%b %d")
    
    lines = [f"☀️ Good morning! Here's your {day_name}, {date_str}:", ""]
    
    # Calendar section
    time_blocks = get_time_blocks_for_date(target_date)
    if time_blocks:
        lines.append(f"📅 CALENDAR ({len(time_blocks)} events)")
        for block in time_blocks:
            start = block.start_time
            end = block.end_time
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            
            start_str = start.strftime("%H:%M") if start else "?"
            end_str = end.strftime("%H:%M") if end else "?"
            lines.append(f"• {start_str}-{end_str} {block.title}")
        lines.append("")
    
    # Priority tasks section
    priority_tasks = task_service.get_priority_tasks(5)
    overdue = task_service.get_overdue_tasks()
    
    if overdue:
        lines.append(f"⚠️ OVERDUE ({len(overdue)} tasks)")
        for i, task in enumerate(overdue[:3], 1):
            imp_str = _importance_str(task.importance)
            due_str = f"(was due {task.due_date})" if task.due_date else ""
            lines.append(f"{i}. {imp_str}{task.name} {due_str}")
        if len(overdue) > 3:
            lines.append(f"   ... and {len(overdue) - 3} more")
        lines.append("")
    
    if priority_tasks:
        lines.append("⚡ TOP PRIORITIES")
        for i, task in enumerate(priority_tasks, 1):
            score_str = f"[{task.priority_score:.0%}] "
            if task.due_date:
                if task.due_date == target_date:
                    due_str = "(due today)"
                elif task.due_date == target_date + timedelta(days=1):
                    due_str = "(due tomorrow)"
                else:
                    due_str = f"(due {task.due_date})"
            else:
                due_str = ""
            lines.append(f"{i}. {score_str}{task.name} {due_str}")
        lines.append("")
    
    # Habits section
    habits_stats = habit_service.get_all_habits_stats()
    habits_due = [h for h in habits_stats if not h.get("done_today", True)]
    
    if habits_stats:
        lines.append("🔄 HABITS TODAY")
        for stat in habits_stats:
            done_marker = "✓" if stat["done_today"] else ""
            week_progress = f"({stat['completions_this_week']}/{stat['target_this_week']} this week)"
            lines.append(f"• {stat['name']} {week_progress} {done_marker}")
        lines.append("")
    
    # Quick actions hint
    lines.append("Reply: \"done 1\" to complete, \"skip 2\" to defer")
    
    return "\n".join(lines)


def generate_today_view() -> str:
    """Generate a condensed view of today."""
    today = date.today()
    
    lines = [f"📋 Today ({today.strftime('%a %b %d')})", ""]
    
    # Calendar
    time_blocks = get_time_blocks_for_date(today)
    if time_blocks:
        lines.append("📅 Calendar:")
        for block in time_blocks:
            start = block.start_time
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            start_str = start.strftime("%H:%M") if start else "?"
            lines.append(f"  {start_str} {block.title}")
        lines.append("")
    
    # Tasks
    tasks = task_service.get_tasks_due_today()
    if tasks:
        lines.append("✅ Tasks:")
        for i, task in enumerate(tasks, 1):
            imp_str = _importance_str(task.importance)
            lines.append(f"  {i}. {imp_str}{task.name}")
    else:
        lines.append("✅ No tasks due today")
    
    return "\n".join(lines)


def generate_week_view() -> str:
    """Generate a view of the week ahead."""
    today = date.today()
    
    lines = ["📅 This Week", ""]
    
    tasks = task_service.get_tasks_due_this_week()
    
    # Group by day
    by_day = {}
    for task in tasks:
        day = task.due_date
        if day not in by_day:
            by_day[day] = []
        by_day[day].append(task)
    
    for i in range(7):
        day = today + timedelta(days=i)
        day_name = day.strftime("%a %d")
        day_tasks = by_day.get(day, [])
        
        if day == today:
            day_name = f"TODAY ({day_name})"
        
        if day_tasks:
            lines.append(f"**{day_name}**")
            for task in day_tasks:
                imp_str = _importance_str(task.importance)
                lines.append(f"  • {imp_str}{task.name}")
        else:
            lines.append(f"{day_name}: -")
    
    return "\n".join(lines)


def _importance_str(importance: float) -> str:
    """Convert importance value to display string."""
    if importance is None:
        return ""
    if importance >= 0.9:
        return "!1 "
    elif importance >= 0.4:
        return ""
    else:
        return "!3 "
