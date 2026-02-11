#!/usr/bin/env python3
"""
Birthday reminder utility.
Reads birthdays from CSV and returns upcoming ones within a window.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# Default paths to check for birthday data
BIRTHDAY_SOURCES = [
    Path(__file__).parent.parent / "personal_mvp" / "example_birthdays.csv",
    Path("/mnt/shared/birthdays.csv"),
    Path.home() / "shared" / "birthdays.csv",
]


def load_birthdays(source_path: Path = None) -> List[Dict]:
    """
    Load birthdays from CSV file.
    
    CSV format: name,birthday,notes
    Birthday format: MM-DD
    """
    # Find a valid source
    if source_path and source_path.exists():
        path = source_path
    else:
        path = None
        for src in BIRTHDAY_SOURCES:
            if src.exists():
                path = src
                break
    
    if not path:
        return []
    
    birthdays = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                birthdays.append({
                    'name': row.get('name', '').strip(),
                    'birthday': row.get('birthday', '').strip(),
                    'notes': row.get('notes', '').strip(),
                })
    except Exception as e:
        print(f"Error loading birthdays: {e}")
        return []
    
    return birthdays


def get_upcoming_birthdays(days_window: int = 3, source_path: Path = None) -> List[Dict]:
    """
    Get birthdays within the next N days (including today).
    
    Returns list of dicts with name, birthday, notes, days_until
    """
    birthdays = load_birthdays(source_path)
    today = datetime.now().date()
    upcoming = []
    
    for bday in birthdays:
        if not bday['birthday']:
            continue
            
        try:
            # Parse MM-DD format
            month, day = map(int, bday['birthday'].split('-'))
            
            # Create date for this year
            this_year_bday = today.replace(month=month, day=day)
            
            # If already passed this year, check next year
            if this_year_bday < today:
                this_year_bday = this_year_bday.replace(year=today.year + 1)
            
            # Calculate days until
            days_until = (this_year_bday - today).days
            
            if 0 <= days_until < days_window:
                upcoming.append({
                    'name': bday['name'],
                    'birthday': bday['birthday'],
                    'notes': bday['notes'],
                    'days_until': days_until,
                    'date': this_year_bday.strftime('%A, %B %d'),
                })
        except (ValueError, AttributeError):
            continue
    
    # Sort by days_until
    upcoming.sort(key=lambda x: x['days_until'])
    return upcoming


def format_birthday_reminder(upcoming: List[Dict]) -> str:
    """Format upcoming birthdays as a message."""
    if not upcoming:
        return ""
    
    lines = ["🎂 Upcoming Birthdays:"]
    for bday in upcoming:
        if bday['days_until'] == 0:
            when = "TODAY!"
        elif bday['days_until'] == 1:
            when = "tomorrow"
        else:
            when = f"in {bday['days_until']} days"
        
        line = f"  • {bday['name']} - {when}"
        if bday['notes']:
            line += f" ({bday['notes']})"
        lines.append(line)
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test
    upcoming = get_upcoming_birthdays(days_window=3)
    print(format_birthday_reminder(upcoming))
    
    if not upcoming:
        print("No birthdays in the next 3 days.")
        print("\nAll loaded birthdays:")
        for b in load_birthdays():
            print(f"  {b['name']}: {b['birthday']}")
