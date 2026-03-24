"""
Tests for Noctem v0.6.0 Phase 3: Slow Mode.
Tests cover:
- Ollama client and graceful degradation
- Task analyzer
- Project analyzer
- Work queue with dependencies
- Slow mode loop

Note: LLM tests are mocked since Ollama may not be available.
"""
import pytest
import tempfile
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

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
from noctem.slow.ollama import OllamaClient, GracefulDegradation, llm_available, llm_generate
from noctem.slow.queue import SlowWorkQueue, WorkType, WorkStatus
from noctem.slow.task_analyzer import (
    analyze_task_for_computer_help, save_task_suggestion,
    get_tasks_needing_analysis, get_task_suggestion, clear_task_suggestion
)
from noctem.slow.project_analyzer import (
    analyze_project_for_next_action, save_project_suggestion,
    get_projects_needing_analysis, get_project_suggestion
)
from noctem.slow.loop import (
    SlowModeLoop, record_user_activity, get_last_activity,
    get_slow_mode_status, get_slow_mode_status_message
)


@pytest.fixture(autouse=True)
def setup_db():
    """Set up fresh database for each test."""
    db.DB_PATH = Path(TEST_DB)
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    init_db()
    Config.clear_cache()
    yield
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


class TestOllamaClient:
    """Test Ollama client functionality."""
    
    def test_client_initialization(self):
        """Client should initialize with config defaults."""
        client = OllamaClient()
        assert client.host is not None
        assert client.model is not None
        assert client.timeout > 0
    
    def test_client_custom_params(self):
        """Client should accept custom parameters."""
        client = OllamaClient(
            host="http://custom:1234",
            model="custom-model",
            timeout=120.0
        )
        assert client.host == "http://custom:1234"
        assert client.model == "custom-model"
        assert client.timeout == 120.0
    
    @patch('httpx.Client')
    def test_health_check_healthy(self, mock_client):
        """Health check should return True when Ollama responds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        client = OllamaClient()
        result = client.check_health(use_cache=False)
        assert result is True
    
    @patch('httpx.Client')
    def test_health_check_unhealthy(self, mock_client):
        """Health check should return False when Ollama doesn't respond."""
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("Connection error")
        
        client = OllamaClient()
        result = client.check_health(use_cache=False)
        assert result is False
    
    @patch('noctem.slow.ollama.OllamaClient.check_health', return_value=True)
    @patch('httpx.Client')
    def test_generate_returns_response(self, mock_client, mock_health):
        """Generate should return LLM response."""
        # Mock generate response
        gen_response = MagicMock()
        gen_response.status_code = 200
        gen_response.json.return_value = {"response": "Test suggestion"}
        
        mock_client.return_value.__enter__.return_value.post.return_value = gen_response
        
        client = OllamaClient()
        result = client.generate("Test prompt")
        assert result == "Test suggestion"


class TestGracefulDegradation:
    """Test graceful degradation functionality."""
    
    @patch.object(OllamaClient, 'check_health', return_value=True)
    @patch.object(OllamaClient, 'is_model_available', return_value=True)
    def test_full_status_when_healthy(self, mock_model, mock_health):
        """Should return 'full' when everything is working."""
        status = GracefulDegradation.get_system_status()
        assert status == GracefulDegradation.FULL
    
    @patch.object(OllamaClient, 'check_health', return_value=False)
    def test_degraded_status_when_unhealthy(self, mock_health):
        """Should return 'degraded' when Ollama unavailable."""
        status = GracefulDegradation.get_system_status()
        assert status == GracefulDegradation.DEGRADED
    
    def test_status_message_not_empty(self):
        """Status message should contain useful info."""
        msg = GracefulDegradation.get_status_message()
        assert len(msg) > 0
        assert "Full" in msg or "Degraded" in msg or "Offline" in msg


