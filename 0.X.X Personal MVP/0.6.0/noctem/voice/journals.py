"""
Voice journal storage and management.
Handles saving audio files and tracking transcription status.
"""
import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from noctem.db import get_db, DB_PATH

logger = logging.getLogger(__name__)

# Audio storage directory (sibling to database)
AUDIO_DIR = DB_PATH.parent / "voice_journals"


def _ensure_audio_dir():
    """Ensure the audio storage directory exists."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def save_voice_journal(
    audio_data: bytes,
    source: str = "web",
    original_filename: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Save a voice journal audio file and create a database record.
    
    Args:
        audio_data: Raw audio bytes
        source: 'telegram' or 'web'
        original_filename: Original filename if known
        metadata: Optional dict with extra info (e.g., telegram message_id)
        
    Returns:
        The voice journal ID
    """
    _ensure_audio_dir()
    
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    
    # Determine extension from original filename or default to .ogg (telegram) / .mp3 (web)
    if original_filename:
        ext = Path(original_filename).suffix.lower() or ".mp3"
    else:
        ext = ".ogg" if source == "telegram" else ".mp3"
    
    filename = f"{timestamp}_{unique_id}{ext}"
    audio_path = AUDIO_DIR / filename
    
    # Save the audio file
    audio_path.write_bytes(audio_data)
    logger.info(f"Saved audio file: {audio_path} ({len(audio_data)} bytes)")
    
    # Create database record
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO voice_journals (audio_path, original_filename, source, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (str(audio_path), original_filename, source, json.dumps(metadata) if metadata else None)
        )
        journal_id = cursor.lastrowid
    
    logger.info(f"Created voice journal record: id={journal_id}")
    return journal_id


def save_voice_journal_from_file(
    file_path: str,
    source: str = "web",
    original_filename: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    copy: bool = True,
) -> int:
    """
    Save a voice journal from an existing file path.
    
    Args:
        file_path: Path to the audio file
        source: 'telegram' or 'web'
        original_filename: Original filename if different from file_path
        metadata: Optional dict with extra info
        copy: If True, copy file to storage. If False, use the path directly.
        
    Returns:
        The voice journal ID
    """
    source_path = Path(file_path)
    
    if copy:
        _ensure_audio_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        ext = source_path.suffix.lower() or ".mp3"
        filename = f"{timestamp}_{unique_id}{ext}"
        dest_path = AUDIO_DIR / filename
        shutil.copy2(source_path, dest_path)
        stored_path = str(dest_path)
        logger.info(f"Copied audio file to: {dest_path}")
    else:
        stored_path = str(source_path.absolute())
    
    # Create database record
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO voice_journals (audio_path, original_filename, source, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (stored_path, original_filename or source_path.name, source, json.dumps(metadata) if metadata else None)
        )
        journal_id = cursor.lastrowid
    
    logger.info(f"Created voice journal record: id={journal_id}")
    return journal_id


def get_pending_journals() -> List[Dict[str, Any]]:
    """Get all voice journals pending transcription."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT id, audio_path, original_filename, source, metadata, created_at
            FROM voice_journals
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """
        )
        rows = cursor.fetchall()
    
    return [dict(row) for row in rows]


def get_journal(journal_id: int) -> Optional[Dict[str, Any]]:
    """Get a voice journal by ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM voice_journals WHERE id = ?
            """,
            (journal_id,)
        )
        row = cursor.fetchone()
    
    return dict(row) if row else None


def get_all_journals(limit: int = 50, include_pending: bool = True) -> List[Dict[str, Any]]:
    """Get all voice journals, most recent first."""
    status_filter = "" if include_pending else "WHERE status = 'completed'"
    
    with get_db() as conn:
        cursor = conn.execute(
            f"""
            SELECT * FROM voice_journals
            {status_filter}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
    
    return [dict(row) for row in rows]


def mark_transcribing(journal_id: int):
    """Mark a journal as currently being transcribed."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE voice_journals
            SET status = 'transcribing'
            WHERE id = ?
            """,
            (journal_id,)
        )
    logger.info(f"Voice journal {journal_id} marked as transcribing")


def complete_transcription(
    journal_id: int,
    transcription: str,
    duration_seconds: Optional[float] = None,
    language: Optional[str] = None,
):
    """Mark a journal as successfully transcribed."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE voice_journals
            SET status = 'completed',
                transcription = ?,
                duration_seconds = ?,
                language = ?,
                transcribed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (transcription, duration_seconds, language, journal_id)
        )
    logger.info(f"Voice journal {journal_id} transcription completed: {len(transcription)} chars")


def fail_transcription(journal_id: int, error_message: str):
    """Mark a journal as failed transcription."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE voice_journals
            SET status = 'failed',
                error_message = ?
            WHERE id = ?
            """,
            (error_message, journal_id)
        )
    logger.error(f"Voice journal {journal_id} transcription failed: {error_message}")


def get_transcription_stats() -> Dict[str, int]:
    """Get counts of journals by status."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM voice_journals
            GROUP BY status
            """
        )
        rows = cursor.fetchall()
    
    stats = {"pending": 0, "transcribing": 0, "completed": 0, "failed": 0}
    for row in rows:
        stats[row["status"]] = row["count"]
    
    return stats


def update_transcription(journal_id: int, new_text: str) -> bool:
    """
    Update/edit the transcription for a voice journal.
    
    Saves the edited text and marks the transcription as edited.
    
    Args:
        journal_id: The voice journal ID
        new_text: The edited transcription text
        
    Returns:
        True if successful
    """
    with get_db() as conn:
        # Check if this column exists (transcription_edited was added in Phase 1)
        # If columns don't exist, just update the transcription field
        try:
            conn.execute(
                """
                UPDATE voice_journals
                SET transcription_edited = ?,
                    transcription_edited_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_text, journal_id)
            )
        except Exception:
            # Fallback: update main transcription if edited columns don't exist
            conn.execute(
                """
                UPDATE voice_journals
                SET transcription = ?
                WHERE id = ?
                """,
                (new_text, journal_id)
            )
    
    logger.info(f"Voice journal {journal_id} transcription edited: {len(new_text)} chars")
    return True


def get_transcription(journal_id: int) -> Optional[str]:
    """
    Get the transcription for a voice journal.
    
    Returns the edited version if available, otherwise the original.
    
    Args:
        journal_id: The voice journal ID
        
    Returns:
        The transcription text or None
    """
    journal = get_journal(journal_id)
    if not journal:
        return None
    
    # Return edited version if available
    if journal.get('transcription_edited'):
        return journal['transcription_edited']
    
    return journal.get('transcription')
