#!/usr/bin/env python3
"""
Tests for file_read and file_write skills.
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.file_ops import FileReadSkill, FileWriteSkill, is_path_safe, PROTECTED_PATHS
from skills.base import SkillContext


# =============================================================================
# Path Safety Tests
# =============================================================================

def test_protected_paths_defined():
    """Test that protected paths are defined."""
    assert len(PROTECTED_PATHS) > 0, "Should have protected paths"
    assert "/etc" in PROTECTED_PATHS, "/etc should be protected"
    assert "/bin" in PROTECTED_PATHS, "/bin should be protected"
    return {"status": "pass", "message": f"{len(PROTECTED_PATHS)} protected paths defined"}


def test_is_path_safe_read():
    """Test path safety for reading."""
    safe, error = is_path_safe("/tmp/test.txt", for_write=False)
    assert safe, f"Reading /tmp should be safe: {error}"
    
    safe, error = is_path_safe("/etc/hostname", for_write=False)
    assert safe, f"Reading /etc/hostname should be safe: {error}"
    
    return {"status": "pass", "message": "Read path safety working"}


def test_is_path_safe_write_tmp():
    """Test path safety for writing to /tmp."""
    safe, error = is_path_safe("/tmp/test.txt", for_write=True)
    assert safe, f"Writing to /tmp should be safe: {error}"
    return {"status": "pass", "message": "Write to /tmp allowed"}


def test_is_path_safe_write_protected():
    """Test that writing to protected paths is blocked."""
    for protected in ["/etc/test", "/bin/test", "/usr/local/test"]:
        safe, error = is_path_safe(protected, for_write=True)
        assert not safe, f"Writing to {protected} should be blocked"
    return {"status": "pass", "message": "Protected paths blocked for writing"}


# =============================================================================
# File Read Tests
# =============================================================================

def test_file_read_existing():
    """Test reading an existing file."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    result = skill.execute({"path": "/etc/hostname"}, ctx)
    
    assert result.success, f"Should read /etc/hostname: {result.error}"
    assert len(result.output) > 0, "Should have content"
    return {"status": "pass", "message": "Read existing file working"}


def test_file_read_nonexistent():
    """Test reading a non-existent file."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    result = skill.execute({"path": "/nonexistent_file_xyz_123.txt"}, ctx)
    
    assert not result.success, "Should fail for non-existent file"
    assert "not found" in result.error.lower(), f"Error should mention not found: {result.error}"
    return {"status": "pass", "message": "Non-existent file handled"}


def test_file_read_no_path():
    """Test reading with no path."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert not result.success, "Should fail without path"
    return {"status": "pass", "message": "Missing path handled"}


def test_file_read_directory():
    """Test reading a directory (should fail)."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    result = skill.execute({"path": "/tmp"}, ctx)
    
    assert not result.success, "Should fail for directory"
    assert "not a file" in result.error.lower(), f"Error should mention not a file: {result.error}"
    return {"status": "pass", "message": "Directory read rejected"}


def test_file_read_user_expansion():
    """Test ~ expansion in paths."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    # This may or may not exist, but it should attempt to expand ~
    result = skill.execute({"path": "~/.bashrc"}, ctx)
    
    # We don't care if it succeeds (file may not exist), just that ~ was expanded
    if result.success:
        assert "/" in result.data.get("path", ""), "Path should be absolute"
    return {"status": "pass", "message": "User path expansion working"}


def test_file_read_with_max_lines():
    """Test max_lines parameter."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    # Create a file with many lines
    temp_path = "/tmp/noctem_test_lines.txt"
    with open(temp_path, "w") as f:
        for i in range(100):
            f.write(f"Line {i}\n")
    
    result = skill.execute({"path": temp_path, "max_lines": 10}, ctx)
    
    assert result.success, f"Should read file: {result.error}"
    assert "truncated" in result.output.lower(), "Should indicate truncation"
    
    os.remove(temp_path)
    return {"status": "pass", "message": "max_lines parameter working"}


def test_file_read_data_fields():
    """Test that data fields are populated."""
    skill = FileReadSkill()
    ctx = SkillContext()
    
    result = skill.execute({"path": "/etc/hostname"}, ctx)
    
    assert result.success
    assert "path" in result.data, "Should have path in data"
    assert "size" in result.data, "Should have size in data"
    assert "lines" in result.data, "Should have lines in data"
    return {"status": "pass", "message": "Data fields populated correctly"}


# =============================================================================
# File Write Tests
# =============================================================================

def test_file_write_new():
    """Test writing to a new file."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    temp_path = "/tmp/noctem_test_write_new.txt"
    content = "Hello from test!"
    
    # Ensure file doesn't exist
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    result = skill.execute({"path": temp_path, "content": content}, ctx)
    
    assert result.success, f"Should write file: {result.error}"
    assert os.path.exists(temp_path), "File should exist"
    
    with open(temp_path, "r") as f:
        actual = f.read()
    assert actual == content, f"Content mismatch: {actual}"
    
    os.remove(temp_path)
    return {"status": "pass", "message": "Write new file working"}


