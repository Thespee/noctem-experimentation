#!/usr/bin/env python3
"""
Tests for skill base classes and registry.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.base import (
    Skill, SkillResult, SkillContext, 
    register_skill, get_skill, get_all_skills, get_skill_manifest
)


# =============================================================================
# SkillResult Tests
# =============================================================================

def test_skill_result_success():
    """Test successful SkillResult creation."""
    result = SkillResult(success=True, output="test output", data={"key": "value"})
    
    assert result.success is True, "Should be successful"
    assert result.output == "test output", "Output should match"
    assert result.data == {"key": "value"}, "Data should match"
    assert result.error is None, "Error should be None for success"
    return {"status": "pass", "message": "SkillResult success creation working"}


def test_skill_result_failure():
    """Test failed SkillResult creation."""
    result = SkillResult(success=False, output="", error="Something went wrong")
    
    assert result.success is False, "Should be failed"
    assert result.error == "Something went wrong", "Error should match"
    return {"status": "pass", "message": "SkillResult failure creation working"}


def test_skill_result_to_dict():
    """Test SkillResult serialization."""
    result = SkillResult(success=True, output="test", data={"a": 1}, error=None)
    d = result.to_dict()
    
    assert "success" in d, "Should have success key"
    assert "output" in d, "Should have output key"
    assert "data" in d, "Should have data key"
    assert d["success"] is True, "success should be True"
    return {"status": "pass", "message": "SkillResult to_dict working"}


# =============================================================================
# SkillContext Tests
# =============================================================================

def test_skill_context_defaults():
    """Test SkillContext default values."""
    ctx = SkillContext()
    
    assert ctx.task_id is None, "task_id should be None by default"
    assert ctx.task_input is None, "task_input should be None"
    assert ctx.previous_output is None, "previous_output should be None"
    assert ctx.memory == [], "memory should be empty list"
    assert ctx.config == {}, "config should be empty dict"
    return {"status": "pass", "message": "SkillContext defaults working"}


def test_skill_context_with_values():
    """Test SkillContext with custom values."""
    ctx = SkillContext(
        task_id=42,
        task_input="test input",
        config={"key": "value"}
    )
    
    assert ctx.task_id == 42, "task_id should be 42"
    assert ctx.task_input == "test input", "task_input should match"
    assert ctx.config["key"] == "value", "config should have key"
    return {"status": "pass", "message": "SkillContext with values working"}


# =============================================================================
# Skill Registry Tests
# =============================================================================

def test_skill_registry_has_skills():
    """Test that skill registry is populated."""
    skills = get_all_skills()
    
    assert len(skills) > 0, f"Should have registered skills, got {len(skills)}"
    return {"status": "pass", "message": f"Registry has {len(skills)} skills"}


def test_get_skill_by_name():
    """Test retrieving skill by name."""
    # Shell skill should always exist
    skill = get_skill("shell")
    
    assert skill is not None, "shell skill should exist"
    assert skill.name == "shell", "Skill name should be shell"
    assert hasattr(skill, 'run'), "Skill should have run method"
    return {"status": "pass", "message": "get_skill() working"}


def test_get_skill_unknown():
    """Test retrieving non-existent skill."""
    skill = get_skill("nonexistent_skill_xyz")
    
    assert skill is None, "Should return None for unknown skill"
    return {"status": "pass", "message": "Unknown skill returns None"}


def test_skill_manifest():
    """Test skill manifest generation."""
    manifest = get_skill_manifest()
    
    assert isinstance(manifest, dict), "Manifest should be dict"
    assert len(manifest) > 0, "Manifest should not be empty"
    
    # Check a skill has required keys
    for name, info in manifest.items():
        assert "name" in info, f"{name} should have name"
        assert "description" in info, f"{name} should have description"
        assert "parameters" in info, f"{name} should have parameters"
        break  # Just check first one
    
    return {"status": "pass", "message": "Skill manifest generation working"}


def test_skill_has_validate_params():
    """Test that skills have validate_params method."""
    skill = get_skill("shell")
    
    assert hasattr(skill, 'validate_params'), "Skill should have validate_params"
    
    # Test validation with missing param
    error = skill.validate_params({})
    assert error is not None, "Should return error for missing command"
    
    # Test validation with required param
    error = skill.validate_params({"command": "echo test"})
    assert error is None, f"Should pass validation, got: {error}"
    
    return {"status": "pass", "message": "validate_params working"}


def test_skill_get_manifest():
    """Test individual skill manifest."""
    skill = get_skill("shell")
    manifest = skill.get_manifest()
    
    assert manifest["name"] == "shell", "Name should be shell"
    assert "command" in manifest["parameters"], "Should have command parameter"
    return {"status": "pass", "message": "Individual skill manifest working"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    ("skill_result_success", test_skill_result_success),
    ("skill_result_failure", test_skill_result_failure),
    ("skill_result_to_dict", test_skill_result_to_dict),
    ("skill_context_defaults", test_skill_context_defaults),
    ("skill_context_with_values", test_skill_context_with_values),
    ("skill_registry_has_skills", test_skill_registry_has_skills),
    ("get_skill_by_name", test_get_skill_by_name),
    ("get_skill_unknown", test_get_skill_unknown),
    ("skill_manifest", test_skill_manifest),
    ("skill_has_validate_params", test_skill_has_validate_params),
    ("skill_get_manifest", test_skill_get_manifest),
]


def run_all(verbose: bool = False) -> dict:
    """Run all base skill tests."""
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
    print("Running base skill tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
