"""
Execution Logger for Noctem v0.6.1.

Provides detailed tracing of the full thought pipeline:
input → classify → route → execute → complete

Each trace is identified by a UUID and can span multiple stages.
"""
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
from typing import Optional, List, Any

from ..db import get_db
from ..models import ExecutionLog

logger = logging.getLogger(__name__)


class ExecutionLogger:
    """
    Context manager for logging execution traces.
    
    Usage:
        with ExecutionLogger(component="fast", source="cli") as trace:
            trace.log_stage("input", input_data={"text": "buy milk"})
            result = classify(text)
            trace.log_stage("classify", output_data={"kind": "actionable"}, confidence=0.9)
            # ... more stages ...
            trace.complete(thought_id=123, task_id=456)
    """
    
    def __init__(self, component: str = "fast", source: str = "cli", 
                 trace_id: Optional[str] = None):
        """
        Initialize an execution trace.
        
        Args:
            component: Which system component ('fast', 'slow', 'butler', 'summon')
            source: Input source ('cli', 'telegram', 'web', 'voice')
            trace_id: Optional existing trace ID to continue (for linked operations)
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.component = component
        self.source = source
        self.stages: List[dict] = []
        self._start_time: Optional[float] = None
        self._stage_start: Optional[float] = None
        self._thought_id: Optional[int] = None
        self._task_id: Optional[int] = None
        self._completed = False
    
    def __enter__(self):
        self._start_time = perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Log error if exception occurred
            self.log_error(str(exc_val), stage="error")
        elif not self._completed:
            # Auto-complete if not explicitly completed
            self.complete()
        return False  # Don't suppress exceptions
    
    def log_stage(self, stage: str, input_data: dict = None, output_data: dict = None,
                  confidence: float = None, model_used: str = None, 
                  metadata: dict = None) -> int:
        """
        Log a pipeline stage.
        
        Args:
            stage: Stage name ('input', 'classify', 'route', 'execute', 'complete')
            input_data: Input to this stage (JSON-serializable dict)
            output_data: Output from this stage (JSON-serializable dict)
            confidence: Confidence score if applicable (0.0-1.0)
            model_used: Model name if LLM was used
            metadata: Additional context
            
        Returns:
            The log entry ID
        """
        now = perf_counter()
        duration_ms = None
        if self._stage_start is not None:
            duration_ms = int((now - self._stage_start) * 1000)
        self._stage_start = now
        
        # Store locally
        self.stages.append({
            "stage": stage,
            "input_data": input_data,
            "output_data": output_data,
            "confidence": confidence,
            "model_used": model_used,
            "metadata": metadata,
            "duration_ms": duration_ms,
        })
        
        # Persist to database
        return self._save_entry(
            stage=stage,
            input_data=input_data,
            output_data=output_data,
            confidence=confidence,
            duration_ms=duration_ms,
            model_used=model_used,
            metadata=metadata,
        )
    
    def log_error(self, error: str, stage: str = "error") -> int:
        """Log an error during execution."""
        return self._save_entry(
            stage=stage,
            error=error,
        )
    
    def set_thought_id(self, thought_id: int):
        """Link this trace to a thought."""
        self._thought_id = thought_id
    
    def set_task_id(self, task_id: int):
        """Link this trace to a task."""
        self._task_id = task_id
    
    def complete(self, thought_id: int = None, task_id: int = None,
                 output_data: dict = None):
        """
        Mark the trace as complete.
        
        Args:
            thought_id: Final thought ID if created
            task_id: Final task ID if created
            output_data: Final output summary
        """
        if thought_id:
            self._thought_id = thought_id
        if task_id:
            self._task_id = task_id
        
        total_duration_ms = None
        if self._start_time:
            total_duration_ms = int((perf_counter() - self._start_time) * 1000)
        
        self._save_entry(
            stage="complete",
            output_data=output_data or {},
            duration_ms=total_duration_ms,
        )
        self._completed = True
        
        logger.debug(f"Trace {self.trace_id[:8]} complete: {len(self.stages)} stages, "
                     f"{total_duration_ms}ms, thought={self._thought_id}, task={self._task_id}")
    
    def _save_entry(self, stage: str, input_data: dict = None, output_data: dict = None,
                    confidence: float = None, duration_ms: int = None,
                    model_used: str = None, error: str = None,
                    metadata: dict = None) -> int:
        """Save a log entry to the database."""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO execution_logs 
                    (trace_id, stage, component, input_data, output_data, confidence,
                     duration_ms, model_used, thought_id, task_id, error, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.trace_id,
                    stage,
                    self.component,
                    json.dumps(input_data) if input_data else None,
                    json.dumps(output_data) if output_data else None,
                    confidence,
                    duration_ms,
                    model_used,
                    self._thought_id,
                    self._task_id,
                    error,
                    json.dumps(metadata) if metadata else None,
                ))
                return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to save execution log: {e}")
            return 0


def get_trace(trace_id: str) -> List[ExecutionLog]:
    """
    Retrieve all log entries for a trace.
    
    Args:
        trace_id: The trace UUID
        
    Returns:
        List of ExecutionLog entries in order
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM execution_logs
            WHERE trace_id = ?
            ORDER BY timestamp ASC, id ASC
        """, (trace_id,)).fetchall()
        return [ExecutionLog.from_row(row) for row in rows]


def get_recent_traces(limit: int = 20, component: str = None) -> List[dict]:
    """
    Get recent unique traces with summary info.
    
    Args:
        limit: Maximum number of traces to return
        component: Filter by component (optional)
        
    Returns:
        List of trace summaries with trace_id, component, stage_count, etc.
    """
    query = """
        SELECT 
            trace_id,
            component,
            MIN(timestamp) as started_at,
            MAX(timestamp) as completed_at,
            COUNT(*) as stage_count,
            MAX(thought_id) as thought_id,
            MAX(task_id) as task_id,
            MAX(CASE WHEN error IS NOT NULL THEN error END) as error
        FROM execution_logs
    """
    params = []
    
    if component:
        query += " WHERE component = ?"
        params.append(component)
    
    query += """
        GROUP BY trace_id
        ORDER BY started_at DESC
        LIMIT ?
    """
    params.append(limit)
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_traces_for_thought(thought_id: int) -> List[str]:
    """Get all trace IDs associated with a thought."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT trace_id FROM execution_logs
            WHERE thought_id = ?
            ORDER BY timestamp DESC
        """, (thought_id,)).fetchall()
        return [row["trace_id"] for row in rows]


def get_traces_for_task(task_id: int) -> List[str]:
    """Get all trace IDs associated with a task."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT trace_id FROM execution_logs
            WHERE task_id = ?
            ORDER BY timestamp DESC
        """, (task_id,)).fetchall()
        return [row["trace_id"] for row in rows]


def get_execution_stats(hours: int = 24) -> dict:
    """
    Get execution statistics for the specified time period.
    
    Returns:
        Dict with counts, average durations, error rates, etc.
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 
                COUNT(DISTINCT trace_id) as trace_count,
                COUNT(*) as log_count,
                AVG(duration_ms) as avg_duration_ms,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count,
                AVG(confidence) as avg_confidence
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
        """, (-hours,)).fetchone()
        
        return {
            "trace_count": row["trace_count"] or 0,
            "log_count": row["log_count"] or 0,
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
            "error_count": row["error_count"] or 0,
            "avg_confidence": round(row["avg_confidence"] or 0, 3),
            "period_hours": hours,
        }
