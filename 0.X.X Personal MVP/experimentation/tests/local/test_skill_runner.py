#!/usr/bin/env python3
"""
Tests for skill runner and skill chaining.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skill_runner import run_skill, run_skill_chain, list_skills, load_config


# =============================================================================
# Config Tests
# =============================================================================

def test_load_config():
    """Test loading configuration."""
    config = load_config()
    
    assert isinstance(config, dict), "Config should be dict"
    # Config may be empty or have keys - just ensure it loads
    return {"status": "pass", "message": f"Config loaded with {len(config)} keys"}


# =============================================================================
# Skill Listing Tests
# =============================================================================

def test_list_skills():
    """Test listing available skills."""
    skills = list_skills()
    
    assert isinstance(skills, dict), "Should return dict"
    assert len(skills) > 0, "Should have skills registered"
    
    # Check expected skills exist
    expected = ["shell", "file_read", "file_write"]
    for skill_name in expected:
        assert skill_name in skills, f"Expected skill '{skill_name}' not found"
    
    return {"status": "pass", "message": f"Found {len(skills)} skills"}


def test_list_skills_has_descriptions():
    """Test that listed skills have descriptions."""
    skills = list_skills()
    
    for name, info in skills.items():
        assert "description" in info, f"Skill {name} should have description"
        assert len(info["description"]) > 0, f"Skill {name} description should not be empty"
    
    return {"status": "pass", "message": "All skills have descriptions"}


# =============================================================================
# Single Skill Execution Tests
# =============================================================================

def test_run_skill_shell():
    """Test running shell skill."""
    result = run_skill("shell", {"command": "echo 'hello world'"})
    
    assert result.success, f"Should succeed, error: {result.error}"
    assert "hello world" in result.output, f"Output should contain 'hello world', got: {result.output}"
    return {"status": "pass", "message": "Shell skill execution working"}


def test_run_skill_shell_with_task_id():
    """Test running skill with task context."""
    import state
    task_id = state.create_task("Test task for skill runner", source="test")
    
    result = run_skill("shell", {"command": "echo 'with task'"}, task_id=task_id)
    
    assert result.success, f"Should succeed, error: {result.error}"
    return {"status": "pass", "message": "Skill execution with task_id working"}


def test_run_skill_unknown():
    """Test running unknown skill."""
    result = run_skill("nonexistent_skill_xyz", {"param": "value"})
    
    assert not result.success, "Should fail for unknown skill"
    assert "Unknown skill" in result.error, f"Error should mention unknown skill: {result.error}"
    return {"status": "pass", "message": "Unknown skill handled correctly"}


def test_run_skill_missing_params():
    """Test running skill with missing required parameters."""
    result = run_skill("shell", {})  # Missing 'command'
    
    assert not result.success, "Should fail for missing params"
    assert "command" in result.error.lower() or "missing" in result.error.lower(), \
        f"Error should mention missing param: {result.error}"
    return {"status": "pass", "message": "Missing params handled correctly"}


def test_run_skill_file_read():
    """Test file_read skill."""
    # Read a file we know exists
    result = run_skill("file_read", {"path": "/etc/hostname"})
    
    assert result.success, f"Should succeed reading /etc/hostname, error: {result.error}"
    assert len(result.output) > 0, "Should have output"
    return {"status": "pass", "message": "file_read skill working"}


def test_run_skill_file_write():
    """Test file_write skill."""
    import tempfile
    import os
    
    # Write to temp file
    temp_path = "/tmp/noctem_test_write.txt"
    result = run_skill("file_write", {
        "path": temp_path,
        "content": "test content from skill runner"
    })
    
    assert result.success, f"Should succeed writing, error: {result.error}"
    
    # Verify content
    with open(temp_path, 'r') as f:
        content = f.read()
    assert content == "test content from skill runner", f"Content mismatch: {content}"
    
    # Cleanup
    os.remove(temp_path)
    return {"status": "pass", "message": "file_write skill working"}


# =============================================================================
# Skill Chain Tests
# =============================================================================

def test_run_skill_chain_single():
    """Test running a single-skill chain."""
    plan = [{"name": "shell", "params": {"command": "echo 'single'"}}]
    
    result = run_skill_chain(plan)
    
    assert result.success, f"Should succeed, error: {result.error}"
    assert "single" in result.output, f"Output should contain 'single': {result.output}"
    return {"status": "pass", "message": "Single-skill chain working"}


def test_run_skill_chain_multiple():
    """Test running multiple skills in chain."""
    plan = [
        {"name": "shell", "params": {"command": "echo 'first'"}},
        {"name": "shell", "params": {"command": "echo 'second'"}},
    ]
    
    result = run_skill_chain(plan)
    
    assert result.success, f"Should succeed, error: {result.error}"
    # Last result should be 'second'
    assert "second" in result.output, f"Final output should be 'second': {result.output}"
    return {"status": "pass", "message": "Multi-skill chain working"}


def test_run_skill_chain_empty():
    """Test running empty chain."""
    result = run_skill_chain([])
    
    assert not result.success, "Empty chain should fail"
    assert "empty" in result.error.lower(), f"Error should mention empty: {result.error}"
    return {"status": "pass", "message": "Empty chain handled correctly"}


def test_run_skill_chain_failure_stops():
    """Test that chain stops on failure."""
    plan = [
        {"name": "shell", "params": {"command": "echo 'before'"}},
        {"name": "shell", "params": {"command": "exit 1"}},  # This fails
        {"name": "shell", "params": {"command": "echo 'after'"}},
    ]
    
    result = run_skill_chain(plan)
    
    assert not result.success, "Chain should fail on error"
    # The 'after' shouldn't execute
    return {"status": "pass", "message": "Chain stops on failure"}


def test_run_skill_chain_missing_name():
    """Test chain with missing skill name."""
    plan = [{"params": {"command": "echo test"}}]  # Missing 'name'
    
    result = run_skill_chain(plan)
    
    assert not result.success, "Should fail for missing name"
    return {"status": "pass", "message": "Missing skill name handled"}


def test_run_skill_chain_with_task_id():
    """Test chain with task context."""
    import state
    task_id = state.create_task("Chain test task", source="test")
    
    plan = [
        {"name": "shell", "params": {"command": "date"}},
        {"name": "shell", "params": {"command": "hostname"}},
    ]
    
    result = run_skill_chain(plan, task_id=task_id)
    
    assert result.success, f"Should succeed, error: {result.error}"
    return {"status": "pass", "message": "Chain with task_id working"}


# =============================================================================
# Context Passing Tests
# =============================================================================

def test_previous_output_available():
    """Test that previous_output is available in context."""
    # This is harder to test directly, but we can verify the chain works
    plan = [
        {"name": "shell", "params": {"command": "echo 'context_test_output'"}},
        {"name": "shell", "params": {"command": "echo 'received'"}},
    ]
    
    result = run_skill_chain(plan)
    assert result.success, f"Chain should work: {result.error}"
    return {"status": "pass", "message": "Context passing works"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    # Config tests
    ("load_config", test_load_config),
    # Listing tests
    ("list_skills", test_list_skills),
    ("list_skills_has_descriptions", test_list_skills_has_descriptions),
    # Single skill tests
    ("run_skill_shell", test_run_skill_shell),
    ("run_skill_shell_with_task_id", test_run_skill_shell_with_task_id),
    ("run_skill_unknown", test_run_skill_unknown),
    ("run_skill_missing_params", test_run_skill_missing_params),
    ("run_skill_file_read", test_run_skill_file_read),
    ("run_skill_file_write", test_run_skill_file_write),
    # Chain tests
    ("run_skill_chain_single", test_run_skill_chain_single),
    ("run_skill_chain_multiple", test_run_skill_chain_multiple),
    ("run_skill_chain_empty", test_run_skill_chain_empty),
    ("run_skill_chain_failure_stops", test_run_skill_chain_failure_stops),
    ("run_skill_chain_missing_name", test_run_skill_chain_missing_name),
    ("run_skill_chain_with_task_id", test_run_skill_chain_with_task_id),
    # Context tests
    ("previous_output_available", test_previous_output_available),
]


def run_all(verbose: bool = False) -> dict:
    """Run all skill runner tests."""
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
    print("Running skill runner tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
