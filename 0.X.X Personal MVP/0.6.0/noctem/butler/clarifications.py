"""
Butler Clarifications - Question queue for Noctem v0.6.0.

When slow mode identifies unclear items, it queues clarification questions.
These are sent during clarification contacts (default: Tue/Thu at 9am).
Maximum 2 clarification contacts per week.

v0.6.0 Polish: Now includes ambiguous thoughts from the capture system.
"""
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
import json
import logging

from ..db import get_db
from ..models import Thought

logger = logging.getLogger(__name__)


# Subcategory-specific clarification questions
AMBIGUITY_QUESTIONS = {
    "scope": {
        "question": "Is this a new project or a single task?",
        "options": ["Project", "Task", "Skip for now"],
    },
    "timing": {
        "question": "When should this be done?",
        "options": ["Today", "Tomorrow", "This week", "No deadline"],
    },
    "intent": {
        "question": "What should I do with this?",
        "options": ["Create task", "Just remember it", "Remind me later", "Ignore"],
    },
    None: {
        "question": "Could you tell me more about this?",
        "options": ["It's a task", "It's a note", "Skip for now"],
    },
}


@dataclass
class ClarificationQuestion:
    """A clarification question to ask the user."""
    id: int
    task_id: int
    task_name: str
    question: str
    options: List[str]
    priority: int
    created_at: datetime
    asked_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    answer: Optional[str] = None


# Add clarification_queue table if not exists
CLARIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS clarification_queue (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    options TEXT,  -- JSON array of suggested answers
    priority INTEGER DEFAULT 0,  -- Higher = more important
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    asked_at TIMESTAMP,  -- When we asked the user
    answered_at TIMESTAMP,
    answer TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_clarification_pending 
    ON clarification_queue(answered_at, priority DESC);
"""


def ensure_clarification_table():
    """Ensure the clarification_queue table exists."""
    with get_db() as conn:
        conn.executescript(CLARIFICATION_SCHEMA)


class ClarificationQueue:
    """
    Manages clarification questions for unclear tasks.
    
    Questions are added by slow mode analysis, then sent during
    clarification contacts (limited to 2 per week).
    """
    
    @staticmethod
    def add_question(task_id: int, question: str, options: List[str] = None, priority: int = 0) -> int:
        """
        Queue a clarification question.
        
        Args:
            task_id: The task this question is about
            question: The question to ask
            options: Optional list of suggested answers
            priority: Higher priority = asked first
            
        Returns:
            The question ID
        """
        ensure_clarification_table()
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO clarification_queue (task_id, question, options, priority)
                VALUES (?, ?, ?, ?)
            """, (task_id, question, json.dumps(options or []), priority))
            question_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        logger.info(f"Added clarification question {question_id} for task {task_id}")
        return question_id
    
    @staticmethod
    def get_pending_questions(limit: int = 10) -> List[ClarificationQuestion]:
        """Get pending questions ordered by priority."""
        ensure_clarification_table()
        
        with get_db() as conn:
            rows = conn.execute("""
                SELECT cq.id, cq.task_id, t.name as task_name, 
                       cq.question, cq.options, cq.priority, cq.created_at
                FROM clarification_queue cq
                JOIN tasks t ON t.id = cq.task_id
                WHERE cq.answered_at IS NULL
                ORDER BY cq.priority DESC, cq.created_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            
            questions = []
            for row in rows:
                questions.append(ClarificationQuestion(
                    id=row["id"],
                    task_id=row["task_id"],
                    task_name=row["task_name"],
                    question=row["question"],
                    options=json.loads(row["options"]) if row["options"] else [],
                    priority=row["priority"],
                    created_at=row["created_at"],
                ))
            return questions
    
    @staticmethod
    def get_next_questions(limit: int = 3) -> List[ClarificationQuestion]:
        """Get highest priority questions for next clarification contact."""
        return ClarificationQueue.get_pending_questions(limit)
    
    @staticmethod
    def mark_asked(question_ids: List[int]):
        """Mark questions as having been asked."""
        ensure_clarification_table()
        
        with get_db() as conn:
            for qid in question_ids:
                conn.execute("""
                    UPDATE clarification_queue
                    SET asked_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (qid,))
    
    @staticmethod
    def mark_answered(question_id: int, answer: str):
        """Record the user's answer to a question."""
        ensure_clarification_table()
        
        with get_db() as conn:
            conn.execute("""
                UPDATE clarification_queue
                SET answered_at = CURRENT_TIMESTAMP, answer = ?
                WHERE id = ?
            """, (answer, question_id))
        
        logger.info(f"Recorded answer for question {question_id}")
    
    @staticmethod
    def get_pending_count() -> int:
        """Count pending questions."""
        ensure_clarification_table()
        
        with get_db() as conn:
            count = conn.execute("""
                SELECT COUNT(*) FROM clarification_queue
                WHERE answered_at IS NULL
            """).fetchone()[0]
            return count
    
    @staticmethod
    def has_pending_questions() -> bool:
        """Check if there are any pending questions."""
        return ClarificationQueue.get_pending_count() > 0
    
    @staticmethod
    def delete_question(question_id: int):
        """Delete a question (e.g., if task was deleted)."""
        ensure_clarification_table()
        
        with get_db() as conn:
            conn.execute("DELETE FROM clarification_queue WHERE id = ?", (question_id,))
    
    @staticmethod
    def delete_questions_for_task(task_id: int):
        """Delete all questions for a task."""
        ensure_clarification_table()
        
        with get_db() as conn:
            conn.execute("DELETE FROM clarification_queue WHERE task_id = ?", (task_id,))


