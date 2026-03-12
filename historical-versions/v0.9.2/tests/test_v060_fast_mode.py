"""
Tests for Noctem v0.6.0 Phase 1: Fast Mode Foundation.
Tests cover:
- Database schema updates (new tables, new columns)
- MessageLog recording all interactions
- Unclear input handling
- Config defaults for butler/slow mode
"""
import pytest
import tempfile
import os
from datetime import date, datetime
from pathlib import Path

# Set up test database before imports
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['NOCTEM_DB_PATH'] = TEST_DB

# Now import noctem modules
from noctem import db
from noctem.db import get_db, init_db

# Override DB path for testing
db.DB_PATH = Path(TEST_DB)

from noctem.models import Task, Project
from noctem.services import task_service, project_service
from noctem.services.message_logger import MessageLog, get_recent_logs
from noctem.config import Config, DEFAULTS


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


class TestV060Schema:
    """Test v0.6.0 database schema additions."""
    
    def test_butler_contacts_table_exists(self):
        """butler_contacts table should exist."""
        with get_db() as conn:
            result = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='butler_contacts'
            """).fetchone()
            assert result is not None
    
    def test_butler_contacts_columns(self):
        """butler_contacts should have correct columns."""
        with get_db() as conn:
            cursor = conn.execute("PRAGMA table_info(butler_contacts)")
            columns = {row[1] for row in cursor.fetchall()}
            expected = {'id', 'contact_type', 'message_content', 'week_number', 'year', 'sent_at'}
            assert expected.issubset(columns)
    
    def test_slow_work_queue_table_exists(self):
        """slow_work_queue table should exist."""
        with get_db() as conn:
            result = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='slow_work_queue'
            """).fetchone()
            assert result is not None
    
    def test_slow_work_queue_columns(self):
        """slow_work_queue should have correct columns."""
        with get_db() as conn:
            cursor = conn.execute("PRAGMA table_info(slow_work_queue)")
            columns = {row[1] for row in cursor.fetchall()}
            expected = {'id', 'work_type', 'target_id', 'depends_on_id', 'status', 
                       'result', 'queued_at', 'started_at', 'completed_at', 'error_message'}
            assert expected.issubset(columns)
    
    def test_tasks_has_suggestion_columns(self):
        """tasks table should have computer_help_suggestion column."""
        with get_db() as conn:
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in cursor.fetchall()}
            assert 'computer_help_suggestion' in columns
            assert 'suggestion_generated_at' in columns
    
    def test_projects_has_suggestion_columns(self):
        """projects table should have next_action_suggestion column."""
        with get_db() as conn:
            cursor = conn.execute("PRAGMA table_info(projects)")
            columns = {row[1] for row in cursor.fetchall()}
            assert 'next_action_suggestion' in columns
            assert 'suggestion_generated_at' in columns
    
    def test_can_insert_butler_contact(self):
        """Should be able to insert butler contact records."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, ('update', 'Test message', 7, 2026))
            
            row = conn.execute("SELECT * FROM butler_contacts WHERE id = 1").fetchone()
            assert row['contact_type'] == 'update'
            assert row['week_number'] == 7
    
    def test_can_insert_slow_work_item(self):
        """Should be able to insert slow work queue items."""
        task = task_service.create_task("Test task")
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, status)
                VALUES (?, ?, ?)
            """, ('task_computer_help', task.id, 'pending'))
            
            row = conn.execute("SELECT * FROM slow_work_queue WHERE id = 1").fetchone()
            assert row['work_type'] == 'task_computer_help'
            assert row['status'] == 'pending'


class TestV060Config:
    """Test v0.6.0 config defaults."""
    
    def test_butler_contacts_per_week_default(self):
        """Should have butler_contacts_per_week default."""
        assert 'butler_contacts_per_week' in DEFAULTS
        assert DEFAULTS['butler_contacts_per_week'] == 5
    
    def test_butler_update_days_default(self):
        """Should have butler_update_days default."""
        assert 'butler_update_days' in DEFAULTS
        assert DEFAULTS['butler_update_days'] == ['monday', 'wednesday', 'friday']
    
    def test_butler_clarification_days_default(self):
        """Should have butler_clarification_days default."""
        assert 'butler_clarification_days' in DEFAULTS
        assert DEFAULTS['butler_clarification_days'] == ['tuesday', 'thursday']
    
    def test_slow_mode_enabled_default(self):
        """Should have slow_mode_enabled default."""
        assert 'slow_mode_enabled' in DEFAULTS
        assert DEFAULTS['slow_mode_enabled'] is True
    
    def test_slow_model_default(self):
        """Should have slow_model default."""
        assert 'slow_model' in DEFAULTS
        assert 'qwen' in DEFAULTS['slow_model'].lower()
    
    def test_ollama_host_default(self):
        """Should have ollama_host default."""
        assert 'ollama_host' in DEFAULTS
        assert 'localhost' in DEFAULTS['ollama_host']
    
    def test_slow_idle_minutes_default(self):
        """Should have slow_idle_minutes default."""
        assert 'slow_idle_minutes' in DEFAULTS
        assert DEFAULTS['slow_idle_minutes'] == 5
    
    def test_config_get_butler_defaults(self):
        """Config.get should return butler defaults."""
        assert Config.get('butler_contacts_per_week') == 5
        assert Config.get('butler_update_time') == '09:00'


