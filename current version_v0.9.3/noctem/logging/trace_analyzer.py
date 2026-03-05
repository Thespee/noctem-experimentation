"""
Trace Analyzer for Noctem v0.7.0.

Provides helper functions for querying and analyzing execution logs.
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from ..db import get_db
from ..models import ExecutionLog

logger = logging.getLogger(__name__)


def get_traces_by_thought(thought_id: int) -> List[str]:
    """Get all trace IDs associated with a thought."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT trace_id 
            FROM execution_logs
            WHERE thought_id = ?
            ORDER BY timestamp DESC
        """, (thought_id,)).fetchall()
        return [row["trace_id"] for row in rows]


def get_traces_by_task(task_id: int) -> List[str]:
    """Get all trace IDs associated with a task."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT trace_id 
            FROM execution_logs
            WHERE task_id = ?
            ORDER BY timestamp DESC
        """, (task_id,)).fetchall()
        return [row["trace_id"] for row in rows]


def get_traces_by_project(project_id: int) -> List[str]:
    """Get all trace IDs associated with a project."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT trace_id 
            FROM execution_logs
            WHERE project_id = ?
            ORDER BY timestamp DESC
        """, (project_id,)).fetchall()
        return [row["trace_id"] for row in rows]


def get_trace_summary(trace_id: str) -> Dict:
    """
    Get summary information about a trace.
    
    Returns:
        Dict with trace_id, component, started_at, completed_at, stage_count, 
        thought_id, task_id, project_id, duration_ms, error
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 
                trace_id,
                component,
                MIN(timestamp) as started_at,
                MAX(timestamp) as completed_at,
                COUNT(*) as stage_count,
                MAX(thought_id) as thought_id,
                MAX(task_id) as task_id,
                MAX(project_id) as project_id,
                SUM(duration_ms) as total_duration_ms,
                MAX(CASE WHEN error IS NOT NULL THEN error END) as error
            FROM execution_logs
            WHERE trace_id = ?
            GROUP BY trace_id
        """, (trace_id,)).fetchone()
        
        return dict(row) if row else None


def get_recent_traces(
    limit: int = 20, 
    component: Optional[str] = None,
    with_errors_only: bool = False
) -> List[Dict]:
    """
    Get recent unique traces with summary info.
    
    Args:
        limit: Maximum number of traces to return
        component: Filter by component (optional)
        with_errors_only: Only return traces with errors
        
    Returns:
        List of trace summaries
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
            MAX(project_id) as project_id,
            MAX(CASE WHEN error IS NOT NULL THEN error END) as error
        FROM execution_logs
    """
    params = []
    
    conditions = []
    if component:
        conditions.append("component = ?")
        params.append(component)
    if with_errors_only:
        conditions.append("error IS NOT NULL")
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += """
        GROUP BY trace_id
        ORDER BY started_at DESC
        LIMIT ?
    """
    params.append(limit)
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_execution_stats(hours: int = 24) -> Dict:
    """
    Get execution statistics for the specified time period.
    
    Returns:
        Dict with counts, average durations, error rates, confidence scores, etc.
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 
                COUNT(DISTINCT trace_id) as trace_count,
                COUNT(*) as log_count,
                AVG(duration_ms) as avg_duration_ms,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count,
                AVG(confidence) as avg_confidence,
                COUNT(DISTINCT thought_id) as thought_count,
                COUNT(DISTINCT task_id) as task_count,
                COUNT(DISTINCT project_id) as project_count
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
        """, (-hours,)).fetchone()
        
        return {
            "trace_count": row["trace_count"] or 0,
            "log_count": row["log_count"] or 0,
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
            "error_count": row["error_count"] or 0,
            "error_rate": round((row["error_count"] or 0) / max(row["log_count"] or 1, 1) * 100, 2),
            "avg_confidence": round(row["avg_confidence"] or 0, 3),
            "thought_count": row["thought_count"] or 0,
            "task_count": row["task_count"] or 0,
            "project_count": row["project_count"] or 0,
            "period_hours": hours,
        }


def get_confidence_distribution(hours: int = 24) -> Dict[str, int]:
    """
    Get distribution of confidence scores.
    
    Returns:
        Dict with confidence ranges as keys (e.g., '0.0-0.5') and counts as values
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT confidence
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
              AND confidence IS NOT NULL
        """, (-hours,)).fetchall()
        
        distribution = {
            "0.0-0.3": 0,  # Low confidence
            "0.3-0.5": 0,  # Medium-low
            "0.5-0.7": 0,  # Medium
            "0.7-0.9": 0,  # Medium-high
            "0.9-1.0": 0,  # High confidence
        }
        
        for row in rows:
            confidence = row["confidence"]
            if confidence < 0.3:
                distribution["0.0-0.3"] += 1
            elif confidence < 0.5:
                distribution["0.3-0.5"] += 1
            elif confidence < 0.7:
                distribution["0.5-0.7"] += 1
            elif confidence < 0.9:
                distribution["0.7-0.9"] += 1
            else:
                distribution["0.9-1.0"] += 1
        
        return distribution


def get_model_performance(hours: int = 24) -> Dict[str, Dict]:
    """
    Get performance statistics per model.
    
    Returns:
        Dict with model name as key and stats as value (count, avg_duration, avg_confidence)
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                model_used,
                COUNT(*) as usage_count,
                AVG(duration_ms) as avg_duration_ms,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
              AND model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY usage_count DESC
        """, (-hours,)).fetchall()
        
        return {
            row["model_used"]: {
                "usage_count": row["usage_count"],
                "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                "avg_confidence": round(row["avg_confidence"] or 0, 3),
                "error_count": row["error_count"],
                "error_rate": round((row["error_count"] or 0) / max(row["usage_count"], 1) * 100, 2),
            }
            for row in rows
        }


def get_component_stats(hours: int = 24) -> Dict[str, Dict]:
    """
    Get statistics per component (fast, slow, butler, summon).
    
    Returns:
        Dict with component name as key and stats as value
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                component,
                COUNT(DISTINCT trace_id) as trace_count,
                COUNT(*) as stage_count,
                AVG(duration_ms) as avg_duration_ms,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
            GROUP BY component
            ORDER BY trace_count DESC
        """, (-hours,)).fetchall()
        
        return {
            row["component"]: {
                "trace_count": row["trace_count"],
                "stage_count": row["stage_count"],
                "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                "avg_confidence": round(row["avg_confidence"] or 0, 3),
                "error_count": row["error_count"],
            }
            for row in rows
        }


def get_slowest_traces(limit: int = 10, hours: int = 24) -> List[Dict]:
    """
    Get the slowest traces in the time period.
    
    Returns:
        List of traces with trace_id, component, total_duration_ms, stage_count
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                trace_id,
                component,
                SUM(duration_ms) as total_duration_ms,
                COUNT(*) as stage_count,
                MIN(timestamp) as started_at
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
              AND duration_ms IS NOT NULL
            GROUP BY trace_id
            ORDER BY total_duration_ms DESC
            LIMIT ?
        """, (-hours, limit)).fetchall()
        
        return [dict(row) for row in rows]


def get_error_traces(limit: int = 20, hours: int = 24) -> List[Dict]:
    """
    Get traces that resulted in errors.
    
    Returns:
        List of traces with trace_id, component, error, timestamp
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT
                trace_id,
                component,
                error,
                timestamp
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' hours')
              AND error IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (-hours, limit)).fetchall()
        
        return [dict(row) for row in rows]


