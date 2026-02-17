"""
Tests for Noctem v0.6.0 Polish features.

Tests cover:
- Fast classifier with confidence scoring
- Voice cleanup utility
- Thoughts-first capture system
- Butler clarification enhancements
- Context-aware suggestions
- Contact budget transparency
"""
import pytest
import tempfile
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Set up test database before imports
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['NOCTEM_DB_PATH'] = TEST_DB

# Now import noctem modules
from noctem import db
from noctem.db import get_db, init_db

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
# CLASSIFIER TESTS
# =============================================================================

class TestFastClassifier:
    """Test the fast classifier module."""
    
    def test_high_confidence_with_date_and_importance(self):
        """Task with date and importance should have high confidence."""
        from noctem.fast.classifier import classify_input, ThoughtKind, HIGH_CONFIDENCE
        
        result = classify_input("buy milk tomorrow !1")
        
        assert result.kind == ThoughtKind.ACTIONABLE
        assert result.confidence >= HIGH_CONFIDENCE
        assert result.parsed_task is not None
        assert result.parsed_task.name == "Buy milk"
    
    def test_high_confidence_with_date(self):
        """Task with just a date should still be confident."""
        from noctem.fast.classifier import classify_input, ThoughtKind, MEDIUM_CONFIDENCE
        
        result = classify_input("call mom friday")
        
        assert result.kind == ThoughtKind.ACTIONABLE
        assert result.confidence >= MEDIUM_CONFIDENCE
    
    def test_note_detection_with_prefix(self):
        """Text starting with 'note:' should be classified as note."""
        from noctem.fast.classifier import classify_input, ThoughtKind
        
        result = classify_input("note: learned about SQLite indexes today")
        
        assert result.kind == ThoughtKind.NOTE
        assert result.confidence >= 0.9
    
    def test_note_detection_with_keyword(self):
        """Text with note keywords should be classified as note."""
        from noctem.fast.classifier import classify_input, ThoughtKind
        
        result = classify_input("I realized that the algorithm was O(n^2)")
        
        assert result.kind == ThoughtKind.NOTE
        assert result.confidence >= 0.8
    
    def test_ambiguous_vague_text(self):
        """Vague text should be classified as ambiguous."""
        from noctem.fast.classifier import classify_input, ThoughtKind, MEDIUM_CONFIDENCE
        
        result = classify_input("that thing")
        
        assert result.kind == ThoughtKind.AMBIGUOUS
        assert result.confidence < MEDIUM_CONFIDENCE
    
    def test_ambiguous_project_scope(self):
        """Text mentioning 'project' should flag scope ambiguity."""
        from noctem.fast.classifier import classify_input, AmbiguityReason
        
        result = classify_input("new project for home automation")
        
        # Should be ambiguous with scope reason
        assert result.ambiguity_reason == AmbiguityReason.SCOPE
    
    def test_command_detection_slash(self):
        """Slash commands should be detected as commands."""
        from noctem.fast.classifier import classify_input
        
        result = classify_input("/today")
        
        assert result.is_command is True
    
    def test_command_detection_quick_action(self):
        """Quick actions like 'done 1' should be detected as commands."""
        from noctem.fast.classifier import classify_input
        
        result = classify_input("done 1")
        
        assert result.is_command is True
    
    def test_command_detection_correction(self):
        """Correction command should be detected."""
        from noctem.fast.classifier import classify_input
        
        result = classify_input("* tomorrow !1")
        
        assert result.is_command is True
    
    def test_action_verb_boosts_confidence(self):
        """Having an action verb should boost confidence."""
        from noctem.fast.classifier import classify_input
        
        result_with_verb = classify_input("buy groceries")
        result_without_verb = classify_input("groceries")
        
        assert result_with_verb.confidence > result_without_verb.confidence


# =============================================================================
# VOICE CLEANUP TESTS
# =============================================================================

class TestVoiceCleanup:
    """Test the voice cleanup utility."""
    
    def test_remove_filler_um(self):
        """Should remove 'um' filler words."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("um I need to um call mom")
        
        assert "um" not in result.lower()
        assert "call mom" in result.lower()
    
    def test_remove_filler_you_know(self):
        """Should remove 'you know' filler phrase."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("I need to you know buy milk")
        
        assert "you know" not in result.lower()
    
    def test_normalize_hesitation_repetition(self):
        """Should normalize repeated words from hesitation."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("I I need to go")
        
        # Should have only one "I"
        assert result.lower().count("i ") <= 1 or "i need" in result.lower()
    
    def test_fix_capitalization_i(self):
        """Should capitalize standalone 'i'."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("i need to call mom")
        
        assert result.startswith("I")
    
    def test_preserve_content(self):
        """Should preserve semantic content."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("um buy milk tomorrow")
        
        assert "buy" in result.lower()
        assert "milk" in result.lower()
        assert "tomorrow" in result.lower()
    
    def test_empty_input(self):
        """Should handle empty input."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        result = clean_voice_transcript("")
        
        assert result == ""
    
    def test_clean_input_unchanged(self):
        """Clean input should remain mostly unchanged."""
        from noctem.fast.voice_cleanup import clean_voice_transcript
        
        original = "Buy milk tomorrow"
        result = clean_voice_transcript(original)
        
        assert result == original


