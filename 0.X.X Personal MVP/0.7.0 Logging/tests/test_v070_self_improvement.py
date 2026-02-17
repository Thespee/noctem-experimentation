"""
Tests for Noctem v0.7.0 Self-Improvement Engine.

Covers pattern detection, log review, improvement engine, and integration.
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

# Set up test database before imports
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['NOCTEM_DB_PATH'] = TEST_DB

# Now import noctem modules
from noctem import db
from noctem.db import get_db, init_db
from noctem.models import Thought, DetectedPattern, MaintenanceInsight, LearnedRule

# Override DB path for testing
db.DB_PATH = Path(TEST_DB)


@pytest.fixture(autouse=True)
def setup_db():
    """Set up fresh database for each test."""
    db.DB_PATH = Path(TEST_DB)
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    init_db()
    yield
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


# =============================================================================
# PATTERN DETECTION TESTS
# =============================================================================

class TestPatternDetection:
    """Test pattern detection algorithms."""
    
    def test_detect_recurring_ambiguities(self):
        """Should detect recurring ambiguous phrases."""
        from noctem.slow.pattern_detection import detect_recurring_ambiguities, MIN_OCCURRENCES
        
        # Create test data: 6 ambiguous thoughts with "work on" phrase
        with get_db() as conn:
            for i in range(6):
                conn.execute("""
                    INSERT INTO thoughts (source, raw_text, kind, ambiguity_reason, confidence, status)
                    VALUES ('cli', ?, 'ambiguous', 'scope', 0.3, 'pending')
                """, (f"work on the project task {i}",))
        
        # Run detection
        patterns = detect_recurring_ambiguities(days=30)
        
        # Should detect "work on" pattern
        assert len(patterns) > 0
        work_on_patterns = [p for p in patterns if "work on" in p["pattern_key"]]
        assert len(work_on_patterns) > 0
        assert work_on_patterns[0]["occurrence_count"] >= MIN_OCCURRENCES
    
    def test_detect_extraction_failures(self):
        """Should detect time word extraction failures."""
        from noctem.slow.pattern_detection import detect_extraction_failures, MIN_OCCURRENCES
        
        # Create test data: tasks with "later" but no due date
        with get_db() as conn:
            for i in range(6):
                # Create task without due date (extraction failed) - FIRST
                conn.execute("""
                    INSERT INTO tasks (name, status)
                    VALUES (?, 'not_started')
                """, (f"do task {i} later",))
                task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                
                # Create thought linked to task - SECOND
                conn.execute("""
                    INSERT INTO thoughts (source, raw_text, kind, confidence, status, linked_task_id)
                    VALUES ('cli', ?, 'actionable', 0.7, 'processed', ?)
                """, (f"do task {i} later", task_id))
        
        # Run detection
        patterns = detect_extraction_failures(days=30)
        
        # Should detect "later" as problematic
        later_patterns = [p for p in patterns if "later" in p["pattern_key"]]
        assert len(later_patterns) > 0
        assert later_patterns[0]["occurrence_count"] >= MIN_OCCURRENCES
    
    def test_detect_user_corrections(self):
        """Should detect patterns in user corrections."""
        from noctem.slow.pattern_detection import detect_user_corrections, MIN_OCCURRENCES
        
        # Create test data: high confidence thoughts that were corrected via summon
        with get_db() as conn:
            for i in range(6):
                conn.execute("""
                    INSERT INTO thoughts (source, raw_text, kind, confidence, status, summon_mode)
                    VALUES ('cli', ?, 'actionable', 0.9, 'processed', 1)
                """, (f"test thought {i}",))
        
        # Run detection
        patterns = detect_user_corrections(days=30)
        
        # Should detect overconfidence pattern
        overconfidence = [p for p in patterns if "high_confidence_wrong" in p["pattern_key"]]
        assert len(overconfidence) > 0
        assert overconfidence[0]["occurrence_count"] >= MIN_OCCURRENCES
    
    def test_pattern_promotion_threshold(self):
        """Should only promote patterns meeting thresholds."""
        from noctem.slow.pattern_detection import (
            save_detected_pattern, 
            get_promotable_patterns,
            MIN_OCCURRENCES,
            MIN_CONFIDENCE
        )
        
        # Save pattern below threshold
        save_detected_pattern(
            pattern_type="test",
            pattern_key="low_occurrence",
            occurrence_count=MIN_OCCURRENCES - 1,  # Too few
            confidence=MIN_CONFIDENCE + 0.1,
            context={"test": True}
        )
        
        # Save pattern above threshold
        save_detected_pattern(
            pattern_type="test",
            pattern_key="high_occurrence",
            occurrence_count=MIN_OCCURRENCES + 5,
            confidence=MIN_CONFIDENCE + 0.1,
            context={"test": True}
        )
        
        # Get promotable patterns
        promotable = get_promotable_patterns(limit=10)
        
        # Should only include high occurrence pattern
        assert len(promotable) == 1
        assert promotable[0].pattern_key == "high_occurrence"


# =============================================================================
# LOG REVIEW TESTS
# =============================================================================

class TestLogReview:
    """Test log review skill."""
    
    def test_should_run_log_review_never_run(self):
        """Should run if never run before."""
        from noctem.slow.log_review import should_run_log_review
        
        # No insights yet = never run
        assert should_run_log_review() == True
    
    def test_should_run_log_review_after_thoughts(self):
        """Should run after 50+ new thoughts."""
        from noctem.slow.log_review import should_run_log_review
        
        # Create a recent log review insight
        with get_db() as conn:
            conn.execute("""
                INSERT INTO maintenance_insights (insight_type, source, title, details, priority, status, created_at)
                VALUES ('pattern', 'log_review', 'Test', '{}', 3, 'pending', datetime('now', '-1 day'))
            """)
            
            # Create 50 new thoughts after the review
            for i in range(50):
                conn.execute("""
                    INSERT INTO thoughts (source, raw_text, kind, confidence, status)
                    VALUES ('cli', ?, 'actionable', 0.8, 'processed')
                """, (f"test thought {i}",))
        
        # Should trigger review
        assert should_run_log_review() == True
    
    def test_log_review_creates_insights(self):
        """End-to-end: log review should create insights from patterns."""
        from noctem.slow.log_review import run_log_review
        from noctem.slow.pattern_detection import save_detected_pattern, MIN_OCCURRENCES, MIN_CONFIDENCE
        
        # Create promotable patterns
        for i in range(3):
            save_detected_pattern(
                pattern_type="ambiguities",
                pattern_key=f"phrase:test pattern {i}",
                occurrence_count=MIN_OCCURRENCES + 5,
                confidence=MIN_CONFIDENCE + 0.2,
                context={
                    "ambiguity_reason": "scope",
                    "example_texts": [f"example {i}"]
                }
            )
        
        # Run log review
        summary = run_log_review(days=30)
        
        # Should have created insights (max 3)
        assert summary["patterns_promoted"] <= 3
        assert len(summary["insights_created"]) <= 3


# =============================================================================
# IMPROVEMENT ENGINE TESTS
# =============================================================================

class TestImprovementEngine:
    """Test improvement engine."""
    
    def test_generate_insight_from_ambiguity_pattern(self):
        """Should generate insight from ambiguity pattern."""
        from noctem.slow.pattern_detection import save_detected_pattern, MIN_OCCURRENCES, MIN_CONFIDENCE
        from noctem.slow.improvement_engine import generate_insight_from_pattern
        
        # Create pattern
        with get_db() as conn:
            pattern_id = save_detected_pattern(
                pattern_type="ambiguities",
                pattern_key="phrase:work on",
                occurrence_count=10,
                confidence=0.9,
                context={
                    "ambiguity_reason": "scope",
                    "example_texts": ["work on project", "work on task"]
                }
            )
            
            # Get pattern
            row = conn.execute("SELECT * FROM detected_patterns WHERE id = ?", (pattern_id,)).fetchone()
            pattern = DetectedPattern.from_row(row)
        
        # Generate insight
        insight = generate_insight_from_pattern(pattern)
        
        assert insight is not None
        assert "work on" in insight.title
        assert insight.insight_type == "pattern"
        assert insight.priority >= 3
    
    def test_apply_insight_creates_learned_rule(self):
        """Accepting insight should create learned rule."""
        from noctem.services.insight_service import accept_insight, get_rule_stats
        
        # Create insight
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO maintenance_insights 
                (insight_type, source, title, details, priority, status)
                VALUES ('pattern', 'log_review', 'Test insight', ?, 4, 'pending')
            """, ('{"proposed_action": "flag_ambiguity:work on", "ambiguity_reason": "scope"}',))
            insight_id = cursor.lastrowid
        
        # Accept insight
        success = accept_insight(insight_id)
        assert success == True
        
        # Should have created learned rule
        stats = get_rule_stats()
        assert stats["total"] >= 1


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestSelfImprovementIntegration:
    """Test end-to-end self-improvement flow."""
    
    def test_full_learning_cycle(self):
        """Test complete cycle: patterns → insights → learned rules."""
        from noctem.slow.pattern_detection import run_all_pattern_detection
        from noctem.slow.log_review import run_log_review
        from noctem.services.insight_service import get_pending_insights, accept_insight, list_learned_rules
        
        # Step 1: Create ambiguous thoughts
        with get_db() as conn:
            for i in range(10):
                conn.execute("""
                    INSERT INTO thoughts (source, raw_text, kind, ambiguity_reason, confidence, status)
                    VALUES ('cli', 'work on the project', 'ambiguous', 'scope', 0.3, 'pending')
                """)
        
        # Step 2: Run pattern detection
        patterns_found = run_all_pattern_detection(days=30)
        assert patterns_found["ambiguities"] is not None
        
        # Step 3: Run log review (creates insights)
        summary = run_log_review(days=30)
        assert summary["patterns_promoted"] > 0
        
        # Step 4: Get pending insights
        insights = get_pending_insights(limit=10)
        assert len(insights) > 0
        
        # Step 5: Accept first insight
        insight_id = insights[0].id
        accept_insight(insight_id)
        
        # Step 6: Verify learned rule was created
        rules = list_learned_rules(enabled_only=True)
        assert len(rules) > 0
    
    def test_work_queue_integration(self):
        """Test LOG_REVIEW integration with slow work queue."""
        from noctem.slow.queue import SlowWorkQueue, WorkType
        
        # Queue log review
        item_id = SlowWorkQueue.queue_log_review()
        assert item_id > 0
        
        # Should be in queue
        next_item = SlowWorkQueue.get_next_item()
        assert next_item is not None
        assert next_item.work_type == WorkType.LOG_REVIEW.value
        assert next_item.target_id == 0  # System-level task


