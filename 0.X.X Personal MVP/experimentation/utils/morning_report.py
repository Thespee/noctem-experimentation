#!/usr/bin/env python3
"""
Morning Report Generator
Generates a daily briefing with birthdays, tasks, and calendar events.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import state
from utils.birthday import get_upcoming_birthdays, format_birthday_reminder


def generate_morning_report() -> str:
    """Generate the morning briefing."""
    now = datetime.now()
    lines = [f"☀️ Good morning! {now.strftime('%A, %B %d')}"]
    lines.append("")
    
    # Birthdays (3-day window)
    upcoming_bdays = get_upcoming_birthdays(days_window=3)
    if upcoming_bdays:
        lines.append(format_birthday_reminder(upcoming_bdays))
        lines.append("")
    
    # Pending tasks
    pending = state.get_user_tasks(status="pending")
    if pending:
        lines.append(f"📋 You have {len(pending)} pending tasks:")
        for t in pending[:5]:
            project = f" [{t['project_name']}]" if t.get('project_name') else ""
            lines.append(f"  • {t['title']}{project}")
        if len(pending) > 5:
            lines.append(f"  ...and {len(pending) - 5} more")
        lines.append("")
    
    # Tasks due soon
    due_soon = state.get_tasks_due_soon(days=3)
    if due_soon:
        lines.append("⚠️ Due soon:")
        for t in due_soon[:3]:
            lines.append(f"  • {t['title']} (due {t['due_date']})")
        lines.append("")
    
    # Completed yesterday
    yesterday = now - timedelta(days=1)
    completed = state.get_completed_tasks_since(yesterday)
    if completed:
        lines.append(f"✅ Completed since yesterday: {len(completed)}")
        for t in completed[:3]:
            lines.append(f"  • {t['title']}")
        lines.append("")
    
    # Calendar events
    try:
        from utils.calendar import get_events_for_date, format_event
        events = get_events_for_date()
        if events:
            lines.append("📅 Today's Events:")
            for e in events[:5]:
                lines.append(f"  • {format_event(e)}")
            if len(events) > 5:
                lines.append(f"  ...and {len(events) - 5} more")
            lines.append("")
    except Exception:
        pass  # Calendar not configured
    
    lines.append("Have a great day! 💪")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_morning_report())
