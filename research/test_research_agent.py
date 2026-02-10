#!/usr/bin/env python3
"""
Test Suite for Noctem Research Agent
Validates setup and core functionality before running the full agent.
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Configuration
RESEARCH_DIR = Path(__file__).parent
FINDINGS_DIR = RESEARCH_DIR / "findings"
QUESTIONS_FILE = RESEARCH_DIR / "questions.json"
TEST_STATE_FILE = RESEARCH_DIR / "test_state.json"

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []


def test_header(name):
    """Print test section header."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")


def test_pass(message):
    """Record a passing test."""
    global tests_passed
    tests_passed += 1
    print(f"  ✅ PASS: {message}")


def test_fail(message, error=None):
    """Record a failing test."""
    global tests_failed
    tests_failed += 1
    failures.append((message, error))
    print(f"  ❌ FAIL: {message}")
    if error:
        print(f"     Error: {error}")


def test_python_version():
    """Test 1: Verify Python version is 3.8+"""
    test_header("Python Version")
    
    try:
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        print(f"  Detected: Python {version_str}")
        
        if version.major >= 3 and version.minor >= 8:
            test_pass(f"Python {version_str} is supported")
        else:
            test_fail(f"Python {version_str} is too old (need 3.8+)")
    except Exception as e:
        test_fail("Could not check Python version", str(e))


def test_imports():
    """Test 2: Verify all required imports work"""
    test_header("Required Imports")
    
    required_modules = [
        "json",
        "subprocess", 
        "time",
        "pathlib",
        "datetime",
        "typing",
        "signal",
        "traceback"
    ]
    
    for module_name in required_modules:
        try:
            __import__(module_name)
            test_pass(f"Import {module_name}")
        except ImportError as e:
            test_fail(f"Import {module_name}", str(e))


def test_directory_structure():
    """Test 3: Verify directory structure exists"""
    test_header("Directory Structure")
    
    # Check research directory
    if RESEARCH_DIR.exists() and RESEARCH_DIR.is_dir():
        test_pass(f"Research directory: {RESEARCH_DIR}")
    else:
        test_fail(f"Research directory not found: {RESEARCH_DIR}")
    
    # Check findings directory
    if FINDINGS_DIR.exists() and FINDINGS_DIR.is_dir():
        test_pass(f"Findings directory: {FINDINGS_DIR}")
    else:
        try:
            FINDINGS_DIR.mkdir(parents=True, exist_ok=True)
            test_pass(f"Created findings directory: {FINDINGS_DIR}")
        except Exception as e:
            test_fail(f"Could not create findings directory", str(e))


def test_questions_file():
    """Test 4: Verify questions.json is valid"""
    test_header("Questions File")
    
    if not QUESTIONS_FILE.exists():
        test_fail(f"questions.json not found: {QUESTIONS_FILE}")
        return
    
    test_pass(f"questions.json exists")
    
    try:
        content = QUESTIONS_FILE.read_text()
        questions = json.loads(content)
        
        if not isinstance(questions, list):
            test_fail("questions.json must contain a JSON array")
            return
        
        test_pass(f"Valid JSON array with {len(questions)} questions")
        
        # Validate question structure
        required_fields = ["id", "question", "category", "priority", "status"]
        for i, q in enumerate(questions):
            missing = [f for f in required_fields if f not in q]
            if missing:
                test_fail(f"Question {i+1} missing fields: {missing}")
            else:
                test_pass(f"Question {i+1} ({q['id']}): Valid structure")
        
        # Check for pending questions
        pending = [q for q in questions if q.get("status") == "pending"]
        if pending:
            test_pass(f"{len(pending)} pending questions ready to research")
        else:
            test_fail("No pending questions found")
            
    except json.JSONDecodeError as e:
        test_fail("questions.json is not valid JSON", str(e))
    except Exception as e:
        test_fail("Error reading questions.json", str(e))


def test_state_management():
    """Test 5: Test state save/load functionality"""
    test_header("State Management")
    
    # Test state creation
    try:
        test_state = {
            "questions_answered": 5,
            "current_question": "q001",
            "start_time": datetime.now().isoformat(),
            "test": True
        }
        
        TEST_STATE_FILE.write_text(json.dumps(test_state, indent=2))
        test_pass("State file created")
    except Exception as e:
        test_fail("Could not create state file", str(e))
        return
    
    # Test state loading
    try:
        loaded_state = json.loads(TEST_STATE_FILE.read_text())
        
        if loaded_state.get("test") == True:
            test_pass("State file loaded correctly")
        else:
            test_fail("State file data corrupted")
            
    except Exception as e:
        test_fail("Could not load state file", str(e))
    
    # Cleanup
    try:
        TEST_STATE_FILE.unlink()
        test_pass("Test state file cleaned up")
    except Exception as e:
        test_fail("Could not clean up test state file", str(e))


def test_file_writing():
    """Test 6: Test findings file creation"""
    test_header("File Writing")
    
    # Create test category directory
    test_category_dir = FINDINGS_DIR / "test_category"
    
    try:
        test_category_dir.mkdir(parents=True, exist_ok=True)
        test_pass(f"Created test category directory")
    except Exception as e:
        test_fail("Could not create category directory", str(e))
        return
    
    # Create test finding file
    test_finding_file = test_category_dir / "test_finding.md"
    test_content = """# Test Finding

This is a test finding to verify file writing works.

**Date**: {date}

## Test Content

If you can read this, file writing is working correctly!
""".format(date=datetime.now().isoformat())
    
    try:
        test_finding_file.write_text(test_content, encoding='utf-8')
        test_pass("Test finding file created")
    except Exception as e:
        test_fail("Could not write test finding file", str(e))
        return
    
    # Verify file can be read
    try:
        read_content = test_finding_file.read_text(encoding='utf-8')
        if "Test Finding" in read_content:
            test_pass("Test finding file readable")
        else:
            test_fail("Test finding file content corrupted")
    except Exception as e:
        test_fail("Could not read test finding file", str(e))
    
    # Cleanup
    try:
        test_finding_file.unlink()
        test_category_dir.rmdir()
        test_pass("Test files cleaned up")
    except Exception as e:
        test_fail("Could not clean up test files", str(e))