# =============================================================================
# INSIGHT SERVICE TESTS
# =============================================================================

class TestInsightService:
    """Test insight service CRUD operations."""
    
    def test_get_pending_insights(self):
        """Should retrieve pending insights ordered by priority."""
        from noctem.services.insight_service import get_pending_insights
        
        # Create insights with different priorities
        with get_db() as conn:
            for priority in [3, 5, 1]:
                conn.execute("""
                    INSERT INTO maintenance_insights 
                    (insight_type, source, title, details, priority, status)
                    VALUES ('pattern', 'test', ?, '{}', ?, 'pending')
                """, (f"Priority {priority}", priority))
        
        # Get pending
        insights = get_pending_insights(limit=10)
        
        # Should be ordered by priority DESC
        assert len(insights) == 3
        assert insights[0].priority == 5
        assert insights[1].priority == 3
        assert insights[2].priority == 1
    
    def test_insight_summary(self):
        """Should provide summary statistics."""
        from noctem.services.insight_service import get_insight_summary
        
        # Create insights with different statuses
        with get_db() as conn:
            for status in ['pending', 'pending', 'actioned', 'dismissed']:
                conn.execute("""
                    INSERT INTO maintenance_insights 
                    (insight_type, source, title, details, priority, status)
                    VALUES ('pattern', 'test', 'Test', '{}', 3, ?)
                """, (status,))
        
        # Get summary
        summary = get_insight_summary()
        
        assert summary["total"] == 4
        assert summary["pending"] == 2
        assert summary["by_status"]["actioned"] == 1
        assert summary["by_status"]["dismissed"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
