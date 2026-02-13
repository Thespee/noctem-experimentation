#!/usr/bin/env python3
"""
Tests for the parent module.
Tests protocol, child_handler, improve, and scheduler components.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from parent.protocol import ParentCommand, ParentRequest, ParentResponse


class TestParentProtocol(unittest.TestCase):
    """Tests for parent/protocol.py"""
    
    def test_parent_command_values(self):
        """Test ParentCommand enum has expected values."""
        self.assertEqual(ParentCommand.STATUS.value, "status")
        self.assertEqual(ParentCommand.HISTORY.value, "history")
        self.assertEqual(ParentCommand.HEALTH.value, "health")
        self.assertEqual(ParentCommand.LOGS.value, "logs")
        self.assertEqual(ParentCommand.REPORT.value, "report")
        self.assertEqual(ParentCommand.APPROVE.value, "approve")
        self.assertEqual(ParentCommand.REJECT.value, "reject")
    
    def test_parent_request_creation(self):
        """Test creating a ParentRequest."""
        request = ParentRequest(
            command=ParentCommand.STATUS,
            params={"test": "value"}
        )
        
        self.assertEqual(request.command, ParentCommand.STATUS)
        self.assertEqual(request.params, {"test": "value"})
        self.assertIsNotNone(request.request_id)
        self.assertIsNotNone(request.timestamp)
    
    def test_parent_request_to_signal_message(self):
        """Test encoding ParentRequest to Signal message."""
        request = ParentRequest(
            command=ParentCommand.HISTORY,
            params={"limit": 10}
        )
        
        message = request.to_signal_message()
        
        self.assertTrue(message.startswith("/parent history"))
        self.assertIn('"limit": 10', message)
    
    def test_parent_request_from_signal_message_basic(self):
        """Test parsing ParentRequest from basic Signal message."""
        message = "/parent status"
        
        request = ParentRequest.from_signal_message(message)
        
        self.assertIsNotNone(request)
        self.assertEqual(request.command, ParentCommand.STATUS)
        self.assertEqual(request.params, {})
    
    def test_parent_request_from_signal_message_with_params(self):
        """Test parsing ParentRequest with parameters."""
        message = '/parent history {"limit": 20, "since_hours": 48}'
        
        request = ParentRequest.from_signal_message(message)
        
        self.assertIsNotNone(request)
        self.assertEqual(request.command, ParentCommand.HISTORY)
        self.assertEqual(request.params["limit"], 20)
        self.assertEqual(request.params["since_hours"], 48)
    
    def test_parent_request_from_invalid_message(self):
        """Test parsing invalid messages returns None."""
        self.assertIsNone(ParentRequest.from_signal_message("hello"))
        self.assertIsNone(ParentRequest.from_signal_message("/status"))
        self.assertIsNone(ParentRequest.from_signal_message("/parent"))
        self.assertIsNone(ParentRequest.from_signal_message("/parent invalid_command"))
    
    def test_parent_request_roundtrip(self):
        """Test encoding and decoding a request."""
        original = ParentRequest(
            command=ParentCommand.HEALTH,
            params={"detailed": True}
        )
        
        message = original.to_signal_message()
        parsed = ParentRequest.from_signal_message(message)
        
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.command, original.command)
        self.assertEqual(parsed.params, original.params)
    
    def test_parent_response_success(self):
        """Test creating a success response."""
        response = ParentResponse(
            request_id="abc123",
            success=True,
            data={"status": {"state": "running"}}
        )
        
        self.assertTrue(response.success)
        self.assertIsNone(response.error)
        self.assertEqual(response.data["status"]["state"], "running")
    
    def test_parent_response_error(self):
        """Test creating an error response."""
        response = ParentResponse(
            request_id="abc123",
            success=False,
            data={},
            error="Something went wrong"
        )
        
        self.assertFalse(response.success)
        self.assertEqual(response.error, "Something went wrong")
    
    def test_parent_response_format_status(self):
        """Test formatting status response for Signal."""
        response = ParentResponse(
            request_id="test",
            success=True,
            data={
                "status": {
                    "state": "running",
                    "uptime": "1:30:00",
                    "active_tasks": 2,
                    "queue_size": 5,
                    "last_activity": "2024-01-01T12:00:00"
                }
            }
        )
        
        message = response.to_signal_message()
        
        self.assertIn("Noctem Status", message)
        self.assertIn("running", message)
        self.assertIn("1:30:00", message)
    
    def test_parent_response_format_error(self):
        """Test formatting error response."""
        response = ParentResponse(
            request_id="test",
            success=False,
            data={},
            error="Connection failed"
        )
        
        message = response.to_signal_message()
        
        self.assertIn("❌", message)
        self.assertIn("Connection failed", message)


class TestChildHandler(unittest.TestCase):
    """Tests for parent/child_handler.py"""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.working_dir = Path(self.temp_dir)
        
        # Create logs directory
        (self.working_dir / "logs").mkdir(exist_ok=True)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_handle_status(self):
        """Test handling status command."""
        from parent.child_handler import ChildHandler
        import state as state_module
        
        with patch.object(state_module, 'get_running_tasks', return_value=[]):
            with patch.object(state_module, 'get_pending_tasks', return_value=[{"id": 1}]):
                with patch.object(state_module, 'get_recent_tasks', return_value=[]):
                    handler = ChildHandler(self.db_path, self.working_dir)
                    request = ParentRequest(command=ParentCommand.STATUS)
                    
                    response = handler.handle_request(request)
                    
                    self.assertTrue(response.success)
                    self.assertIn("status", response.data)
                    self.assertEqual(response.data["status"]["queue_size"], 1)
    
    def test_handle_health(self):
        """Test handling health command."""
        from parent.child_handler import ChildHandler
        
        handler = ChildHandler(self.db_path, self.working_dir)
        request = ParentRequest(command=ParentCommand.HEALTH)
        
        response = handler.handle_request(request)
        
        self.assertTrue(response.success)
        self.assertIn("health", response.data)
        # Health data should have these keys even if services aren't running
        health = response.data["health"]
        self.assertIn("ollama", health)
        self.assertIn("signal", health)
        self.assertIn("disk_usage", health)
    
    def test_handle_logs_no_file(self):
        """Test handling logs command when no log file exists."""
        from parent.child_handler import ChildHandler
        
        handler = ChildHandler(self.db_path, self.working_dir)
        request = ParentRequest(command=ParentCommand.LOGS)
        
        response = handler.handle_request(request)
        
        self.assertTrue(response.success)
        self.assertEqual(response.data["logs"], [])
    
    def test_handle_logs_with_file(self):
        """Test handling logs command with log file."""
        from parent.child_handler import ChildHandler
        
        # Create a log file
        log_file = self.working_dir / "logs" / "noctem.log"
        log_file.write_text("Line 1\nLine 2\nLine 3\n")
        
        handler = ChildHandler(self.db_path, self.working_dir)
        request = ParentRequest(command=ParentCommand.LOGS, params={"lines": 2})
        
        response = handler.handle_request(request)
        
        self.assertTrue(response.success)
        self.assertEqual(len(response.data["logs"]), 2)
        self.assertIn("Line 2", response.data["logs"])
        self.assertIn("Line 3", response.data["logs"])
    
    def test_handle_unknown_command(self):
        """Test handling unknown command returns error."""
        from parent.child_handler import ChildHandler
        
        handler = ChildHandler(self.db_path, self.working_dir)
        
        # Create a request with a command not in handler map
        request = ParentRequest(command=ParentCommand.IMPROVE)
        
        response = handler.handle_request(request)
        
        self.assertFalse(response.success)
        self.assertIn("Unknown command", response.error)


class TestImprove(unittest.TestCase):
    """Tests for parent/improve.py"""
    
    def test_improvement_from_dict(self):
        """Test creating Improvement from dictionary."""
        from parent.improve import Improvement
        
        data = {
            "id": 1,
            "title": "Test improvement",
            "description": "Test description",
            "priority": 2,
            "patch": "--- a/file.py\n+++ b/file.py",
            "status": "pending"
        }
        
        imp = Improvement.from_dict(data)
        
        self.assertEqual(imp.id, 1)
        self.assertEqual(imp.title, "Test improvement")
        self.assertEqual(imp.priority, 2)
        self.assertEqual(imp.status, "pending")
    
    def test_improvement_to_dict(self):
        """Test converting Improvement to dictionary."""
        from parent.improve import Improvement
        
        imp = Improvement(
            id=1,
            title="Test",
            description="Desc",
            priority=3,
            patch=""
        )
        
        data = imp.to_dict()
        
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["title"], "Test")
        self.assertIn("created_at", data)
    
    def test_improvement_format_for_signal(self):
        """Test formatting improvement for Signal."""
        from parent.improve import Improvement
        
        imp = Improvement(
            id=42,
            title="Fix timeout issue",
            description="Increase timeout from 30s to 60s",
            priority=2,
            patch=""
        )
        
        message = imp.format_for_signal()
        
        self.assertIn("#42", message)
        self.assertIn("Fix timeout issue", message)
        self.assertIn("⭐⭐", message)  # Priority 2 = 2 stars
    
    def test_analyze_problems_timeout_pattern(self):
        """Test analyzing problems detects timeout patterns."""
        from parent.improve import analyze_problems
        
        problems = [
            {"type": "task_failure", "input": "task1", "result": "Timeout error"},
            {"type": "task_failure", "input": "task2", "result": "Connection timeout"},
            {"type": "task_failure", "input": "task3", "result": "Request timeout"},
        ]
        
        suggestions = analyze_problems(problems)
        
        self.assertTrue(len(suggestions) > 0)
        timeout_suggestion = next(
            (s for s in suggestions if "timeout" in s["title"].lower()),
            None
        )
        self.assertIsNotNone(timeout_suggestion)
    
    def test_analyze_problems_skill_pattern(self):
        """Test analyzing problems detects skill failure patterns."""
        from parent.improve import analyze_problems
        
        problems = [
            {"type": "skill_failure", "skill": "web_fetch", "input": "url1"},
            {"type": "skill_failure", "skill": "web_fetch", "input": "url2"},
            {"type": "skill_failure", "skill": "shell", "input": "cmd1"},
        ]
        
        suggestions = analyze_problems(problems)
        
        # Should detect repeated web_fetch failures
        web_fetch_suggestion = next(
            (s for s in suggestions if "web_fetch" in s["title"]),
            None
        )
        self.assertIsNotNone(web_fetch_suggestion)
    
    def test_generate_training_pair(self):
        """Test generating training data pairs."""
        from parent.improve import generate_training_pair
        
        problem = {
            "type": "task_failure",
            "input": "fetch weather data",
            "result": "Connection refused"
        }
        
        solution = {
            "type": "retry_logic",
            "description": "Add exponential backoff",
            "action": "Implement retry with backoff"
        }
        
        pair = generate_training_pair(problem, solution)
        
        self.assertIn("problem", pair)
        self.assertIn("solution", pair)
        self.assertIn("timestamp", pair)
        self.assertEqual(pair["problem"]["type"], "task_failure")


class TestScheduler(unittest.TestCase):
    """Tests for parent/scheduler.py"""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.working_dir = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_is_idle_true(self):
        """Test is_idle returns True when no tasks."""
        from parent.scheduler import BabysittingScheduler
        import state as state_module
        
        with patch.object(state_module, 'get_running_tasks', return_value=[]):
            with patch.object(state_module, 'get_pending_tasks', return_value=[]):
                scheduler = BabysittingScheduler(self.working_dir, self.db_path)
                self.assertTrue(scheduler.is_idle())
    
    def test_is_idle_false_running(self):
        """Test is_idle returns False when tasks running."""
        from parent.scheduler import BabysittingScheduler
        import state as state_module
        
        with patch.object(state_module, 'get_running_tasks', return_value=[{"id": 1}]):
            with patch.object(state_module, 'get_pending_tasks', return_value=[]):
                scheduler = BabysittingScheduler(self.working_dir, self.db_path)
                self.assertFalse(scheduler.is_idle())
    
    def test_is_idle_false_pending(self):
        """Test is_idle returns False when tasks pending."""
        from parent.scheduler import BabysittingScheduler
        import state as state_module
        
        with patch.object(state_module, 'get_running_tasks', return_value=[]):
            with patch.object(state_module, 'get_pending_tasks', return_value=[{"id": 1}]):
                scheduler = BabysittingScheduler(self.working_dir, self.db_path)
                self.assertFalse(scheduler.is_idle())
    
    def test_should_generate_report_first_time(self):
        """Test report should be generated on first run."""
        from parent.scheduler import BabysittingScheduler
        
        scheduler = BabysittingScheduler(self.working_dir, self.db_path)
        
        self.assertTrue(scheduler._should_generate_report())
    
    def test_should_generate_report_after_interval(self):
        """Test report should be generated after interval."""
        from parent.scheduler import BabysittingScheduler
        
        scheduler = BabysittingScheduler(self.working_dir, self.db_path)
        scheduler.report_interval_hours = 1
        
        # Set last report to 2 hours ago
        scheduler._last_report = datetime.now() - timedelta(hours=2)
        
        self.assertTrue(scheduler._should_generate_report())
    
    def test_should_not_generate_report_too_soon(self):
        """Test report should not be generated too soon."""
        from parent.scheduler import BabysittingScheduler
        
        scheduler = BabysittingScheduler(self.working_dir, self.db_path)
        scheduler.report_interval_hours = 6
        
        # Set last report to 1 hour ago
        scheduler._last_report = datetime.now() - timedelta(hours=1)
        
        self.assertFalse(scheduler._should_generate_report())


class TestStateIntegration(unittest.TestCase):
    """Integration tests for state.py additions."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_path = None
        
        # Patch the DB_PATH in state module
        import state
        self.original_db_path = state.DB_PATH
        state.DB_PATH = Path(self.temp_dir) / "test.db"
        state.init_db()
    
    def tearDown(self):
        """Clean up test database."""
        import state
        state.DB_PATH = self.original_db_path
        
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_and_get_improvement(self):
        """Test creating and retrieving an improvement."""
        import state
        
        imp_id = state.create_improvement(
            title="Test improvement",
            description="Test description",
            priority=2,
            patch="test patch"
        )
        
        self.assertIsNotNone(imp_id)
        
        imp = state.get_improvement(imp_id)
        
        self.assertIsNotNone(imp)
        self.assertEqual(imp["title"], "Test improvement")
        self.assertEqual(imp["priority"], 2)
        self.assertEqual(imp["status"], "pending")
    
    def test_update_improvement_status(self):
        """Test updating improvement status."""
        import state
        
        imp_id = state.create_improvement(title="Test", description="Desc")
        
        result = state.update_improvement_status(imp_id, "approved")
        self.assertTrue(result)
        
        imp = state.get_improvement(imp_id)
        self.assertEqual(imp["status"], "approved")
    
    def test_get_pending_improvements(self):
        """Test getting pending improvements."""
        import state
        
        state.create_improvement(title="Pending 1", description="")
        state.create_improvement(title="Pending 2", description="")
        
        imp_id = state.create_improvement(title="Approved", description="")
        state.update_improvement_status(imp_id, "approved")
        
        pending = state.get_pending_improvements()
        
        self.assertEqual(len(pending), 2)
        self.assertTrue(all(p["status"] == "pending" for p in pending))
    
    def test_create_and_get_report(self):
        """Test creating and retrieving a report."""
        import state
        
        report_id = state.create_report(
            report_type="babysitting",
            content="Test report content",
            metrics={"uptime": "1h", "tasks": 10},
            problems=[{"type": "error", "msg": "test"}],
            solutions=[{"type": "fix", "desc": "solution"}]
        )
        
        self.assertIsNotNone(report_id)
        
        reports = state.get_recent_reports("babysitting", limit=1)
        
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["report_type"], "babysitting")
        self.assertEqual(reports[0]["content"], "Test report content")
    
    def test_get_task_stats(self):
        """Test getting task statistics."""
        import state
        
        # Create some tasks
        state.create_task("Task 1", source="test")
        task_id = state.create_task("Task 2", source="test")
        state.complete_task(task_id, "Success", success=True)
        
        task_id = state.create_task("Task 3", source="test")
        state.complete_task(task_id, "Failed", success=False)
        
        # Use a longer time window to ensure we capture the tasks
        stats = state.get_task_stats(since_hours=24)
        
        self.assertGreaterEqual(stats["total"], 3)
        self.assertGreaterEqual(stats["successful"], 1)
        self.assertGreaterEqual(stats["failed"], 1)


if __name__ == "__main__":
    unittest.main()
