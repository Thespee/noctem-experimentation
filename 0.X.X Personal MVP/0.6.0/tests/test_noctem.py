"""
Comprehensive tests for Noctem 0.5
"""
import pytest
import tempfile
import os
from datetime import date, time, timedelta
from pathlib import Path

# Import noctem modules - DB path is handled by conftest.py
from noctem import db
from noctem.db import get_db, init_db
from noctem.models import Task, Project, Goal
from noctem.services import task_service, project_service, goal_service
from noctem.services.briefing import generate_morning_briefing, generate_today_view, generate_week_view
from noctem.parser.task_parser import parse_task, parse_importance
from noctem.parser.command import parse_command, CommandType
from noctem.parser.natural_date import parse_datetime
from noctem.session import get_session, Session, SessionMode
from noctem.handlers.interactive import (
    start_prioritize_mode, handle_prioritize_input,
    start_update_mode, handle_update_input,
    handle_correction,
)


# Database setup is handled by conftest.py fixtures


class TestModels:
    """Test model classes."""
    
    def test_task_urgency_overdue(self):
        """Overdue tasks should have urgency 1.0."""
        task = Task(
            id=1, name="Test", status="not_started",
            due_date=date.today() - timedelta(days=1),
            importance=0.5
        )
        assert task.urgency == 1.0
    
    def test_task_urgency_today(self):
        """Tasks due today should have urgency 1.0."""
        task = Task(
            id=1, name="Test", status="not_started",
            due_date=date.today(),
            importance=0.5
        )
        assert task.urgency == 1.0
    
    def test_task_urgency_tomorrow(self):
        """Tasks due tomorrow should have urgency 0.9."""
        task = Task(
            id=1, name="Test", status="not_started",
            due_date=date.today() + timedelta(days=1),
            importance=0.5
        )
        assert task.urgency == 0.9
    
    def test_task_urgency_no_date(self):
        """Tasks with no due date should have urgency 0.0."""
        task = Task(id=1, name="Test", status="not_started", importance=0.5)
        assert task.urgency == 0.0
    
    def test_task_priority_score(self):
        """Priority score should combine importance and urgency."""
        task = Task(
            id=1, name="Test", status="not_started",
            due_date=date.today(),  # urgency = 1.0
            importance=1.0
        )
        # (1.0 * 0.6) + (1.0 * 0.4) = 1.0
        assert task.priority_score == 1.0
    
    def test_task_priority_score_medium(self):
        """Medium importance + no urgency."""
        task = Task(
            id=1, name="Test", status="not_started",
            importance=0.5
        )
        # (0.5 * 0.6) + (0.0 * 0.4) = 0.3
        assert task.priority_score == 0.3


class TestTaskParser:
    """Test task parsing."""
    
    def test_parse_importance_high(self):
        """!1 should map to 1.0."""
        importance, remaining = parse_importance("test !1")
        assert importance == 1.0
        assert "!1" not in remaining
    
    def test_parse_importance_medium(self):
        """!2 should map to 0.5."""
        importance, remaining = parse_importance("test !2")
        assert importance == 0.5
    
    def test_parse_importance_low(self):
        """!3 should map to 0.0."""
        importance, remaining = parse_importance("test !3")
        assert importance == 0.0
    
    def test_parse_task_with_date(self):
        """Parse task with due date."""
        parsed = parse_task("buy groceries tomorrow")
        assert "groceries" in parsed.name.lower()
        assert parsed.due_date == date.today() + timedelta(days=1)
    
    def test_parse_task_with_importance(self):
        """Parse task with importance."""
        parsed = parse_task("urgent task !1")
        assert parsed.importance == 1.0
    
    def test_parse_task_with_project(self):
        """Parse task with project."""
        parsed = parse_task("write code /myproject")
        assert parsed.project_name == "myproject"
    
    def test_parse_task_with_tags(self):
        """Parse task with tags."""
        parsed = parse_task("email boss #work #urgent")
        assert "work" in parsed.tags
        assert "urgent" in parsed.tags