def compare_thought_classifications(
    original_confidence_threshold: float = 0.5
) -> Dict[str, int]:
    """
    Compare fast classifier decisions with user corrections (via summon).
    
    Args:
        original_confidence_threshold: Confidence below this is considered "uncertain"
        
    Returns:
        Dict with comparison statistics
    """
    with get_db() as conn:
        # Get thoughts that were corrected via summon
        corrected_thoughts = conn.execute("""
            SELECT t.id, t.confidence, t.kind as original_kind
            FROM thoughts t
            WHERE t.summon_mode = 1
        """).fetchall()
        
        stats = {
            "total_corrections": len(corrected_thoughts),
            "low_confidence_corrected": 0,
            "high_confidence_corrected": 0,
            "avg_confidence_corrected": 0.0,
        }
        
        if corrected_thoughts:
            confidences = [t["confidence"] for t in corrected_thoughts if t["confidence"] is not None]
            if confidences:
                stats["avg_confidence_corrected"] = round(sum(confidences) / len(confidences), 3)
                stats["low_confidence_corrected"] = len([c for c in confidences if c < original_confidence_threshold])
                stats["high_confidence_corrected"] = len([c for c in confidences if c >= original_confidence_threshold])
        
        return stats


def get_clarification_outcomes(days: int = 7) -> Dict:
    """
    Analyze Butler clarification effectiveness.
    
    Returns:
        Dict with clarification statistics (asked, resolved, avg_resolution_time_hours)
    """
    with get_db() as conn:
        # Get ambiguous thoughts that needed clarification
        ambiguous = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'clarified' THEN 1 END) as resolved,
                AVG(
                    CASE 
                        WHEN status = 'clarified' AND processed_at IS NOT NULL 
                        THEN (julianday(processed_at) - julianday(created_at)) * 24 
                    END
                ) as avg_resolution_hours
            FROM thoughts
            WHERE kind = 'ambiguous'
              AND created_at >= datetime('now', ? || ' days')
        """, (-days,)).fetchone()
        
        total = ambiguous["total"] or 0
        resolved = ambiguous["resolved"] or 0
        
        return {
            "clarifications_needed": total,
            "clarifications_resolved": resolved,
            "clarifications_pending": total - resolved,
            "resolution_rate": round((resolved / max(total, 1)) * 100, 2),
            "avg_resolution_hours": round(ambiguous["avg_resolution_hours"] or 0, 2),
        }


def export_traces_to_jsonl(
    output_path: str, 
    hours: Optional[int] = None,
    component: Optional[str] = None
) -> int:
    """
    Export execution traces to JSONL format for audit/replay.
    
    Args:
        output_path: Path to output file
        hours: Only export traces from last N hours (None = all)
        component: Filter by component (None = all)
        
    Returns:
        Number of log entries exported
    """
    import json
    from pathlib import Path
    
    query = "SELECT * FROM execution_logs"
    params = []
    conditions = []
    
    if hours is not None:
        conditions.append("timestamp >= datetime('now', ? || ' hours')")
        params.append(-hours)
    if component:
        conditions.append("component = ?")
        params.append(component)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY timestamp ASC"
    
    count = 0
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            for row in rows:
                log_entry = dict(row)
                f.write(json.dumps(log_entry) + '\n')
                count += 1
    
    logger.info(f"Exported {count} log entries to {output_path}")
    return count
