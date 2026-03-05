"""
Tests for Noctem v0.6.0 Phase 2: Butler Protocol.
Tests cover:
- Contact budget management
- Update message generation
- Clarification queue
- Scheduler integration
"""
import pytest
import tempfile
import os
from datetime import date, timedelta
from pathlib import Path

# Set up test database before imports
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['NOCTEM_DB_PATH'] = TEST_DB

# Now import noctem modules
from noctem import db
from noctem.db import get_db, init_db

# Override DB path for testing
db.DB_PATH = Path(TEST_DB)

from noctem.services import task_service, project_service
from noctem.config import Config
from noctem.butler.protocol import ButlerProtocol, get_butler_status, get_butler_status_message
from noctem.butler.updates import (
    generate_update_message, generate_brief_update,
    get_overdue_tasks, get_tasks_due_today, get_tasks_due_this_week,
    get_unclear_tasks_count
)
from noctem.butler.clarifications import (
    ClarificationQueue, generate_clarification_message,
    parse_clarification_response, ensure_clarification_table
)


@pytest.fixture(autouse=True)
def setup_db():
    """Set up fresh database for each test."""
    db.DB_PATH = Path(TEST_DB)
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    init_db()
    ensure_clarification_table()
    Config.clear_cache()
    yield
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


class TestButlerProtocol:
    """Test butler contact budget management."""
    
    def test_get_current_week(self):
        """Should return current ISO week and year."""
        week, year = ButlerProtocol.get_current_week()
        assert 1 <= week <= 53
        assert year >= 2026
    
    def test_initial_budget_is_5(self):
        """Fresh week should have 5 contacts remaining."""
        remaining = ButlerProtocol.get_remaining_contacts()
        assert remaining == 5
    
    def test_can_contact_initially_true(self):
        """Should be able to contact when budget is full."""
        assert ButlerProtocol.can_contact("update") is True
        assert ButlerProtocol.can_contact("clarification") is True
    
    def test_record_contact_decreases_budget(self):
        """Recording a contact should decrease remaining budget."""
        initial = ButlerProtocol.get_remaining_contacts()
        ButlerProtocol.record_contact("update", "Test message")
        after = ButlerProtocol.get_remaining_contacts()
        assert after == initial - 1
    
    def test_max_3_updates_per_week(self):
        """Should only allow 3 updates per week."""
        for i in range(3):
            assert ButlerProtocol.can_contact("update") is True
            ButlerProtocol.record_contact("update", f"Update {i}")
        
        # 4th update should be blocked
        assert ButlerProtocol.can_contact("update") is False
    
    def test_max_2_clarifications_per_week(self):
        """Should only allow 2 clarifications per week."""
        for i in range(2):
            assert ButlerProtocol.can_contact("clarification") is True
            ButlerProtocol.record_contact("clarification", f"Clarification {i}")
        
        # 3rd clarification should be blocked
        assert ButlerProtocol.can_contact("clarification") is False
    
    def test_total_budget_enforced(self):
        """Total contacts should not exceed 5."""
        # Use 3 updates
        for i in range(3):
            ButlerProtocol.record_contact("update", f"Update {i}")
        
        # Use 2 clarifications
        for i in range(2):
            ButlerProtocol.record_contact("clarification", f"Clarification {i}")
        
        # Should be at 0 remaining
        assert ButlerProtocol.get_remaining_contacts() == 0
        assert ButlerProtocol.can_contact("update") is False
        assert ButlerProtocol.can_contact("clarification") is False
    
    def test_record_contact_returns_none_when_budget_exceeded(self):
        """record_contact should return None when budget exceeded."""
        # Exhaust budget
        for i in range(5):
            ButlerProtocol.record_contact("update", f"Message {i}")
        
        # Next should return None
        result = ButlerProtocol.record_contact("update", "Should fail")
        assert result is None
    
    def test_get_budget_status(self):
        """get_budget_status should return complete status dict."""
        ButlerProtocol.record_contact("update", "Test")
        
        status = ButlerProtocol.get_budget_status()
        assert "week" in status
        assert "year" in status
        assert "total_remaining" in status
        assert status["updates_sent"] == 1
        assert status["total_remaining"] == 4
    
    def test_get_butler_status_string(self):
        """get_butler_status_message should return formatted string."""
        status_str = get_butler_status_message()
        assert "Butler Status" in status_str
        assert "Contacts used" in status_str  # v0.6.0: changed to "X/5 used" format
    
    def test_get_butler_status_dict(self):
        """get_butler_status should return dict with budget info."""
        status = get_butler_status()
        assert isinstance(status, dict)
        assert 'remaining' in status
        assert 'budget' in status
        assert status['budget'] == 5
    
    def test_contacts_tracked_per_week(self):
        """Different weeks should have separate budgets."""
        week, year = ButlerProtocol.get_current_week()
        
        # Record contact this week
        ButlerProtocol.record_contact("update", "This week")
        
        # Check a different week (manually query)
        other_week = week + 1 if week < 52 else 1
        other_year = year if week < 52 else year + 1
        
        remaining_other = ButlerProtocol.get_remaining_contacts(other_week, other_year)
        assert remaining_other == 5  # Other week should be full


