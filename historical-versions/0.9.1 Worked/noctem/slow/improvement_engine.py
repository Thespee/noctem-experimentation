"""
Improvement Engine for Noctem v0.7.0.

Generates actionable insights and recommendations from detected patterns.
"""
import logging
import json
from typing import Optional, Dict, List

from ..db import get_db
from ..models import DetectedPattern, MaintenanceInsight, LearnedRule

logger = logging.getLogger(__name__)


def generate_insight_from_pattern(pattern: DetectedPattern) -> Optional[MaintenanceInsight]:
    """
    Generate a MaintenanceInsight from a DetectedPattern.
    
    Args:
        pattern: The detected pattern
        
    Returns:
        MaintenanceInsight object if successful, None otherwise
    """
    # Extract context
    context = pattern.context if isinstance(pattern.context, dict) else {}
    
    # Generate insight based on pattern type
    insight = None
    
    if pattern.pattern_type == "ambiguities":
        insight = _generate_ambiguity_insight(pattern, context)
    elif pattern.pattern_type == "extraction_failures":
        insight = _generate_extraction_insight(pattern, context)
    elif pattern.pattern_type == "user_corrections":
        insight = _generate_correction_insight(pattern, context)
    elif pattern.pattern_type == "clarifications":
        insight = _generate_clarification_insight(pattern, context)
    elif pattern.pattern_type == "model_performance":
        insight = _generate_model_insight(pattern, context)
    
    if insight:
        # Save to database
        insight_id = _save_insight(insight)
        insight.id = insight_id
        logger.info(f"Generated insight #{insight_id}: {insight.title}")
        return insight
    
    return None


def _generate_ambiguity_insight(pattern: DetectedPattern, context: Dict) -> MaintenanceInsight:
    """Generate insight for recurring ambiguity patterns."""
    phrase = pattern.pattern_key.replace("phrase:", "")
    ambiguity_reason = context.get("ambiguity_reason", "unknown")
    examples = context.get("example_texts", [])
    
    title = f"Phrase \"{phrase}\" often causes {ambiguity_reason} ambiguity"
    
    details = {
        "pattern_id": pattern.id,
        "phrase": phrase,
        "ambiguity_reason": ambiguity_reason,
        "occurrence_count": pattern.occurrence_count,
        "examples": examples[:2],
        "proposed_action": f"flag_ambiguity:{phrase}",
        "recommendation": f"Flag inputs containing \"{phrase}\" for {ambiguity_reason} clarification",
    }
    
    # Higher priority for more frequent patterns
    priority = 3 if pattern.occurrence_count < 10 else 4
    
    return MaintenanceInsight(
        insight_type="pattern",
        source="log_review",
        title=title,
        details=details,
        priority=priority,
        status="pending",
    )


def _generate_extraction_insight(pattern: DetectedPattern, context: Dict) -> MaintenanceInsight:
    """Generate insight for time/date extraction failures."""
    time_word = pattern.pattern_key.replace("time_word:", "")
    examples = context.get("example_texts", [])
    
    title = f"Time word \"{time_word}\" often fails date extraction"
    
    # Suggest default mappings based on common patterns
    suggested_mappings = {
        "soon": "tomorrow 9am",
        "later": "today +4 hours",
        "weekend": "Saturday 9am",
        "tonight": "today 8pm",
        "morning": "tomorrow 9am",
        "afternoon": "tomorrow 2pm",
        "evening": "tomorrow 6pm",
    }
    
    details = {
        "pattern_id": pattern.id,
        "time_word": time_word,
        "occurrence_count": pattern.occurrence_count,
        "examples": examples[:2],
        "suggested_mapping": suggested_mappings.get(time_word, "clarify with user"),
        "proposed_action": f"time_mapping:{time_word}",
        "recommendation": f"Add default time mapping for \"{time_word}\" or ask user for preference",
    }
    
    priority = 4  # Time extraction is high impact
    
    return MaintenanceInsight(
        insight_type="recommendation",
        source="log_review",
        title=title,
        details=details,
        priority=priority,
        status="pending",
    )


def _generate_correction_insight(pattern: DetectedPattern, context: Dict) -> MaintenanceInsight:
    """Generate insight for user correction patterns."""
    correction_type = context.get("correction_type", "unknown")
    details_ctx = context.get("details", {})
    
    title = details_ctx.get("message", f"User corrections detected: {correction_type}")
    
    details = {
        "pattern_id": pattern.id,
        "correction_type": correction_type,
        "occurrence_count": pattern.occurrence_count,
        "recommendation": details_ctx.get("recommendation", "Review classifier rules"),
        "proposed_action": f"review_classifier:{correction_type}",
    }
    
    priority = 5  # User corrections are highest priority
    
    return MaintenanceInsight(
        insight_type="recommendation",
        source="log_review",
        title=title,
        details=details,
        priority=priority,
        status="pending",
    )


def _generate_clarification_insight(pattern: DetectedPattern, context: Dict) -> MaintenanceInsight:
    """Generate insight for clarification effectiveness patterns."""
    details_ctx = context.get("details", {})
    resolution_rate = context.get("resolution_rate", 0.0)
    
    title = details_ctx.get("message", "Clarification pattern detected")
    
    details = {
        "pattern_id": pattern.id,
        "resolution_rate": resolution_rate,
        "occurrence_count": pattern.occurrence_count,
        "recommendation": details_ctx.get("recommendation", "Review clarification approach"),
        "proposed_action": "review_clarifications",
    }
    
    # Low resolution = higher priority (needs fixing)
    priority = 4 if resolution_rate < 0.5 else 3
    
    return MaintenanceInsight(
        insight_type="pattern",
        source="log_review",
        title=title,
        details=details,
        priority=priority,
        status="pending",
    )


