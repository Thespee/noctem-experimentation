#!/usr/bin/env python3
"""
Master test runner for Noctem local tests.
Runs all test modules and produces a summary report.

Usage:
    python tests/local/run_all.py [-v|--verbose] [--module MODULE]

These tests can later be used as troubleshooting sub-skills.
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import all test modules
from tests.local import test_utils
from tests.local import test_base_skill
from tests.local import test_state
from tests.local import test_skill_runner
from tests.local import test_shell_skill
from tests.local import test_file_ops_skill
from tests.local import test_task_status_skill
from tests.local import test_signal_send_skill
from tests.local import test_web_skills


# Test module registry
TEST_MODULES = [
    ("utils", test_utils, "Cache, robots.txt, rate limiting"),
    ("base_skill", test_base_skill, "Skill framework and registry"),
    ("state", test_state, "SQLite state management"),
    ("skill_runner", test_skill_runner, "Skill execution and chaining"),
    ("shell_skill", test_shell_skill, "Shell command execution and safety"),
    ("file_ops_skill", test_file_ops_skill, "File read/write operations"),
    ("task_status_skill", test_task_status_skill, "Task queue status"),
    ("signal_send_skill", test_signal_send_skill, "Signal messaging (mock)"),
    ("web_skills", test_web_skills, "Web fetch and search (network)"),
]


def run_module(module, verbose: bool = False) -> dict:
    """Run a single test module."""
    return module.run_all(verbose=verbose)


def run_all_tests(verbose: bool = False, module_filter: str = None) -> dict:
    """Run all test modules and return aggregated results."""
    total_passed = 0
    total_failed = 0
    module_results = {}
    all_errors = []
    
    start_time = time.time()
    
    for name, module, description in TEST_MODULES:
        if module_filter and module_filter.lower() not in name.lower():
            continue
        
        print(f"\n{'='*60}")
        print(f"📋 {name}: {description}")
        print(f"{'='*60}")
        
        module_start = time.time()
        results = run_module(module, verbose=verbose)
        module_duration = time.time() - module_start
        
        module_results[name] = {
            "passed": results["passed"],
            "failed": results["failed"],
            "duration_ms": int(module_duration * 1000),
            "errors": results.get("errors", [])
        }
        
        total_passed += results["passed"]
        total_failed += results["failed"]
        
        for error in results.get("errors", []):
            error["module"] = name
            all_errors.append(error)
        
        status = "✅" if results["failed"] == 0 else "❌"
        print(f"\n{status} {name}: {results['passed']} passed, {results['failed']} failed ({module_duration:.2f}s)")
    
    total_duration = time.time() - start_time
    
    return {
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_duration_seconds": total_duration,
        "modules": module_results,
        "errors": all_errors
    }


def print_summary(results: dict):
    """Print a summary of test results."""
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    print(f"\nTotal: {results['total_passed']} passed, {results['total_failed']} failed")
    print(f"Duration: {results['total_duration_seconds']:.2f}s")
    
    # Module breakdown
    print("\nModule Results:")
    for name, data in results["modules"].items():
        status = "✅" if data["failed"] == 0 else "❌"
        print(f"  {status} {name}: {data['passed']}/{data['passed'] + data['failed']} ({data['duration_ms']}ms)")
    
    # Error details
    if results["errors"]:
        print(f"\n❌ {len(results['errors'])} Error(s):")
        for error in results["errors"]:
            print(f"  • [{error.get('module', '?')}] {error.get('test', '?')}: {error.get('error', 'Unknown')}")
    
    # Final status
    print("\n" + "="*60)
    if results["total_failed"] == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {results['total_failed']} TEST(S) FAILED")
    print("="*60)


def get_test_manifest() -> dict:
    """Get manifest of all available tests for troubleshooting integration."""
    manifest = {}
    
    for name, module, description in TEST_MODULES:
        tests = []
        if hasattr(module, 'ALL_TESTS'):
            for test_name, test_fn in module.ALL_TESTS:
                tests.append({
                    "name": test_name,
                    "doc": test_fn.__doc__ or ""
                })
        
        manifest[name] = {
            "description": description,
            "tests": tests,
            "test_count": len(tests)
        }
    
    return manifest


def run_single_test(module_name: str, test_name: str) -> dict:
    """Run a single test by module and test name."""
    for name, module, _ in TEST_MODULES:
        if name == module_name:
            if hasattr(module, 'ALL_TESTS'):
                for tname, test_fn in module.ALL_TESTS:
                    if tname == test_name:
                        try:
                            result = test_fn()
                            return {
                                "status": "pass",
                                "module": module_name,
                                "test": test_name,
                                "message": result.get("message", "OK")
                            }
                        except AssertionError as e:
                            return {
                                "status": "fail",
                                "module": module_name,
                                "test": test_name,
                                "error": str(e)
                            }
                        except Exception as e:
                            return {
                                "status": "error",
                                "module": module_name,
                                "test": test_name,
                                "error": str(e),
                                "type": type(e).__name__
                            }
    
    return {"status": "error", "error": f"Test not found: {module_name}.{test_name}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Noctem local tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--module", type=str, help="Run only tests matching this module name")
    parser.add_argument("--list", action="store_true", help="List available tests")
    parser.add_argument("--test", type=str, help="Run single test (format: module.test_name)")
    args = parser.parse_args()
    
    print(f"🌙 Noctem Local Test Suite")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.list:
        manifest = get_test_manifest()
        print("\nAvailable Test Modules:")
        for name, data in manifest.items():
            print(f"\n  {name} ({data['test_count']} tests)")
            print(f"    {data['description']}")
            for test in data["tests"][:5]:
                print(f"      • {test['name']}")
            if len(data["tests"]) > 5:
                print(f"      ... and {len(data['tests']) - 5} more")
        sys.exit(0)
    
    if args.test:
        if "." not in args.test:
            print("Error: --test format should be 'module.test_name'")
            sys.exit(1)
        module_name, test_name = args.test.split(".", 1)
        result = run_single_test(module_name, test_name)
        if result["status"] == "pass":
            print(f"✅ {args.test}: {result.get('message', 'OK')}")
            sys.exit(0)
        else:
            print(f"❌ {args.test}: {result.get('error', 'Failed')}")
            sys.exit(1)
    
    results = run_all_tests(verbose=args.verbose, module_filter=args.module)
    print_summary(results)
    
    sys.exit(0 if results["total_failed"] == 0 else 1)
