"""
ICS calendar file import service.
Parses .ics files and imports events as TimeBlocks.
"""
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Union, Optional
import json
from icalendar import Calendar
from dateutil.rrule import rrulestr

from ..db import get_db
from ..models import TimeBlock
from .base import log_action


def parse_ics_file(
    file_path: Union[str, Path],
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> list[dict]:
    """Parse an ICS file and return list of events."""
    with open(file_path, 'rb') as f:
        return parse_ics_content(f.read(), window_start=window_start, window_end=window_end)


def parse_ics_content(
    content: bytes,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> list[dict]:
    """Parse ICS content (bytes) and return list of events."""
    cal = Calendar.from_ical(content)
    events = []
    
    for component in cal.walk():
        if component.name == "VEVENT":
            event_list = parse_vevent_events(
                component,
                window_start=window_start,
                window_end=window_end,
            )
            if event_list:
                events.extend(event_list)
    
    return events


def _to_datetime(value) -> tuple[Optional[datetime], bool]:
    """Convert ICS dt value to datetime and return (datetime, is_all_day)."""
    if value is None:
        return None, False
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time()), True
    return value, False


def _build_rrule_string(component) -> Optional[str]:
    """Build RFC5545 RRULE string from an icalendar VEVENT component."""
    recur = component.get('rrule')
    if not recur:
        return None
    
    parts = []
    for key, values in recur.items():
        if not isinstance(values, (list, tuple)):
            values = [values]
        
        normalized = []
        for v in values:
            if hasattr(v, 'to_ical'):
                v = v.to_ical()
            if isinstance(v, bytes):
                v = v.decode('utf-8')
            normalized.append(str(v))
        
        parts.append(f"{str(key).upper()}={','.join(normalized)}")
    
    return ";".join(parts) if parts else None


def _dt_key(dt: datetime) -> str:
    """Stable key for datetime comparisons (timezone-agnostic)."""
    if dt is None:
        return ""
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat()


def _extract_exdates(component) -> set[str]:
    """Extract EXDATE values as normalized datetime keys."""
    exdate_keys = set()
    exdate_prop = component.get('exdate')
    if not exdate_prop:
        return exdate_keys
    
    exdate_entries = exdate_prop if isinstance(exdate_prop, list) else [exdate_prop]
    for entry in exdate_entries:
        if hasattr(entry, 'dts'):
            for d in entry.dts:
                value = getattr(d, 'dt', None)
                dt, _ = _to_datetime(value)
                if dt:
                    exdate_keys.add(_dt_key(dt))
        else:
            value = getattr(entry, 'dt', None)
            dt, _ = _to_datetime(value)
            if dt:
                exdate_keys.add(_dt_key(dt))
    
    return exdate_keys


def parse_vevent_events(
    component,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
) -> list[dict]:
    """Parse VEVENT into one or more event dicts (expands RRULE recurrences)."""
    try:
        # Get UID for deduplication
        uid = str(component.get('uid', ''))
        
        # Get title
        summary = str(component.get('summary', 'Untitled'))
        
        # Start time
        dtstart = component.get('dtstart')
        if not dtstart:
            return []
        start, is_all_day = _to_datetime(dtstart.dt)
        if not start:
            return []
        
        # Get end time
        dtend = component.get('dtend')
        if dtend:
            end, end_is_all_day = _to_datetime(dtend.dt)
            if end and end_is_all_day:
                # All-day event end date — use same day at 23:59
                end = datetime.combine(end - timedelta(days=1), datetime.max.time().replace(microsecond=0))
        else:
            # Default to 1 hour duration (or end of day for all-day)
            if is_all_day:
                end = datetime.combine(start.date(), datetime.max.time().replace(microsecond=0))
            else:
                end = start + timedelta(hours=1)
        
        if not end:
            return []
        
        duration = end - start
        
        # Get description (optional)
        description = str(component.get('description', '')) or None
        
        # Get location (optional)
        location = str(component.get('location', '')) or None
        
        # Recurrence override instances should be treated as one concrete event
        recurrence_id = component.get('recurrence-id')
        if recurrence_id:
            recurrence_dt, _ = _to_datetime(recurrence_id.dt)
            recurrence_uid = f"{uid}::{_dt_key(recurrence_dt)}" if recurrence_dt else uid
            return [{
                'uid': recurrence_uid,
                'title': summary,
                'start_time': start,
                'end_time': end,
                'all_day': is_all_day,
                'description': description,
                'location': location,
            }]
        
        # Expand RRULE recurrences when present
        rrule_string = _build_rrule_string(component)
        if rrule_string:
            start_tz = start.tzinfo if hasattr(start, 'tzinfo') else None
            if window_start is None:
                window_start = datetime.now(start_tz) - timedelta(days=14)
            if window_end is None:
                window_end = datetime.now(start_tz) + timedelta(days=30)
            
            # Ensure timezone compatibility between recurrence rule and range window
            if start_tz is not None:
                if window_start.tzinfo is None:
                    window_start = window_start.replace(tzinfo=start_tz)
                if window_end.tzinfo is None:
                    window_end = window_end.replace(tzinfo=start_tz)
            else:
                if window_start.tzinfo is not None:
                    window_start = window_start.replace(tzinfo=None)
                if window_end.tzinfo is not None:
                    window_end = window_end.replace(tzinfo=None)
            
            try:
                rule = rrulestr(rrule_string, dtstart=start)
                occurrences = list(rule.between(window_start, window_end, inc=True))
            except Exception:
                # Fall back to single event if RRULE parsing fails
                occurrences = [start]
            
            exdate_keys = _extract_exdates(component)
            events = []
            for occ_start in occurrences:
                if _dt_key(occ_start) in exdate_keys:
                    continue
                
                occ_end = occ_start + duration
                events.append({
                    'uid': f"{uid}::{_dt_key(occ_start)}",
                    'title': summary,
                    'start_time': occ_start,
                    'end_time': occ_end,
                    'all_day': is_all_day,
                    'description': description,
                    'location': location,
                })
            return events
        
        # Non-recurring event
        return [{
            'uid': uid,
            'title': summary,
            'start_time': start,
            'end_time': end,
            'all_day': is_all_day,
            'description': description,
            'location': location,
        }]
    except Exception as e:
        print(f"Error parsing event: {e}")
        return []


def parse_vevent(component) -> Optional[dict]:
    """Backward-compatible wrapper: returns first event from parse_vevent_events."""
    events = parse_vevent_events(component)
    return events[0] if events else None


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
        
        all_day = 1 if event.get('all_day', False) else 0
        
        if existing:
            conn.execute(
                """
                UPDATE time_blocks 
                SET title = ?, start_time = ?, end_time = ?, all_day = ?
                WHERE gcal_event_id = ?
                """,
                (event['title'], start_time, end_time, all_day, event['uid']),
            )
            return 'updated'
        else:
            conn.execute(
                """
                INSERT INTO time_blocks (title, start_time, end_time, source, gcal_event_id, block_type, all_day)
                VALUES (?, ?, ?, 'ics', ?, 'meeting', ?)
                """,
                (event['title'], start_time, end_time, event['uid'], all_day),
            )
            return 'created'


def import_ics_file(file_path: Union[str, Path], days_ahead: int = 30) -> dict:
    """
    Full import: parse ICS file and import events.
    Returns stats dict.
    """
    now = datetime.now()
    window_start = now - timedelta(days=14)
    window_end = now + timedelta(days=days_ahead)
    events = parse_ics_file(file_path, window_start=window_start, window_end=window_end)
    return import_ics_events(events, days_ahead)


def import_ics_bytes(content: bytes, days_ahead: int = 30) -> dict:
    """
    Full import from bytes (for web upload).
    Returns stats dict.
    """
    now = datetime.now()
    window_start = now - timedelta(days=14)
    window_end = now + timedelta(days=days_ahead)
    events = parse_ics_content(content, window_start=window_start, window_end=window_end)
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
