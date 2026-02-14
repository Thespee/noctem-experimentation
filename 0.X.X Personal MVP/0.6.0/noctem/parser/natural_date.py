"""
Natural language date and time parsing.
Regex-based extraction of dates, times, and recurrence patterns.
"""
import re
from datetime import date, time, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ParsedDateTime:
    """Result of parsing date/time from text."""
    date: Optional[date] = None
    time: Optional[time] = None
    recurrence: Optional[str] = None
    remaining_text: str = ""


# Day name mappings
WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _next_weekday(weekday: int, from_date: Optional[date] = None) -> date:
    """Get the next occurrence of a weekday (0=Monday)."""
    if from_date is None:
        from_date = date.today()
    days_ahead = weekday - from_date.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return from_date + timedelta(days=days_ahead)


def _this_weekday(weekday: int, from_date: Optional[date] = None) -> date:
    """Get this week's occurrence of a weekday."""
    if from_date is None:
        from_date = date.today()
    days_diff = weekday - from_date.weekday()
    return from_date + timedelta(days=days_diff)


def parse_date(text: str) -> Tuple[Optional[date], str]:
    """
    Extract a date from text.
    Returns (parsed_date, remaining_text).
    """
    text_lower = text.lower()
    today = date.today()
    
    # Today
    if re.search(r'\btoday\b', text_lower):
        return today, re.sub(r'\btoday\b', '', text, flags=re.IGNORECASE).strip()
    
    # Tomorrow
    if re.search(r'\btomorrow\b', text_lower):
        return today + timedelta(days=1), re.sub(r'\btomorrow\b', '', text, flags=re.IGNORECASE).strip()
    
    # Yesterday (for logging past tasks)
    if re.search(r'\byesterday\b', text_lower):
        return today - timedelta(days=1), re.sub(r'\byesterday\b', '', text, flags=re.IGNORECASE).strip()
    
    # In N days
    match = re.search(r'\bin\s+(\d+)\s+days?\b', text_lower)
    if match:
        days = int(match.group(1))
        return today + timedelta(days=days), re.sub(r'\bin\s+\d+\s+days?\b', '', text, flags=re.IGNORECASE).strip()
    
    # Next [weekday]
    match = re.search(r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b', text_lower)
    if match:
        weekday_name = match.group(1)
        weekday_num = WEEKDAYS.get(weekday_name)
        if weekday_num is not None:
            target = _next_weekday(weekday_num)
            # "next" means the one after this week
            if target <= today + timedelta(days=7):
                target += timedelta(days=7)
            return target, re.sub(r'\bnext\s+\w+\b', '', text, flags=re.IGNORECASE).strip()
    
    # This [weekday]
    match = re.search(r'\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b', text_lower)
    if match:
        weekday_name = match.group(1)
        weekday_num = WEEKDAYS.get(weekday_name)
        if weekday_num is not None:
            return _this_weekday(weekday_num), re.sub(r'\bthis\s+\w+\b', '', text, flags=re.IGNORECASE).strip()
    
    # Just weekday name (means next occurrence)
    match = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b', text_lower)
    if match:
        weekday_name = match.group(1)
        weekday_num = WEEKDAYS.get(weekday_name)
        if weekday_num is not None:
            target = _next_weekday(weekday_num)
            # If it's today, use today
            if today.weekday() == weekday_num:
                target = today
            return target, re.sub(r'\b' + weekday_name + r'\b', '', text, flags=re.IGNORECASE).strip()
    
    # ISO format: 2026-02-15
    match = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', text)
    if match:
        try:
            parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return parsed, re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', text).strip()
        except ValueError:
            pass
    
    # DD/MM or DD-MM (European format)
    match = re.search(r'\b(\d{1,2})[/\-](\d{1,2})\b', text)
    if match:
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            year = today.year
            parsed = date(year, month, day)
            # If date is in the past, assume next year
            if parsed < today:
                parsed = date(year + 1, month, day)
            return parsed, re.sub(r'\b\d{1,2}[/\-]\d{1,2}\b', '', text).strip()
        except ValueError:
            pass
    
    # Month Day: feb 15, february 15
    month_pattern = '|'.join(MONTHS.keys())
    match = re.search(rf'\b({month_pattern})\s+(\d{{1,2}})\b', text_lower)
    if match:
        month_name = match.group(1)
        day = int(match.group(2))
        month_num = MONTHS.get(month_name)
        if month_num:
            try:
                year = today.year
                parsed = date(year, month_num, day)
                if parsed < today:
                    parsed = date(year + 1, month_num, day)
                return parsed, re.sub(rf'\b{month_name}\s+\d{{1,2}}\b', '', text, flags=re.IGNORECASE).strip()
            except ValueError:
                pass
    
    # Day Month: 15 feb, 15 february
    match = re.search(rf'\b(\d{{1,2}})\s+({month_pattern})\b', text_lower)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        month_num = MONTHS.get(month_name)
        if month_num:
            try:
                year = today.year
                parsed = date(year, month_num, day)
                if parsed < today:
                    parsed = date(year + 1, month_num, day)
                return parsed, re.sub(rf'\b\d{{1,2}}\s+{month_name}\b', '', text, flags=re.IGNORECASE).strip()
            except ValueError:
                pass
    
    # Next week
    if re.search(r'\bnext\s+week\b', text_lower):
        return today + timedelta(days=7), re.sub(r'\bnext\s+week\b', '', text, flags=re.IGNORECASE).strip()
    
    return None, text


def parse_time(text: str) -> Tuple[Optional[time], str]:
    """
    Extract a time from text.
    Returns (parsed_time, remaining_text).
    """
    text_lower = text.lower()
    
    # At noon
    if re.search(r'\bat\s+noon\b', text_lower):
        return time(12, 0), re.sub(r'\bat\s+noon\b', '', text, flags=re.IGNORECASE).strip()
    
    # At midnight
    if re.search(r'\bat\s+midnight\b', text_lower):
        return time(0, 0), re.sub(r'\bat\s+midnight\b', '', text, flags=re.IGNORECASE).strip()
    
    # 24-hour format: 15:00, 9:30
    match = re.search(r'\b(\d{1,2}):(\d{2})\b', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute), re.sub(r'\b\d{1,2}:\d{2}\b', '', text).strip()
    
    # 12-hour format: 3pm, 3:30pm, 3 pm
    match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            pattern = r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b'
            return time(hour, minute), re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    
    # "at" followed by time: at 3, at 15
    match = re.search(r'\bat\s+(\d{1,2})\b(?!\s*(?:am|pm|:))', text_lower)
    if match:
        hour = int(match.group(1))
        # Assume PM for small numbers during working hours
        if 1 <= hour <= 7:
            hour += 12
        if 0 <= hour <= 23:
            return time(hour, 0), re.sub(r'\bat\s+\d{1,2}\b', '', text, flags=re.IGNORECASE).strip()
    
    return None, text


def parse_recurrence(text: str) -> Tuple[Optional[str], str]:
    """
    Extract a recurrence pattern from text.
    Returns (rrule_string, remaining_text).
    """
    text_lower = text.lower()
    
    # Daily
    if re.search(r'\bdaily\b', text_lower):
        return "FREQ=DAILY", re.sub(r'\bdaily\b', '', text, flags=re.IGNORECASE).strip()
    
    # Weekly
    if re.search(r'\bweekly\b', text_lower):
        return "FREQ=WEEKLY", re.sub(r'\bweekly\b', '', text, flags=re.IGNORECASE).strip()
    
    # Monthly
    if re.search(r'\bmonthly\b', text_lower):
        return "FREQ=MONTHLY", re.sub(r'\bmonthly\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every day
    if re.search(r'\bevery\s+day\b', text_lower):
        return "FREQ=DAILY", re.sub(r'\bevery\s+day\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every N days
    match = re.search(r'\bevery\s+(\d+)\s+days?\b', text_lower)
    if match:
        interval = int(match.group(1))
        return f"FREQ=DAILY;INTERVAL={interval}", re.sub(r'\bevery\s+\d+\s+days?\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every [weekday]
    weekday_map = {"mo": "MO", "tu": "TU", "we": "WE", "th": "TH", "fr": "FR", "sa": "SA", "su": "SU"}
    match = re.search(r'\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b', text_lower)
    if match:
        day_name = match.group(1)[:2]
        rrule_day = weekday_map.get(day_name, "MO")
        return f"FREQ=WEEKLY;BYDAY={rrule_day}", re.sub(r'\bevery\s+\w+day\b|\bevery\s+\w{3}\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every Nth (of month): every 1st, every 15th
    match = re.search(r'\bevery\s+(\d{1,2})(?:st|nd|rd|th)?\b', text_lower)
    if match:
        day = int(match.group(1))
        if 1 <= day <= 31:
            return f"FREQ=MONTHLY;BYMONTHDAY={day}", re.sub(r'\bevery\s+\d{1,2}(?:st|nd|rd|th)?\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every week
    if re.search(r'\bevery\s+week\b', text_lower):
        return "FREQ=WEEKLY", re.sub(r'\bevery\s+week\b', '', text, flags=re.IGNORECASE).strip()
    
    # Every month
    if re.search(r'\bevery\s+month\b', text_lower):
        return "FREQ=MONTHLY", re.sub(r'\bevery\s+month\b', '', text, flags=re.IGNORECASE).strip()
    
    return None, text


def parse_datetime(text: str) -> ParsedDateTime:
    """
    Parse date, time, and recurrence from text.
    Returns a ParsedDateTime with all extracted components.
    """
    remaining = text
    
    # Parse recurrence first (it might contain date-like words)
    recurrence, remaining = parse_recurrence(remaining)
    
    # Parse time
    parsed_time, remaining = parse_time(remaining)
    
    # Parse date
    parsed_date, remaining = parse_date(remaining)
    
    # Clean up remaining text
    remaining = ' '.join(remaining.split())  # Normalize whitespace
    
    return ParsedDateTime(
        date=parsed_date,
        time=parsed_time,
        recurrence=recurrence,
        remaining_text=remaining,
    )
