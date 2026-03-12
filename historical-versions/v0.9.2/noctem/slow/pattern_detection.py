"""
Pattern Detection for Noctem v0.7.0 Self-Improvement Engine.

Analyzes execution logs and user behavior to detect recurring patterns.
"""
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import json

from ..db import get_db
from ..models import DetectedPattern

logger = logging.getLogger(__name__)

# Pattern detection thresholds (from plan)
MIN_OCCURRENCES = 5  # Minimum times a pattern must occur to be detected
MIN_CONFIDENCE = 0.7  # Minimum confidence to promote pattern to insight


def detect_recurring_ambiguities(days: int = 30) -> List[Dict]:
    """
    Detect phrases/patterns that frequently result in ambiguous classifications.
    
    Returns:
        List of dicts with pattern_key, occurrence_count, example_texts, confidence
    """
    with get_db() as conn:
        # Get ambiguous thoughts from the period
        rows = conn.execute("""
            SELECT raw_text, ambiguity_reason, confidence
            FROM thoughts
            WHERE kind = 'ambiguous'
              AND created_at >= datetime('now', ? || ' days')
        """, (-days,)).fetchall()
        
        # Extract common phrases (2-3 words)
        phrase_examples = defaultdict(list)
        phrase_reasons = defaultdict(lambda: Counter())
        
        for row in rows:
            text = row["raw_text"].lower()
            words = text.split()
            
            # Extract 2-word and 3-word phrases
            for i in range(len(words) - 1):
                phrase = " ".join(words[i:i+2])
                phrase_examples[phrase].append(text)
                phrase_reasons[phrase][row["ambiguity_reason"]] += 1
                
                if i < len(words) - 2:
                    phrase3 = " ".join(words[i:i+3])
                    phrase_examples[phrase3].append(text)
                    phrase_reasons[phrase3][row["ambiguity_reason"]] += 1
        
        # Filter to phrases that occur >= MIN_OCCURRENCES
        patterns = []
        for phrase, examples in phrase_examples.items():
            count = len(examples)
            if count >= MIN_OCCURRENCES:
                # Get most common ambiguity reason
                most_common_reason = phrase_reasons[phrase].most_common(1)[0][0]
                reason_count = phrase_reasons[phrase][most_common_reason]
                
                # Confidence = how often this phrase leads to same ambiguity reason
                confidence = reason_count / count
                
                if confidence >= MIN_CONFIDENCE:
                    patterns.append({
                        "pattern_key": f"phrase:{phrase}",
                        "occurrence_count": count,
                        "ambiguity_reason": most_common_reason,
                        "confidence": round(confidence, 3),
                        "example_texts": examples[:3],  # First 3 examples
                    })
        
        # Sort by occurrence count descending
        patterns.sort(key=lambda x: x["occurrence_count"], reverse=True)
        logger.info(f"Detected {len(patterns)} recurring ambiguity patterns")
        return patterns


def detect_extraction_failures(days: int = 30) -> List[Dict]:
    """
    Detect patterns where time/date extraction fails or is corrected by user.
    
    Returns:
        List of dicts with pattern_key, occurrence_count, examples
    """
    patterns = []
    
    with get_db() as conn:
        # Get thoughts with low confidence in time extraction
        # (These might have time words but failed to parse)
        rows = conn.execute("""
            SELECT t.raw_text, t.confidence, tk.due_date
            FROM thoughts t
            LEFT JOIN tasks tk ON t.linked_task_id = tk.id
            WHERE t.created_at >= datetime('now', ? || ' days')
              AND t.kind = 'actionable'
              AND t.confidence < 0.8
        """, (-days,)).fetchall()
        
        # Look for time-related words that might have failed parsing
        time_words = ["soon", "later", "weekend", "tonight", "morning", "afternoon", "evening"]
        time_word_failures = Counter()
        time_word_examples = defaultdict(list)
        
        for row in rows:
            text = row["raw_text"].lower()
            for word in time_words:
                if word in text and not row["due_date"]:
                    # Time word present but no due date extracted = failure
                    time_word_failures[word] += 1
                    time_word_examples[word].append(row["raw_text"])
        
        # Create patterns for words with >= MIN_OCCURRENCES failures
        for word, count in time_word_failures.items():
            if count >= MIN_OCCURRENCES:
                patterns.append({
                    "pattern_key": f"time_word:{word}",
                    "occurrence_count": count,
                    "failure_type": "date_extraction",
                    "confidence": 0.9,  # High confidence that this is a pattern
                    "example_texts": time_word_examples[word][:3],
                })
        
        logger.info(f"Detected {len(patterns)} extraction failure patterns")
        return patterns


