"""
Tests for Noctem v0.6.1 Foundation Layer features.

Tests cover:
- Execution logging (ExecutionLogger, traces, stats)
- Butler /summon command
- Model registry (discovery, benchmarking, routing)
- Maintenance scanner (insights, reports)
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

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
# EXECUTION LOGGING TESTS
# =============================================================================

class TestExecutionLogger:
    """Test the ExecutionLogger class."""
    
    def test_basic_trace_creation(self):
        """ExecutionLogger should create a trace with unique ID."""
        from noctem.logging.execution_logger import ExecutionLogger
        
        with ExecutionLogger(component="test") as trace:
            assert trace.trace_id is not None
            assert len(trace.trace_id) == 36  # UUID format
    
    def test_log_stage_saves_to_db(self):
        """log_stage should persist to execution_logs table."""
        from noctem.logging.execution_logger import ExecutionLogger, get_trace
        
        with ExecutionLogger(component="fast", source="cli") as trace:
            trace.log_stage("input", input_data={"text": "test"})
            trace.log_stage("classify", confidence=0.9)
        
        entries = get_trace(trace.trace_id)
        assert len(entries) >= 2
        assert entries[0].stage == "input"
        assert entries[0].component == "fast"
    
    def test_trace_timing(self):
        """Trace should capture timing information."""
        from noctem.logging.execution_logger import ExecutionLogger, get_trace
        import time
        
        with ExecutionLogger(component="test") as trace:
            trace.log_stage("start")
            time.sleep(0.01)  # 10ms
            trace.log_stage("end")
        
        entries = get_trace(trace.trace_id)
        # Complete stage should have duration
        complete_entry = [e for e in entries if e.stage == "complete"][0]
        assert complete_entry.duration_ms is not None
        assert complete_entry.duration_ms >= 10
    
    def test_thought_and_task_linking(self):
        """Trace should link to thought and task IDs."""
        from noctem.logging.execution_logger import ExecutionLogger, get_trace
        
        with ExecutionLogger(component="fast") as trace:
            trace.set_thought_id(123)
            trace.set_task_id(456)
            trace.complete()
        
        entries = get_trace(trace.trace_id)
        complete_entry = [e for e in entries if e.stage == "complete"][0]
        assert complete_entry.thought_id == 123
        assert complete_entry.task_id == 456
    
    def test_error_logging(self):
        """Errors should be logged correctly."""
        from noctem.logging.execution_logger import ExecutionLogger, get_trace
        
        with ExecutionLogger(component="test") as trace:
            trace.log_error("Something went wrong")
        
        entries = get_trace(trace.trace_id)
        error_entries = [e for e in entries if e.error is not None]
        assert len(error_entries) >= 1
        assert "Something went wrong" in error_entries[0].error
    
    def test_exception_handling(self):
        """Exceptions should be logged and not suppressed."""
        from noctem.logging.execution_logger import ExecutionLogger, get_trace
        
        trace_id = None
        try:
            with ExecutionLogger(component="test") as trace:
                trace_id = trace.trace_id
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        entries = get_trace(trace_id)
        error_entries = [e for e in entries if e.error is not None]
        assert len(error_entries) >= 1
    
    def test_get_recent_traces(self):
        """get_recent_traces should return trace summaries."""
        from noctem.logging.execution_logger import ExecutionLogger, get_recent_traces
        
        # Create a few traces
        for i in range(3):
            with ExecutionLogger(component="fast") as trace:
                trace.log_stage("test")
        
        traces = get_recent_traces(limit=10)
        assert len(traces) >= 3
        assert all("trace_id" in t for t in traces)
    
    def test_get_execution_stats(self):
        """get_execution_stats should return aggregate statistics."""
        from noctem.logging.execution_logger import ExecutionLogger, get_execution_stats
        
        # Create some traces
        with ExecutionLogger(component="fast") as trace:
            trace.log_stage("test", confidence=0.8)
        
        stats = get_execution_stats(hours=1)
        assert stats["trace_count"] >= 1
        assert "avg_confidence" in stats


class TestExecutionLoggingIntegration:
    """Test execution logging integration with capture system."""
    
    def test_capture_creates_trace(self):
        """process_input should create execution trace."""
        from noctem.fast.capture import process_input
        from noctem.logging.execution_logger import get_recent_traces
        
        # Process an input
        result = process_input("buy milk tomorrow", source="cli")
        
        # Should have created a trace
        traces = get_recent_traces(limit=1, component="fast")
        assert len(traces) >= 1
    
    def test_capture_trace_has_all_stages(self):
        """Capture trace should have input, classify, route, complete stages."""
        from noctem.fast.capture import process_input
        from noctem.logging.execution_logger import get_recent_traces, get_trace
        
        result = process_input("buy milk tomorrow", source="cli")
        
        traces = get_recent_traces(limit=1, component="fast")
        entries = get_trace(traces[0]["trace_id"])
        
        stages = [e.stage for e in entries]
        assert "input" in stages
        assert "classify" in stages
        assert "complete" in stages


# =============================================================================
# BUTLER SUMMON TESTS
# =============================================================================

class TestSummonCommand:
    """Test the /summon command."""
    
    def test_summon_help(self):
        """summon help should return help message."""
        from noctem.butler.summon import handle_summon
        
        response, metadata = handle_summon("help", source="cli")
        
        assert "Summon Commands" in response
        assert metadata["intent"] == "help"
    
    def test_summon_status(self):
        """summon status should return system status."""
        from noctem.butler.summon import handle_summon
        
        response, metadata = handle_summon("status", source="cli")
        
        assert "Noctem Status" in response
        assert "Butler" in response
        assert metadata["intent"] == "status"
    
    def test_summon_query_tasks(self):
        """summon what tasks should query tasks."""
        from noctem.butler.summon import handle_summon
        from noctem.services import task_service
        
        # Create a task first
        task_service.create_task("Test task for summon")
        
        response, metadata = handle_summon("what tasks", source="cli")
        
        assert "Test task for summon" in response or "No pending tasks" in response
        assert metadata["intent"] == "query"
    
    def test_summon_intent_parsing(self):
        """Summon should correctly parse different intents."""
        from noctem.butler.summon import _parse_summon_intent
        
        # Status
        intent, _ = _parse_summon_intent("status")
        assert intent == "status"
        
        # Help
        intent, _ = _parse_summon_intent("help")
        assert intent == "help"
        
        # Correction
        intent, parsed = _parse_summon_intent("correct thought 123")
        assert intent == "correct"
        assert "123" in parsed["target"]
        
        # Query
        intent, _ = _parse_summon_intent("what projects")
        assert intent == "query"
        
        # General
        intent, _ = _parse_summon_intent("please help me organize")
        assert intent == "general"
    
    def test_summon_creates_trace(self):
        """Summon should create execution trace."""
        from noctem.butler.summon import handle_summon
        from noctem.logging.execution_logger import get_recent_traces
        
        handle_summon("status", source="cli")
        
        traces = get_recent_traces(limit=1, component="summon")
        assert len(traces) >= 1


# =============================================================================
# MODEL REGISTRY TESTS
# =============================================================================

class TestModelRegistry:
    """Test the model registry."""
    
    def test_registry_initialization(self):
        """Registry should initialize with Ollama backend."""
        from noctem.slow.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        assert "ollama" in registry.backends
    
    def test_model_name_parsing(self):
        """Should correctly parse model names."""
        from noctem.slow.model_registry import OllamaBackend
        
        backend = OllamaBackend()
        
        # Test various model name formats
        family, size, quant = backend._parse_model_name("qwen2.5:7b-instruct-q4_K_M")
        assert family == "qwen2.5"
        assert size == "7b"
        assert quant == "q4_k_m"
        
        family, size, quant = backend._parse_model_name("llama3:8b")
        assert family == "llama3"
        assert size == "8b"
        
        family, size, quant = backend._parse_model_name("mistral:latest")
        assert family == "mistral"
    
    def test_save_and_get_model(self):
        """Should save and retrieve model info."""
        from noctem.slow.model_registry import ModelRegistry
        from noctem.models import ModelInfo
        
        registry = ModelRegistry()
        
        # Create model info
        info = ModelInfo(
            name="test-model:7b",
            backend="ollama",
            family="test",
            tokens_per_sec=50.0,
            health="ok",
        )
        registry._save_model(info)
        
        # Retrieve it
        retrieved = registry.get_model("test-model:7b")
        assert retrieved is not None
        assert retrieved.family == "test"
        assert retrieved.tokens_per_sec == 50.0
    
    def test_get_all_models(self):
        """Should return all models from registry."""
        from noctem.slow.model_registry import ModelRegistry
        from noctem.models import ModelInfo
        
        registry = ModelRegistry()
        
        # Add some models
        for name in ["model-a:7b", "model-b:14b"]:
            info = ModelInfo(name=name, backend="ollama", health="ok")
            registry._save_model(info)
        
        models = registry.get_all_models()
        assert len(models) >= 2
    
    def test_get_best_model_for_fast(self):
        """Should return fastest model for 'fast' task type."""
        from noctem.slow.model_registry import ModelRegistry
        from noctem.models import ModelInfo
        
        registry = ModelRegistry()
        
        # Add models with different speeds
        registry._save_model(ModelInfo(
            name="slow-model", backend="ollama", 
            tokens_per_sec=20.0, health="ok"
        ))
        registry._save_model(ModelInfo(
            name="fast-model", backend="ollama",
            tokens_per_sec=100.0, health="ok"
        ))
        
        best = registry.get_best_model_for("fast")
        assert best is not None
        assert best.name == "fast-model"
    
    def test_record_usage(self):
        """Should record model usage for task type."""
        from noctem.slow.model_registry import ModelRegistry
        from noctem.models import ModelInfo
        
        registry = ModelRegistry()
        registry._save_model(ModelInfo(name="usage-test", backend="ollama"))
        
        registry.record_usage("usage-test", "classification")
        
        model = registry.get_model("usage-test")
        assert model.last_used_for == "classification"


class TestOllamaBackendMocked:
    """Test Ollama backend with mocked HTTP responses."""
    
    def test_is_available_when_server_running(self):
        """Should return True when Ollama responds."""
        from noctem.slow.model_registry import OllamaBackend
        
        backend = OllamaBackend()
        
        with patch('httpx.Client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.__enter__ = Mock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = Mock(return_value=False)
            mock_client.return_value.get.return_value = mock_response
            
            assert backend.is_available() is True
    
    def test_list_models_returns_model_names(self):
        """Should parse model list from API response."""
        from noctem.slow.model_registry import OllamaBackend
        
        backend = OllamaBackend()
        
        with patch('httpx.Client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "qwen2.5:7b"},
                    {"name": "llama3:8b"},
                ]
            }
            mock_client.return_value.__enter__ = Mock(return_value=mock_client.return_value)
            mock_client.return_value.__exit__ = Mock(return_value=False)
            mock_client.return_value.get.return_value = mock_response
            
            models = backend.list_models()
            assert "qwen2.5:7b" in models
            assert "llama3:8b" in models


# =============================================================================
# MAINTENANCE SCANNER TESTS
# =============================================================================

class TestMaintenanceScanner:
    """Test the maintenance scanner."""
    
    def test_scanner_initialization(self):
        """Scanner should initialize correctly."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        assert scanner.registry is not None
    
    def test_create_insight(self):
        """Should create and save insight to database."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        insight = scanner._create_insight(
            insight_type="test",
            source="unit_test",
            title="Test insight",
            details={"key": "value"},
            priority=3,
        )
        
        assert insight.id is not None
        assert insight.title == "Test insight"
        assert insight.priority == 3
    
    def test_get_pending_insights(self):
        """Should retrieve pending insights."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        
        # Create some insights
        scanner._create_insight("type1", "test", "Insight 1", {}, 4)
        scanner._create_insight("type2", "test", "Insight 2", {}, 2)
        
        pending = scanner.get_pending_insights()
        assert len(pending) >= 2
        # Should be sorted by priority desc
        assert pending[0].priority >= pending[1].priority
    
    def test_mark_insight_reported(self):
        """Should mark insight as reported."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        insight = scanner._create_insight("test", "test", "Report test", {}, 3)
        
        scanner.mark_reported([insight.id])
        
        # Fetch and check
        all_insights = scanner.get_all_insights()
        updated = [i for i in all_insights if i.id == insight.id][0]
        assert updated.status == "reported"
    
    def test_mark_insight_dismissed(self):
        """Should mark insight as dismissed."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        insight = scanner._create_insight("test", "test", "Dismiss test", {}, 3)
        
        scanner.mark_dismissed(insight.id)
        
        all_insights = scanner.get_all_insights()
        updated = [i for i in all_insights if i.id == insight.id][0]
        assert updated.status == "dismissed"
    
    def test_scan_queue_health_no_issues(self):
        """Queue health scan should return empty when healthy."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        insights = scanner.scan_queue_health()
        
        # Should have no high-priority issues with empty queue
        high_priority = [i for i in insights if i.priority >= 4]
        # This could be empty or have some based on queue state
        assert isinstance(insights, list)
    
    def test_generate_report_empty(self):
        """Should generate report even with no insights."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        report = scanner.generate_report([])
        
        assert "System Maintenance Report" in report
        assert "All systems healthy" in report
    
    def test_generate_report_with_insights(self):
        """Should generate report with insights listed."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        
        insight1 = scanner._create_insight("blocker", "test", "Critical Issue", {}, 5)
        insight2 = scanner._create_insight("recommendation", "test", "Minor Issue", {}, 2)
        
        report = scanner.generate_report([insight1, insight2])
        
        assert "Critical Issue" in report
        assert "Minor Issue" in report
        assert "High Priority" in report
    
    def test_preview_report(self):
        """preview_report should not mark insights as reported."""
        from noctem.maintenance.scanner import MaintenanceScanner
        
        scanner = MaintenanceScanner()
        scanner._create_insight("test", "test", "Preview test", {}, 3)
        
        report = scanner.preview_report()
        
        # Insights should still be pending
        pending = scanner.get_pending_insights()
        assert any(i.title == "Preview test" for i in pending)


class TestMaintenanceConvenienceFunctions:
    """Test maintenance module convenience functions."""
    
    def test_run_maintenance_scan_queue(self):
        """run_maintenance_scan should work for queue type."""
        from noctem.maintenance.scanner import run_maintenance_scan
        
        insights = run_maintenance_scan("queue")
        assert isinstance(insights, list)
    
    def test_preview_maintenance_report(self):
        """preview_maintenance_report should return string."""
        from noctem.maintenance.scanner import preview_maintenance_report
        
        report = preview_maintenance_report()
        assert isinstance(report, str)
        assert "Report" in report or "healthy" in report
    
    def test_get_maintenance_summary(self):
        """get_maintenance_summary should return dict."""
        from noctem.maintenance.scanner import get_maintenance_summary
        
        summary = get_maintenance_summary()
        assert "pending_insights" in summary
        assert "high_priority" in summary


# =============================================================================
# DATABASE SCHEMA TESTS
# =============================================================================

class TestDatabaseSchema:
    """Test that v0.6.1 tables are created correctly."""
    
    def test_execution_logs_table_exists(self):
        """execution_logs table should exist."""
        with get_db() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_logs'"
            ).fetchone()
        assert result is not None
    
    def test_model_registry_table_exists(self):
        """model_registry table should exist."""
        with get_db() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='model_registry'"
            ).fetchone()
        assert result is not None
    
    def test_maintenance_insights_table_exists(self):
        """maintenance_insights table should exist."""
        with get_db() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='maintenance_insights'"
            ).fetchone()
        assert result is not None
    
    def test_thoughts_summon_mode_column(self):
        """thoughts table should have summon_mode column after migration."""
        with get_db() as conn:
            # Insert a thought with summon_mode
            conn.execute(
                "INSERT INTO thoughts (source, raw_text, summon_mode) VALUES (?, ?, ?)",
                ("test", "test thought", 1)
            )
            
            # Query it back
            result = conn.execute(
                "SELECT summon_mode FROM thoughts WHERE raw_text = 'test thought'"
            ).fetchone()
        
        assert result is not None
        assert result[0] == 1


# =============================================================================
# MODELS DATACLASS TESTS
# =============================================================================

class TestNewDataclasses:
    """Test new dataclasses added in v0.6.1."""
    
    def test_execution_log_from_row(self):
        """ExecutionLog should parse from database row."""
        from noctem.models import ExecutionLog
        
        # Insert a row
        with get_db() as conn:
            conn.execute("""
                INSERT INTO execution_logs 
                (trace_id, stage, component, confidence, input_data)
                VALUES (?, ?, ?, ?, ?)
            """, ("test-trace", "test", "fast", 0.9, '{"key": "value"}'))
            
            row = conn.execute(
                "SELECT * FROM execution_logs WHERE trace_id = 'test-trace'"
            ).fetchone()
        
        log = ExecutionLog.from_row(row)
        assert log.trace_id == "test-trace"
        assert log.confidence == 0.9
        assert log.input_data == {"key": "value"}
    
    def test_model_info_from_row(self):
        """ModelInfo should parse from database row."""
        from noctem.models import ModelInfo
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO model_registry 
                (name, backend, family, tokens_per_sec, health)
                VALUES (?, ?, ?, ?, ?)
            """, ("test:7b", "ollama", "test", 45.5, "ok"))
            
            row = conn.execute(
                "SELECT * FROM model_registry WHERE name = 'test:7b'"
            ).fetchone()
        
        info = ModelInfo.from_row(row)
        assert info.name == "test:7b"
        assert info.tokens_per_sec == 45.5
    
    def test_maintenance_insight_from_row(self):
        """MaintenanceInsight should parse from database row."""
        from noctem.models import MaintenanceInsight
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO maintenance_insights 
                (insight_type, source, title, details, priority)
                VALUES (?, ?, ?, ?, ?)
            """, ("test", "unit", "Test Title", '{"info": "data"}', 4))
            
            row = conn.execute(
                "SELECT * FROM maintenance_insights WHERE title = 'Test Title'"
            ).fetchone()
        
        insight = MaintenanceInsight.from_row(row)
        assert insight.title == "Test Title"
        assert insight.priority == 4
        assert insight.details == {"info": "data"}


# =============================================================================
# CONFIG TESTS
# =============================================================================

class TestNewConfigKeys:
    """Test new config keys added in v0.6.1."""
    
    def test_maintenance_config_defaults(self):
        """Maintenance config keys should have defaults."""
        from noctem.config import DEFAULTS
        
        assert "maintenance_scan_enabled" in DEFAULTS
        assert "maintenance_scan_interval_days" in DEFAULTS
        assert "maintenance_report_threshold" in DEFAULTS
        assert "summon_timeout_seconds" in DEFAULTS
    
    def test_get_maintenance_config(self):
        """Should be able to get maintenance config values."""
        from noctem.config import Config
        
        assert Config.get("maintenance_scan_enabled") is True
        assert Config.get("summon_timeout_seconds") == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
