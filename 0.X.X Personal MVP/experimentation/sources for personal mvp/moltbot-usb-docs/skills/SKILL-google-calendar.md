# Moltbot Skill: Google Calendar Integration

## Purpose
This skill enables Moltbot to:
- Read your Google Calendar events
- Find free time slots
- Summarize upcoming events
- Alert about upcoming meetings

**Security**: This is READ-ONLY access. The system cannot create, modify, or delete calendar events.

## Prerequisites

### 1. Install Required Packages
```bash
pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 2. Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Create a new project (e.g., "Moltbot Calendar")
3. Enable the Google Calendar API:
   - Go to "APIs & Services" → "Enable APIs and Services"
   - Search for "Google Calendar API"
   - Click "Enable"

### 3. Create OAuth Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Desktop app"
4. Name: "Moltbot"
5. Download the JSON file
6. Save as `~/.config/moltbot/google_credentials.json`

### 4. Set Permissions (Important for Security)
```bash
chmod 600 ~/.config/moltbot/google_credentials.json
```

## Implementation

### calendar_reader.py - Main Module
Location: `~/moltbot-system/skills/calendar_reader.py`

```python
#!/usr/bin/env python3
"""
Moltbot Google Calendar Reader
READ-ONLY access to Google Calendar
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Configuration
CONFIG_DIR = Path.home() / ".config" / "moltbot"
CREDENTIALS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "google_token.json"

# READ-ONLY scope - we cannot modify calendar
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class CalendarReader:
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None
        
        # Load existing token
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        
        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {CREDENTIALS_FILE}\n"
                        "Please follow setup instructions to create OAuth credentials."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token for future use
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
            os.chmod(TOKEN_FILE, 0o600)
        
        self.service = build('calendar', 'v3', credentials=creds)
    
    def get_events(self, 
                   days_ahead: int = 7, 
                   max_results: int = 50,
                   calendar_id: str = 'primary') -> List[Dict]:
        """
        Get upcoming events
        
        Args:
            days_ahead: Number of days to look ahead
            max_results: Maximum events to return
            calendar_id: Calendar ID ('primary' for main calendar)
        
        Returns:
            List of event dictionaries
        """
        now = datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
        
        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return [self._parse_event(e) for e in events]
    
    def get_today_events(self, calendar_id: str = 'primary') -> List[Dict]:
        """Get events for today only"""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=today_start.isoformat() + 'Z',
            timeMax=today_end.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return [self._parse_event(e) for e in events]
    
    def find_free_time(self, 
                       days_ahead: int = 7,
                       min_duration_minutes: int = 30,
                       work_hours: tuple = (9, 17)) -> List[Dict]:
        """
        Find free time slots in calendar
        
        Args:
            days_ahead: Days to search
            min_duration_minutes: Minimum free slot duration
            work_hours: Tuple of (start_hour, end_hour) for work day
        
        Returns:
            List of free time slots
        """
        events = self.get_events(days_ahead=days_ahead)
        
        free_slots = []
        now = datetime.now()
        
        for day_offset in range(days_ahead):
            day = now + timedelta(days=day_offset)
            day_start = day.replace(hour=work_hours[0], minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=work_hours[1], minute=0, second=0, microsecond=0)
            
            # Skip if day already passed
            if day_end < now:
                continue
            
            # Adjust start time if it's today
            if day.date() == now.date() and now > day_start:
                day_start = now.replace(second=0, microsecond=0)
            
            # Get events for this day
            day_events = [
                e for e in events 
                if e.get('start_datetime') and 
                   e['start_datetime'].date() == day.date()
            ]
            
            # Sort by start time
            day_events.sort(key=lambda x: x.get('start_datetime', datetime.max))
            
            # Find gaps
            current_time = day_start
            
            for event in day_events:
                event_start = event.get('start_datetime')
                event_end = event.get('end_datetime')
                
                if event_start and event_start > current_time:
                    gap_minutes = (event_start - current_time).total_seconds() / 60
                    
                    if gap_minutes >= min_duration_minutes:
                        free_slots.append({
                            'date': day.strftime('%Y-%m-%d'),
                            'start': current_time.strftime('%H:%M'),
                            'end': event_start.strftime('%H:%M'),
                            'duration_minutes': int(gap_minutes)
                        })
                
                if event_end:
                    current_time = max(current_time, event_end)
            
            # Check gap after last event
            if current_time < day_end:
                gap_minutes = (day_end - current_time).total_seconds() / 60
                if gap_minutes >= min_duration_minutes:
                    free_slots.append({
                        'date': day.strftime('%Y-%m-%d'),
                        'start': current_time.strftime('%H:%M'),
                        'end': day_end.strftime('%H:%M'),
                        'duration_minutes': int(gap_minutes)
                    })
        
        return free_slots
    
    def get_next_event(self, calendar_id: str = 'primary') -> Optional[Dict]:
        """Get the next upcoming event"""
        events = self.get_events(days_ahead=1, max_results=1, calendar_id=calendar_id)
        return events[0] if events else None
    
    def summarize_week(self) -> Dict:
        """Get a summary of the upcoming week"""
        events = self.get_events(days_ahead=7)
        
        summary = {
            'total_events': len(events),
            'events_by_day': {},
            'busy_hours': 0
        }
        
        for event in events:
            if event.get('start_datetime'):
                day = event['start_datetime'].strftime('%A')
                if day not in summary['events_by_day']:
                    summary['events_by_day'][day] = []
                summary['events_by_day'][day].append(event['summary'])
                
                if event.get('duration_minutes'):
                    summary['busy_hours'] += event['duration_minutes'] / 60
        
        summary['busy_hours'] = round(summary['busy_hours'], 1)
        
        return summary
    
    def _parse_event(self, event: dict) -> Dict:
        """Parse raw event into clean dictionary"""
        start = event.get('start', {})
        end = event.get('end', {})
        
        # Handle all-day events vs timed events
        if 'dateTime' in start:
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
            is_all_day = False
            duration = (end_dt - start_dt).total_seconds() / 60
        else:
            start_dt = datetime.strptime(start.get('date', ''), '%Y-%m-%d') if start.get('date') else None
            end_dt = None
            is_all_day = True
            duration = None
        
        return {
            'id': event.get('id'),
            'summary': event.get('summary', 'No title'),
            'description': event.get('description', ''),
            'location': event.get('location', ''),
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'start_str': start.get('dateTime', start.get('date', '')),
            'is_all_day': is_all_day,
            'duration_minutes': duration,
            'status': event.get('status'),
            'organizer': event.get('organizer', {}).get('email', ''),
            'attendees_count': len(event.get('attendees', []))
        }


# CLI Interface
if __name__ == "__main__":
    import sys
    
    cal = CalendarReader()
    
    if len(sys.argv) < 2:
        print("Usage: calendar_reader.py <command> [args]")
        print("Commands: today, week, next, free, summary")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "today":
        events = cal.get_today_events()
        if not events:
            print("No events today!")
        for e in events:
            time_str = e['start_datetime'].strftime('%H:%M') if e['start_datetime'] else 'All day'
            print(f"[{time_str}] {e['summary']}")
    
    elif cmd == "week":
        events = cal.get_events(days_ahead=7)
        current_day = None
        for e in events:
            if e['start_datetime']:
                day = e['start_datetime'].strftime('%A, %b %d')
                if day != current_day:
                    print(f"\n=== {day} ===")
                    current_day = day
                time_str = e['start_datetime'].strftime('%H:%M')
                print(f"  [{time_str}] {e['summary']}")
    
    elif cmd == "next":
        event = cal.get_next_event()
        if event:
            print(f"Next event: {event['summary']}")
            if event['start_datetime']:
                print(f"  When: {event['start_datetime'].strftime('%A %H:%M')}")
            if event['location']:
                print(f"  Where: {event['location']}")
        else:
            print("No upcoming events")
    
    elif cmd == "free":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        slots = cal.find_free_time(days_ahead=days)
        print(f"Free time slots (next {days} days):")
        for slot in slots:
            print(f"  {slot['date']}: {slot['start']}-{slot['end']} ({slot['duration_minutes']} min)")
    
    elif cmd == "summary":
        summary = cal.summarize_week()
        print(f"Week Summary:")
        print(f"  Total events: {summary['total_events']}")
        print(f"  Busy hours: {summary['busy_hours']}h")
        print(f"\n  Events by day:")
        for day, events in summary['events_by_day'].items():
            print(f"    {day}: {len(events)} events")
    
    else:
        print(f"Unknown command: {cmd}")
```

### Background Check Task
Location: `~/moltbot-system/tasks/check-calendar.sh`

```bash
#!/bin/bash
# Check calendar for upcoming events

cd ~/moltbot-system/skills
python3 calendar_reader.py next >> ~/moltbot-system/logs/calendar.log 2>&1

# Optional: Send Signal notification for events in next 15 minutes
NEXT_EVENT=$(python3 calendar_reader.py next 2>/dev/null)
if echo "$NEXT_EVENT" | grep -q "in [0-9] minutes\|in 1[0-4] minutes"; then
    signal-cli -a "$SIGNAL_PHONE" send -m "Reminder: $NEXT_EVENT" "$SIGNAL_PHONE"
fi
```

## First-Time Authentication

The first time you run the calendar reader, it will:
1. Open a browser window for Google sign-in
2. Ask you to authorize read-only calendar access
3. Store the token locally at `~/.config/moltbot/google_token.json`

Run authentication manually:
```bash
python3 ~/moltbot-system/skills/calendar_reader.py today
```

## Usage Instructions

### For Moltbot (Agent)

When the user asks about their calendar:

**"What's on my calendar today?"**
```bash
python3 ~/moltbot-system/skills/calendar_reader.py today
```

**"What does my week look like?"**
```bash
python3 ~/moltbot-system/skills/calendar_reader.py week
```

**"When is my next meeting?"**
```bash
python3 ~/moltbot-system/skills/calendar_reader.py next
```

**"When do I have free time this week?"**
```bash
python3 ~/moltbot-system/skills/calendar_reader.py free 7
```

**"Give me a summary of my week"**
```bash
python3 ~/moltbot-system/skills/calendar_reader.py summary
```

## Security Notes

1. **Read-Only Access**: The OAuth scope is `calendar.readonly` - the system CANNOT create, modify, or delete events

2. **Token Storage**: The OAuth token is stored locally with restricted permissions (600)

3. **No Data Transmission**: Calendar data is only processed locally, never sent to external services

4. **Revoke Access**: You can revoke access at any time at https://myaccount.google.com/permissions

## Troubleshooting

**"Credentials file not found"**
- Download OAuth credentials from Google Cloud Console
- Save to `~/.config/moltbot/google_credentials.json`

**"Token expired"**
- Delete `~/.config/moltbot/google_token.json`
- Run any command to re-authenticate

**"Access denied"**
- Ensure Calendar API is enabled in Google Cloud Console
- Check that OAuth consent screen is configured

## Remote Commands via Signal

From your phone, send these to your Moltbot Signal number:
- `run:check-calendar` - Get next event info
- Custom commands can be added to the Signal handler
