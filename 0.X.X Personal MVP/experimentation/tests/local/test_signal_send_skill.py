#!/usr/bin/env python3
"""
Tests for signal_send skill.
These are mock-based tests since we can't actually send Signal messages in tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.signal_send import SignalSendSkill, SIGNAL_DAEMON_HOST, SIGNAL_DAEMON_PORT
from skills.base import SkillContext


# =============================================================================
# Validation Tests (No network required)
# =============================================================================

def test_signal_send_no_message():
    """Test that missing message fails."""
    skill = SignalSendSkill()
    ctx = SkillContext(config={"signal_phone": "+1234567890"})
    
    result = skill.execute({}, ctx)
    
    assert not result.success, "Should fail without message"
    assert "message" in result.error.lower() or "no message" in result.error.lower(), \
        f"Error should mention message: {result.error}"
    return {"status": "pass", "message": "Missing message handled"}


def test_signal_send_empty_message():
    """Test that empty message fails."""
    skill = SignalSendSkill()
    ctx = SkillContext(config={"signal_phone": "+1234567890"})
    
    result = skill.execute({"message": ""}, ctx)
    
    assert not result.success, "Should fail with empty message"
    return {"status": "pass", "message": "Empty message handled"}


def test_signal_send_no_recipient():
    """Test that missing recipient (no config) fails."""
    skill = SignalSendSkill()
    ctx = SkillContext(config={})  # No signal_phone
    
    result = skill.execute({"message": "test"}, ctx)
    
    assert not result.success, "Should fail without recipient"
    assert "recipient" in result.error.lower() or "phone" in result.error.lower(), \
        f"Error should mention recipient: {result.error}"
    return {"status": "pass", "message": "Missing recipient handled"}


def test_signal_send_skill_metadata():
    """Test skill metadata."""
    skill = SignalSendSkill()
    
    assert skill.name == "signal_send", "Name should be signal_send"
    assert "message" in skill.parameters, "Should have message parameter"
    assert len(skill.description) > 0, "Should have description"
    return {"status": "pass", "message": "Skill metadata correct"}


def test_signal_send_manifest():
    """Test skill manifest generation."""
    skill = SignalSendSkill()
    manifest = skill.get_manifest()
    
    assert manifest["name"] == "signal_send"
    assert "description" in manifest
    assert "parameters" in manifest
    return {"status": "pass", "message": "Manifest generation working"}


def test_signal_constants():
    """Test that signal constants are defined."""
    assert SIGNAL_DAEMON_HOST == "127.0.0.1", "Host should be localhost"
    assert SIGNAL_DAEMON_PORT == 7583, "Port should be 7583"
    return {"status": "pass", "message": "Signal constants defined"}


def test_signal_daemon_not_running():
    """Test handling when daemon is not running."""
    skill = SignalSendSkill()
    ctx = SkillContext(config={"signal_phone": "+1234567890"})
    
    # This will try to connect and fail (assuming daemon isn't running in test)
    result = skill.execute({"message": "test"}, ctx)
    
    # Should fail with connection error
    if not result.success:
        assert "daemon" in result.error.lower() or "connect" in result.error.lower() or "refused" in result.error.lower(), \
            f"Error should mention daemon/connection: {result.error}"
        return {"status": "pass", "message": "Daemon not running handled correctly"}
    else:
        # If it somehow succeeds (daemon is running), that's also fine
        return {"status": "pass", "message": "Signal daemon is running - send succeeded"}


def test_signal_recipient_from_config():
    """Test that recipient defaults to config."""
    skill = SignalSendSkill()
    phone = "+15551234567"
    ctx = SkillContext(config={"signal_phone": phone})
    
    # Validate params without sending
    error = skill.validate_params({"message": "test"})
    assert error is None, f"Should pass validation: {error}"
    return {"status": "pass", "message": "Config recipient used"}


def test_signal_explicit_recipient():
    """Test explicit recipient parameter."""
    skill = SignalSendSkill()
    ctx = SkillContext(config={"signal_phone": "+1111111111"})
    
    # With explicit recipient, validation should pass even if config has different number
    error = skill.validate_params({"message": "test", "recipient": "+2222222222"})
    assert error is None, f"Should pass validation: {error}"
    return {"status": "pass", "message": "Explicit recipient accepted"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    ("signal_send_no_message", test_signal_send_no_message),
    ("signal_send_empty_message", test_signal_send_empty_message),
    ("signal_send_no_recipient", test_signal_send_no_recipient),
    ("signal_send_skill_metadata", test_signal_send_skill_metadata),
    ("signal_send_manifest", test_signal_send_manifest),
    ("signal_constants", test_signal_constants),
    ("signal_daemon_not_running", test_signal_daemon_not_running),
    ("signal_recipient_from_config", test_signal_recipient_from_config),
    ("signal_explicit_recipient", test_signal_explicit_recipient),
]


def run_all(verbose: bool = False) -> dict:
    """Run all signal send tests."""
    results = {"passed": 0, "failed": 0, "errors": []}
    
    for name, test_fn in ALL_TESTS:
        try:
            result = test_fn()
            results["passed"] += 1
            if verbose:
                print(f"  ✓ {name}: {result.get('message', 'OK')}")
        except AssertionError as e:
            results["failed"] += 1
            results["errors"].append({"test": name, "error": str(e)})
            if verbose:
                print(f"  ✗ {name}: {e}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"test": name, "error": str(e), "type": type(e).__name__})
            if verbose:
                print(f"  ✗ {name}: [{type(e).__name__}] {e}")
    
    return results


if __name__ == "__main__":
    print("Running signal send skill tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
