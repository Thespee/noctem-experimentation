"""
Tests for service layer.
"""
import pytest
from datetime import date, timedelta
import tempfile
import os

# Override DB path before importing
from .. import db
_original_db_path = db.DB_PATH


@pytest.fixture(autouse=True)
def setup_test_db():
    """Use a temporary database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db.DB_PATH = db.Path(tmpdir) / "test.db"
        db.init_db()
        yield
        db.DB_PATH = _original_db_path


class TestTaskService:
    def test_create_task(self):
        from ..services import task_service
        
        task = task_service.create_task("Test task")
        assert task.id is not None
        assert task.name == "Test task"
        assert task.status == "not_started"
    
    def test_create_task_with_date(self):
        from ..services import task_service
        
        tomorrow = date.today() + timedelta(days=1)
        task = task_service.create_task("Task with date", due_date=tomorrow)
        assert task.due_date == tomorrow
    
    def test_complete_task(self):
        from ..services import task_service
        
        task = task_service.create_task("Task to complete")
        completed = task_service.complete_task(task.id)
        assert completed.status == "done"
        assert completed.completed_at is not None
    
    def test_skip_task(self):
        from ..services import task_service
        
        task = task_service.create_task("Task to skip", due_date=date.today())
        skipped = task_service.skip_task(task.id)
        assert skipped.due_date == date.today() + timedelta(days=1)
    
    def test_get_tasks_due_today(self):
        from ..services import task_service
        
        task_service.create_task("Today task", due_date=date.today())
        task_service.create_task("Tomorrow task", due_date=date.today() + timedelta(days=1))
        
        today_tasks = task_service.get_tasks_due_today()
        assert len(today_tasks) == 1
        assert today_tasks[0].name == "Today task"
    
    def test_get_priority_tasks(self):
        from ..services import task_service
        
        task_service.create_task("High importance", due_date=date.today(), importance=1.0)
        task_service.create_task("Low importance", due_date=date.today(), importance=0.0)
        
        priority_tasks = task_service.get_priority_tasks(5)
        assert len(priority_tasks) >= 1
        # Higher importance (1.0) should come first
        assert priority_tasks[0].importance == 1.0


class TestHabitService:
    def test_create_habit(self):
        from ..services import habit_service
        
        habit = habit_service.create_habit("Exercise")
        assert habit.id is not None
        assert habit.name == "Exercise"
        assert habit.frequency == "daily"
    
    def test_log_habit(self):
        from ..services import habit_service
        
        habit = habit_service.create_habit("Meditate")
        log = habit_service.log_habit(habit.id)
        assert log.habit_id == habit.id
    
    def test_is_habit_done_today(self):
        from ..services import habit_service
        
        habit = habit_service.create_habit("Read")
        assert not habit_service.is_habit_done_today(habit.id)
        
        habit_service.log_habit(habit.id)
        assert habit_service.is_habit_done_today(habit.id)
    
    def test_habit_stats(self):
        from ..services import habit_service
        
        habit = habit_service.create_habit("Journal")
        habit_service.log_habit(habit.id)
        
        stats = habit_service.get_habit_stats(habit.id)
        assert stats["name"] == "Journal"
        assert stats["done_today"] == True
        assert stats["completions_this_week"] >= 1


class TestProjectService:
    def test_create_project(self):
        from ..services import project_service
        
        project = project_service.create_project("Test Project")
        assert project.id is not None
        assert project.name == "Test Project"
        assert project.status == "in_progress"
    
    def test_get_active_projects(self):
        from ..services import project_service
        
        project_service.create_project("Active Project")
        project = project_service.create_project("Done Project")
        project_service.complete_project(project.id)
        
        active = project_service.get_active_projects()
        assert len(active) == 1
        assert active[0].name == "Active Project"


class TestGoalService:
    def test_create_goal(self):
        from ..services import goal_service
        
        goal = goal_service.create_goal("Learn Python")
        assert goal.id is not None
        assert goal.name == "Learn Python"
    
    def test_archive_goal(self):
        from ..services import goal_service
        
        goal = goal_service.create_goal("Old Goal")
        archived = goal_service.archive_goal(goal.id)
        assert archived.archived == True
        
        # Should not appear in default list
        goals = goal_service.get_all_goals()
        assert all(g.id != goal.id for g in goals)


class TestBriefing:
    def test_generate_briefing(self):
        from ..services import task_service
        from ..services.briefing import generate_morning_briefing
        
        task_service.create_task("Important task", due_date=date.today(), importance=1.0)
        
        briefing = generate_morning_briefing()
        assert "Good morning" in briefing
        assert "Important task" in briefing
