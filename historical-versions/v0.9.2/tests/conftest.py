"""
Pytest configuration and fixtures for Noctem tests.
"""
import pytest
import os
import sys
import tempfile
from pathlib import Path

# Ensure noctem package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create a shared test database path for all tests
_TEST_DB_PATH = Path(tempfile.gettempdir()) / "noctem_test.db"


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """
    Initialize a shared test database for all tests.
    This runs once per test session.
    """
    from noctem import db
    from noctem.db import init_db
    
    # Remove old test DB if exists
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
    
    # Set the shared test DB path
    db.DB_PATH = _TEST_DB_PATH
    
    # Initialize with full schema including voice_journals
    init_db()
    
    yield
    
    # Cleanup after all tests
    if _TEST_DB_PATH.exists():
        try:
            _TEST_DB_PATH.unlink()
        except Exception:
            pass  # File might be locked


@pytest.fixture(autouse=True)
def ensure_db_path():
    """
    Ensure DB_PATH is set correctly for each test.
    This handles tests that might override DB_PATH.
    Also cleans up skills tables between tests for isolation.
    """
    from noctem import db
    from noctem.db import get_db
    
    original_path = db.DB_PATH
    db.DB_PATH = _TEST_DB_PATH
    
    # Clean up skills tables before each test for isolation
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM skill_executions")
            conn.execute("DELETE FROM skills")
    except Exception:
        pass  # Tables might not exist yet
    
    # Clean up wiki tables before each test for isolation
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM knowledge_chunks")
            conn.execute("DELETE FROM sources")
    except Exception:
        pass  # Tables might not exist yet
    
    # Clean up feedback tables before each test for isolation
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM feedback_questions")
            conn.execute("DELETE FROM feedback_sessions")
    except Exception:
        pass  # Tables might not exist yet
    
    yield
    
    db.DB_PATH = original_path
