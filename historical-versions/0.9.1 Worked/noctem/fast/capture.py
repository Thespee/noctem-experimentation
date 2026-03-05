"""Thoughts-first capture system for Noctem v0.6.0 Polish.

Universal capture layer that records all inputs as "thoughts" before routing.
Implements the "royal scribe" pattern: capture everything, classify second.

v0.6.1: Added execution logging for full pipeline tracing.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import get_db
from ..models import Thought, Task
from ..services import task_service, project_service
from ..session import get_session
from .classifier import (
    classify_input, ClassificationResult, ThoughtKind, AmbiguityReason,
    HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, get_confidence_level
)
from .voice_cleanup import clean_voice_transcript
from ..parser.task_parser import format_task_confirmation
from ..logging.execution_logger import ExecutionLogger

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    """Result of processing an input through the capture system."""
    thought_id: int
    kind: ThoughtKind
    confidence: float
    response: str
    task: Optional[Task] = None
    is_command: bool = False
    needs_confirmation: bool = False


def create_thought(
    raw_text: str,
    source: str,
    kind: Optional[str] = None,
    ambiguity_reason: Optional[str] = None,
    confidence: Optional[float] = None,
    voice_journal_id: Optional[int] = None,
) -> Thought:
    """
    Create a thought record in the database.
    
    Args:
        raw_text: The raw input text
        source: 'cli', 'telegram', 'web', 'voice'
        kind: Classification kind if known
        ambiguity_reason: Reason for ambiguity if applicable
        confidence: Classifier confidence score
        voice_journal_id: Link to voice journal if from voice (must exist in voice_journals table)
    
    Returns:
        The created Thought object
    """
    # Only include voice_journal_id if it's a valid reference (or None)
    # Setting to None if the reference doesn't exist avoids FK constraint errors
    actual_voice_journal_id = None
    if voice_journal_id is not None:
        with get_db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM voice_journals WHERE id = ?", (voice_journal_id,)
            ).fetchone()
            if exists:
                actual_voice_journal_id = voice_journal_id
    
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO thoughts (source, raw_text, kind, ambiguity_reason, confidence, voice_journal_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (source, raw_text, kind, ambiguity_reason, confidence, actual_voice_journal_id)
        )
        thought_id = cursor.lastrowid
    
    conf_str = f"{confidence:.2f}" if confidence is not None else "N/A"
    logger.info(f"Created thought {thought_id}: kind={kind}, confidence={conf_str}")
    return get_thought(thought_id)


def get_thought(thought_id: int) -> Optional[Thought]:
    """Get a thought by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM thoughts WHERE id = ?",
            (thought_id,)
        ).fetchone()
    return Thought.from_row(row) if row else None


def update_thought(
    thought_id: int,
    status: Optional[str] = None,
    linked_task_id: Optional[int] = None,
    linked_project_id: Optional[int] = None,
    kind: Optional[str] = None,
) -> Thought:
    """Update a thought record."""
    updates = []
    params = []
    
    if status:
        updates.append("status = ?")
        params.append(status)
        if status == 'processed':
            updates.append("processed_at = ?")
            params.append(datetime.now())
    
    if linked_task_id:
        updates.append("linked_task_id = ?")
        params.append(linked_task_id)
    
    if linked_project_id:
        updates.append("linked_project_id = ?")
        params.append(linked_project_id)
    
    if kind:
        updates.append("kind = ?")
        params.append(kind)
    
    if updates:
        params.append(thought_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE thoughts SET {', '.join(updates)} WHERE id = ?",
                params
            )
    
    return get_thought(thought_id)


