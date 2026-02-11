#!/usr/bin/env python3
"""
Tests for email skills: email_send and daily_report.

Run with: python tests/test_email_skills.py
        or: pytest tests/test_email_skills.py -v
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import tempfile
import pytest

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import state
import utils.vault as vault_module
from utils.vault import Vault, get_vault, init_vault


class MockSMTP:
    """Mock SMTP server for testing."""
    
    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.messages_sent = []
        self._logged_in = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def ehlo(self):
        pass
    
    def starttls(self, context=None):
        pass
    
    def login(self, user, password):
        if password == "bad_password":
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, "Authentication failed")
        self._logged_in = True
    
    def send_message(self, msg):
        if not self._logged_in:
            raise Exception("Not logged in")
        self.messages_sent.append(msg)
    
    def noop(self):
        pass


def setup_test_environment():
    """Set up test database and environment."""
    # Use temp directory for test data
    test_dir = Path(tempfile.mkdtemp())
    test_db = test_dir / "test_noctem.db"
    
    # Monkey-patch the DB path
    state.DB_PATH = test_db
    state.init_db()
    
    # Reset global vault first
    vault_module._vault = None
    
    # Initialize vault with test credentials
    os.environ["NOCTEM_EMAIL_USER"] = "test@example.com"
    os.environ["NOCTEM_EMAIL_PASSWORD"] = "test_password"
    os.environ["NOCTEM_EMAIL_SMTP_SERVER"] = "smtp.test.com"
    os.environ["NOCTEM_EMAIL_RECIPIENT"] = "recipient@example.com"
    
    init_vault()
    
    return test_dir


def cleanup_test_environment():
    """Clean up test environment."""
    for key in ["NOCTEM_EMAIL_USER", "NOCTEM_EMAIL_PASSWORD", 
                "NOCTEM_EMAIL_SMTP_SERVER", "NOCTEM_EMAIL_RECIPIENT"]:
        os.environ.pop(key, None)
    # Reset global vault
    vault_module._vault = None


@pytest.fixture(autouse=True)
def email_test_setup():
    """Pytest fixture that runs before each test."""
    test_dir = setup_test_environment()
    yield
    cleanup_test_environment()
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)


def test_vault_env_backend():
    """Test vault with environment variable backend."""
    print("Testing vault with env backend...")
    
    vault = get_vault()
    
    # Should read from env
    assert vault.get("email_user") == "test@example.com"
    assert vault.get("email_password") == "test_password"
    assert vault.get_backend() == "env"
    
    # Status should show configured keys
    status = vault.status()
    assert "email_user" in status["configured_keys"]
    
    print("✓ Vault env backend test passed")


def test_vault_invalid_key():
    """Test vault rejects invalid keys."""
    print("Testing vault invalid key handling...")
    
    vault = get_vault()
    
    try:
        vault.get("invalid_key_name")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid key" in str(e)
    
    print("✓ Vault invalid key test passed")


@patch("smtplib.SMTP", MockSMTP)
def test_email_send_success():
    """Test successful email sending."""
    print("Testing email send (success)...")
    
    from skills.email_send import send_email_smtp
    
    success, message = send_email_smtp(
        to="recipient@example.com",
        subject="Test Subject",
        body="Test body content"
    )
    
    assert success, f"Expected success, got: {message}"
    assert "sent" in message.lower()
    
    print("✓ Email send success test passed")


@patch("smtplib.SMTP", MockSMTP)
def test_email_send_auth_failure():
    """Test email send with authentication failure."""
    print("Testing email send (auth failure)...")
    
    from skills.email_send import send_email_smtp
    
    # Temporarily set bad password
    os.environ["NOCTEM_EMAIL_PASSWORD"] = "bad_password"
    init_vault()  # Reinitialize
    
    success, message = send_email_smtp(
        to="recipient@example.com",
        subject="Test",
        body="Test"
    )
    
    assert not success
    assert "authentication" in message.lower()
    
    # Restore good password
    os.environ["NOCTEM_EMAIL_PASSWORD"] = "test_password"
    init_vault()
    
    print("✓ Email send auth failure test passed")


def test_email_send_no_credentials():
    """Test email send without credentials configured."""
    print("Testing email send (no credentials)...")
    
    # Clear credentials
    cleanup_test_environment()
    init_vault()
    
    from skills.email_send import send_email_smtp
    
    success, message = send_email_smtp(
        to="test@example.com",
        subject="Test",
        body="Test"
    )
    
    assert not success
    assert "not configured" in message.lower()
    
    # Restore credentials
    setup_test_environment()
    
    print("✓ Email send no credentials test passed")


def test_daily_report_generation():
    """Test daily report generation."""
    print("Testing daily report generation...")
    
    from skills.daily_report import generate_report
    
    # Add some test data
    task_id = state.create_task("Test task 1", source="test")
    state.complete_task(task_id, "Success", success=True)
    
    task_id2 = state.create_task("Test task 2", source="test")
    state.complete_task(task_id2, "Failed because reasons", success=False)
    
    state.log_incident("Test warning", severity="warning", category="test")
    state.log_incident("Test error", severity="error", category="test")
    
    # Generate report
    report_text, stats = generate_report(period_hours=24)
    
    assert "NOCTEM DAILY REPORT" in report_text
    assert "TASKS COMPLETED" in report_text
    assert "INCIDENTS" in report_text
    assert "SUGGESTED ACTIONS" in report_text
    
    assert stats["tasks_completed"] >= 1
    assert stats["incidents_count"] >= 2
    
    print(f"✓ Daily report generation test passed")
    print(f"  Stats: {stats}")


def test_daily_report_suggestions():
    """Test that suggestions are generated correctly."""
    print("Testing daily report suggestions...")
    
    from skills.daily_report import generate_suggestions
    
    # No activity - should suggest checking
    suggestions = generate_suggestions([], [], [], [])
    assert any("no tasks" in s.lower() or "nominal" in s.lower() for s in suggestions)
    
    # Failed tasks - should suggest retry
    failed = [{"id": 1, "status": "failed"}]
    suggestions = generate_suggestions([], failed, [], [])
    assert any("failed" in s.lower() for s in suggestions)
    
    # Pending tasks
    pending = [{"id": 1, "priority": 2}]
    suggestions = generate_suggestions([], [], [], pending)
    assert any("priority" in s.lower() or "queue" in s.lower() for s in suggestions)
    
    # Multiple errors
    errors = [
        {"severity": "error"} for _ in range(5)
    ]
    suggestions = generate_suggestions([], [], errors, [])
    assert any("error" in s.lower() or "health" in s.lower() for s in suggestions)
    
    print("✓ Daily report suggestions test passed")


@patch("smtplib.SMTP", MockSMTP)
def test_daily_report_send():
    """Test daily report send."""
    print("Testing daily report send...")
    
    from skills.daily_report import send_daily_report
    
    success, message, stats = send_daily_report(
        recipient="test@example.com",
        period_hours=24
    )
    
    assert success, f"Expected success, got: {message}"
    assert "sent" in message.lower() or "email" in message.lower()
    
    # Check that report was saved
    last_report = state.get_last_report_date()
    assert last_report is not None
    
    print("✓ Daily report send test passed")


def test_incident_logging():
    """Test incident logging functions."""
    print("Testing incident logging...")
    
    # Log some incidents
    state.log_incident("Info message", severity="info", category="test")
    state.log_incident("Warning message", severity="warning", category="test")
    state.log_incident("Error message", severity="error", category="system")
    
    # Get recent incidents
    since = datetime.now() - timedelta(hours=1)
    incidents = state.get_incidents_since(since)
    
    assert len(incidents) >= 3
    assert any(i["severity"] == "error" for i in incidents)
    
    # Test acknowledgment
    unacked = state.get_unacknowledged_incidents()
    assert len(unacked) >= 3
    
    state.acknowledge_incidents()
    
    unacked_after = state.get_unacknowledged_incidents()
    assert len(unacked_after) == 0
    
    print("✓ Incident logging test passed")


def test_email_skill_class():
    """Test EmailSendSkill class integration."""
    print("Testing EmailSendSkill class...")
    
    from skills.email_send import EmailSendSkill
    from skills.base import SkillContext
    
    skill = EmailSendSkill()
    
    # Test validation
    ctx = SkillContext()
    
    # Missing recipient
    result = skill.run({"subject": "Test", "body": "Test"}, ctx)
    assert not result.success
    assert "recipient" in result.error.lower() or "address" in result.error.lower()
    
    # Invalid email
    result = skill.run({"to": "invalid", "subject": "Test", "body": "Test"}, ctx)
    assert not result.success
    
    # Missing subject
    result = skill.run({"to": "test@example.com", "body": "Test"}, ctx)
    assert not result.success
    assert "subject" in result.error.lower()
    
    print("✓ EmailSendSkill class test passed")


@patch("smtplib.SMTP", MockSMTP)
def test_daily_report_skill_class():
    """Test DailyReportSkill class integration."""
    print("Testing DailyReportSkill class...")
    
    from skills.daily_report import DailyReportSkill
    from skills.base import SkillContext
    
    skill = DailyReportSkill()
    ctx = SkillContext()
    
    # Generate only (no send)
    result = skill.run({"send": False}, ctx)
    assert result.success
    assert "NOCTEM DAILY REPORT" in result.output
    assert result.data["sent"] == False
    
    # Generate and send
    result = skill.run({"send": True}, ctx)
    assert result.success
    assert result.data["sent"] == True
    
    print("✓ DailyReportSkill class test passed")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("NOCTEM EMAIL SKILLS TESTS")
    print("=" * 50 + "\n")
    
    # Setup
    test_dir = setup_test_environment()
    print(f"Test database: {state.DB_PATH}\n")
    
    try:
        # Run tests
        test_vault_env_backend()
        test_vault_invalid_key()
        test_email_send_success()
        test_email_send_auth_failure()
        test_email_send_no_credentials()
        test_daily_report_generation()
        test_daily_report_suggestions()
        test_daily_report_send()
        test_incident_logging()
        test_email_skill_class()
        test_daily_report_skill_class()
        
        print("\n" + "=" * 50)
        print("✓ ALL TESTS PASSED!")
        print("=" * 50 + "\n")
        return 0
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cleanup_test_environment()
        # Clean up temp directory
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_all_tests())
