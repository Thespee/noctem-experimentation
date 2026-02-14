"""
Slow Work Queue for Noctem v0.6.0.

Manages the queue of work items for slow mode processing.
Supports dependencies between items (e.g., analyze all tasks before project).
"""
import logging
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..db import get_db

logger = logging.getLogger(__name__)


class WorkType(Enum):
    TASK_COMPUTER_HELP = "task_computer_help"
    PROJECT_NEXT_ACTION = "project_next_action"


class WorkStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkItem:
    """A work item in the slow queue."""
    id: int
    work_type: str
    target_id: int
    depends_on_id: Optional[int]
    status: str
    result: Optional[str]
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]


class SlowWorkQueue:
    """
    Manages the slow work queue.
    
    Work items are processed in order, respecting dependencies.
    """
    
    @staticmethod
    def add_item(work_type: str, target_id: int, depends_on_id: int = None) -> int:
        """
        Add a work item to the queue.
        
        Args:
            work_type: Type of work (task_computer_help, project_next_action)
            target_id: ID of the task or project
            depends_on_id: Optional ID of another queue item this depends on
            
        Returns:
            The queue item ID
        """
        with get_db() as conn:
            # Check if already queued
            existing = conn.execute("""
                SELECT id FROM slow_work_queue
                WHERE work_type = ? AND target_id = ? AND status IN ('pending', 'processing')
            """, (work_type, target_id)).fetchone()
            
            if existing:
                return existing["id"]
            
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, depends_on_id, status)
                VALUES (?, ?, ?, 'pending')
            """, (work_type, target_id, depends_on_id))
            item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        logger.debug(f"Queued {work_type} for target {target_id} (id={item_id})")
        return item_id
    
    @staticmethod
    def get_next_item() -> Optional[WorkItem]:
        """
        Get the next item to process.
        
        Returns items that:
        - Are pending
        - Have no unfinished dependencies
        - Ordered by queue time
        """
        with get_db() as conn:
            row = conn.execute("""
                SELECT q.*
                FROM slow_work_queue q
                WHERE q.status = 'pending'
                  AND (q.depends_on_id IS NULL 
                       OR EXISTS (
                           SELECT 1 FROM slow_work_queue dep 
                           WHERE dep.id = q.depends_on_id 
                           AND dep.status = 'completed'
                       ))
                ORDER BY q.queued_at ASC
                LIMIT 1
            """).fetchone()
            
            if row:
                return WorkItem(
                    id=row["id"],
                    work_type=row["work_type"],
                    target_id=row["target_id"],
                    depends_on_id=row["depends_on_id"],
                    status=row["status"],
                    result=row["result"],
                    queued_at=row["queued_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    error_message=row["error_message"],
                )
            return None
    
    @staticmethod
    def mark_processing(item_id: int):
        """Mark an item as being processed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE slow_work_queue
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item_id,))
    
    @staticmethod
    def mark_completed(item_id: int, result: str = None):
        """Mark an item as completed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE slow_work_queue
                SET status = 'completed', 
                    completed_at = CURRENT_TIMESTAMP,
                    result = ?
                WHERE id = ?
            """, (result, item_id))
        
        logger.debug(f"Completed queue item {item_id}")
    
    @staticmethod
    def mark_failed(item_id: int, error: str):
        """Mark an item as failed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE slow_work_queue
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
            """, (error, item_id))
        
        logger.warning(f"Failed queue item {item_id}: {error}")
    
    @staticmethod
    def get_pending_count() -> int:
        """Get count of pending items."""
        with get_db() as conn:
            return conn.execute("""
                SELECT COUNT(*) FROM slow_work_queue WHERE status = 'pending'
            """).fetchone()[0]
    
    @staticmethod
    def get_pending_items(limit: int = 10) -> list:
        """Get pending items for display."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT id, work_type, target_id, depends_on_id, status, queued_at
                FROM slow_work_queue
                WHERE status = 'pending'
                ORDER BY queued_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            return [
                {
                    'id': r['id'],
                    'work_type': r['work_type'],
                    'entity_type': 'task' if 'task' in r['work_type'] else 'project',
                    'entity_id': r['target_id'],
                    'queued_at': r['queued_at'],
                }
                for r in rows
            ]
    
    @staticmethod
    def get_queue_status() -> dict:
        """Get queue status summary."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM slow_work_queue
                GROUP BY status
            """).fetchall()
            
            status = {r["status"]: r["count"] for r in rows}
            return {
                "pending": status.get("pending", 0),
                "processing": status.get("processing", 0),
                "completed": status.get("completed", 0),
                "failed": status.get("failed", 0),
            }
    
    @staticmethod
    def clear_completed(older_than_days: int = 7):
        """Remove completed items older than N days."""
        with get_db() as conn:
            conn.execute("""
                DELETE FROM slow_work_queue
                WHERE status = 'completed'
                  AND completed_at < datetime('now', ? || ' days')
            """, (f"-{older_than_days}",))
    
    @staticmethod
    def retry_failed():
        """Reset failed items to pending for retry."""
        with get_db() as conn:
            conn.execute("""
                UPDATE slow_work_queue
                SET status = 'pending',
                    started_at = NULL,
                    completed_at = NULL,
                    error_message = NULL
                WHERE status = 'failed'
            """)
    
    @staticmethod
    def queue_task_analysis(task_id: int) -> int:
        """Convenience method to queue task analysis."""
        return SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task_id)
    
    @staticmethod
    def queue_project_analysis(project_id: int, after_task_items: List[int] = None) -> int:
        """
        Queue project analysis, optionally depending on task analyses.
        
        If after_task_items is provided, project analysis will wait for those items.
        Otherwise, it's queued immediately.
        """
        depends_on = after_task_items[-1] if after_task_items else None
        return SlowWorkQueue.add_item(
            WorkType.PROJECT_NEXT_ACTION.value, 
            project_id, 
            depends_on
        )