def get_pending_thoughts_for_clarification(limit: int = 3) -> List[Thought]:
    """
    Get pending ambiguous thoughts for clarification.
    Returns oldest first.
    """
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


def generate_thought_clarification_question(thought: Thought) -> dict:
    """
    Generate a clarification question for an ambiguous thought.
    Returns dict with question text and options.
    """
    template = AMBIGUITY_QUESTIONS.get(
        thought.ambiguity_reason,
        AMBIGUITY_QUESTIONS[None]
    )
    
    return {
        "thought_id": thought.id,
        "text_preview": thought.raw_text[:50] + ("..." if len(thought.raw_text) > 50 else ""),
        "question": template["question"],
        "options": template["options"],
        "ambiguity_reason": thought.ambiguity_reason,
    }


def generate_clarification_message() -> Optional[str]:
    """
    Generate a clarification message with pending questions.
    Includes both task-based questions and ambiguous thoughts.
    
    Returns None if nothing pending.
    """
    # Get task-based questions
    task_questions = ClarificationQueue.get_next_questions(2)
    
    # Get ambiguous thoughts
    thoughts = get_pending_thoughts_for_clarification(2)
    
    if not task_questions and not thoughts:
        return None
    
    lines = [
        "❓ **Quick Questions**",
        "",
        "_A few things I'd like to clarify:_",
        "",
    ]
    
    item_num = 1
    asked_question_ids = []
    thought_items = []  # Track which items are thoughts
    
    # Add task-based questions
    for q in task_questions:
        lines.append(f"**{item_num}. {q.task_name}**")
        lines.append(f"   {q.question}")
        
        if q.options:
            options_str = " / ".join(q.options[:4])
            lines.append(f"   _Options: {options_str}_")
        lines.append("")
        asked_question_ids.append(q.id)
        item_num += 1
    
    # Add ambiguous thoughts
    for thought in thoughts:
        clarification = generate_thought_clarification_question(thought)
        lines.append(f"**{item_num}. \"{clarification['text_preview']}\"**")
        lines.append(f"   {clarification['question']}")
        options_str = " / ".join(clarification['options'])
        lines.append(f"   _Options: {options_str}_")
        lines.append("")
        thought_items.append((item_num, thought.id))
        item_num += 1
    
    lines.append("_Reply with the number and your answer (e.g., \"1: tomorrow\" or \"3: task\")_")
    
    # Mark task questions as asked
    if asked_question_ids:
        ClarificationQueue.mark_asked(asked_question_ids)
    
    return "\n".join(lines)


def parse_clarification_response(text: str) -> Optional[tuple]:
    """
    Parse a clarification response like "1: tomorrow" or "2 call her at noon".
    
    Returns (question_number, answer) or None if not a clarification response.
    """
    text = text.strip()
    
    # Try formats: "1: answer", "1 - answer", "1. answer", "1 answer"
    import re
    match = re.match(r'^(\d+)\s*[:\-\.]\s*(.+)$', text)
    if match:
        return int(match.group(1)), match.group(2).strip()
    
    # Try just "1 answer" (number followed by text)
    match = re.match(r'^(\d+)\s+(.+)$', text)
    if match:
        return int(match.group(1)), match.group(2).strip()
    
    return None