class TestCommandParser:
    """Test command parsing."""
    
    def test_parse_today(self):
        cmd = parse_command("today")
        assert cmd.type == CommandType.TODAY
    
    def test_parse_done_number(self):
        cmd = parse_command("done 1")
        assert cmd.type == CommandType.DONE
        assert cmd.target_id == 1
    
    def test_parse_done_name(self):
        cmd = parse_command("done buy milk")
        assert cmd.type == CommandType.DONE
        assert cmd.target_name == "buy milk"
    
    def test_parse_delete(self):
        cmd = parse_command("delete some task")
        assert cmd.type == CommandType.DELETE
        assert cmd.target_name == "some task"
    
    def test_parse_remove_alias(self):
        """'remove' should work same as 'delete'."""
        cmd = parse_command("remove some task")
        assert cmd.type == CommandType.DELETE
        assert cmd.target_name == "some task"
    
    def test_parse_correction(self):
        """* prefix should trigger correction."""
        cmd = parse_command("* tomorrow !1")
        assert cmd.type == CommandType.CORRECT
        assert "tomorrow !1" in cmd.args[0]
    
    def test_parse_prioritize(self):
        cmd = parse_command("/prioritize 5")
        assert cmd.type == CommandType.PRIORITIZE
        assert "5" in cmd.args
    
    def test_parse_update(self):
        cmd = parse_command("/update 3")
        assert cmd.type == CommandType.UPDATE
        assert "3" in cmd.args
    
    def test_parse_new_task(self):
        cmd = parse_command("buy groceries tomorrow")
        assert cmd.type == CommandType.NEW_TASK


class TestTaskService:
    """Test task service."""
    
    def test_create_task(self):
        task = task_service.create_task("Test task")
        assert task.id is not None
        assert task.name == "Test task"
        assert task.importance == 0.5  # default
    
    def test_create_task_with_importance(self):
        task = task_service.create_task("Important", importance=1.0)
        assert task.importance == 1.0
    
    def test_create_task_with_due_date(self):
        tomorrow = date.today() + timedelta(days=1)
        task = task_service.create_task("Due tomorrow", due_date=tomorrow)
        assert task.due_date == tomorrow
    
    def test_get_task(self):
        created = task_service.create_task("Find me")
        found = task_service.get_task(created.id)
        assert found.name == "Find me"
    
    def test_get_task_by_name(self):
        task_service.create_task("Unique name xyz")
        found = task_service.get_task_by_name("xyz")
        assert found is not None
        assert "xyz" in found.name.lower()
    
    def test_get_priority_tasks(self):
        # Create tasks with different priorities
        task_service.create_task("High", importance=1.0, due_date=date.today())
        task_service.create_task("Low", importance=0.0)
        
        tasks = task_service.get_priority_tasks(5)
        assert len(tasks) >= 2
        # High priority should be first
        assert tasks[0].importance == 1.0
    
    def test_complete_task(self):
        task = task_service.create_task("Complete me")
        task_service.complete_task(task.id)
        updated = task_service.get_task(task.id)
        assert updated.status == "done"
    
    def test_update_task(self):
        task = task_service.create_task("Update me")
        task_service.update_task(task.id, importance=1.0)
        updated = task_service.get_task(task.id)
        assert updated.importance == 1.0
    
    def test_delete_task(self):
        task = task_service.create_task("Delete me")
        result = task_service.delete_task(task.id)
        assert result is True
        assert task_service.get_task(task.id) is None


class TestProjectService:
    """Test project service."""
    
    def test_create_project(self):
        project = project_service.create_project("Test Project")
        assert project.id is not None
        assert project.name == "Test Project"
    
    def test_create_project_with_goal(self):
        goal = goal_service.create_goal("Test Goal")
        project = project_service.create_project("Linked Project", goal_id=goal.id)
        assert project.goal_id == goal.id
    
    def test_get_project_by_name(self):
        project_service.create_project("Find This Project")
        found = project_service.get_project_by_name("This Project")
        assert found is not None


class TestGoalService:
    """Test goal service."""
    
    def test_create_goal(self):
        goal = goal_service.create_goal("Test Goal")
        assert goal.id is not None
        assert goal.name == "Test Goal"
    
    def test_create_goal_with_type(self):
        goal = goal_service.create_goal("Daily", goal_type="daily_goal")
        assert goal.type == "daily_goal"