class TestSlowWorkQueue:
    """Test slow work queue functionality."""
    
    def test_add_item_returns_id(self):
        """Adding an item should return its ID."""
        task = task_service.create_task("Test task")
        
        item_id = SlowWorkQueue.add_item(
            WorkType.TASK_COMPUTER_HELP.value,
            task.id
        )
        
        assert item_id > 0
    
    def test_duplicate_item_returns_existing(self):
        """Adding duplicate item should return existing ID."""
        task = task_service.create_task("Test task")
        
        id1 = SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        id2 = SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        
        assert id1 == id2
    
    def test_get_next_item_pending(self):
        """get_next_item should return pending items."""
        task = task_service.create_task("Test task")
        SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        
        item = SlowWorkQueue.get_next_item()
        
        assert item is not None
        assert item.work_type == WorkType.TASK_COMPUTER_HELP.value
        assert item.target_id == task.id
    
    def test_get_next_item_respects_dependencies(self):
        """Items with unfulfilled dependencies should not be returned."""
        task = task_service.create_task("Test task")
        project = project_service.create_project("Test project")
        
        # Add task analysis
        task_item_id = SlowWorkQueue.add_item(
            WorkType.TASK_COMPUTER_HELP.value, task.id
        )
        
        # Add project analysis depending on task analysis
        SlowWorkQueue.add_item(
            WorkType.PROJECT_NEXT_ACTION.value, 
            project.id,
            depends_on_id=task_item_id
        )
        
        # First item should be task analysis (no dependencies)
        item = SlowWorkQueue.get_next_item()
        assert item.work_type == WorkType.TASK_COMPUTER_HELP.value
    
    def test_mark_processing(self):
        """mark_processing should update status."""
        task = task_service.create_task("Test task")
        item_id = SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        
        SlowWorkQueue.mark_processing(item_id)
        
        # Should no longer appear in get_next_item
        next_item = SlowWorkQueue.get_next_item()
        assert next_item is None or next_item.id != item_id
    
    def test_mark_completed(self):
        """mark_completed should update status and result."""
        task = task_service.create_task("Test task")
        item_id = SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        
        SlowWorkQueue.mark_completed(item_id, "Test result")
        
        status = SlowWorkQueue.get_queue_status()
        assert status["completed"] >= 1
    
    def test_mark_failed(self):
        """mark_failed should update status and error."""
        task = task_service.create_task("Test task")
        item_id = SlowWorkQueue.add_item(WorkType.TASK_COMPUTER_HELP.value, task.id)
        
        SlowWorkQueue.mark_failed(item_id, "Test error")
        
        status = SlowWorkQueue.get_queue_status()
        assert status["failed"] >= 1
    
    def test_get_queue_status(self):
        """get_queue_status should return counts."""
        status = SlowWorkQueue.get_queue_status()
        
        assert "pending" in status
        assert "processing" in status
        assert "completed" in status
        assert "failed" in status
    
    def test_dependency_fulfilled_unlocks_item(self):
        """Completing dependency should unlock dependent item."""
        task = task_service.create_task("Test task")
        project = project_service.create_project("Test project")
        
        # Add items with dependency
        task_item_id = SlowWorkQueue.add_item(
            WorkType.TASK_COMPUTER_HELP.value, task.id
        )
        SlowWorkQueue.add_item(
            WorkType.PROJECT_NEXT_ACTION.value, 
            project.id,
            depends_on_id=task_item_id
        )
        
        # Complete task analysis
        SlowWorkQueue.mark_completed(task_item_id, "Done")
        
        # Now project analysis should be available
        item = SlowWorkQueue.get_next_item()
        assert item is not None
        assert item.work_type == WorkType.PROJECT_NEXT_ACTION.value


class TestTaskAnalyzer:
    """Test task analyzer functionality."""
    
    def test_get_tasks_needing_analysis(self):
        """Should return tasks without suggestions."""
        task1 = task_service.create_task("Needs analysis")
        task2 = task_service.create_task("Already analyzed")
        
        # Save suggestion for task2
        save_task_suggestion(task2.id, "Test suggestion")
        
        tasks = get_tasks_needing_analysis()
        task_ids = [t.id for t in tasks]
        
        assert task1.id in task_ids
        assert task2.id not in task_ids
    
    def test_save_task_suggestion(self):
        """save_task_suggestion should store the suggestion."""
        task = task_service.create_task("Test task")
        
        save_task_suggestion(task.id, "Could set a reminder")
        
        suggestion = get_task_suggestion(task.id)
        assert suggestion == "Could set a reminder"
    
    def test_clear_task_suggestion(self):
        """clear_task_suggestion should remove the suggestion."""
        task = task_service.create_task("Test task")
        save_task_suggestion(task.id, "Old suggestion")
        
        clear_task_suggestion(task.id)
        
        suggestion = get_task_suggestion(task.id)
        assert suggestion is None
    
    @patch('noctem.slow.task_analyzer.llm_generate')
    def test_analyze_task_calls_llm(self, mock_llm):
        """analyze_task_for_computer_help should call LLM."""
        mock_llm.return_value = "Test suggestion"
        task = task_service.create_task("Buy groceries")
        
        result = analyze_task_for_computer_help(task)
        
        assert result == "Test suggestion"
        assert mock_llm.called


