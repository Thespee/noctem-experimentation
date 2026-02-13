#!/usr/bin/env python3
"""
Natural Language Task Parser
Parses task input like "Buy milk tomorrow at 4pm" without AI.
Inspired by Todoist's plain text parsing.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Dict


# Days of the week
DAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Relative day words
RELATIVE_DAYS = {
    "today": 0,
    "tomorrow": 1,
    "tmr": 1,
    "tmrw": 1,
}


def parse_time(text: str) -> Optional[tuple]:
    """
    Extract time from text. Returns (hour, minute) or None.
    Supports: 4pm, 4:30pm, 16:00, noon, midnight
    """
    text = text.lower()
    
    # noon/midnight
    if "noon" in text:
        return (12, 0)
    if "midnight" in text:
        return (0, 0)
    
    # 4pm, 4:30pm, 4 pm
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        if match.group(3) == 'pm' and hour != 12:
            hour += 12
        elif match.group(3) == 'am' and hour == 12:
            hour = 0
        return (hour, minute)
    
    # 16:00, 09:30 (24-hour)
    match = re.search(r'(\d{1,2}):(\d{2})(?!\s*(am|pm))', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)
    
    return None


def parse_date(text: str) -> Optional[datetime]:
    """
    Extract date from text. Returns datetime or None.
    Supports: today, tomorrow, monday, next friday, in 3 days, dec 25
    """
    text_lower = text.lower()
    now = datetime.now()
    
    # "today", "tomorrow"
    for word, offset in RELATIVE_DAYS.items():
        if word in text_lower:
            return now + timedelta(days=offset)
    
    # "in X days/weeks"
    match = re.search(r'in\s+(\d+)\s+(day|days|week|weeks)', text_lower)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if 'week' in unit:
            return now + timedelta(weeks=num)
        return now + timedelta(days=num)
    
    # Day of week: "monday", "on friday", "next tuesday"
    for day_name, day_num in DAYS.items():
        if day_name in text_lower:
            # Find next occurrence of this day
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            # "next" adds another week
            if f"next {day_name}" in text_lower or f"next {day_name[:3]}" in text_lower:
                days_ahead += 7
            return now + timedelta(days=days_ahead)
    
    # Month day: "dec 25", "december 25", "25th of december"
    months = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    # "dec 25" or "december 25"
    for month_name, month_num in months.items():
        match = re.search(rf'{month_name}\s+(\d{{1,2}})', text_lower)
        if match:
            day = int(match.group(1))
            year = now.year
            target = datetime(year, month_num, day)
            if target < now:
                target = datetime(year + 1, month_num, day)
            return target
    
    # "25th of december" or "25 december"
    match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(\w+)', text_lower)
    if match:
        day = int(match.group(1))
        month_word = match.group(2)
        if month_word in months:
            month_num = months[month_word]
            year = now.year
            target = datetime(year, month_num, day)
            if target < now:
                target = datetime(year + 1, month_num, day)
            return target
    
    return None


def extract_project(text: str) -> tuple:
    """
    Extract project from text using "in <project>" or "#project" syntax.
    Returns (cleaned_text, project_name) tuple.
    """
    # "#project" syntax
    match = re.search(r'#(\w+)', text)
    if match:
        project = match.group(1)
        cleaned = re.sub(r'\s*#\w+\s*', ' ', text).strip()
        return (cleaned, project)
    
    # "in <project>" at end of text
    match = re.search(r'\s+in\s+([^,\.]+)$', text, re.IGNORECASE)
    if match:
        project = match.group(1).strip()
        # Avoid matching date phrases like "in 3 days"
        if not re.match(r'^\d+\s+(day|week|month|hour)', project):
            cleaned = text[:match.start()].strip()
            return (cleaned, project)
    
    return (text, None)


def extract_priority(text: str) -> tuple:
    """
    Extract priority from text using "!!!" (high), "!!" (medium), "!" (low).
    Returns (cleaned_text, priority) tuple. Priority is 1-5 (1=highest).
    """
    if text.startswith("!!!"):
        return (text[3:].strip(), 1)
    if text.startswith("!!"):
        return (text[2:].strip(), 2)
    if text.startswith("!"):
        return (text[1:].strip(), 3)
    
    # Also check for p1, p2, p3 anywhere in text
    match = re.search(r'\bp([1-4])\b', text)
    if match:
        priority = int(match.group(1))
        cleaned = re.sub(r'\s*\bp[1-4]\b\s*', ' ', text).strip()
        return (cleaned, priority)
    
    return (text, 5)  # Default priority


def clean_date_time_from_title(title: str) -> str:
    """Remove parsed date/time phrases from title."""
    patterns = [
        r'\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?',  # at 4pm, at 4:30pm
        r'\s+(?:on\s+)?(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b',
        r'\s+tomorrow\b',
        r'\s+today\b',
        r'\s+in\s+\d+\s+(?:day|days|week|weeks)\b',
        r'\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}',
        r'\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?\w+',
    ]
    
    result = title
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    return result.strip()


def parse_task(text: str) -> Optional[Dict]:
    """
    Parse natural language task input.
    
    Returns dict with:
        - title: Task title (cleaned)
        - due_date: datetime or None
        - due_time: (hour, minute) tuple or None
        - project: Project name or None
        - priority: 1-5 (1=highest)
    
    Examples:
        "Buy milk tomorrow at 4pm" -> 
            {title: "Buy milk", due_date: <tomorrow>, due_time: (16, 0)}
        "!!! Call client in Work" ->
            {title: "Call client", project: "Work", priority: 1}
    """
    if not text or not text.strip():
        return None
    
    text = text.strip()
    
    # Extract components
    text, priority = extract_priority(text)
    text, project = extract_project(text)
    
    due_date = parse_date(text)
    due_time = parse_time(text)
    
    # Clean the title
    title = clean_date_time_from_title(text)
    
    # If we removed too much, use original
    if len(title) < 3:
        title = text
    
    return {
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "project": project,
        "priority": priority,
    }


# Quick test
if __name__ == "__main__":
    tests = [
        "Buy milk tomorrow at 4pm",
        "Call mom on Friday",
        "!!! Urgent task",
        "Review PR in Engineering",
        "Send email next monday at 9am",
        "Pay rent on the 1st",
        "Dentist appointment dec 15 at 2:30pm #Health",
        "in 3 days finish report",
    ]
    
    for t in tests:
        result = parse_task(t)
        print(f"\n'{t}'")
        print(f"  -> {result}")