class TestBriefing:
    """Test briefing generation."""
    
    def test_generate_today_view(self):
        view = generate_today_view()
        assert "Today" in view
    
    def test_generate_morning_briefing(self):
        briefing = generate_morning_briefing()
        assert "Good morning" in briefing
    
    def test_generate_week_view(self):
        view = generate_week_view()
        assert "Week" in view
    
    def test_briefing_shows_overdue(self):
        # Create an overdue task
        task_service.create_task(
            "Overdue task",
            due_date=date.today() - timedelta(days=1)
        )
        briefing = generate_morning_briefing()
        assert "OVERDUE" in briefing
    
    def test_briefing_shows_priorities(self):
        task_service.create_task("Priority task", importance=1.0)
        briefing = generate_morning_briefing()
        assert "PRIORITIES" in briefing


class TestSession:
    """Test session management."""
    
    def test_session_default_mode(self):
        session = get_session()
        session.reset()
        assert session.mode == SessionMode.NORMAL
    
    def test_session_set_last_entity(self):
        session = get_session()
        session.set_last_entity("task", 123)
        assert session.last_entity_type == "task"
        assert session.last_entity_id == 123


class TestInteractiveModes:
    """Test interactive modes."""
    
    def test_prioritize_mode_start(self):
        task_service.create_task("Task 1")
        task_service.create_task("Task 2")
        
        result = start_prioritize_mode(5)
        assert "Priority" in result
        
        session = get_session()
        assert session.mode == SessionMode.PRIORITIZE
    
    def test_prioritize_mode_exit(self):
        task_service.create_task("Task 1")
        start_prioritize_mode(5)
        
        response, exited = handle_prioritize_input("done")
        assert exited is True
        assert get_session().mode == SessionMode.NORMAL
    
    def test_update_mode_start(self):
        # Create task missing info
        task_service.create_task("No date task")
        
        result = start_update_mode(5)
        session = get_session()
        
        # Should either be in update mode or say everything is complete
        assert session.mode == SessionMode.UPDATE or "complete" in result.lower()
    
    def test_correction_no_last_entity(self):
        session = get_session()
        session.reset()
        session.last_entity_type = None
        session.last_entity_id = None
        
        result = handle_correction("tomorrow")
        assert "No recent" in result
    
    def test_correction_updates_task(self):
        task = task_service.create_task("Original task")
        
        session = get_session()
        session.set_last_entity("task", task.id)
        
        result = handle_correction("tomorrow !1")
        assert "Updated" in result
        
        updated = task_service.get_task(task.id)
        assert updated.due_date == date.today() + timedelta(days=1)
        assert updated.importance == 1.0


class TestNaturalDateParser:
    """Test natural date parsing."""
    
    def test_parse_today(self):
        result = parse_datetime("today")
        assert result.date == date.today()
    
    def test_parse_tomorrow(self):
        result = parse_datetime("tomorrow")
        assert result.date == date.today() + timedelta(days=1)
    
    def test_parse_time(self):
        result = parse_datetime("3pm")
        assert result.time is not None
        assert result.time.hour == 15


class TestIntegration:
    """Integration tests."""
    
    def test_full_workflow(self):
        """Test creating goal -> project -> task -> complete."""
        # Create goal
        goal = goal_service.create_goal("Test Goal")
        assert goal.id is not None
        
        # Create project under goal
        project = project_service.create_project("Test Project", goal_id=goal.id)
        assert project.goal_id == goal.id
        
        # Create task in project
        task = task_service.create_task(
            "Test Task",
            project_id=project.id,
            due_date=date.today(),
            importance=1.0
        )
        assert task.project_id == project.id
        
        # Verify in priority list
        priorities = task_service.get_priority_tasks(10)
        assert any(t.id == task.id for t in priorities)
        
        # Complete task
        task_service.complete_task(task.id)
        updated = task_service.get_task(task.id)
        assert updated.status == "done"
    
    def test_briefing_with_data(self):
        """Test briefing includes created data."""
        task_service.create_task(
            "Briefing Test Task",
            due_date=date.today(),
            importance=1.0
        )
        
        briefing = generate_morning_briefing()
        assert "Briefing Test Task" in briefing or "PRIORITIES" in briefing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
