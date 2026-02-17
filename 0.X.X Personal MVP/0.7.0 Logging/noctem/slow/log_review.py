"""
Log Review Skill for Noctem v0.7.0.

Periodically analyzes execution logs, identifies patterns, and promotes them to insights.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

from ..db import get_db
from ..logging import trace_analyzer
from .pattern_detection import (
    run_all_pattern_detection,
    get_promotable_patterns,
    mark_pattern_promoted
)
from .improvement_engine import generate_insight_from_pattern

logger = logging.getLogger(__name__)


def run_log_review(days: int = 30) -> Dict:
    """
    Main log review function - runs all pattern detection and promotes to insights.
    
    Args:
        days: How many days of history to analyze
        
    Returns:
        Dict with review summary
    """
    logger.info(f"Starting log review for last {days} days...")
    
    # Get execution stats for context
    stats = trace_analyzer.get_execution_stats(hours=days * 24)
    logger.info(f"Execution stats: {stats['trace_count']} traces, {stats['error_count']} errors")
    
    # Run pattern detection
    patterns_found = run_all_pattern_detection(days=days)
    
    # Count total patterns detected
    total_patterns = sum(len(p) for p in patterns_found.values())
    logger.info(f"Detected {total_patterns} patterns across all types")
    
    # Get patterns ready for promotion to insights
    promotable = get_promotable_patterns(limit=10)
    logger.info(f"{len(promotable)} patterns meet promotion criteria")
    
    # Promote top patterns to insights
    insights_created = []
    for pattern in promotable[:3]:  # Max 3 insights per review to avoid overwhelming user
        try:
            insight = generate_insight_from_pattern(pattern)
            if insight:
                insights_created.append(insight)
                mark_pattern_promoted(pattern.id)
                logger.info(f"Created insight from pattern: {pattern.pattern_key}")
        except Exception as e:
            logger.error(f"Failed to generate insight from pattern {pattern.id}: {e}")
    
    # Get clarification outcomes
    clarification_stats = trace_analyzer.get_clarification_outcomes(days=min(days, 7))
    
    # Get confidence distribution
    confidence_dist = trace_analyzer.get_confidence_distribution(hours=days * 24)
    
    summary = {
        "review_date": datetime.now().isoformat(),
        "days_analyzed": days,
        "execution_stats": stats,
        "patterns_detected": {
            "total": total_patterns,
            "by_type": {k: len(v) for k, v in patterns_found.items()},
        },
        "patterns_promoted": len(insights_created),
        "insights_created": [i.id for i in insights_created],
        "clarification_effectiveness": clarification_stats,
        "confidence_distribution": confidence_dist,
    }
    
    logger.info(f"Log review complete: {len(insights_created)} insights created")
    return summary


def get_log_review_recommendations() -> List[str]:
    """
    Get high-level recommendations based on recent patterns.
    
    Returns:
        List of recommendation strings
    """
    recommendations = []
    
    # Check execution stats
    stats = trace_analyzer.get_execution_stats(hours=24)
    
    if stats["error_rate"] > 5.0:
        recommendations.append(
            f"⚠️ Error rate is {stats['error_rate']:.1f}% (last 24h). Review error traces and consider stability improvements."
        )
    
    if stats["avg_confidence"] < 0.6:
        recommendations.append(
            f"📉 Average confidence is {stats['avg_confidence']:.2f}. System may need better training data or rule adjustments."
        )
    
    # Check for unresolved clarifications
    clarification_stats = trace_analyzer.get_clarification_outcomes(days=7)
    if clarification_stats["clarifications_pending"] > 10:
        recommendations.append(
            f"❓ {clarification_stats['clarifications_pending']} clarifications pending. "
            f"Resolution rate: {clarification_stats['resolution_rate']:.1f}%. Consider improving question quality."
        )
    
    # Check for promotable patterns
    promotable_count = len(get_promotable_patterns(limit=100))
    if promotable_count > 5:
        recommendations.append(
            f"💡 {promotable_count} patterns ready for promotion. Run log review to generate insights."
        )
    
    if not recommendations:
        recommendations.append("✅ System is running smoothly. No urgent issues detected.")
    
    return recommendations


def should_run_log_review() -> bool:
    """
    Determine if it's time to run a log review.
    
    Criteria:
    - At least 7 days since last review
    - OR at least 50 new thoughts since last review
    - OR at least 10 promotable patterns exist
    
    Returns:
        True if log review should run
    """
    with get_db() as conn:
        # Check when last review ran (look for insights from log_review source)
        last_review = conn.execute("""
            SELECT MAX(created_at) as last_review_date
            FROM maintenance_insights
            WHERE source = 'log_review'
        """).fetchone()
        
        if last_review and last_review["last_review_date"]:
            # Check if 7+ days since last review
            days_since = conn.execute("""
                SELECT (julianday('now') - julianday(?)) as days_diff
            """, (last_review["last_review_date"],)).fetchone()["days_diff"]
            
            if days_since >= 7:
                logger.info(f"Log review needed: {days_since:.1f} days since last review")
                return True
        else:
            # Never run before - should run
            logger.info("Log review needed: never run before")
            return True
        
        # Check thought count since last review
        thought_count = conn.execute("""
            SELECT COUNT(*) as count
            FROM thoughts
            WHERE created_at > COALESCE(?, '1970-01-01')
        """, (last_review["last_review_date"] if last_review else None,)).fetchone()["count"]
        
        if thought_count >= 50:
            logger.info(f"Log review needed: {thought_count} new thoughts since last review")
            return True
        
        # Check promotable patterns
        promotable_count = len(get_promotable_patterns(limit=100))
        if promotable_count >= 10:
            logger.info(f"Log review needed: {promotable_count} patterns ready for promotion")
            return True
    
    logger.debug("Log review not needed yet")
    return False


def get_log_review_status() -> Dict:
    """
    Get current status of log review system.
    
    Returns:
        Dict with status information
    """
    with get_db() as conn:
        # Last review date
        last_review = conn.execute("""
            SELECT MAX(created_at) as last_review_date
            FROM maintenance_insights
            WHERE source = 'log_review'
        """).fetchone()
        
        last_review_date = last_review["last_review_date"] if last_review else None
        
        # Pending insights count
        pending_insights = conn.execute("""
            SELECT COUNT(*) as count
            FROM maintenance_insights
            WHERE source = 'log_review' AND status = 'pending'
        """).fetchone()["count"]
        
        # Promotable patterns count
        promotable_count = len(get_promotable_patterns(limit=100))
        
        # Total patterns detected
        total_patterns = conn.execute("""
            SELECT COUNT(*) as count
            FROM detected_patterns
        """).fetchone()["count"]
    
    return {
        "last_review_date": last_review_date,
        "pending_insights": pending_insights,
        "promotable_patterns": promotable_count,
        "total_patterns_detected": total_patterns,
        "should_run_now": should_run_log_review(),
    }
