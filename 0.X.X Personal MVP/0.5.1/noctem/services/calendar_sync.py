"""
Google Calendar sync service.
Polls GCal and imports events as TimeBlocks.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from ..db import get_db
from ..models import TimeBlock
from ..config import Config
from .base import log_action

# Google API imports - optional, only needed when actually syncing
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GCAL_AVAILABLE = True
except ImportError:
    GCAL_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = Path(__file__).parent.parent / "data" / "gcal_token.json"
CREDENTIALS_PATH = Path(__file__).parent.parent / "data" / "gcal_credentials.json"


def is_gcal_configured() -> bool:
    """Check if Google Calendar is configured."""
    return GCAL_AVAILABLE and CREDENTIALS_PATH.exists()


def get_gcal_service():
    """Get an authenticated Google Calendar service."""
    if not GCAL_AVAILABLE:
        raise RuntimeError("Google Calendar API not installed. Run: pip install google-api-python-client google-auth-oauthlib")
    
    creds = None
    
    # Load existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise RuntimeError(
                    f"Google Calendar credentials not found at {CREDENTIALS_PATH}. "
                    "Download from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    
    return build("calendar", "v3", credentials=creds)


def sync_calendar(days_ahead: int = 7) -> dict:
    """
    Sync events from Google Calendar.
    Returns a dict with sync stats.
    """
    if not is_gcal_configured():
        return {"status": "not_configured", "message": "Google Calendar not configured"}
    
    try:
        service = get_gcal_service()
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    calendar_ids = Config.get("gcal_calendar_ids", ["primary"])
    timezone = Config.timezone()
    
    # Time range
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"
    
    stats = {"created": 0, "updated": 0, "deleted": 0, "errors": 0}
    seen_event_ids = set()
    
    for calendar_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            
            events = events_result.get("items", [])
            
            for event in events:
                event_id = event["id"]
                seen_event_ids.add(event_id)
                
                # Parse event times
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                
                # Convert to datetime
                if "T" in start:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                else:
                    start_dt = datetime.fromisoformat(start + "T00:00:00")
                
                if "T" in end:
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                else:
                    end_dt = datetime.fromisoformat(end + "T23:59:59")
                
                # Upsert time block
                result = upsert_time_block(
                    gcal_event_id=event_id,
                    title=event.get("summary", "Untitled"),
                    start_time=start_dt,
                    end_time=end_dt,
                )
                
                if result == "created":
                    stats["created"] += 1
                elif result == "updated":
                    stats["updated"] += 1
                    
        except Exception as e:
            stats["errors"] += 1
            print(f"Error syncing calendar {calendar_id}: {e}")
    
    # Delete events no longer in calendar
    deleted = delete_removed_gcal_events(seen_event_ids)
    stats["deleted"] = deleted
    
    log_action("gcal_sync", details=stats)
    return {"status": "success", **stats}


def upsert_time_block(
    gcal_event_id: str,
    title: str,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """Insert or update a time block from GCal. Returns 'created' or 'updated'."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM time_blocks WHERE gcal_event_id = ?",
            (gcal_event_id,),
        ).fetchone()
        
        if existing:
            conn.execute(
                """
                UPDATE time_blocks 
                SET title = ?, start_time = ?, end_time = ?
                WHERE gcal_event_id = ?
                """,
                (title, start_time, end_time, gcal_event_id),
            )
            return "updated"
        else:
            conn.execute(
                """
                INSERT INTO time_blocks (title, start_time, end_time, source, gcal_event_id, block_type)
                VALUES (?, ?, ?, 'gcal', ?, 'meeting')
                """,
                (title, start_time, end_time, gcal_event_id),
            )
            return "created"


def delete_removed_gcal_events(current_event_ids: set) -> int:
    """Delete time blocks for events no longer in GCal."""
    if not current_event_ids:
        return 0
    
    with get_db() as conn:
        # Get all gcal events
        rows = conn.execute(
            "SELECT id, gcal_event_id FROM time_blocks WHERE source = 'gcal'"
        ).fetchall()
        
        deleted = 0
        for row in rows:
            if row["gcal_event_id"] not in current_event_ids:
                conn.execute("DELETE FROM time_blocks WHERE id = ?", (row["id"],))
                deleted += 1
        
        return deleted


def create_manual_time_block(
    title: str,
    start_time: datetime,
    end_time: datetime,
    block_type: str = "other",
) -> TimeBlock:
    """Create a manual time block (not from GCal)."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO time_blocks (title, start_time, end_time, source, block_type)
            VALUES (?, ?, ?, 'manual', ?)
            """,
            (title, start_time, end_time, block_type),
        )
        block_id = cursor.lastrowid
    
    log_action("time_block_created", "time_block", block_id, {"title": title})
    
    with get_db() as conn:
        row = conn.execute("SELECT * FROM time_blocks WHERE id = ?", (block_id,)).fetchone()
        return TimeBlock.from_row(row)