def test_file_write_overwrite():
    """Test overwriting an existing file."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    temp_path = "/tmp/noctem_test_overwrite.txt"
    
    # Create initial file
    with open(temp_path, "w") as f:
        f.write("Original content")
    
    # Overwrite
    result = skill.execute({"path": temp_path, "content": "New content"}, ctx)
    
    assert result.success
    with open(temp_path, "r") as f:
        actual = f.read()
    assert actual == "New content", f"Should be overwritten: {actual}"
    
    os.remove(temp_path)
    return {"status": "pass", "message": "Overwrite working"}


def test_file_write_append():
    """Test appending to file."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    temp_path = "/tmp/noctem_test_append.txt"
    
    # Create initial file
    with open(temp_path, "w") as f:
        f.write("Line 1\n")
    
    # Append
    result = skill.execute({"path": temp_path, "content": "Line 2\n", "append": True}, ctx)
    
    assert result.success
    with open(temp_path, "r") as f:
        actual = f.read()
    assert actual == "Line 1\nLine 2\n", f"Append failed: {actual}"
    
    os.remove(temp_path)
    return {"status": "pass", "message": "Append working"}


def test_file_write_creates_parents():
    """Test that parent directories are created."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    temp_path = "/tmp/noctem_test_parent/subdir/file.txt"
    
    # Cleanup first
    if os.path.exists(temp_path):
        os.remove(temp_path)
        os.rmdir(os.path.dirname(temp_path))
        os.rmdir("/tmp/noctem_test_parent")
    
    result = skill.execute({"path": temp_path, "content": "test"}, ctx)
    
    assert result.success, f"Should create parents: {result.error}"
    assert os.path.exists(temp_path), "File should exist"
    
    # Cleanup
    os.remove(temp_path)
    os.rmdir("/tmp/noctem_test_parent/subdir")
    os.rmdir("/tmp/noctem_test_parent")
    return {"status": "pass", "message": "Parent directory creation working"}


def test_file_write_protected_path():
    """Test that writing to protected paths is blocked."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    result = skill.execute({"path": "/etc/noctem_test.txt", "content": "test"}, ctx)
    
    assert not result.success, "Should not write to /etc"
    assert "protected" in result.error.lower() or "cannot write" in result.error.lower(), \
        f"Error should mention protection: {result.error}"
    return {"status": "pass", "message": "Protected path blocked"}


def test_file_write_no_path():
    """Test writing with no path."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    result = skill.execute({"content": "test"}, ctx)
    
    assert not result.success, "Should fail without path"
    return {"status": "pass", "message": "Missing path handled"}


def test_file_write_data_fields():
    """Test that write data fields are populated."""
    skill = FileWriteSkill()
    ctx = SkillContext()
    
    temp_path = "/tmp/noctem_test_data.txt"
    result = skill.execute({"path": temp_path, "content": "test content"}, ctx)
    
    assert result.success
    assert "path" in result.data, "Should have path"
    assert "size" in result.data, "Should have size"
    assert "mode" in result.data, "Should have mode"
    
    os.remove(temp_path)
    return {"status": "pass", "message": "Write data fields populated"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    # Path safety
    ("protected_paths_defined", test_protected_paths_defined),
    ("is_path_safe_read", test_is_path_safe_read),
    ("is_path_safe_write_tmp", test_is_path_safe_write_tmp),
    ("is_path_safe_write_protected", test_is_path_safe_write_protected),
    # File read
    ("file_read_existing", test_file_read_existing),
    ("file_read_nonexistent", test_file_read_nonexistent),
    ("file_read_no_path", test_file_read_no_path),
    ("file_read_directory", test_file_read_directory),
    ("file_read_user_expansion", test_file_read_user_expansion),
    ("file_read_with_max_lines", test_file_read_with_max_lines),
    ("file_read_data_fields", test_file_read_data_fields),
    # File write
    ("file_write_new", test_file_write_new),
    ("file_write_overwrite", test_file_write_overwrite),
    ("file_write_append", test_file_write_append),
    ("file_write_creates_parents", test_file_write_creates_parents),
    ("file_write_protected_path", test_file_write_protected_path),
    ("file_write_no_path", test_file_write_no_path),
    ("file_write_data_fields", test_file_write_data_fields),
]


def run_all(verbose: bool = False) -> dict:
    """Run all file ops tests."""
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
    print("Running file ops skill tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
