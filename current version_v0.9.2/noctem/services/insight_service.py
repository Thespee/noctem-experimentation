"""
Insight Service for Noctem v0.7.0.

CRUD operations for maintenance insights and learned rules.
"""
import logging
from typing import List, Optional
import json

from ..db import get_db
from ..models import MaintenanceInsight, LearnedRule
from ..slow.improvement_engine import apply_insight, dismiss_insight, get_learned_rules

logger = logging.getLogger(__name__)


def get_pending_insights(limit: int = 10) -> List[MaintenanceInsight]:
    """
    Get pending insights ordered by priority.
    
    Args:
        limit: Maximum number of insights to return
        
    Returns:
        List of MaintenanceInsight objects
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM maintenance_insights
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [MaintenanceInsight.from_row(row) for row in rows]


def get_insight(insight_id: int) -> Optional[MaintenanceInsight]:
    """
    Get a specific insight by ID.
    
    Args:
        insight_id: The insight ID
        
    Returns:
        MaintenanceInsight object or None if not found
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM maintenance_insights WHERE id = ?
        """, (insight_id,)).fetchone()
        return MaintenanceInsight.from_row(row) if row else None


def get_insights_by_source(source: str, limit: int = 20) -> List[MaintenanceInsight]:
    """
    Get insights from a specific source.
    
    Args:
        source: Source name (e.g., 'log_review', 'model_scan')
        limit: Maximum number to return
        
    Returns:
        List of MaintenanceInsight objects
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM maintenance_insights
            WHERE source = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (source, limit)).fetchall()
        return [MaintenanceInsight.from_row(row) for row in rows]


def get_all_insights(status: Optional[str] = None, limit: int = 50) -> List[MaintenanceInsight]:
    """
    Get all insights, optionally filtered by status.
    
    Args:
        status: Filter by status ('pending', 'actioned', 'dismissed')
        limit: Maximum number to return
        
    Returns:
        List of MaintenanceInsight objects
    """
    query = "SELECT * FROM maintenance_insights"
    params = []
    
    if status:
        query += " WHERE status = ?"
        params.append(status)
    
    query += " ORDER BY priority DESC, created_at DESC LIMIT ?"
    params.append(limit)
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [MaintenanceInsight.from_row(row) for row in rows]


def accept_insight(insight_id: int) -> bool:
    """
    Accept an insight (creates learned rule if applicable).
    
    Args:
        insight_id: The insight ID to accept
        
    Returns:
        True if successful
    """
    return apply_insight(insight_id)


def reject_insight(insight_id: int) -> bool:
    """
    Reject/dismiss an insight.
    
    Args:
        insight_id: The insight ID to dismiss
        
    Returns:
        True if successful
    """
    return dismiss_insight(insight_id)


def get_insight_summary() -> dict:
    """
    Get summary statistics for insights.
    
    Returns:
        Dict with counts by status and priority
    """
    with get_db() as conn:
        # Count by status
        status_counts = {}
        rows = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM maintenance_insights
            GROUP BY status
        """).fetchall()
        for row in rows:
            status_counts[row["status"]] = row["count"]
        
        # Count by priority (pending only)
        priority_counts = {}
        rows = conn.execute("""
            SELECT priority, COUNT(*) as count
            FROM maintenance_insights
            WHERE status = 'pending'
            GROUP BY priority
        """).fetchall()
        for row in rows:
            priority_counts[row["priority"]] = row["count"]
        
        # Count by source
        source_counts = {}
        rows = conn.execute("""
            SELECT source, COUNT(*) as count
            FROM maintenance_insights
            GROUP BY source
        """).fetchall()
        for row in rows:
            source_counts[row["source"]] = row["count"]
        
        return {
            "by_status": status_counts,
            "by_priority": priority_counts,
            "by_source": source_counts,
            "total": sum(status_counts.values()),
            "pending": status_counts.get("pending", 0),
        }


# Learned Rules Functions (wrap improvement_engine for convenience)

def list_learned_rules(rule_type: Optional[str] = None, enabled_only: bool = True) -> List[LearnedRule]:
    """
    Get learned rules.
    
    Args:
        rule_type: Filter by type (None = all)
        enabled_only: Only return enabled rules
        
    Returns:
        List of LearnedRule objects
    """
    return get_learned_rules(rule_type=rule_type, enabled_only=enabled_only)


def get_rule(rule_id: int) -> Optional[LearnedRule]:
    """Get a specific learned rule by ID."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM learned_rules WHERE id = ?
        """, (rule_id,)).fetchone()
        return LearnedRule.from_row(row) if row else None


def enable_rule(rule_id: int) -> bool:
    """Enable a learned rule."""
    with get_db() as conn:
        conn.execute("""
            UPDATE learned_rules
            SET enabled = 1
            WHERE id = ?
        """, (rule_id,))
        logger.info(f"Enabled rule {rule_id}")
        return True


def disable_rule(rule_id: int) -> bool:
    """Disable a learned rule."""
    with get_db() as conn:
        conn.execute("""
            UPDATE learned_rules
            SET enabled = 0
            WHERE id = ?
        """, (rule_id,))
        logger.info(f"Disabled rule {rule_id}")
        return True


def delete_rule(rule_id: int) -> bool:
    """Delete a learned rule."""
    with get_db() as conn:
        conn.execute("""
            DELETE FROM learned_rules
            WHERE id = ?
        """, (rule_id,))
        logger.info(f"Deleted rule {rule_id}")
        return True


def get_rule_stats() -> dict:
    """Get statistics about learned rules."""
    with get_db() as conn:
        # Count by type
        type_counts = {}
        rows = conn.execute("""
            SELECT rule_type, COUNT(*) as count
            FROM learned_rules
            WHERE enabled = 1
            GROUP BY rule_type
        """).fetchall()
        for row in rows:
            type_counts[row["rule_type"]] = row["count"]
        
        # Most applied rules
        most_applied = []
        rows = conn.execute("""
            SELECT id, rule_key, rule_type, applied_count
            FROM learned_rules
            WHERE enabled = 1 AND applied_count > 0
            ORDER BY applied_count DESC
            LIMIT 10
        """).fetchall()
        for row in rows:
            most_applied.append({
                "id": row["id"],
                "rule_key": row["rule_key"],
                "rule_type": row["rule_type"],
                "applied_count": row["applied_count"],
            })
        
        # Total counts
        total = conn.execute("SELECT COUNT(*) FROM learned_rules").fetchone()[0]
        enabled = conn.execute("SELECT COUNT(*) FROM learned_rules WHERE enabled = 1").fetchone()[0]
        
        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_type": type_counts,
            "most_applied": most_applied,
        }
