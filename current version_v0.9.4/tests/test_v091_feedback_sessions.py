"""
Tests for v0.9.1 feedback sessions — Butler-driven task disambiguation.
"""
import pytest
from datetime import datetime, timedelta
from noctem.butler.feedback import (
    create_session, get_session_by_id, start_session, complete_session,
    ensure_upcoming_session, get_next_session,
    get_session_questions, get_pending_questions,
    answer_question, skip_question, get_session_status,
)
from noctem.models import FeedbackSession, FeedbackQuestion
from noctem.services import task_service


class TestSessionLifecycle:
    """Test creating, starting, and completing sessions."""

    def test_create_session(self):
        scheduled = datetime.now() + timedelta(days=1)
        session = create_session(scheduled_for=scheduled, session_type="scheduled")
        assert session is not None
        assert session.id is not None
        assert session.status == "pending"
        assert session.session_type == "scheduled"

    def test_get_session_by_id(self):
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        found = get_session_by_id(session.id)
        assert found is not None
        assert found.id == session.id

    def test_start_session_sets_active(self):
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        started = start_session(session.id)
        assert started.status == "active"
        assert started.started_at is not None

    def test_complete_session(self):
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        completed = complete_session(session.id)
        assert completed.status == "completed"
        assert completed.completed_at is not None


class TestEnsureUpcomingSession:
    """Test that ensure_upcoming_session always creates one."""

    def test_creates_session_when_none_exist(self):
        session = ensure_upcoming_session()
        assert session is not None
        assert session.status == "pending"
        assert session.scheduled_for is not None

    def test_returns_existing_if_present(self):
        first = ensure_upcoming_session()
        second = ensure_upcoming_session()
        assert first.id == second.id

    def test_get_next_session_returns_pending(self):
        ensure_upcoming_session()
        next_sess = get_next_session()
        assert next_sess is not None
        assert next_sess.status == "pending"


class TestQuestionGeneration:
    """Test that starting a session generates appropriate questions."""

    def test_generates_questions_for_tasks_without_due_date(self):
        # Create a task without due date
        task = task_service.create_task("Vague task")
        
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        
        questions = get_session_questions(session.id)
        # Should have at least one question about due date
        due_date_q = [q for q in questions if "due" in q.question_text.lower()]
        assert len(due_date_q) >= 1

    def test_generates_questions_for_tasks_without_project(self):
        task = task_service.create_task("Orphan task")
        
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        
        questions = get_session_questions(session.id)
        project_q = [q for q in questions if "project" in q.question_text.lower()]
        assert len(project_q) >= 1

    def test_generates_questions_for_short_task_names(self):
        task = task_service.create_task("Do it")
        
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        
        questions = get_session_questions(session.id)
        clarify_q = [q for q in questions if "clarify" in q.question_text.lower()]
        assert len(clarify_q) >= 1

    def test_caps_questions_at_ten(self):
        # Create many tasks that will trigger questions
        for i in range(15):
            task_service.create_task(f"x{i}")
        
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        
        questions = get_session_questions(session.id)
        assert len(questions) <= 10


class TestQuestionAnswering:
    """Test answering and skipping questions."""

    def _setup_session_with_questions(self):
        task_service.create_task("Review PR")
        session = create_session(
            scheduled_for=datetime.now() + timedelta(days=1)
        )
        start_session(session.id)
        return session

    def test_answer_question(self):
        session = self._setup_session_with_questions()
        questions = get_pending_questions(session.id)
        assert len(questions) > 0
        
        q = questions[0]
        answered = answer_question(q.id, "Next Friday")
        assert answered.status == "answered"
        assert answered.answer_text == "Next Friday"

    def test_skip_question(self):
        session = self._setup_session_with_questions()
        questions = get_pending_questions(session.id)
        assert len(questions) > 0
        
        q = questions[0]
        skipped = skip_question(q.id)
        assert skipped.status == "skipped"

    def test_pending_questions_decreases_after_answer(self):
        session = self._setup_session_with_questions()
        initial = get_pending_questions(session.id)
        count_before = len(initial)
        
        if count_before > 0:
            answer_question(initial[0].id, "Tomorrow")
            remaining = get_pending_questions(session.id)
            assert len(remaining) == count_before - 1


class TestSessionStatus:
    """Test the session status dict for Butler widget."""

    def test_status_with_no_sessions(self):
        status = get_session_status()
        assert status["next_session"] is None
        assert status["next_session_id"] is None
        assert status["total_pending_questions"] == 0

    def test_status_with_upcoming_session(self):
        ensure_upcoming_session()
        status = get_session_status()
        assert status["next_session"] is not None
        assert status["next_session_id"] is not None

    def test_complete_session_ensures_next(self):
        """Completing a session should auto-create the next one."""
        session = ensure_upcoming_session()
        start_session(session.id)
        complete_session(session.id)
        
        # Should have a new pending session
        next_sess = get_next_session()
        assert next_sess is not None
        assert next_sess.id != session.id