class TestUpdateMessages:
    """Test update message generation."""
    
    def test_generate_update_message_empty(self):
        """Update with no data should still generate valid message."""
        msg = generate_update_message()
        assert "Update" in msg
        assert "Today" in msg
    
    def test_generate_update_includes_overdue(self):
        """Update should include overdue tasks."""
        task_service.create_task(
            "Overdue task",
            due_date=date.today() - timedelta(days=2)
        )
        
        msg = generate_update_message()
        assert "OVERDUE" in msg
        assert "Overdue task" in msg
    
    def test_generate_update_includes_today(self):
        """Update should include tasks due today."""
        task_service.create_task(
            "Today's task",
            due_date=date.today()
        )
        
        msg = generate_update_message()
        assert "Today" in msg
        assert "Today's task" in msg
    
    def test_generate_update_includes_this_week(self):
        """Update should include tasks due this week."""
        # Create task for tomorrow (if not Sunday)
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task(
            "This week task",
            due_date=tomorrow
        )
        
        msg = generate_update_message()
        # Message should have This Week section if tasks exist
        due_week = get_tasks_due_this_week()
        if due_week:
            assert "This Week" in msg
    
    def test_get_overdue_tasks(self):
        """get_overdue_tasks should return overdue tasks."""
        task_service.create_task("Overdue", due_date=date.today() - timedelta(days=1))
        task_service.create_task("Not overdue", due_date=date.today() + timedelta(days=1))
        
        overdue = get_overdue_tasks()
        assert len(overdue) == 1
        assert overdue[0]["name"] == "Overdue"
    
    def test_get_tasks_due_today(self):
        """get_tasks_due_today should return today's tasks."""
        task_service.create_task("Today", due_date=date.today())
        task_service.create_task("Tomorrow", due_date=date.today() + timedelta(days=1))
        
        today_tasks = get_tasks_due_today()
        assert len(today_tasks) == 1
        assert today_tasks[0]["name"] == "Today"
    
    def test_get_unclear_tasks_count(self):
        """get_unclear_tasks_count should count unclear-tagged tasks."""
        task_service.create_task("Clear task")
        task_service.create_task("Unclear task", tags=["unclear"])
        
        count = get_unclear_tasks_count()
        assert count == 1
    
    def test_generate_brief_update(self):
        """generate_brief_update should return short summary."""
        task_service.create_task("Task", due_date=date.today())
        
        brief = generate_brief_update()
        assert len(brief) < 200
        assert "due today" in brief.lower()