class TestProjectAnalyzer:
    """Test project analyzer functionality."""
    
    def test_get_projects_needing_analysis(self):
        """Should return projects without suggestions."""
        project1 = project_service.create_project("Needs analysis")
        project2 = project_service.create_project("Already analyzed")
        
        # Save suggestion for project2
        save_project_suggestion(project2.id, "Do the first task")
        
        projects = get_projects_needing_analysis()
        project_ids = [p.id for p in projects]
        
        assert project1.id in project_ids
        assert project2.id not in project_ids
    
    def test_save_project_suggestion(self):
        """save_project_suggestion should store the suggestion."""
        project = project_service.create_project("Test project")
        
        save_project_suggestion(project.id, "Start with task A")
        
        suggestion = get_project_suggestion(project.id)
        assert suggestion == "Start with task A"
    
    @patch('noctem.slow.project_analyzer.llm_generate')
    def test_analyze_project_calls_llm(self, mock_llm):
        """analyze_project_for_next_action should call LLM."""
        mock_llm.return_value = "Do the first task"
        project = project_service.create_project("Home Renovation")
        task_service.create_task("Buy paint", project_id=project.id)
        
        result = analyze_project_for_next_action(project)
        
        assert result == "Do the first task"
        assert mock_llm.called


class TestSlowModeLoop:
    """Test slow mode loop functionality."""
    
    def test_record_user_activity(self):
        """record_user_activity should update timestamp."""
        old_time = get_last_activity()
        
        import time
        time.sleep(0.1)
        record_user_activity()
        
        new_time = get_last_activity()
        assert new_time > old_time
    
    def test_get_slow_mode_status(self):
        """get_slow_mode_status should return status dict."""
        status = get_slow_mode_status()
        
        assert "enabled" in status
        assert "system_status" in status
        assert "can_run" in status
        assert "user_idle" in status
        assert "queue" in status
    
    def test_get_slow_mode_status_message(self):
        """get_slow_mode_status_message should return string."""
        msg = get_slow_mode_status_message()
        
        assert len(msg) > 0
        assert "Slow Mode" in msg
    
    def test_loop_initialization(self):
        """SlowModeLoop should initialize with defaults."""
        loop = SlowModeLoop()
        
        assert loop.check_interval == 60
        assert loop._running is False
    
    def test_loop_custom_interval(self):
        """SlowModeLoop should accept custom interval."""
        loop = SlowModeLoop(check_interval=30)
        
        assert loop.check_interval == 30


class TestSlowModeIntegration:
    """Integration tests for slow mode components."""
    
    def test_task_to_queue_to_analysis(self):
        """Task should be queued and analyzed."""
        task = task_service.create_task("Integration test task")
        
        # Queue it
        item_id = SlowWorkQueue.queue_task_analysis(task.id)
        assert item_id > 0
        
        # Verify in queue
        item = SlowWorkQueue.get_next_item()
        assert item is not None
        assert item.target_id == task.id
    
    def test_project_depends_on_tasks(self):
        """Project analysis should depend on task analyses."""
        project = project_service.create_project("Test Project")
        task = task_service.create_task("Task in project", project_id=project.id)
        
        # Queue task analysis
        task_item_id = SlowWorkQueue.queue_task_analysis(task.id)
        
        # Queue project analysis with dependency
        project_item_id = SlowWorkQueue.queue_project_analysis(
            project.id, 
            after_task_items=[task_item_id]
        )
        
        # First available should be task
        first = SlowWorkQueue.get_next_item()
        assert first.work_type == WorkType.TASK_COMPUTER_HELP.value
        
        # Complete task analysis
        SlowWorkQueue.mark_completed(task_item_id)
        
        # Now project should be available
        second = SlowWorkQueue.get_next_item()
        assert second.work_type == WorkType.PROJECT_NEXT_ACTION.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