def resolve_thought_clarification(
    thought_id: int,
    resolution: str,
) -> Optional[dict]:
    """
    Resolve an ambiguous thought based on user's clarification response.
    
    Args:
        thought_id: The thought to resolve
        resolution: User's answer (e.g., "task", "project", "today")
    
    Returns:
        Dict with result info or None if thought not found
    """
    from ..fast.capture import get_thought, update_thought
    from ..services import task_service, project_service
    from ..parser.task_parser import parse_task
    
    thought = get_thought(thought_id)
    if not thought:
        return None
    
    resolution_lower = resolution.lower().strip()
    result = {"thought_id": thought_id, "action": None}
    
    # Handle different resolution types
    if resolution_lower in ("task", "create task", "it's a task"):
        # Create a task from the thought
        parsed = parse_task(thought.raw_text)
        if parsed.name:
            task = task_service.create_task(
                name=parsed.name,
                due_date=parsed.due_date,
                due_time=parsed.due_time,
                importance=parsed.importance,
                tags=parsed.tags,
            )
            update_thought(thought_id, status="clarified", linked_task_id=task.id)
            result["action"] = "task_created"
            result["task_id"] = task.id
            result["task_name"] = task.name
        else:
            result["action"] = "parse_failed"
    
    elif resolution_lower in ("project", "new project"):
        # Create a project from the thought
        # Use the raw text as project name (first 50 chars)
        name = thought.raw_text[:50].strip()
        if name:
            project = project_service.create_project(name)
            update_thought(thought_id, status="clarified", linked_project_id=project.id)
            result["action"] = "project_created"
            result["project_id"] = project.id
            result["project_name"] = project.name
        else:
            result["action"] = "name_too_short"
    
    elif resolution_lower in ("note", "just remember it", "it's a note"):
        # Keep as a note (processed but not linked)
        update_thought(thought_id, status="clarified", kind="note")
        result["action"] = "kept_as_note"
    
    elif resolution_lower in ("skip", "skip for now", "ignore"):
        # Skip this thought for now
        update_thought(thought_id, status="clarified")
        result["action"] = "skipped"
    
    elif resolution_lower in ("today", "tomorrow", "this week", "no deadline"):
        # Timing clarification - create task with the specified timing
        from ..parser.natural_date import parse_datetime
        parsed = parse_task(thought.raw_text)
        
        # Parse the timing
        if resolution_lower != "no deadline":
            dt_result = parse_datetime(resolution_lower)
            due_date = dt_result.date
        else:
            due_date = None
        
        if parsed.name:
            task = task_service.create_task(
                name=parsed.name,
                due_date=due_date,
                importance=parsed.importance,
                tags=parsed.tags,
            )
            update_thought(thought_id, status="clarified", linked_task_id=task.id)
            result["action"] = "task_created_with_timing"
            result["task_id"] = task.id
            result["task_name"] = task.name
            result["due_date"] = str(due_date) if due_date else None
        else:
            result["action"] = "parse_failed"
    
    else:
        # Treat as additional context - append to thought and keep pending
        # Or create task with the response as additional info
        parsed = parse_task(f"{thought.raw_text} {resolution}")
        if parsed.name:
            task = task_service.create_task(
                name=parsed.name,
                due_date=parsed.due_date,
                due_time=parsed.due_time,
                importance=parsed.importance,
                tags=parsed.tags,
            )
            update_thought(thought_id, status="clarified", linked_task_id=task.id)
            result["action"] = "task_created_with_context"
            result["task_id"] = task.id
            result["task_name"] = task.name
        else:
            update_thought(thought_id, status="clarified")
            result["action"] = "clarified_generic"
    
    return result


def get_pending_clarification_count() -> dict:
    """
    Get count of items pending clarification.
    """
    task_count = ClarificationQueue.get_pending_count()
    
    with get_db() as conn:
        thought_count = conn.execute(
            """
            SELECT COUNT(*) FROM thoughts
            WHERE kind = 'ambiguous' AND status = 'pending'
            """
        ).fetchone()[0]
    
    return {
        "tasks": task_count,
        "thoughts": thought_count,
        "total": task_count + thought_count,
    }
