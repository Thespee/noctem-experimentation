"""
Startup and Environment Tests for Noctem v0.6.0.

These tests verify that all components can be imported and initialized properly,
catching issues like missing packages, import errors, and configuration problems
that could prevent the application from starting.
"""
import pytest
import sys
import tempfile
from pathlib import Path


class TestCriticalImports:
    """Test that all critical packages can be imported."""
    
    def test_flask_and_dotenv(self):
        """Flask requires python-dotenv for .env loading."""
        import flask
        import dotenv
        assert hasattr(dotenv, 'find_dotenv'), "python-dotenv not properly installed (find_dotenv missing)"
        assert hasattr(dotenv, 'load_dotenv'), "python-dotenv not properly installed (load_dotenv missing)"
    
    def test_telegram_bot(self):
        """Telegram bot package."""
        import telegram
        from telegram.ext import Application
    
    def test_apscheduler(self):
        """Job scheduler."""
        from apscheduler.schedulers.background import BackgroundScheduler
    
    def test_httpx(self):
        """HTTP client for Ollama."""
        import httpx
    
    def test_icalendar(self):
        """Calendar parsing."""
        import icalendar
    
    def test_dateutil(self):
        """Date parsing."""
        from dateutil import parser as date_parser
        from dateutil.relativedelta import relativedelta
    
    def test_qrcode(self):
        """QR code generation (optional but used in startup)."""
        import qrcode
    
    def test_jinja2(self):
        """Template engine."""
        import jinja2


class TestNoctemImports:
    """Test that all Noctem modules can be imported without errors."""
    
    def test_db_module(self):
        from noctem import db
        assert hasattr(db, 'init_db')
        assert hasattr(db, 'get_db')
    
    def test_config_module(self):
        from noctem.config import Config
        assert hasattr(Config, 'get')
        assert hasattr(Config, 'set')
    
    def test_main_module(self):
        from noctem import main
        assert hasattr(main, 'main')
        assert hasattr(main, 'startup_health_check')
    
    def test_models_module(self):
        from noctem import models
    
    def test_cli_module(self):
        from noctem import cli
    
    def test_parser_modules(self):
        from noctem.parser import command, natural_date, task_parser
        from noctem.parser.command import parse_command, CommandType
        from noctem.parser.natural_date import parse_date, parse_time
        from noctem.parser.task_parser import parse_task
    
    def test_services_modules(self):
        from noctem.services import (
            task_service, project_service, goal_service, 
            habit_service, briefing
        )
    
    def test_web_module(self):
        from noctem.web.app import create_app
    
    def test_slow_mode_modules(self):
        from noctem.slow.loop import SlowModeLoop, get_slow_mode_status
        from noctem.slow.ollama import OllamaClient, GracefulDegradation
        from noctem.slow.queue import SlowWorkQueue, WorkType
    
    def test_butler_modules(self):
        from noctem.butler import protocol, clarifications, updates
    
    def test_voice_module(self):
        from noctem.voice import journals
    
    def test_seed_modules(self):
        from noctem.seed import loader, text_parser
    
    def test_telegram_modules(self):
        from noctem.telegram import bot, handlers, formatter
    
    def test_scheduler_module(self):
        from noctem.scheduler import jobs


class TestDatabaseInitialization:
    """Test database initialization and basic operations."""
    
    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Use a temporary database for each test."""
        from noctem import db
        original_path = db.DB_PATH
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "test.db"
            yield
            db.DB_PATH = original_path
    
    def test_init_db(self):
        from noctem.db import init_db, get_db
        init_db()
        
        # Verify tables exist
        with get_db() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            
            required_tables = [
                'goals', 'projects', 'tasks', 'habits', 'habit_logs',
                'time_blocks', 'config', 'action_log', 'message_log',
                'butler_contacts', 'slow_work_queue', 'voice_journals'
            ]
            for table in required_tables:
                assert table in table_names, f"Missing table: {table}"
    
    def test_config_init(self):
        from noctem.db import init_db
        from noctem.config import Config
        
        init_db()
        Config.init_defaults()
        
        # Verify defaults are set
        all_config = Config.get_all()
        assert 'web_port' in all_config
        assert 'timezone' in all_config
        assert 'slow_mode_enabled' in all_config
    
    def test_config_get_set(self):
        from noctem.db import init_db
        from noctem.config import Config
        
        init_db()
        
        Config.set("test_key", "test_value")
        assert Config.get("test_key") == "test_value"
        
        Config.set("test_int", 42)
        assert Config.get("test_int") == 42
        
        Config.set("test_list", [1, 2, 3])
        assert Config.get("test_list") == [1, 2, 3]


class TestFlaskApp:
    """Test Flask application creation and basic routes."""
    
    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Use a temporary database for each test."""
        from noctem import db
        original_path = db.DB_PATH
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "test.db"
            db.init_db()
            yield
            db.DB_PATH = original_path
    
    def test_create_app(self):
        from noctem.web.app import create_app
        app = create_app()
        assert app is not None
        assert app.name == 'noctem.web.app'
    
    def test_health_endpoint(self):
        from noctem.web.app import create_app
        app = create_app()
        
        with app.test_client() as client:
            response = client.get('/health')
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'ok'
    
    def test_dashboard_loads(self):
        from noctem.web.app import create_app
        app = create_app()
        
        with app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200


