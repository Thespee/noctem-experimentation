"""
Import smoke tests for Noctem.

These tests verify that all modules can be imported successfully,
catching missing dependencies before runtime.
"""
import pytest
import importlib
import sys


# All modules that should be importable
CORE_MODULES = [
    "noctem",
    "noctem.db",
    "noctem.config",
    "noctem.models",
    "noctem.cli",
    "noctem.main",
]

SERVICE_MODULES = [
    "noctem.services",
    "noctem.services.task_service",
    "noctem.services.project_service",
    "noctem.services.goal_service",
    "noctem.services.briefing",
    "noctem.services.message_logger",
    "noctem.services.ics_import",
]

PARSER_MODULES = [
    "noctem.parser",
    "noctem.parser.task_parser",
    "noctem.parser.command",
]

TELEGRAM_MODULES = [
    "noctem.telegram",
    "noctem.telegram.bot",
    "noctem.telegram.handlers",
    "noctem.telegram.formatter",
]

WEB_MODULES = [
    "noctem.web",
    "noctem.web.app",
]

SCHEDULER_MODULES = [
    "noctem.scheduler",
    "noctem.scheduler.jobs",
]

# v0.6.0 modules
V060_MODULES = [
    "noctem.fast",
    "noctem.slow",
    "noctem.butler",
    "noctem.slow.ollama",
    "noctem.slow.queue",
    "noctem.slow.loop",
    "noctem.slow.task_analyzer",
    "noctem.slow.project_analyzer",
    "noctem.butler.protocol",
    "noctem.butler.updates",
    "noctem.butler.clarifications",
]

ALL_MODULES = (
    CORE_MODULES + 
    SERVICE_MODULES + 
    PARSER_MODULES + 
    TELEGRAM_MODULES + 
    WEB_MODULES + 
    SCHEDULER_MODULES + 
    V060_MODULES
)


class TestImports:
    """Test that all modules can be imported."""
    
    @pytest.mark.parametrize("module_name", CORE_MODULES)
    def test_core_imports(self, module_name):
        """Core modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", SERVICE_MODULES)
    def test_service_imports(self, module_name):
        """Service modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", PARSER_MODULES)
    def test_parser_imports(self, module_name):
        """Parser modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", TELEGRAM_MODULES)
    def test_telegram_imports(self, module_name):
        """Telegram modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", WEB_MODULES)
    def test_web_imports(self, module_name):
        """Web modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", SCHEDULER_MODULES)
    def test_scheduler_imports(self, module_name):
        """Scheduler modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None
    
    @pytest.mark.parametrize("module_name", V060_MODULES)
    def test_v060_imports(self, module_name):
        """v0.6.0 modules should import without errors."""
        module = importlib.import_module(module_name)
        assert module is not None


class TestDependencies:
    """Test that critical third-party dependencies are available."""
    
    def test_flask_available(self):
        """Flask should be installed."""
        import flask
        assert flask.__version__
    
    def test_telegram_available(self):
        """python-telegram-bot should be installed."""
        import telegram
        assert telegram.__version__
    
    def test_httpx_available(self):
        """httpx should be installed (for Ollama client)."""
        import httpx
        assert httpx.__version__
    
    def test_apscheduler_available(self):
        """APScheduler should be installed."""
        import apscheduler
        assert apscheduler.__version__
    
    def test_icalendar_available(self):
        """icalendar should be installed."""
        import icalendar
        assert icalendar.__version__
    
    def test_dotenv_has_find_dotenv(self):
        """python-dotenv should have find_dotenv (not the wrong dotenv package)."""
        import dotenv
        assert hasattr(dotenv, 'find_dotenv'), \
            "Wrong dotenv package installed! Run: pip uninstall dotenv && pip install python-dotenv"


class TestModuleAttributes:
    """Test that key module attributes exist."""
    
    def test_db_has_init_db(self):
        """db module should have init_db function."""
        from noctem import db
        assert hasattr(db, 'init_db')
        assert callable(db.init_db)
    
    def test_config_has_get(self):
        """Config should have get method."""
        from noctem.config import Config
        assert hasattr(Config, 'get')
    
    def test_ollama_client_has_health_check(self):
        """OllamaClient should have health_check method."""
        from noctem.slow.ollama import OllamaClient
        client = OllamaClient()
        assert hasattr(client, 'health_check')
        assert callable(client.health_check)
    
    def test_butler_protocol_has_get_status(self):
        """Butler protocol should have get_butler_status."""
        from noctem.butler.protocol import get_butler_status
        assert callable(get_butler_status)
    
    def test_web_app_has_create_app(self):
        """Web app should have create_app function."""
        from noctem.web.app import create_app
        assert callable(create_app)