def _generate_model_insight(pattern: DetectedPattern, context: Dict) -> MaintenanceInsight:
    """Generate insight for model performance patterns."""
    details_ctx = context.get("details", {})
    component = details_ctx.get("component", "unknown")
    better_model = details_ctx.get("better_model", "")
    worse_model = details_ctx.get("worse_model", "")
    
    title = f"Model {better_model} performs better for {component} tasks"
    
    details = {
        "pattern_id": pattern.id,
        "component": component,
        "better_model": better_model,
        "worse_model": worse_model,
        "error_rate_diff": details_ctx.get("error_rate_diff", 0.0),
        "occurrence_count": pattern.occurrence_count,
        "recommendation": details_ctx.get("recommendation", f"Use {better_model} for {component}"),
        "proposed_action": f"switch_model:{component}:{better_model}",
    }
    
    priority = 3
    
    return MaintenanceInsight(
        insight_type="model_upgrade",
        source="log_review",
        title=title,
        details=details,
        priority=priority,
        status="pending",
    )


def _save_insight(insight: MaintenanceInsight) -> int:
    """Save an insight to the database."""
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO maintenance_insights 
            (insight_type, source, title, details, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            insight.insight_type,
            insight.source,
            insight.title,
            json.dumps(insight.details),
            insight.priority,
            insight.status,
        ))
        return cursor.lastrowid


def apply_insight(insight_id: int) -> bool:
    """
    Apply an insight (user accepted it).
    
    Creates a learned rule if applicable.
    
    Returns:
        True if successfully applied
    """
    with get_db() as conn:
        # Get the insight
        row = conn.execute("""
            SELECT * FROM maintenance_insights WHERE id = ?
        """, (insight_id,)).fetchone()
        
        if not row:
            logger.error(f"Insight {insight_id} not found")
            return False
        
        insight = MaintenanceInsight.from_row(row)
        details = insight.details
        proposed_action = details.get("proposed_action", "")
        
        # Create learned rule based on action type
        rule_created = False
        
        if proposed_action.startswith("flag_ambiguity:"):
            phrase = proposed_action.replace("flag_ambiguity:", "")
            rule = LearnedRule(
                rule_type="ambiguity_flag",
                pattern_id=details.get("pattern_id"),
                rule_key=f"phrase:{phrase}",
                rule_value={"phrase": phrase, "ambiguity_reason": details.get("ambiguity_reason")},
                priority=4,
                enabled=True,
            )
            rule_created = _save_learned_rule(rule)
        
        elif proposed_action.startswith("time_mapping:"):
            time_word = proposed_action.replace("time_mapping:", "")
            rule = LearnedRule(
                rule_type="time_expression",
                pattern_id=details.get("pattern_id"),
                rule_key=f"time_word:{time_word}",
                rule_value={"time_word": time_word, "default_mapping": details.get("suggested_mapping")},
                priority=4,
                enabled=True,
            )
            rule_created = _save_learned_rule(rule)
        
        # Mark insight as actioned
        conn.execute("""
            UPDATE maintenance_insights
            SET status = 'actioned', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (insight_id,))
        
        logger.info(f"Applied insight #{insight_id}, rule_created={rule_created}")
        return True


def dismiss_insight(insight_id: int) -> bool:
    """
    Dismiss an insight (user rejected it).
    
    Returns:
        True if successfully dismissed
    """
    with get_db() as conn:
        conn.execute("""
            UPDATE maintenance_insights
            SET status = 'dismissed', resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (insight_id,))
        
        logger.info(f"Dismissed insight #{insight_id}")
        return True


def _save_learned_rule(rule: LearnedRule) -> int:
    """Save a learned rule to the database."""
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT OR REPLACE INTO learned_rules 
            (rule_type, pattern_id, rule_key, rule_value, priority, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            rule.rule_type,
            rule.pattern_id,
            rule.rule_key,
            json.dumps(rule.rule_value),
            rule.priority,
            int(rule.enabled),
        ))
        logger.info(f"Created learned rule: {rule.rule_key}")
        return cursor.lastrowid


def get_learned_rules(rule_type: Optional[str] = None, enabled_only: bool = True) -> List[LearnedRule]:
    """
    Get learned rules from the database.
    
    Args:
        rule_type: Filter by rule type (None = all)
        enabled_only: Only return enabled rules
        
    Returns:
        List of LearnedRule objects
    """
    query = "SELECT * FROM learned_rules WHERE 1=1"
    params = []
    
    if rule_type:
        query += " AND rule_type = ?"
        params.append(rule_type)
    
    if enabled_only:
        query += " AND enabled = 1"
    
    query += " ORDER BY priority DESC"
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [LearnedRule.from_row(row) for row in rows]


def record_rule_application(rule_id: int):
    """Record that a learned rule was applied."""
    with get_db() as conn:
        conn.execute("""
            UPDATE learned_rules
            SET applied_count = applied_count + 1,
                last_applied = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (rule_id,))