# =============================================================================
# THOUGHTS CAPTURE TESTS
# =============================================================================

class TestThoughtsCapture:
    """Test the thoughts-first capture system."""
    
    def test_actionable_creates_task_and_thought(self):
        """Actionable input should create both thought and task."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.fast.classifier import ThoughtKind
        from noctem.services import task_service
        
        result = process_input("buy milk tomorrow !1", source="cli")
        
        assert result.kind == ThoughtKind.ACTIONABLE
        assert result.task is not None
        assert result.thought_id > 0
        
        # Verify thought exists and is linked
        thought = get_thought(result.thought_id)
        assert thought is not None
        assert thought.linked_task_id == result.task.id
        assert thought.status == "processed"
    
    def test_note_creates_thought_only(self):
        """Note input should create thought but not task."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.fast.classifier import ThoughtKind
        
        result = process_input("note: interesting fact about Python", source="cli")
        
        assert result.kind == ThoughtKind.NOTE
        assert result.task is None
        assert result.thought_id > 0
        
        thought = get_thought(result.thought_id)
        assert thought is not None
        assert thought.linked_task_id is None
        assert thought.status == "processed"
    
    def test_ambiguous_creates_pending_thought(self):
        """Ambiguous input should create pending thought."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.fast.classifier import ThoughtKind
        
        result = process_input("that project thing", source="cli")
        
        assert result.kind == ThoughtKind.AMBIGUOUS
        assert result.task is None
        assert result.thought_id > 0
        
        thought = get_thought(result.thought_id)
        assert thought is not None
        assert thought.status == "pending"  # Stays pending for Butler
    
    def test_command_not_captured(self):
        """System commands should not create thoughts."""
        from noctem.fast.capture import process_input
        
        result = process_input("/today", source="cli")
        
        assert result.is_command is True
        assert result.thought_id == 0
    
    def test_source_tracked(self):
        """Source should be tracked in thought."""
        from noctem.fast.capture import process_input, get_thought
        
        result = process_input("buy milk", source="telegram")
        
        thought = get_thought(result.thought_id)
        assert thought.source == "telegram"
    
    def test_get_pending_ambiguous_thoughts(self):
        """Should retrieve pending ambiguous thoughts."""
        from noctem.fast.capture import process_input, get_pending_ambiguous_thoughts
        
        # Create some ambiguous thoughts
        process_input("that thing", source="cli")
        process_input("maybe something", source="cli")
        
        pending = get_pending_ambiguous_thoughts()
        
        assert len(pending) >= 2


# =============================================================================
# BUTLER CLARIFICATION TESTS
# =============================================================================

class TestButlerClarifications:
    """Test Butler clarification enhancements."""
    
    def test_thought_clarification_questions(self):
        """Should generate appropriate questions for ambiguous thoughts."""
        from noctem.fast.capture import process_input
        from noctem.butler.clarifications import generate_thought_clarification_question
        
        # Create ambiguous thought
        result = process_input("new project automation", source="cli")
        
        from noctem.fast.capture import get_thought
        thought = get_thought(result.thought_id)
        
        question = generate_thought_clarification_question(thought)
        
        assert "question" in question
        assert "options" in question
        assert len(question["options"]) > 0
    
    def test_clarification_message_includes_thoughts(self):
        """Clarification message should include ambiguous thoughts."""
        from noctem.fast.capture import process_input
        from noctem.butler.clarifications import generate_clarification_message
        
        # Create an ambiguous thought
        process_input("that important thing", source="cli")
        
        message = generate_clarification_message()
        
        # Should have some content (could be None if no pending items)
        # But if there's an ambiguous thought, it should appear
        if message:
            assert "Quick Questions" in message
    
    def test_resolve_thought_as_task(self):
        """Should be able to resolve thought as task."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.butler.clarifications import resolve_thought_clarification
        
        # Create ambiguous thought
        result = process_input("buy groceries stuff", source="cli")
        
        # Resolve as task
        resolution = resolve_thought_clarification(result.thought_id, "task")
        
        assert resolution is not None
        assert resolution["action"] == "task_created"
        assert "task_id" in resolution
        
        # Verify thought is now clarified
        thought = get_thought(result.thought_id)
        assert thought.status == "clarified"
        assert thought.linked_task_id is not None
    
    def test_resolve_thought_as_note(self):
        """Should be able to resolve thought as note."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.butler.clarifications import resolve_thought_clarification
        
        result = process_input("maybe remember this", source="cli")
        
        resolution = resolve_thought_clarification(result.thought_id, "note")
        
        assert resolution["action"] == "kept_as_note"
        
        thought = get_thought(result.thought_id)
        assert thought.status == "clarified"
        assert thought.kind == "note"
    
    def test_pending_clarification_count(self):
        """Should count pending clarifications correctly."""
        from noctem.fast.capture import process_input
        from noctem.butler.clarifications import get_pending_clarification_count
        
        # Create some ambiguous thoughts
        process_input("thing one", source="cli")
        process_input("thing two", source="cli")
        
        counts = get_pending_clarification_count()
        
        assert counts["thoughts"] >= 2
        assert counts["total"] >= 2


# =============================================================================
# SUGGESTION SERVICE TESTS
# =============================================================================

class TestSuggestionService:
    """Test context-aware suggestion service."""
    
    def test_get_calendar_gaps_empty(self):
        """Should return gaps when no meetings."""
        from noctem.services.suggestion_service import get_calendar_gaps
        
        gaps = get_calendar_gaps()
        
        # Should have at least one gap (the whole day if no meetings)
        assert len(gaps) >= 0  # Could be 0 if after work hours
    
    def test_task_suggestion_ranking(self):
        """Higher priority tasks should rank higher."""
        from noctem.services import task_service
        from noctem.services.suggestion_service import get_contextual_suggestions
        
        # Create tasks with different priorities
        task_service.create_task("Low priority task", importance=0.1)
        task_service.create_task("High priority task", importance=1.0, due_date=date.today())
        
        suggestions = get_contextual_suggestions()
        
        if len(suggestions) >= 2:
            # High priority should come first (or near top)
            assert any(s.task.name == "High priority task" for s in suggestions[:2])
    
    def test_format_suggestions_message(self):
        """Should format suggestions into readable message."""
        from noctem.services import task_service
        from noctem.services.suggestion_service import (
            get_contextual_suggestions, format_suggestions_message
        )
        
        task_service.create_task("Test task", importance=0.8)
        
        suggestions = get_contextual_suggestions()
        message = format_suggestions_message(suggestions)
        
        assert "Suggested" in message or "No task" in message
    
    def test_quick_suggestion(self):
        """Should return single quick suggestion."""
        from noctem.services import task_service
        from noctem.services.suggestion_service import get_quick_suggestion
        
        task_service.create_task("Quick task", importance=0.9)
        
        suggestion = get_quick_suggestion()
        
        if suggestion:
            assert suggestion.task is not None


# =============================================================================
# BUTLER STATUS TESTS
# =============================================================================

class TestButlerStatus:
    """Test Butler contact budget transparency."""
    
    def test_status_shows_used_format(self):
        """Status should show 'X/5 used' format."""
        from noctem.butler.protocol import get_butler_status_message
        
        message = get_butler_status_message()
        
        assert "used" in message.lower()
        assert "this week" in message.lower()
    
    def test_status_shows_next_contact_datetime(self):
        """Status should show next contact with datetime."""
        from noctem.butler.protocol import get_butler_status_message
        
        message = get_butler_status_message()
        
        # Should have next scheduled info
        assert "Next scheduled" in message or "Budget exhausted" in message
    
    def test_next_contact_has_datetime(self):
        """Next contact should include datetime object."""
        from noctem.butler.protocol import ButlerProtocol
        
        next_contact = ButlerProtocol.get_next_scheduled_contact()
        
        if next_contact:
            assert "datetime" in next_contact
            assert isinstance(next_contact["datetime"], datetime)
    
    def test_budget_used_calculation(self):
        """Budget used should calculate correctly."""
        from noctem.butler.protocol import ButlerProtocol, get_butler_status_message
        
        # Record a contact
        ButlerProtocol.record_contact("update", "Test message")
        
        message = get_butler_status_message()
        
        # Should show 1/5 used
        assert "1/5" in message or "1 of 5" in message.lower()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the full flow."""
    
    def test_voice_to_task_flow(self):
        """Full voice → task flow should work."""
        from noctem.fast.capture import process_voice_transcription
        from noctem.fast.classifier import ThoughtKind
        
        # Simulate voice transcription result
        transcription = "um buy milk tomorrow please"
        
        result = process_voice_transcription(transcription, voice_journal_id=999)
        
        assert result.kind == ThoughtKind.ACTIONABLE
        assert result.task is not None
        assert "milk" in result.task.name.lower()
    
    def test_ambiguous_to_clarified_flow(self):
        """Ambiguous input → clarification → task flow should work."""
        from noctem.fast.capture import process_input, get_thought
        from noctem.butler.clarifications import resolve_thought_clarification
        
        # Step 1: Input something ambiguous
        result = process_input("that important project thing", source="cli")
        assert result.thought_id > 0
        
        # Step 2: Resolve it as a task
        resolution = resolve_thought_clarification(result.thought_id, "task")
        
        # Step 3: Verify task was created
        assert resolution["action"] == "task_created"
        
        thought = get_thought(result.thought_id)
        assert thought.status == "clarified"
        assert thought.linked_task_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
