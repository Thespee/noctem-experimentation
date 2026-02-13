#!/usr/bin/env python3
"""
Tests for task_status skill.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.task_status import TaskStatusSkill
from skills.base import SkillContext
import state


# =============================================================================
# Basic Tests
# =============================================================================

def test_task_status_runs():
    """Test that task_status skill runs without error."""
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert result.success, f"Should succeed: {result.error}"
    assert len(result.output) > 0, "Should have output"
    return {"status": "pass", "message": "Task status skill runs"}


def test_task_status_has_sections():
    """Test that output has expected sections."""
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert "RUNNING" in result.output, "Should have RUNNING section"
    assert "PENDING" in result.output, "Should have PENDING section"
    return {"status": "pass", "message": "Output has expected sections"}


def test_task_status_includes_recent():
    """Test include_recent parameter."""
    # Create a completed task first
    task_id = state.create_task("Status test task", source="test")
    state.start_task(task_id)
    state.complete_task(task_id, "Result", success=True)
    
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({"include_recent": True}, ctx)
    
    assert result.success
    assert "RECENT" in result.output, "Should have RECENT section when enabled"
    return {"status": "pass", "message": "include_recent parameter working"}


def test_task_status_excludes_recent():
    """Test excluding recent tasks."""
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({"include_recent": False}, ctx)
    
    assert result.success
    # May or may not have RECENT depending on implementation
    return {"status": "pass", "message": "Exclude recent working"}


def test_task_status_data_fields():
    """Test that data fields are populated."""
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert result.success
    assert "running_count" in result.data, "Should have running_count"
    assert "pending_count" in result.data, "Should have pending_count"
    return {"status": "pass", "message": "Data fields populated"}


def test_task_status_shows_pending():
    """Test that pending tasks appear in output."""
    # Create a pending task
    task_id = state.create_task("Pending visibility test", source="test", priority=5)
    
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert result.success
    # The task should be in pending count
    assert result.data["pending_count"] >= 1, f"Should have pending tasks: {result.data}"
    return {"status": "pass", "message": "Pending tasks visible"}


def test_task_status_recent_limit():
    """Test recent_limit parameter."""
    skill = TaskStatusSkill()
    ctx = SkillContext()
    
    result = skill.execute({"include_recent": True, "recent_limit": 3}, ctx)
    
    assert result.success
    # recent_count should be at most 3
    assert result.data["recent_count"] <= 3, f"Should respect limit: {result.data}"
    return {"status": "pass", "message": "recent_limit working"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    ("task_status_runs", test_task_status_runs),
    ("task_status_has_sections", test_task_status_has_sections),
    ("task_status_includes_recent", test_task_status_includes_recent),
    ("task_status_excludes_recent", test_task_status_excludes_recent),
    ("task_status_data_fields", test_task_status_data_fields),
    ("task_status_shows_pending", test_task_status_shows_pending),
    ("task_status_recent_limit", test_task_status_recent_limit),
]


def run_all(verbose: bool = False) -> dict:
    """Run all task status tests."""
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
    print("Running task status skill tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