def detect_user_corrections(days: int = 30) -> List[Dict]:
    """
    Detect patterns in user corrections via /summon or task amendments.
    
    Returns:
        List of dicts with pattern_key, occurrence_count, correction_type, examples
    """
    patterns = []
    
    with get_db() as conn:
        # Get thoughts corrected via summon
        summon_corrections = conn.execute("""
            SELECT raw_text, confidence, kind
            FROM thoughts
            WHERE summon_mode = 1
              AND created_at >= datetime('now', ? || ' days')
        """, (-days,)).fetchall()
        
        # Analyze what gets corrected
        low_confidence_corrected = 0
        high_confidence_corrected = 0
        kind_corrections = Counter()
        
        for row in summon_corrections:
            if row["confidence"] and row["confidence"] < 0.5:
                low_confidence_corrected += 1
            elif row["confidence"] and row["confidence"] >= 0.8:
                high_confidence_corrected += 1
            
            if row["kind"]:
                kind_corrections[row["kind"]] += 1
        
        # Pattern: High confidence items getting corrected = classifier overconfident
        if high_confidence_corrected >= MIN_OCCURRENCES:
            patterns.append({
                "pattern_key": "correction:high_confidence_wrong",
                "occurrence_count": high_confidence_corrected,
                "correction_type": "overconfidence",
                "confidence": 0.85,
                "details": {
                    "message": "Classifier is overconfident on some classifications",
                    "recommendation": "Consider lowering confidence threshold or adding validation step",
                },
            })
        
        # Pattern: Specific kind gets corrected often
        for kind, count in kind_corrections.items():
            if count >= MIN_OCCURRENCES:
                patterns.append({
                    "pattern_key": f"correction:kind_{kind}",
                    "occurrence_count": count,
                    "correction_type": "misclassification",
                    "confidence": 0.8,
                    "details": {
                        "message": f"'{kind}' classifications often need correction",
                        "recommendation": f"Review classifier rules for '{kind}' kind",
                    },
                })
        
        logger.info(f"Detected {len(patterns)} user correction patterns")
        return patterns


def detect_clarification_patterns(days: int = 30) -> List[Dict]:
    """
    Analyze which Butler clarification questions are effective vs. ignored.
    
    Returns:
        List of dicts with pattern_key, resolution_rate, avg_response_time
    """
    patterns = []
    
    with get_db() as conn:
        # Get clarification outcomes by ambiguity reason
        rows = conn.execute("""
            SELECT 
                ambiguity_reason,
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
            GROUP BY ambiguity_reason
        """, (-days,)).fetchall()
        
        for row in rows:
            total = row["total"]
            resolved = row["resolved"] or 0
            resolution_rate = (resolved / total) if total > 0 else 0
            
            if total >= MIN_OCCURRENCES:
                # Pattern: Low resolution rate = ineffective clarification type
                if resolution_rate < 0.3:
                    patterns.append({
                        "pattern_key": f"clarification:low_response_{row['ambiguity_reason']}",
                        "occurrence_count": total,
                        "resolution_rate": round(resolution_rate, 3),
                        "confidence": 0.9,
                        "details": {
                            "message": f"Clarifications for '{row['ambiguity_reason']}' are often ignored",
                            "recommendation": "Rephrase clarification questions or provide better defaults",
                        },
                    })
                
                # Pattern: High resolution rate + fast response = good clarification
                elif resolution_rate > 0.7 and row["avg_resolution_hours"] and row["avg_resolution_hours"] < 2:
                    patterns.append({
                        "pattern_key": f"clarification:effective_{row['ambiguity_reason']}",
                        "occurrence_count": total,
                        "resolution_rate": round(resolution_rate, 3),
                        "avg_response_hours": round(row["avg_resolution_hours"], 2),
                        "confidence": 0.95,
                        "details": {
                            "message": f"Clarifications for '{row['ambiguity_reason']}' work well",
                            "recommendation": "Use this clarification style as template for other types",
                        },
                    })
        
        logger.info(f"Detected {len(patterns)} clarification effectiveness patterns")
        return patterns


def detect_model_performance_patterns(days: int = 7) -> List[Dict]:
    """
    Compare model performance on same task types.
    
    Returns:
        List of dicts with pattern_key, models_compared, recommendation
    """
    patterns = []
    
    with get_db() as conn:
        # Get model performance by component/stage
        rows = conn.execute("""
            SELECT 
                model_used,
                component,
                COUNT(*) as usage_count,
                AVG(duration_ms) as avg_duration_ms,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count
            FROM execution_logs
            WHERE timestamp >= datetime('now', ? || ' days')
              AND model_used IS NOT NULL
            GROUP BY model_used, component
            HAVING usage_count >= 10
        """, (-days,)).fetchall()
        
        # Group by component to compare models
        by_component = defaultdict(list)
        for row in rows:
            by_component[row["component"]].append(dict(row))
        
        # Compare models within same component
        for component, models in by_component.items():
            if len(models) >= 2:
                # Sort by error rate then avg_confidence
                models.sort(key=lambda m: (
                    m["error_count"] / m["usage_count"],
                    -m["avg_confidence"]
                ))
                
                best = models[0]
                worst = models[-1]
                
                # Pattern: Clear performance difference
                best_error_rate = best["error_count"] / best["usage_count"]
                worst_error_rate = worst["error_count"] / worst["usage_count"]
                
                if worst_error_rate - best_error_rate > 0.1:  # 10%+ difference
                    patterns.append({
                        "pattern_key": f"model_perf:{component}:{best['model_used']}_better",
                        "occurrence_count": best["usage_count"] + worst["usage_count"],
                        "confidence": 0.85,
                        "details": {
                            "component": component,
                            "better_model": best["model_used"],
                            "worse_model": worst["model_used"],
                            "error_rate_diff": round(worst_error_rate - best_error_rate, 3),
                            "recommendation": f"Prefer {best['model_used']} for {component} tasks",
                        },
                    })
        
        logger.info(f"Detected {len(patterns)} model performance patterns")
        return patterns


