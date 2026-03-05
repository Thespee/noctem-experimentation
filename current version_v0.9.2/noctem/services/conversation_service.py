"""
Conversation service for Noctem v0.6.0 Final Polish.

Provides unified conversation experience across web/CLI/Telegram:
- Record messages with thinking context
- Get recent conversation context
- Get thinking feed for verbose display
- Export thinking log as JSON
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Generator
from uuid import uuid4

from ..db import get_db
from ..models import Conversation

logger = logging.getLogger(__name__)


# ============================================================================
# Message Recording
# ============================================================================

def record_message(
    content: str,
    role: str = "user",
    source: str = "cli",
    session_id: Optional[str] = None,
    thinking_summary: Optional[str] = None,
    thinking_level: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Conversation:
    """
    Record a conversation message.
    
    Args:
        content: The message content
        role: 'user', 'assistant', or 'system'
        source: 'web', 'cli', or 'telegram'
        session_id: Optional session identifier (auto-generated if not provided)
        thinking_summary: Brief summary of system thinking (for assistant messages)
        thinking_level: 'decision', 'activity', or 'debug'
        metadata: Additional metadata dict
    
    Returns:
        The created Conversation object
    """
    if session_id is None:
        session_id = _get_or_create_session(source)
    
    with get_db() as conn:
        conn.execute(
            """INSERT INTO conversations 
               (session_id, source, role, content, thinking_summary, thinking_level, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                source,
                role,
                content,
                thinking_summary,
                thinking_level,
                json.dumps(metadata) if metadata else None,
            )
        )
        msg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (msg_id,)
        ).fetchone()
        
        return Conversation.from_row(row)


def record_thinking(
    summary: str,
    level: str = "activity",
    source: str = "system",
    metadata: Optional[dict] = None,
) -> Conversation:
    """
    Record a system thinking entry (for the thinking feed).
    
    Args:
        summary: What the system is thinking/doing
        level: 'decision' (important), 'activity' (normal), 'debug' (verbose)
        source: Which component generated this ('butler', 'slow', 'sync', etc.)
        metadata: Additional context
    
    Returns:
        The created Conversation object
    """
    return record_message(
        content=summary,
        role="system",
        source=source,
        thinking_summary=summary,
        thinking_level=level,
        metadata=metadata,
    )


# ============================================================================
# Context Retrieval
# ============================================================================

def get_recent_context(
    limit: int = 20,
    source: Optional[str] = None,
    include_system: bool = False,
) -> list[Conversation]:
    """
    Get recent conversation context for continuity.
    
    Args:
        limit: Maximum messages to return
        source: Filter by source (None = all sources)
        include_system: Include system thinking messages
    
    Returns:
        List of Conversation objects, oldest first
    """
    with get_db() as conn:
        if source and not include_system:
            rows = conn.execute(
                """SELECT * FROM conversations 
                   WHERE source = ? AND role != 'system'
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (source, limit)
            ).fetchall()
        elif source:
            rows = conn.execute(
                """SELECT * FROM conversations 
                   WHERE source = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (source, limit)
            ).fetchall()
        elif not include_system:
            rows = conn.execute(
                """SELECT * FROM conversations 
                   WHERE role != 'system'
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM conversations 
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
        
        # Reverse to get oldest first
        return [Conversation.from_row(row) for row in reversed(rows)]


def get_session_messages(session_id: str) -> list[Conversation]:
    """
    Get all messages from a specific session.
    
    Args:
        session_id: The session identifier
    
    Returns:
        List of Conversation objects, oldest first
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM conversations 
               WHERE session_id = ?
               ORDER BY created_at ASC""",
            (session_id,)
        ).fetchall()
        
        return [Conversation.from_row(row) for row in rows]


# ============================================================================
# Thinking Feed
# ============================================================================

def get_thinking_feed(
    limit: int = 50,
    level_filter: Optional[str] = None,
    since: Optional[datetime] = None,
) -> list[Conversation]:
    """
    Get the thinking feed (system activity log).
    
    Args:
        limit: Maximum entries to return
        level_filter: Filter by level: 'all', 'activity', 'decisions'
        since: Only get entries after this time
    
    Returns:
        List of thinking entries, newest first
    """
    with get_db() as conn:
        conditions = ["thinking_level IS NOT NULL"]
        params = []
        
        if level_filter == "decisions":
            conditions.append("thinking_level = 'decision'")
        elif level_filter == "activity":
            conditions.append("thinking_level IN ('decision', 'activity')")
        # 'all' or None includes everything including debug
        
        if since:
            conditions.append("created_at > ?")
            params.append(since.isoformat())
        
        params.append(limit)
        
        query = f"""
            SELECT * FROM conversations 
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        
        rows = conn.execute(query, params).fetchall()
        return [Conversation.from_row(row) for row in rows]


def get_thinking_feed_since(last_id: int) -> list[Conversation]:
    """
    Get thinking feed entries since a specific ID (for polling).
    
    Args:
        last_id: Get entries with ID greater than this
    
    Returns:
        List of new thinking entries, oldest first
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM conversations 
               WHERE id > ? AND thinking_level IS NOT NULL
               ORDER BY created_at ASC""",
            (last_id,)
        ).fetchall()
        
        return [Conversation.from_row(row) for row in rows]


# ============================================================================
# Export
# ============================================================================