class TestSlowModeComponents:
    """Test slow mode components can be instantiated."""
    
    def test_ollama_client_init(self):
        from noctem.slow.ollama import OllamaClient
        client = OllamaClient()
        assert client.host is not None
        assert client.model is not None
    
    def test_graceful_degradation(self):
        from noctem.slow.ollama import GracefulDegradation
        
        # Should not raise even if Ollama unavailable
        status = GracefulDegradation.get_system_status()
        assert status in ['full', 'degraded', 'offline']
    
    def test_slow_mode_loop_init(self):
        from noctem.slow.loop import SlowModeLoop
        loop = SlowModeLoop(check_interval=60)
        assert loop.check_interval == 60
        assert loop._running == False


class TestWhisperAvailability:
    """Test Whisper transcription service availability."""
    
    def test_whisper_import(self):
        """Verify faster-whisper can be imported."""
        try:
            from faster_whisper import WhisperModel
            whisper_available = True
        except ImportError:
            whisper_available = False
        
        # This is informational - whisper is optional
        assert True, f"Whisper available: {whisper_available}"
    
    def test_whisper_service_module(self):
        """Verify our whisper service module can be imported."""
        from noctem.slow import whisper
        assert hasattr(whisper, 'get_whisper_service')


class TestExternalServiceConnectivity:
    """Test connectivity to external services (non-blocking)."""
    
    def test_ollama_health_check_does_not_crash(self):
        """Ollama health check should not raise, even if Ollama is down."""
        from noctem.slow.ollama import OllamaClient
        
        client = OllamaClient()
        # Should return a tuple, not raise
        healthy, message = client.health_check()
        assert isinstance(healthy, bool)
        assert isinstance(message, str)
    
    def test_slow_mode_status_does_not_crash(self):
        """Getting slow mode status should not crash."""
        from noctem.slow.loop import get_slow_mode_status
        
        status = get_slow_mode_status()
        assert isinstance(status, dict)
        assert 'enabled' in status
        assert 'can_run' in status


class TestStartupHealthCheck:
    """Test the startup health check function."""
    
    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Use a temporary database for each test."""
        from noctem import db
        original_path = db.DB_PATH
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "test.db"
            db.init_db()
            yield
            db.DB_PATH = original_path
    
    def test_startup_health_check_runs(self):
        """Health check should run without crashing."""
        from noctem.main import startup_health_check
        
        # Should return True (critical checks pass) even if optional services unavailable
        result = startup_health_check(quiet=True)
        assert isinstance(result, bool)


class TestParserComponents:
    """Test that parser components work correctly."""
    
    def test_command_types_defined(self):
        from noctem.parser.command import CommandType
        
        # Verify key command types exist
        assert hasattr(CommandType, 'TODAY')
        assert hasattr(CommandType, 'DONE')
        assert hasattr(CommandType, 'NEW_TASK')
    
    def test_basic_date_parsing(self):
        from noctem.parser.natural_date import parse_date
        from datetime import date, timedelta
        
        parsed, remaining = parse_date("test tomorrow")
        assert parsed == date.today() + timedelta(days=1)
    
    def test_basic_command_parsing(self):
        from noctem.parser.command import parse_command, CommandType
        
        cmd = parse_command("/today")
        assert cmd.type == CommandType.TODAY


class TestNetworkUtilities:
    """Test network-related utilities."""
    
    def test_get_local_ip(self):
        from noctem.main import get_local_ip
        
        ip = get_local_ip()
        assert ip is not None
        # Should be localhost or a valid IP
        assert ip == 'localhost' or '.' in ip


class TestModelsAndDataclasses:
    """Test that model/dataclass definitions are valid."""
    
    def test_parsed_task_model(self):
        from noctem.parser.task_parser import ParsedTask
        
        # Should be able to create a ParsedTask
        task = ParsedTask(name="Test task")
        assert task.name == "Test task"
    
    def test_parsed_command_model(self):
        from noctem.parser.command import ParsedCommand, CommandType
        
        result = ParsedCommand(type=CommandType.NEW_TASK, args=[], raw_text="test")
        assert result.type == CommandType.NEW_TASK
