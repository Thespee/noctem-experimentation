#!/usr/bin/env python3
"""
Calendar ICS Parser
Reads ICS calendar files and extracts events.
Standard library only - no icalendar package needed.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Default paths to check for calendar files
CALENDAR_SOURCES = [
    Path("/mnt/shared/calendar/calendar.ics"),
    Path("/mnt/shared/calendar/"),
    Path.home() / "shared" / "calendar",
]


def parse_ics_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ICS datetime format (YYYYMMDDTHHMMSS or YYYYMMDD)."""
    dt_str = dt_str.strip()
    
    # Remove timezone suffix if present
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1]
    
    try:
        if 'T' in dt_str:
            return datetime.strptime(dt_str[:15], "%Y%m%dT%H%M%S")
        else:
            return datetime.strptime(dt_str[:8], "%Y%m%d")
    except ValueError:
        return None


def parse_ics_file(filepath: Path) -> List[Dict]:
    """
    Parse an ICS file and extract events.
    
    Returns list of events with: summary, start, end, location, description
    """
    events = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []
    
    # Split into VEVENT blocks
    vevent_pattern = re.compile(r'BEGIN:VEVENT(.*?)END:VEVENT', re.DOTALL)
    
    for match in vevent_pattern.finditer(content):
        event_text = match.group(1)
        event = {}
        
        # Extract fields
        for line in event_text.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            
            # Handle folded lines (continuation)
            key_value = line.split(':', 1)
            if len(key_value) != 2:
                continue
            
            key, value = key_value
            key = key.split(';')[0]  # Remove parameters like DTSTART;VALUE=DATE
            
            if key == 'SUMMARY':
                event['summary'] = value
            elif key == 'DTSTART':
                event['start'] = parse_ics_datetime(value)
            elif key == 'DTEND':
                event['end'] = parse_ics_datetime(value)
            elif key == 'LOCATION':
                event['location'] = value
            elif key == 'DESCRIPTION':
                # Unescape ICS escapes
                event['description'] = value.replace('\\n', '\n').replace('\\,', ',')
        
        if event.get('summary') and event.get('start'):
            events.append(event)
    
    return events


def load_calendar_events(source_path: Path = None) -> List[Dict]:
    """Load events from calendar file(s)."""
    events = []
    
    # Find calendar source
    paths_to_check = []
    if source_path:
        paths_to_check.append(source_path)
    paths_to_check.extend(CALENDAR_SOURCES)
    
    for path in paths_to_check:
        if not path.exists():
            continue
        
        if path.is_file() and path.suffix.lower() == '.ics':
            events.extend(parse_ics_file(path))
        elif path.is_dir():
            for ics_file in path.glob('*.ics'):
                events.extend(parse_ics_file(ics_file))
    
    # Sort by start time
    events.sort(key=lambda e: e.get('start') or datetime.max)
    return events


def get_events_for_date(date: datetime = None, source_path: Path = None) -> List[Dict]:
    """Get events for a specific date (default: today)."""
    if date is None:
        date = datetime.now()
    
    target_date = date.date()
    events = load_calendar_events(source_path)
    
    matching = []
    for event in events:
        if event.get('start'):
            event_date = event['start'].date()
            if event_date == target_date:
                matching.append(event)
    
    return matching


def get_upcoming_events(days: int = 7, source_path: Path = None) -> List[Dict]:
    """Get events in the next N days."""
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    
    events = load_calendar_events(source_path)
    
    upcoming = []
    for event in events:
        start = event.get('start')
        if start and now <= start <= cutoff:
            upcoming.append(event)
    
    return upcoming


def format_event(event: Dict) -> str:
    """Format a single event for display."""
    start = event.get('start')
    time_str = start.strftime('%H:%M') if start else '??:??'
    
    # All-day events (no time component or midnight)
    if start and start.hour == 0 and start.minute == 0:
        time_str = 'All day'
    
    summary = event.get('summary', 'Untitled')
    location = event.get('location')
    
    result = f"{time_str} - {summary}"
    if location:
        result += f" @ {location}"
    
    return result


def format_todays_events(events: List[Dict] = None) -> str:
    """Format today's events as a message."""
    if events is None:
        events = get_events_for_date()
    
    if not events:
        return ""
    
    lines = ["📅 Today's Events:"]
    for event in events:
        lines.append(f"  • {format_event(event)}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Calendar Test ===")
    
    # Test loading
    events = load_calendar_events()
    print(f"Loaded {len(events)} events")
    
    # Today's events
    today = get_events_for_date()
    if today:
        print(format_todays_events(today))
    else:
        print("No events today")
    
    # Upcoming
    upcoming = get_upcoming_events(days=7)
    if upcoming:
        print(f"\nUpcoming ({len(upcoming)} events):")
        for e in upcoming[:5]:
            print(f"  {format_event(e)}")