def test_warp_cli():
    """Test 7: Check if Warp CLI is available"""
    test_header("Warp CLI Availability")
    
    try:
        result = subprocess.run(
            ["warp", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            test_pass(f"Warp CLI available")
            
            # Try a test agent command (optional)
            print("  Testing Warp agent capability...")
            chat_result = subprocess.run(
                ["warp", "agent", "run", "--prompt", "Reply with just: OK"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if chat_result.returncode == 0:
                test_pass("Warp agent command works")
            else:
                test_fail("Warp agent command failed", chat_result.stderr)
        else:
            test_fail("Warp CLI returned error", result.stderr)
            
    except FileNotFoundError:
        test_fail("Warp CLI not found in PATH")
        print("  ⚠️  Install from: https://www.warp.dev/")
        print("  ⚠️  Then run: warp login")
    except subprocess.TimeoutExpired:
        test_fail("Warp CLI timed out")
    except Exception as e:
        test_fail("Warp CLI check failed", str(e))


def test_research_agent_import():
    """Test 8: Verify research_agent.py can be imported"""
    test_header("Research Agent Module")
    
    agent_file = RESEARCH_DIR / "research_agent.py"
    
    if not agent_file.exists():
        test_fail("research_agent.py not found")
        return
    
    test_pass("research_agent.py exists")
    
    # Check for key classes
    try:
        content = agent_file.read_text(encoding='utf-8')
        
        required_classes = [
            "ResearchState",
            "QuestionManager", 
            "WarpResearcher",
            "FindingsWriter",
            "ResearchAgent"
        ]
        
        for class_name in required_classes:
            if f"class {class_name}" in content:
                test_pass(f"Found class: {class_name}")
            else:
                test_fail(f"Missing class: {class_name}")
                
    except Exception as e:
        test_fail("Could not validate research_agent.py", str(e))


def test_json_parsing():
    """Test 9: Test JSON parsing with mock Warp output"""
    test_header("JSON Parsing")
    
    # Test extracting JSON from mixed content
    test_cases = [
        # Case 1: Clean JSON array
        (
            '[{"question": "Test?", "category": "Test", "priority": 1}]',
            True,
            "Clean JSON array"
        ),
        # Case 2: JSON with surrounding text
        (
            'Here are the questions:\n[{"question": "Test?", "category": "Test", "priority": 1}]\nEnd of response.',
            True,
            "JSON with surrounding text"
        ),
        # Case 3: Invalid JSON
        (
            '{"invalid": json without closing',
            False,
            "Invalid JSON (should fail gracefully)"
        )
    ]
    
    for content, should_succeed, description in test_cases:
        try:
            start = content.find('[')
            end = content.rfind(']') + 1
            
            if start >= 0 and end > start:
                json_str = content[start:end]
                questions = json.loads(json_str)
                
                if should_succeed:
                    test_pass(description)
                else:
                    test_fail(f"{description} (expected to fail)")
            else:
                if not should_succeed:
                    test_pass(description)
                else:
                    test_fail(f"{description} (no JSON found)")
                    
        except json.JSONDecodeError:
            if not should_succeed:
                test_pass(description)
            else:
                test_fail(f"{description} (JSON parsing error)")
        except Exception as e:
            test_fail(description, str(e))


def test_signal_handling():
    """Test 10: Verify signal handling works"""
    test_header("Signal Handling")
    
    import signal as signal_module
    
    # Check that signal module works
    try:
        # Test setting a dummy handler
        original_handler = signal_module.signal(signal_module.SIGINT, signal_module.SIG_DFL)
        signal_module.signal(signal_module.SIGINT, original_handler)
        test_pass("Signal handling module works")
    except Exception as e:
        test_fail("Signal handling failed", str(e))


def print_summary():
    """Print test summary"""
    print(f"\n\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}\n")
    
    total = tests_passed + tests_failed
    
    print(f"  Total Tests: {total}")
    print(f"  ✅ Passed: {tests_passed}")
    print(f"  ❌ Failed: {tests_failed}")
    
    if tests_failed > 0:
        print(f"\n  Failed Tests:")
        for msg, error in failures:
            print(f"    • {msg}")
            if error:
                print(f"      {error}")
    
    print(f"\n{'='*60}\n")
    
    if tests_failed == 0:
        print("  🎉 ALL TESTS PASSED!")
        print("  ✅ Research agent is ready to run")
        print(f"\n  Start with: python research_agent.py\n")
        return 0
    else:
        print("  ⚠️  SOME TESTS FAILED")
        print("  ❌ Fix issues before running research agent")
        print(f"\n  See errors above for details\n")
        return 1


def main():
    """Run all tests"""
    print("\n🔬 Noctem Research Agent - Test Suite")
    print("=" * 60)
    print("Validating setup and functionality...\n")
    
    # Run all tests
    test_python_version()
    test_imports()
    test_directory_structure()
    test_questions_file()
    test_state_management()
    test_file_writing()
    test_warp_cli()
    test_research_agent_import()
    test_json_parsing()
    test_signal_handling()
    
    # Print summary and return exit code
    return print_summary()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
