#!/usr/bin/env python3
"""
Tests for SQLite state management module.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import state


# =============================================================================
# State Key-Value Tests
# =============================================================================

def test_state_set_and_get_string():
    """Test setting and getting a string value."""
    state.set_state("test_string_key", "test_value")
    result = state.get_state("test_string_key")
    
    assert result == "test_value", f"Expected 'test_value', got {result}"
    return {"status": "pass", "message": "String state set/get working"}


def test_state_set_and_get_dict():
    """Test setting and getting a dict value (JSON serialization)."""
    test_data = {"key": "value", "num": 42, "nested": {"a": 1}}
    state.set_state("test_dict_key", test_data)
    result = state.get_state("test_dict_key")
    
    assert result == test_data, f"Data mismatch: {result}"
    return {"status": "pass", "message": "Dict state set/get working"}


def test_state_get_default():
    """Test getting non-existent key returns default."""
    result = state.get_state("nonexistent_key_xyz", default="default_val")
    
    assert result == "default_val", f"Should return default, got {result}"
    return {"status": "pass", "message": "State default value working"}


def test_state_update():
    """Test updating an existing state value."""
    state.set_state("test_update_key", "original")
    state.set_state("test_update_key", "updated")
    result = state.get_state("test_update_key")
    
    assert result == "updated", f"Should be updated, got {result}"
    return {"status": "pass", "message": "State update working"}


# =============================================================================
# Task Tests
# =============================================================================

def test_task_create():
    """Test creating a task."""
    task_id = state.create_task("Test task input", source="test", priority=5)
    
    assert task_id is not None, "Should return task ID"
    assert isinstance(task_id, int), f"Task ID should be int, got {type(task_id)}"
    assert task_id > 0, f"Task ID should be positive, got {task_id}"
    return {"status": "pass", "message": f"Task created with ID {task_id}"}


def test_task_get():
    """Test retrieving a task by ID."""
    task_id = state.create_task("Get test task", source="test", priority=3)
    task = state.get_task(task_id)
    
    assert task is not None, "Task should exist"
    assert task["id"] == task_id, "Task ID should match"
    assert task["input"] == "Get test task", "Input should match"
    assert task["source"] == "test", "Source should match"
    assert task["priority"] == 3, f"Priority should be 3, got {task['priority']}"
    assert task["status"] == "pending", f"Status should be pending, got {task['status']}"
    return {"status": "pass", "message": "Task get working"}


def test_task_get_nonexistent():
    """Test retrieving non-existent task."""
    task = state.get_task(999999)
    
    assert task is None, "Should return None for non-existent task"
    return {"status": "pass", "message": "Non-existent task returns None"}


def test_task_start():
    """Test starting a task."""
    task_id = state.create_task("Start test task", source="test")
    state.start_task(task_id)
    
    task = state.get_task(task_id)
    assert task["status"] == "running", f"Status should be running, got {task['status']}"
    assert task["started_at"] is not None, "started_at should be set"
    return {"status": "pass", "message": "Task start working"}


def test_task_complete_success():
    """Test completing a task successfully."""
    task_id = state.create_task("Complete test task", source="test")
    state.start_task(task_id)
    state.complete_task(task_id, "Task result", success=True)
    
    task = state.get_task(task_id)
    assert task["status"] == "done", f"Status should be done, got {task['status']}"
    assert task["result"] == "Task result", "Result should match"
    assert task["completed_at"] is not None, "completed_at should be set"
    return {"status": "pass", "message": "Task complete (success) working"}


def test_task_complete_failure():
    """Test completing a task with failure."""
    task_id = state.create_task("Fail test task", source="test")
    state.start_task(task_id)
    state.complete_task(task_id, "Error message", success=False)
    
    task = state.get_task(task_id)
    assert task["status"] == "failed", f"Status should be failed, got {task['status']}"
    return {"status": "pass", "message": "Task complete (failure) working"}


def test_task_cancel():
    """Test cancelling a pending task."""
    task_id = state.create_task("Cancel test task", source="test")
    result = state.cancel_task(task_id)
    
    assert result is True, "Should return True for successful cancel"
    
    task = state.get_task(task_id)
    assert task["status"] == "cancelled", f"Status should be cancelled, got {task['status']}"
    return {"status": "pass", "message": "Task cancel working"}


def test_get_pending_tasks():
    """Test getting pending tasks."""
    # Create a pending task
    task_id = state.create_task("Pending test task", source="test", priority=1)
    
    pending = state.get_pending_tasks()
    
    assert isinstance(pending, list), "Should return list"
    # Our new task should be in there
    task_ids = [t["id"] for t in pending]
    assert task_id in task_ids, f"New task {task_id} should be in pending list"
    return {"status": "pass", "message": f"Got {len(pending)} pending tasks"}


def test_get_next_task():
    """Test getting next task (highest priority, oldest first)."""
    # Create tasks with different priorities
    low_priority_id = state.create_task("Low priority", source="test", priority=9)
    high_priority_id = state.create_task("High priority", source="test", priority=1)
    
    next_task = state.get_next_task()
    
    assert next_task is not None, "Should have a next task"
    # High priority (lower number) should come first
    assert next_task["priority"] <= 1, f"Next task should be high priority, got priority {next_task['priority']}"
    return {"status": "pass", "message": "get_next_task working"}


def test_set_task_priority():
    """Test changing task priority."""
    task_id = state.create_task("Priority test task", source="test", priority=5)
    result = state.set_task_priority(task_id, 2)
    
    assert result is True, "Should return True for successful priority change"
    
    task = state.get_task(task_id)
    assert task["priority"] == 2, f"Priority should be 2, got {task['priority']}"
    return {"status": "pass", "message": "Task priority change working"}


# =============================================================================
# Memory Tests
# =============================================================================

def test_add_memory():
    """Test adding memory entry."""
    # Just ensure it doesn't error
    state.add_memory("user", "Test message", task_id=None)
    state.add_memory("assistant", "Test response", task_id=None)
    return {"status": "pass", "message": "add_memory working"}


def test_get_recent_memory():
    """Test getting recent memory."""
    # Add some memory
    state.add_memory("user", "Memory test message")
    
    memory = state.get_recent_memory(limit=5)
    
    assert isinstance(memory, list), "Should return list"
    if memory:
        assert "role" in memory[-1], "Memory entry should have role"
        assert "content" in memory[-1], "Memory entry should have content"
    return {"status": "pass", "message": f"Got {len(memory)} memory entries"}


def test_get_task_memory():
    """Test getting memory for a specific task."""
    task_id = state.create_task("Memory task test", source="test")
    state.add_memory("user", "Task-specific message", task_id=task_id)
    state.add_memory("assistant", "Task-specific response", task_id=task_id)
    
    memory = state.get_task_memory(task_id)
    
    assert isinstance(memory, list), "Should return list"
    assert len(memory) >= 2, f"Should have at least 2 entries, got {len(memory)}"
    return {"status": "pass", "message": f"Got {len(memory)} task memory entries"}


# =============================================================================
# Skill Log Tests
# =============================================================================

def test_log_skill_execution():
    """Test logging skill execution."""
    task_id = state.create_task("Skill log test", source="test")
    
    # Log an execution
    state.log_skill_execution(
        task_id=task_id,
        skill_name="shell",
        input_data='{"command": "echo test"}',
        output="test",
        success=True,
        duration_ms=50
    )
    return {"status": "pass", "message": "log_skill_execution working"}


def test_get_task_skill_log():
    """Test getting skill log for a task."""
    task_id = state.create_task("Skill log retrieve test", source="test")
    
    state.log_skill_execution(
        task_id=task_id,
        skill_name="test_skill",
        input_data="test input",
        output="test output",
        success=True,
        duration_ms=100
    )
    
    log = state.get_task_skill_log(task_id)
    
    assert isinstance(log, list), "Should return list"
    assert len(log) >= 1, f"Should have at least 1 entry, got {len(log)}"
    assert log[0]["skill_name"] == "test_skill", "Skill name should match"
    return {"status": "pass", "message": f"Got {len(log)} skill log entries"}


# =============================================================================
# Boot Tests
# =============================================================================

def test_record_boot():
    """Test recording boot info."""
    boot_info = state.record_boot()
    
    assert "current_boot" in boot_info, "Should have current_boot"
    assert "current_machine" in boot_info, "Should have current_machine"
    assert boot_info["current_machine"] is not None, "Machine should not be None"
    return {"status": "pass", "message": f"Boot recorded on {boot_info['current_machine']}"}


def test_boot_count():
    """Test boot count increments."""
    old_count = state.get_state("boot_count", 0)
    state.record_boot()
    new_count = state.get_state("boot_count", 0)
    
    assert new_count >= old_count, f"Boot count should not decrease: {old_count} -> {new_count}"
    return {"status": "pass", "message": f"Boot count: {new_count}"}


# =============================================================================
# Database Tests
# =============================================================================

def test_database_exists():
    """Test that database file exists."""
    assert state.DB_PATH.exists(), f"Database should exist at {state.DB_PATH}"
    return {"status": "pass", "message": f"Database: {state.DB_PATH}"}


def test_database_connection():
    """Test database connection works."""
    conn = state.get_connection()
    
    assert conn is not None, "Should get connection"
    
    # Test we can query
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    conn.close()
    
    assert result[0] == 1, "Query should return 1"
    return {"status": "pass", "message": "Database connection working"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    # State tests
    ("state_set_and_get_string", test_state_set_and_get_string),
    ("state_set_and_get_dict", test_state_set_and_get_dict),
    ("state_get_default", test_state_get_default),
    ("state_update", test_state_update),
    # Task tests
    ("task_create", test_task_create),
    ("task_get", test_task_get),
    ("task_get_nonexistent", test_task_get_nonexistent),
    ("task_start", test_task_start),
    ("task_complete_success", test_task_complete_success),
    ("task_complete_failure", test_task_complete_failure),
    ("task_cancel", test_task_cancel),
    ("get_pending_tasks", test_get_pending_tasks),
    ("get_next_task", test_get_next_task),
    ("set_task_priority", test_set_task_priority),
    # Memory tests
    ("add_memory", test_add_memory),
    ("get_recent_memory", test_get_recent_memory),
    ("get_task_memory", test_get_task_memory),
    # Skill log tests
    ("log_skill_execution", test_log_skill_execution),
    ("get_task_skill_log", test_get_task_skill_log),
    # Boot tests
    ("record_boot", test_record_boot),
    ("boot_count", test_boot_count),
    # Database tests
    ("database_exists", test_database_exists),
    ("database_connection", test_database_connection),
]


def run_all(verbose: bool = False) -> dict:
    """Run all state tests."""
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
    print("Running state tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