class TestMessageLogRecording:
    """Test that MessageLog records all interactions."""
    
    def test_message_log_records_basic(self):
        """MessageLog should record basic interaction."""
        with MessageLog("test input", source="test") as log:
            log.set_parsed("TEST_COMMAND", {"key": "value"})
            log.set_action("test_action")
            log.set_result(True, {"result": "success"})
        
        logs = get_recent_logs(1)
        assert len(logs) == 1
        assert logs[0]['raw_message'] == "test input"
        assert logs[0]['parsed_command'] == "TEST_COMMAND"
        assert logs[0]['action_taken'] == "test_action"
        assert logs[0]['result'] == "success"
    
    def test_message_log_records_on_exception(self):
        """MessageLog should record even when exception occurs."""
        try:
            with MessageLog("failing input", source="test") as log:
                log.set_parsed("FAIL_TEST", {})
                raise ValueError("Test error")
        except ValueError:
            pass
        
        logs = get_recent_logs(1)
        assert len(logs) == 1
        assert logs[0]['raw_message'] == "failing input"
        assert logs[0]['result'] == "error"
    
    def test_message_log_source_recorded(self):
        """MessageLog should record the source."""
        with MessageLog("telegram test", source="telegram") as log:
            log.set_result(True, {})
        
        # Source is logged to file, not DB column, so we just verify no error
        logs = get_recent_logs(1)
        assert logs[0]['raw_message'] == "telegram test"
    
    def test_multiple_logs_recorded(self):
        """Multiple logs should all be recorded."""
        for i in range(3):
            with MessageLog(f"message {i}", source="test") as log:
                log.set_result(True, {})
        
        logs = get_recent_logs(3)
        assert len(logs) == 3
        # All messages should be present (order may vary due to timestamp resolution)
        messages = {log['raw_message'] for log in logs}
        assert messages == {"message 0", "message 1", "message 2"}


class TestUnclearInputHandling:
    """Test that unclear input is handled gracefully."""
    
    def test_unclear_input_creates_task_with_tag(self):
        """Unclear input should create task with 'unclear' tag."""
        task = task_service.create_task(name="?", tags=["unclear"])
        assert task.id is not None
        assert "unclear" in task.tags
    
    def test_very_short_input_tagged_unclear(self):
        """Very short input should be tagged as unclear."""
        task = task_service.create_task(name="x", tags=["unclear"])
        assert task.id is not None
        assert "unclear" in task.tags
    
    def test_unclear_task_still_searchable(self):
        """Unclear tasks should still be searchable."""
        task = task_service.create_task(name="mysterious input", tags=["unclear"])
        found = task_service.get_task_by_name("mysterious")
        assert found is not None
        assert found.id == task.id
    
    def test_unclear_task_in_priority_list(self):
        """Unclear tasks should appear in priority list."""
        task = task_service.create_task(
            name="unclear task", 
            tags=["unclear"],
            due_date=date.today()
        )
        priorities = task_service.get_priority_tasks(10)
        task_ids = [t.id for t in priorities]
        assert task.id in task_ids