def get_pending_ambiguous_thoughts(limit: int = 10) -> list[Thought]:
    """Get pending ambiguous thoughts for Butler clarification."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM thoughts
            WHERE kind = 'ambiguous' AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    return [Thought.from_row(row) for row in rows]


def get_thoughts_stats() -> dict:
    """Get statistics about thoughts."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT kind, status, COUNT(*) as count
            FROM thoughts
            GROUP BY kind, status
            """
        ).fetchall()
    
    stats = {
        "total": 0,
        "by_kind": {"actionable": 0, "note": 0, "ambiguous": 0},
        "by_status": {"pending": 0, "processed": 0, "clarified": 0},
    }
    
    for row in rows:
        count = row["count"]
        stats["total"] += count
        if row["kind"] in stats["by_kind"]:
            stats["by_kind"][row["kind"]] += count
        if row["status"] in stats["by_status"]:
            stats["by_status"][row["status"]] += count
    
    return stats


def process_input(
    text: str,
    source: str = "cli",
    voice_journal_id: Optional[int] = None,
) -> CaptureResult:
    """
    Process an input through the full capture and classification pipeline.
    
    This is the main entry point for the royal scribe pattern:
    1. Capture the raw input as a thought
    2. Classify it
    3. Route appropriately (task, note, or clarification queue)
    4. Return result with response message
    
    v0.6.1: Full execution tracing with ExecutionLogger.
    
    Args:
        text: The input text
        source: Where the input came from
        voice_journal_id: Optional link to voice journal
    
    Returns:
        CaptureResult with thought ID, classification, and response
    """
    # Start execution trace
    with ExecutionLogger(component="fast", source=source) as trace:
        # Log input stage
        trace.log_stage("input", input_data={
            "text": text[:200] if text else "",  # Truncate for logging
            "source": source,
            "voice_journal_id": voice_journal_id,
        })
        
        # Clean voice transcripts
        original_text = text
        if source == "voice" and text:
            text = clean_voice_transcript(text)
            if text != original_text:
                trace.log_stage("voice_cleanup", output_data={
                    "original_length": len(original_text),
                    "cleaned_length": len(text),
                })
        
        # Classify the input
        classification = classify_input(text, source)
        trace.log_stage("classify", 
            output_data={
                "kind": classification.kind.value,
                "ambiguity_reason": classification.ambiguity_reason.value if classification.ambiguity_reason else None,
                "is_command": classification.is_command,
            },
            confidence=classification.confidence,
        )
        
        # If it's a system command, don't capture as thought
        if classification.is_command:
            trace.log_stage("route", output_data={"action": "command_passthrough"})
            return CaptureResult(
                thought_id=0,
                kind=classification.kind,
                confidence=classification.confidence,
                response="",  # Let the normal command handler respond
                is_command=True,
            )
        
        # Create thought record
        ambiguity_str = classification.ambiguity_reason.value if classification.ambiguity_reason else None
        thought = create_thought(
            raw_text=text,
            source=source,
            kind=classification.kind.value,
            ambiguity_reason=ambiguity_str,
            confidence=classification.confidence,
            voice_journal_id=voice_journal_id,
        )
        trace.set_thought_id(thought.id)
        trace.log_stage("thought_created", output_data={"thought_id": thought.id})
        
        # Route based on classification
        if classification.kind == ThoughtKind.ACTIONABLE:
            trace.log_stage("route", output_data={"action": "actionable"})
            result = _handle_actionable(thought, classification, source)
            if result.task:
                trace.set_task_id(result.task.id)
            trace.complete(thought_id=thought.id, task_id=result.task.id if result.task else None)
            return result
        
        elif classification.kind == ThoughtKind.NOTE:
            trace.log_stage("route", output_data={"action": "note"})
            result = _handle_note(thought, classification)
            trace.complete(thought_id=thought.id)
            return result
        
        else:  # AMBIGUOUS
            trace.log_stage("route", output_data={
                "action": "ambiguous",
                "reason": ambiguity_str,
            })
            result = _handle_ambiguous(thought, classification)
            trace.complete(thought_id=thought.id)
            return result


def _handle_actionable(
    thought: Thought,
    classification: ClassificationResult,
    source: str,
) -> CaptureResult:
    """Handle actionable thought - create task."""
    parsed = classification.parsed_task
    
    if not parsed or not parsed.name:
        # Parsing failed, mark as ambiguous
        update_thought(thought.id, kind="ambiguous")
        return CaptureResult(
            thought_id=thought.id,
            kind=ThoughtKind.AMBIGUOUS,
            confidence=classification.confidence,
            response="I couldn't parse that clearly. I'll ask about it later.",
        )
    
    # Create the task
    project_id = None
    if parsed.project_name:
        project = project_service.get_project_by_name(parsed.project_name)
        if project:
            project_id = project.id
    
    task = task_service.create_task(
        name=parsed.name,
        project_id=project_id,
        due_date=parsed.due_date,
        due_time=parsed.due_time,
        importance=parsed.importance,
        tags=parsed.tags,
        recurrence_rule=parsed.recurrence_rule,
    )
    
    # Link thought to task
    update_thought(thought.id, status="processed", linked_task_id=task.id)
    
    # Set last entity for * correction
    session = get_session()
    session.set_last_entity("task", task.id)
    
    # Build response
    confirmation = format_task_confirmation(parsed)
    
    # Add correction hint for medium confidence
    needs_confirmation = classification.confidence < HIGH_CONFIDENCE
    if needs_confirmation:
        confirmation += "\n_Reply `*` to amend_"
    
    return CaptureResult(
        thought_id=thought.id,
        kind=ThoughtKind.ACTIONABLE,
        confidence=classification.confidence,
        response=confirmation,
        task=task,
        needs_confirmation=needs_confirmation,
    )


def _handle_note(thought: Thought, classification: ClassificationResult) -> CaptureResult:
    """Handle note thought - store without creating task."""
    update_thought(thought.id, status="processed")
    
    return CaptureResult(
        thought_id=thought.id,
        kind=ThoughtKind.NOTE,
        confidence=classification.confidence,
        response="📝 Noted.",
    )


def _handle_ambiguous(thought: Thought, classification: ClassificationResult) -> CaptureResult:
    """Handle ambiguous thought - queue for Butler clarification."""
    # Thought stays pending for Butler to pick up
    
    # Generate context-aware response
    if classification.ambiguity_reason == AmbiguityReason.SCOPE:
        hint = "project or task"
    elif classification.ambiguity_reason == AmbiguityReason.TIMING:
        hint = "timing"
    elif classification.ambiguity_reason == AmbiguityReason.INTENT:
        hint = "what you'd like me to do"
    else:
        hint = "more details"
    
    return CaptureResult(
        thought_id=thought.id,
        kind=ThoughtKind.AMBIGUOUS,
        confidence=classification.confidence,
        response=f"📥 Got it. I'll ask about {hint} later.",
    )


def process_voice_transcription(
    transcription: str,
    voice_journal_id: int,
) -> CaptureResult:
    """
    Process a completed voice transcription.
    
    Called by the slow mode loop after Whisper transcription completes.
    
    Args:
        transcription: The transcribed text
        voice_journal_id: The voice journal ID
    
    Returns:
        CaptureResult (same as process_input)
    """
    return process_input(
        text=transcription,
        source="voice",
        voice_journal_id=voice_journal_id,
    )


def get_pending_voice_confirmations(limit: int = 5) -> list[CaptureResult]:
    """
    Get recent voice-originated tasks that may need user confirmation.
    
    Used to show "Voice memo processed" confirmations when user next interacts.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.*, th.confidence
            FROM thoughts th
            JOIN tasks t ON t.id = th.linked_task_id
            WHERE th.source = 'voice' 
              AND th.status = 'processed'
              AND th.processed_at > datetime('now', '-1 hour')
            ORDER BY th.processed_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    
    results = []
    for row in rows:
        task = Task.from_row(row)
        confidence = row["confidence"] if "confidence" in row.keys() else 0.8
        results.append(CaptureResult(
            thought_id=0,  # Not tracked here
            kind=ThoughtKind.ACTIONABLE,
            confidence=confidence,
            response=f"🎤 Voice memo → \"{task.name}\"",
            task=task,
            needs_confirmation=confidence < HIGH_CONFIDENCE,
        ))
    
    return results
