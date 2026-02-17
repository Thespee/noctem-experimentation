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
    """
    from noctem import db
    original_path = db.DB_PATH
    db.DB_PATH = _TEST_DB_PATH
    yield
    db.DB_PATH = original_path