class TestClarificationQueue:
    """Test clarification question queue."""
    
    def test_add_question(self):
        """Should be able to add a clarification question."""
        task = task_service.create_task("Test task")
        
        qid = ClarificationQueue.add_question(
            task.id,
            "When is this due?",
            options=["Today", "Tomorrow", "Next week"]
        )
        
        assert qid is not None
        assert qid > 0
    
    def test_get_pending_questions(self):
        """Should retrieve pending questions."""
        task = task_service.create_task("Test task")
        ClarificationQueue.add_question(task.id, "Question 1?")
        ClarificationQueue.add_question(task.id, "Question 2?")
        
        questions = ClarificationQueue.get_pending_questions()
        assert len(questions) == 2
    
    def test_questions_ordered_by_priority(self):
        """Higher priority questions should come first."""
        task = task_service.create_task("Test task")
        ClarificationQueue.add_question(task.id, "Low priority", priority=1)
        ClarificationQueue.add_question(task.id, "High priority", priority=10)
        
        questions = ClarificationQueue.get_pending_questions()
        assert questions[0].question == "High priority"
    
    def test_mark_answered(self):
        """Answered questions should not appear in pending."""
        task = task_service.create_task("Test task")
        qid = ClarificationQueue.add_question(task.id, "Question?")
        
        ClarificationQueue.mark_answered(qid, "The answer")
        
        pending = ClarificationQueue.get_pending_questions()
        assert len(pending) == 0
    
    def test_has_pending_questions(self):
        """has_pending_questions should return correct boolean."""
        assert ClarificationQueue.has_pending_questions() is False
        
        task = task_service.create_task("Test task")
        ClarificationQueue.add_question(task.id, "Question?")
        
        assert ClarificationQueue.has_pending_questions() is True
    
    def test_get_pending_count(self):
        """get_pending_count should return correct count."""
        task = task_service.create_task("Test task")
        
        assert ClarificationQueue.get_pending_count() == 0
        
        ClarificationQueue.add_question(task.id, "Q1?")
        ClarificationQueue.add_question(task.id, "Q2?")
        
        assert ClarificationQueue.get_pending_count() == 2
    
    def test_delete_question(self):
        """delete_question should remove the question."""
        task = task_service.create_task("Test task")
        qid = ClarificationQueue.add_question(task.id, "Question?")
        
        ClarificationQueue.delete_question(qid)
        
        assert ClarificationQueue.get_pending_count() == 0
    
    def test_delete_questions_for_task(self):
        """delete_questions_for_task should remove all task questions."""
        task = task_service.create_task("Test task")
        ClarificationQueue.add_question(task.id, "Q1?")
        ClarificationQueue.add_question(task.id, "Q2?")
        
        ClarificationQueue.delete_questions_for_task(task.id)
        
        assert ClarificationQueue.get_pending_count() == 0
    
    def test_generate_clarification_message(self):
        """generate_clarification_message should format questions."""
        task = task_service.create_task("My task")
        ClarificationQueue.add_question(
            task.id,
            "When is this due?",
            options=["Today", "Tomorrow"]
        )
        
        msg = generate_clarification_message()
        
        assert msg is not None
        assert "Quick Questions" in msg
        assert "My task" in msg
        assert "When is this due?" in msg
    
    def test_generate_clarification_message_empty(self):
        """generate_clarification_message should return None if no questions."""
        msg = generate_clarification_message()
        assert msg is None
    
    def test_mark_asked(self):
        """mark_asked should update asked_at timestamp."""
        task = task_service.create_task("Test task")
        qid = ClarificationQueue.add_question(task.id, "Question?")
        
        ClarificationQueue.mark_asked([qid])
        
        with get_db() as conn:
            row = conn.execute(
                "SELECT asked_at FROM clarification_queue WHERE id = ?",
                (qid,)
            ).fetchone()
            assert row["asked_at"] is not None


class TestClarificationResponseParsing:
    """Test parsing of user clarification responses."""
    
    def test_parse_colon_format(self):
        """Should parse '1: answer' format."""
        result = parse_clarification_response("1: tomorrow")
        assert result == (1, "tomorrow")
    
    def test_parse_dash_format(self):
        """Should parse '1 - answer' format."""
        result = parse_clarification_response("2 - next week")
        assert result == (2, "next week")
    
    def test_parse_dot_format(self):
        """Should parse '1. answer' format."""
        result = parse_clarification_response("3. call her at noon")
        assert result == (3, "call her at noon")
    
    def test_parse_space_format(self):
        """Should parse '1 answer' format."""
        result = parse_clarification_response("1 do it today")
        assert result == (1, "do it today")
    
    def test_parse_invalid_returns_none(self):
        """Should return None for non-clarification responses."""
        assert parse_clarification_response("buy milk") is None
        assert parse_clarification_response("hello") is None
        assert parse_clarification_response("") is None


class TestButlerIntegration:
    """Test integration between butler components."""
    
    def test_update_uses_budget(self):
        """Sending update should use budget correctly."""
        initial = ButlerProtocol.get_remaining_contacts()
        
        msg = generate_update_message()
        ButlerProtocol.record_contact("update", msg[:100])
        
        assert ButlerProtocol.get_remaining_contacts() == initial - 1
    
    def test_clarification_uses_budget(self):
        """Sending clarification should use budget correctly."""
        task = task_service.create_task("Test")
        ClarificationQueue.add_question(task.id, "Question?")
        
        initial = ButlerProtocol.get_remaining_contacts()
        
        msg = generate_clarification_message()
        if msg:
            ButlerProtocol.record_contact("clarification", msg[:100])
        
        assert ButlerProtocol.get_remaining_contacts() == initial - 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
