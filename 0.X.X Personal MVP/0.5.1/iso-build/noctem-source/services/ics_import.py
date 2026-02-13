"""
ICS calendar file import service.
Parses .ics files and imports events as TimeBlocks.
"""
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Union, Optional
import json
from icalendar import Calendar

from ..db import get_db
from ..models import TimeBlock
from .base import log_action


def parse_ics_file(file_path: Union[str, Path]) -> list[dict]:
    """Parse an ICS file and return list of events."""
    with open(file_path, 'rb') as f:
        return parse_ics_content(f.read())


def parse_ics_content(content: bytes) -> list[dict]:
    """Parse ICS content (bytes) and return list of events."""
    cal = Calendar.from_ical(content)
    events = []
    
    for component in cal.walk():
        if component.name == "VEVENT":
            event = parse_vevent(component)
            if event:
                events.append(event)
    
    return events


def parse_vevent(component) -> dict:
    """Parse a VEVENT component into a dict."""
    try:
        # Get UID for deduplication
        uid = str(component.get('uid', ''))
        
        # Get title
        summary = str(component.get('summary', 'Untitled'))
        
        # Get start time
        dtstart = component.get('dtstart')
        if dtstart:
            start = dtstart.dt
            if isinstance(start, date) and not isinstance(start, datetime):
                # All-day event
                start = datetime.combine(start, datetime.min.time())
        else:
            return None
        
        # Get end time
        dtend = component.get('dtend')
        if dtend:
            end = dtend.dt
            if isinstance(end, date) and not isinstance(end, datetime):
                end = datetime.combine(end, datetime.max.time().replace(microsecond=0))
        else:
            # Default to 1 hour duration
            end = start + timedelta(hours=1)
        
        # Get description (optional)
        description = str(component.get('description', '')) or None
        
        # Get location (optional)
        location = str(component.get('location', '')) or None
        
        return {
            'uid': uid,
            'title': summary,
            'start_time': start,
            'end_time': end,
            'description': description,
            'location': location,
        }
    except Exception as e:
        print(f"Error parsing event: {e}")
        return None


def import_ics_events(events: list[dict], days_ahead: int = 30) -> dict:
    """
    Import parsed ICS events into the database.
    Only imports events within the specified time range.
    Returns stats dict.
    """
    now = datetime.now()
    cutoff_past = now - timedelta(days=14)  # Include past 2 weeks
    cutoff_future = now + timedelta(days=days_ahead)
    
    stats = {'created': 0, 'updated': 0, 'skipped': 0}
    imported_uids = set()
    
    for event in events:
        start = event['start_time']
        
        # Convert to naive datetime for comparison
        start_naive = start
        if hasattr(start, 'tzinfo') and start.tzinfo is not None:
            # Convert to local time then strip timezone
            try:
                start_naive = start.replace(tzinfo=None)
            except:
                start_naive = start
        
        # Skip events outside our range (be lenient - import if in doubt)
        try:
            if start_naive < cutoff_past or start_naive > cutoff_future:
                stats['skipped'] += 1
                continue
        except TypeError:
            # If comparison fails due to tz issues, import anyway
            pass
        
        # Upsert the event
        result = upsert_ics_event(event)
        stats[result] += 1
        imported_uids.add(event['uid'])
    
    log_action("ics_import", details=stats)
    return stats


def _to_local_naive(dt: datetime) -> datetime:
    """Convert a datetime to local time and strip timezone info."""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        # Convert to local time, then strip timezone
        local_dt = dt.astimezone()  # Converts to system local timezone
        return local_dt.replace(tzinfo=None)
    return dt


def upsert_ics_event(event: dict) -> str:
    """Insert or update a time block from ICS. Returns 'created' or 'updated'."""
    # Convert to local time (naive) for storage
    start_time = _to_local_naive(event['start_time'])
    end_time = _to_local_naive(event['end_time'])
    
    with get_db() as conn:
        # Check if event exists by UID
        existing = conn.execute(
            "SELECT id FROM time_blocks WHERE gcal_event_id = ?",
            (event['uid'],),
        ).fetchone()
        
        if existing:
            conn.execute(
                """
                UPDATE time_blocks 
                SET title = ?, start_time = ?, end_time = ?
                WHERE gcal_event_id = ?
                """,
                (event['title'], start_time, end_time, event['uid']),
            )
            return 'updated'
        else:
            conn.execute(
                """
                INSERT INTO time_blocks (title, start_time, end_time, source, gcal_event_id, block_type)
                VALUES (?, ?, ?, 'ics', ?, 'meeting')
                """,
                (event['title'], start_time, end_time, event['uid']),
            )
            return 'created'


def import_ics_file(file_path: Union[str, Path], days_ahead: int = 30) -> dict:
    """
    Full import: parse ICS file and import events.
    Returns stats dict.
    """
    events = parse_ics_file(file_path)
    return import_ics_events(events, days_ahead)


def import_ics_bytes(content: bytes, days_ahead: int = 30) -> dict:
    """
    Full import from bytes (for web upload).
    Returns stats dict.
    """
    events = parse_ics_content(content)
    return import_ics_events(events, days_ahead)


def import_ics_url(url: str, days_ahead: int = 30) -> dict:
    """
    Fetch and import ICS from a URL.
    Returns stats dict.
    """
    import requests
    
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return import_ics_bytes(resp.content, days_ahead)
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def clear_ics_events():
    """Remove all ICS-imported time blocks."""
    with get_db() as conn:
        result = conn.execute("DELETE FROM time_blocks WHERE source = 'ics'")
        return result.rowcount


# --- Saved URL Management ---

def get_saved_urls() -> list[dict]:
    """Get all saved ICS URLs with their names."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'ics_urls'"
        ).fetchone()
        if row and row['value']:
            return json.loads(row['value'])
        return []


def save_url(url: str, name: Optional[str] = None) -> dict:
    """Save an ICS URL for later refresh. Returns import stats."""
    urls = get_saved_urls()
    
    # Check if already exists
    for u in urls:
        if u['url'] == url:
            # Already saved, just refresh it
            return import_ics_url(url)
    
    # Add new URL
    if not name:
        # Extract name from URL
        name = url.split('/')[-1].replace('.ics', '')[:30]
    
    urls.append({
        'url': url,
        'name': name,
        'added_at': datetime.now().isoformat()
    })
    
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('ics_urls', ?)",
            (json.dumps(urls),)
        )
    
    # Import immediately
    return import_ics_url(url)


def remove_url(url: str) -> bool:
    """Remove a saved ICS URL."""
    urls = get_saved_urls()
    urls = [u for u in urls if u['url'] != url]
    
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('ics_urls', ?)",
            (json.dumps(urls),)
        )
    return True


def refresh_all_urls() -> dict:
    """Refresh all saved URLs. Returns combined stats."""
    urls = get_saved_urls()
    total_stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}
    
    for u in urls:
        try:
            stats = import_ics_url(u['url'])
            if 'error' not in stats.get('status', ''):
                total_stats['created'] += stats.get('created', 0)
                total_stats['updated'] += stats.get('updated', 0)
                total_stats['skipped'] += stats.get('skipped', 0)
            else:
                total_stats['errors'].append(f"{u['name']}: {stats.get('message', 'Unknown error')}")
        except Exception as e:
            total_stats['errors'].append(f"{u['name']}: {str(e)}")
    
    return total_stats


def refresh_url(url: str) -> dict:
    """Refresh a single saved URL."""
    return import_ics_url(url)
