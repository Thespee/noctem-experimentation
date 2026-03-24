"""Shared test fixtures for Noctem tests."""
import tempfile
import pytest
from pathlib import Path

from .. import db


@pytest.fixture(autouse=True)
def setup_test_db():
    """Use a temporary database for each test — shared across all test files."""
    original_path = db.DB_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        db.DB_PATH = Path(tmpdir) / "test.db"
        db.init_db()
        yield
        db.DB_PATH = original_path