def save_detected_pattern(
    pattern_type: str,
    pattern_key: str,
    occurrence_count: int,
    confidence: float,
    context: Dict
) -> int:
    """
    Save or update a detected pattern in the database.
    
    Returns:
        Pattern ID
    """
    with get_db() as conn:
        # Check if pattern already exists
        existing = conn.execute("""
            SELECT id, occurrence_count, first_seen
            FROM detected_patterns
            WHERE pattern_type = ? AND pattern_key = ?
        """, (pattern_type, pattern_key)).fetchone()
        
        if existing:
            # Update existing pattern
            new_count = existing["occurrence_count"] + occurrence_count
            conn.execute("""
                UPDATE detected_patterns
                SET occurrence_count = ?,
                    last_seen = CURRENT_TIMESTAMP,
                    context = ?,
                    confidence = ?
                WHERE id = ?
            """, (new_count, json.dumps(context), confidence, existing["id"]))
            logger.debug(f"Updated pattern {pattern_key}: {new_count} occurrences")
            return existing["id"]
        else:
            # Insert new pattern
            cursor = conn.execute("""
                INSERT INTO detected_patterns 
                (pattern_type, pattern_key, occurrence_count, confidence, context)
                VALUES (?, ?, ?, ?, ?)
            """, (pattern_type, pattern_key, occurrence_count, confidence, json.dumps(context)))
            pattern_id = cursor.lastrowid
            logger.info(f"Created new pattern {pattern_key}: {occurrence_count} occurrences")
            return pattern_id


def get_promotable_patterns(limit: int = 10) -> List[DetectedPattern]:
    """
    Get patterns that meet criteria for promotion to insights.
    
    Criteria:
    - occurrence_count >= MIN_OCCURRENCES
    - confidence >= MIN_CONFIDENCE
    - status = 'pending' (not already promoted)
    
    Returns:
        List of DetectedPattern objects
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT *
            FROM detected_patterns
            WHERE occurrence_count >= ?
              AND confidence >= ?
              AND status = 'pending'
            ORDER BY occurrence_count DESC, confidence DESC
            LIMIT ?
        """, (MIN_OCCURRENCES, MIN_CONFIDENCE, limit)).fetchall()
        
        return [DetectedPattern.from_row(row) for row in rows]


def mark_pattern_promoted(pattern_id: int):
    """Mark a pattern as promoted to insight."""
    with get_db() as conn:
        conn.execute("""
            UPDATE detected_patterns
            SET status = 'promoted_to_insight'
            WHERE id = ?
        """, (pattern_id,))
        logger.debug(f"Marked pattern {pattern_id} as promoted")


def dismiss_pattern(pattern_id: int):
    """Dismiss a pattern (user decided it's not useful)."""
    with get_db() as conn:
        conn.execute("""
            UPDATE detected_patterns
            SET status = 'dismissed'
            WHERE id = ?
        """, (pattern_id,))
        logger.debug(f"Dismissed pattern {pattern_id}")


def run_all_pattern_detection(days: int = 30) -> Dict[str, List[Dict]]:
    """
    Run all pattern detection algorithms.
    
    Returns:
        Dict with pattern_type as key and list of patterns as value
    """
    logger.info(f"Running pattern detection for last {days} days...")
    
    results = {
        "ambiguities": detect_recurring_ambiguities(days),
        "extraction_failures": detect_extraction_failures(days),
        "user_corrections": detect_user_corrections(days),
        "clarifications": detect_clarification_patterns(days),
        "model_performance": detect_model_performance_patterns(min(days, 7)),  # Only 7 days for model perf
    }
    
    # Save all detected patterns
    total_saved = 0
    for pattern_type, patterns in results.items():
        for pattern in patterns:
            save_detected_pattern(
                pattern_type=pattern_type,
                pattern_key=pattern["pattern_key"],
                occurrence_count=pattern["occurrence_count"],
                confidence=pattern.get("confidence", 0.8),
                context=pattern
            )
            total_saved += 1
    
    logger.info(f"Pattern detection complete: saved {total_saved} patterns")
    return results
