"""
Butler Protocol - Contact Budget Management for Noctem v0.6.0.

The butler is graceful and respectful. Maximum 5 unprompted contacts per calendar week:
- 3 update messages (scheduled days)
- 2 clarification requests (only if needed)

User-initiated contact doesn't count against the budget.
"""
from datetime import datetime, date
from typing import Optional, List, Tuple
import logging

from ..db import get_db
from ..config import Config

logger = logging.getLogger(__name__)


class ButlerProtocol:
    """
    Manages the 5 contacts per week budget.
    
    Contact types:
    - 'update': Status updates (tasks due, overdue, habits)
    - 'clarification': Questions about unclear items
    """
    
    @staticmethod
    def get_current_week() -> Tuple[int, int]:
        """Get current ISO week number and year."""
        today = date.today()
        iso_cal = today.isocalendar()
        return iso_cal[1], iso_cal[0]  # week, year
    
    @staticmethod
    def get_contacts_this_week(week: Optional[int] = None, year: Optional[int] = None) -> List[dict]:
        """Get all contacts for a given week."""
        if week is None or year is None:
            week, year = ButlerProtocol.get_current_week()
        
        with get_db() as conn:
            rows = conn.execute("""
                SELECT id, contact_type, message_content, sent_at
                FROM butler_contacts
                WHERE week_number = ? AND year = ?
                ORDER BY sent_at DESC
            """, (week, year)).fetchall()
            return [dict(row) for row in rows]
    
    @staticmethod
    def get_remaining_contacts(week: Optional[int] = None, year: Optional[int] = None) -> int:
        """How many contacts left this week?"""
        if week is None or year is None:
            week, year = ButlerProtocol.get_current_week()
        
        max_contacts = Config.get("butler_contacts_per_week", 5)
        
        with get_db() as conn:
            count = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts
                WHERE week_number = ? AND year = ?
            """, (week, year)).fetchone()[0]
        
        return max(0, max_contacts - count)
    
    @staticmethod
    def get_contacts_by_type(contact_type: str, week: Optional[int] = None, year: Optional[int] = None) -> int:
        """Count contacts of a specific type this week."""
        if week is None or year is None:
            week, year = ButlerProtocol.get_current_week()
        
        with get_db() as conn:
            count = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts
                WHERE week_number = ? AND year = ? AND contact_type = ?
            """, (week, year, contact_type)).fetchone()[0]
        
        return count
    
    @staticmethod
    def can_contact(contact_type: str) -> bool:
        """
        Check if we have budget for this contact type.
        
        Rules:
        - Max 5 total contacts per week
        - Max 3 updates per week
        - Max 2 clarifications per week
        """
        remaining = ButlerProtocol.get_remaining_contacts()
        if remaining <= 0:
            return False
        
        # Check type-specific limits
        if contact_type == "update":
            updates_sent = ButlerProtocol.get_contacts_by_type("update")
            return updates_sent < 3
        elif contact_type == "clarification":
            clarifications_sent = ButlerProtocol.get_contacts_by_type("clarification")
            return clarifications_sent < 2
        
        return True
    
    @staticmethod
    def record_contact(contact_type: str, message: str) -> Optional[int]:
        """
        Log that we contacted the user.
        
        Returns the contact ID if successful, None if budget exceeded.
        """
        if not ButlerProtocol.can_contact(contact_type):
            logger.warning(f"Contact budget exceeded for type: {contact_type}")
            return None
        
        week, year = ButlerProtocol.get_current_week()
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, (contact_type, message, week, year))
            contact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        logger.info(f"Recorded {contact_type} contact (id={contact_id}), {ButlerProtocol.get_remaining_contacts()} remaining this week")
        return contact_id
    
    @staticmethod
    def get_budget_status() -> dict:
        """Get current budget status for display."""
        week, year = ButlerProtocol.get_current_week()
        remaining = ButlerProtocol.get_remaining_contacts()
        updates_sent = ButlerProtocol.get_contacts_by_type("update")
        clarifications_sent = ButlerProtocol.get_contacts_by_type("clarification")
        
        return {
            "week": week,
            "year": year,
            "total_remaining": remaining,
            "updates_sent": updates_sent,
            "updates_remaining": max(0, 3 - updates_sent),
            "clarifications_sent": clarifications_sent,
            "clarifications_remaining": max(0, 2 - clarifications_sent),
            "can_send_update": ButlerProtocol.can_contact("update"),
            "can_send_clarification": ButlerProtocol.can_contact("clarification"),
        }
    
    @staticmethod
    def get_next_scheduled_contact() -> Optional[dict]:
        """
        Get info about next scheduled contact.
        Returns dict with 'type', 'day', 'time' or None if fully exhausted.
        """
        status = ButlerProtocol.get_budget_status()
        
        # Get configured days
        update_days = Config.get("butler_update_days", ["monday", "wednesday", "friday"])
        update_time = Config.get("butler_update_time", "09:00")
        clarification_days = Config.get("butler_clarification_days", ["tuesday", "thursday"])
        clarification_time = Config.get("butler_clarification_time", "09:00")
        
        today = datetime.now()
        today_name = today.strftime("%A").lower()
        
        # Find next update day if we can still send updates
        if status["can_send_update"]:
            for day in update_days:
                # Simple check - in real impl would calculate actual next occurrence
                if day != today_name:
                    return {"type": "update", "day": day, "time": update_time}
        
        # Find next clarification day if we can still send clarifications
        if status["can_send_clarification"]:
            for day in clarification_days:
                if day != today_name:
                    return {"type": "clarification", "day": day, "time": clarification_time}
        
        return None


def get_butler_status() -> dict:
    """Get butler status as a dict for programmatic use."""
    status = ButlerProtocol.get_budget_status()
    budget = Config.get("butler_contacts_per_week", 5)
    
    return {
        'remaining': status['total_remaining'],
        'budget': budget,
        'updates_remaining': status['updates_remaining'],
        'clarifications_remaining': status['clarifications_remaining'],
        'week': status['week'],
        'year': status['year'],
    }


def get_butler_status_message() -> str:
    """Get a human-readable butler status string."""
    status = ButlerProtocol.get_budget_status()
    
    lines = [
        f"📬 **Butler Status** (Week {status['week']})",
        "",
        f"Contacts remaining: {status['total_remaining']}/5",
        f"• Updates: {status['updates_sent']}/3 sent",
        f"• Clarifications: {status['clarifications_sent']}/2 sent",
    ]
    
    next_contact = ButlerProtocol.get_next_scheduled_contact()
    if next_contact:
        lines.append(f"\nNext scheduled: {next_contact['type'].title()} on {next_contact['day'].title()} at {next_contact['time']}")
    else:
        lines.append("\n_Budget exhausted for this week_")
    
    return "\n".join(lines)
