"""
Butler Clarifications - Question queue for Noctem v0.6.0.

When slow mode identifies unclear items, it queues clarification questions.
These are sent during clarification contacts (default: Tue/Thu at 9am).
Maximum 2 clarification contacts per week.
"""
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
import json
import logging

from ..db import get_db

logger = logging.getLogger(__name__)


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


def generate_clarification_message() -> Optional[str]:
    """
    Generate a clarification message with pending questions.
    
    Returns None if no questions pending.
    """
    questions = ClarificationQueue.get_next_questions(3)
    
    if not questions:
        return None
    
    lines = [
        "❓ **Quick Questions**",
        "",
        "_A few things I'd like to clarify:_",
        "",
    ]
    
    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}. {q.task_name}**")
        lines.append(f"   {q.question}")
        
        if q.options:
            options_str = " / ".join(q.options[:4])
            lines.append(f"   _Options: {options_str}_")
        lines.append("")
    
    lines.append("_Reply with the number and your answer (e.g., \"1: tomorrow\")_")
    
    # Mark these as asked
    ClarificationQueue.mark_asked([q.id for q in questions])
    
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