def export_thinking_log(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    level_filter: Optional[str] = None,
) -> dict:
    """
    Export thinking log as JSON-serializable dict.
    
    Args:
        start_date: Start of export range (default: 24h ago)
        end_date: End of export range (default: now)
        level_filter: Filter by level
    
    Returns:
        Dict with metadata and entries
    """
    if start_date is None:
        start_date = datetime.now() - timedelta(hours=24)
    if end_date is None:
        end_date = datetime.now()
    
    with get_db() as conn:
        conditions = ["thinking_level IS NOT NULL"]
        params = []
        
        conditions.append("created_at >= ?")
        params.append(start_date.isoformat())
        
        conditions.append("created_at <= ?")
        params.append(end_date.isoformat())
        
        if level_filter == "decisions":
            conditions.append("thinking_level = 'decision'")
        elif level_filter == "activity":
            conditions.append("thinking_level IN ('decision', 'activity')")
        
        query = f"""
            SELECT * FROM conversations 
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at ASC
        """
        
        rows = conn.execute(query, params).fetchall()
        entries = [Conversation.from_row(row) for row in rows]
    
    return {
        "export_time": datetime.now().isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "level_filter": level_filter,
        "entry_count": len(entries),
        "entries": [
            {
                "id": e.id,
                "timestamp": e.created_at.isoformat() if e.created_at else None,
                "source": e.source,
                "level": e.thinking_level,
                "summary": e.thinking_summary,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in entries
        ],
    }


def export_conversation_log(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    source: Optional[str] = None,
) -> dict:
    """
    Export full conversation log as JSON-serializable dict.
    
    Args:
        start_date: Start of export range (default: 7 days ago)
        end_date: End of export range (default: now)
        source: Filter by source
    
    Returns:
        Dict with metadata and messages
    """
    if start_date is None:
        start_date = datetime.now() - timedelta(days=7)
    if end_date is None:
        end_date = datetime.now()
    
    with get_db() as conn:
        conditions = ["1=1"]
        params = []
        
        conditions.append("created_at >= ?")
        params.append(start_date.isoformat())
        
        conditions.append("created_at <= ?")
        params.append(end_date.isoformat())
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        
        query = f"""
            SELECT * FROM conversations 
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at ASC
        """
        
        rows = conn.execute(query, params).fetchall()
        messages = [Conversation.from_row(row) for row in rows]
    
    return {
        "export_time": datetime.now().isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "source_filter": source,
        "message_count": len(messages),
        "messages": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "timestamp": m.created_at.isoformat() if m.created_at else None,
                "source": m.source,
                "role": m.role,
                "content": m.content,
                "thinking_summary": m.thinking_summary,
                "thinking_level": m.thinking_level,
                "metadata": m.metadata,
            }
            for m in messages
        ],
    }


# ============================================================================
# Session Management
# ============================================================================

def _get_or_create_session(source: str) -> str:
    """
    Get the current session ID for a source, or create a new one.
    Sessions are considered active for 30 minutes.
    """
    with get_db() as conn:
        # Find most recent session from this source
        row = conn.execute(
            """SELECT session_id, created_at FROM conversations 
               WHERE source = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (source,)
        ).fetchone()
        
        if row:
            last_time = row["created_at"]
            if isinstance(last_time, str):
                last_time = datetime.fromisoformat(last_time)
            
            # If less than 30 minutes ago, reuse session
            if datetime.now() - last_time < timedelta(minutes=30):
                return row["session_id"]
        
        # Create new session
        return f"{source}_{uuid4().hex[:8]}"


def create_new_session(source: str) -> str:
    """
    Force create a new session for a source.
    
    Returns:
        New session ID
    """
    return f"{source}_{uuid4().hex[:8]}"


def get_recent_sessions(limit: int = 10) -> list[dict]:
    """
    Get list of recent sessions with summary.
    
    Returns:
        List of dicts with session_id, source, message_count, last_activity
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT session_id, source, 
                      COUNT(*) as message_count,
                      MAX(created_at) as last_activity
               FROM conversations
               WHERE session_id IS NOT NULL
               GROUP BY session_id
               ORDER BY last_activity DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        
        return [
            {
                "session_id": row["session_id"],
                "source": row["source"],
                "message_count": row["message_count"],
                "last_activity": row["last_activity"],
            }
            for row in rows
        ]


# ============================================================================
# Cleanup
# ============================================================================

def cleanup_old_conversations(days: int = 30) -> int:
    """
    Delete conversations older than specified days.
    
    Args:
        days: Delete conversations older than this many days
    
    Returns:
        Number of deleted conversations
    """
    cutoff = datetime.now() - timedelta(days=days)
    
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM conversations WHERE created_at < ?",
            (cutoff.isoformat(),)
        )
        count = result.rowcount
    
    if count > 0:
        logger.info(f"Cleaned up {count} old conversations")
    
    return count


def get_conversation_stats() -> dict:
    """
    Get conversation statistics.
    
    Returns:
        Dict with counts and other stats
    """
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0]
        
        by_source = conn.execute(
            """SELECT source, COUNT(*) as count
               FROM conversations
               GROUP BY source"""
        ).fetchall()
        
        by_role = conn.execute(
            """SELECT role, COUNT(*) as count
               FROM conversations
               GROUP BY role"""
        ).fetchall()
        
        thinking_count = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE thinking_level IS NOT NULL"
        ).fetchone()[0]
    
    return {
        "total": total,
        "by_source": {row["source"]: row["count"] for row in by_source},
        "by_role": {row["role"]: row["count"] for row in by_role},
        "thinking_entries": thinking_count,
    }