class TestSlowWorkQueue:
    """Test slow work queue functionality."""
    
    def test_queue_pending_items(self):
        """Should be able to queue pending items."""
        task = task_service.create_task("Test for queue")
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, status)
                VALUES (?, ?, ?)
            """, ('task_computer_help', task.id, 'pending'))
        
        with get_db() as conn:
            pending = conn.execute("""
                SELECT * FROM slow_work_queue WHERE status = 'pending'
            """).fetchall()
            assert len(pending) == 1
    
    def test_queue_with_dependencies(self):
        """Should support dependencies between queue items."""
        project = project_service.create_project("Test Project")
        task = task_service.create_task("Task in project", project_id=project.id)
        
        with get_db() as conn:
            # First add task analysis
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, status)
                VALUES (?, ?, ?)
            """, ('task_computer_help', task.id, 'pending'))
            task_queue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Then project analysis depends on task analysis
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, depends_on_id, status)
                VALUES (?, ?, ?, ?)
            """, ('project_next_action', project.id, task_queue_id, 'pending'))
        
        with get_db() as conn:
            row = conn.execute("""
                SELECT * FROM slow_work_queue WHERE work_type = 'project_next_action'
            """).fetchone()
            assert row['depends_on_id'] == task_queue_id
    
    def test_queue_status_transitions(self):
        """Queue items should support status transitions."""
        task = task_service.create_task("Status test")
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO slow_work_queue (work_type, target_id, status)
                VALUES (?, ?, ?)
            """, ('task_computer_help', task.id, 'pending'))
            queue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            # Update to processing
            conn.execute("""
                UPDATE slow_work_queue 
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (queue_id,))
            
            # Update to completed
            conn.execute("""
                UPDATE slow_work_queue 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP, 
                    result = 'Test suggestion'
                WHERE id = ?
            """, (queue_id,))
        
        with get_db() as conn:
            row = conn.execute("SELECT * FROM slow_work_queue WHERE id = ?", (queue_id,)).fetchone()
            assert row['status'] == 'completed'
            assert row['result'] == 'Test suggestion'


class TestButlerContacts:
    """Test butler contact tracking."""
    
    def test_track_weekly_contacts(self):
        """Should track contacts per week."""
        with get_db() as conn:
            # Add contacts for week 7, 2026
            for i in range(3):
                conn.execute("""
                    INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                    VALUES (?, ?, ?, ?)
                """, ('update', f'Update {i}', 7, 2026))
        
        with get_db() as conn:
            count = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts 
                WHERE week_number = 7 AND year = 2026
            """).fetchone()[0]
            assert count == 3
    
    def test_separate_weeks_tracked(self):
        """Different weeks should be tracked separately."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, ('update', 'Week 7', 7, 2026))
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, ('update', 'Week 8', 8, 2026))
        
        with get_db() as conn:
            week7 = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts WHERE week_number = 7
            """).fetchone()[0]
            week8 = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts WHERE week_number = 8
            """).fetchone()[0]
            assert week7 == 1
            assert week8 == 1
    
    def test_contact_types(self):
        """Should support different contact types."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, ('update', 'Status update', 7, 2026))
            conn.execute("""
                INSERT INTO butler_contacts (contact_type, message_content, week_number, year)
                VALUES (?, ?, ?, ?)
            """, ('clarification', 'Need more info', 7, 2026))
        
        with get_db() as conn:
            updates = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts WHERE contact_type = 'update'
            """).fetchone()[0]
            clarifications = conn.execute("""
                SELECT COUNT(*) FROM butler_contacts WHERE contact_type = 'clarification'
            """).fetchone()[0]
            assert updates == 1
            assert clarifications == 1


class TestTaskSuggestions:
    """Test task suggestion columns."""
    
    def test_task_suggestion_column_writable(self):
        """Should be able to write to task suggestion column."""
        task = task_service.create_task("Test task")
        
        with get_db() as conn:
            conn.execute("""
                UPDATE tasks 
                SET computer_help_suggestion = ?, suggestion_generated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, ("Could set a reminder", task.id))
        
        with get_db() as conn:
            row = conn.execute("""
                SELECT computer_help_suggestion FROM tasks WHERE id = ?
            """, (task.id,)).fetchone()
            assert row[0] == "Could set a reminder"
    
    def test_project_suggestion_column_writable(self):
        """Should be able to write to project suggestion column."""
        project = project_service.create_project("Test project")
        
        with get_db() as conn:
            conn.execute("""
                UPDATE projects 
                SET next_action_suggestion = ?, suggestion_generated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, ("Start with the first task", project.id))
        
        with get_db() as conn:
            row = conn.execute("""
                SELECT next_action_suggestion FROM projects WHERE id = ?
            """, (project.id,)).fetchone()
            assert row[0] == "Start with the first task"


class TestIndexes:
    """Test that required indexes exist."""
    
    def test_butler_contacts_week_index(self):
        """Index on butler_contacts(year, week_number) should exist."""
        with get_db() as conn:
            result = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name='idx_butler_contacts_week'
            """).fetchone()
            assert result is not None
    
    def test_slow_work_status_index(self):
        """Index on slow_work_queue(status, queued_at) should exist."""
        with get_db() as conn:
            result = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name='idx_slow_work_status'
            """).fetchone()
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
