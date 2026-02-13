#!/usr/bin/env python3
"""
Tests for utility modules: cache, robots, rate_limit.
Each test function can be used as a troubleshooting sub-skill.
"""
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.cache import cache_get, cache_set, cache_clear, get_cache_key, CACHE_DIR
from utils.robots import parse_robots_txt, is_allowed
from utils.rate_limit import wait_for_rate_limit, reset_rate_limits, get_domain


# =============================================================================
# Cache Tests
# =============================================================================

def test_cache_key_generation():
    """Test cache key generation is deterministic."""
    key1 = get_cache_key("test", "data")
    key2 = get_cache_key("test", "data")
    key3 = get_cache_key("test", "different")
    
    assert key1 == key2, "Same input should produce same key"
    assert key1 != key3, "Different input should produce different key"
    assert key1.startswith("test_"), "Key should have prefix"
    return {"status": "pass", "message": "Cache key generation working"}


def test_cache_set_and_get():
    """Test basic cache set/get operations."""
    test_key = "test_cache_ops"
    test_value = {"foo": "bar", "num": 42}
    
    # Clear any existing
    cache_clear("test_cache_ops")
    
    # Set value
    cache_set(test_key, test_value)
    
    # Get value
    result = cache_get(test_key, max_age_seconds=60)
    
    assert result is not None, "Should retrieve cached value"
    assert result == test_value, f"Value mismatch: {result} != {test_value}"
    
    # Cleanup
    cache_clear("test_cache_ops")
    return {"status": "pass", "message": "Cache set/get working"}


def test_cache_expiry():
    """Test that cache respects TTL."""
    test_key = "test_cache_expiry"
    test_value = "will_expire"
    
    cache_clear("test_cache_expiry")
    cache_set(test_key, test_value)
    
    # Should exist with long TTL
    result = cache_get(test_key, max_age_seconds=60)
    assert result == test_value, "Should exist with long TTL"
    
    # Should NOT exist with 0 TTL (already expired)
    result = cache_get(test_key, max_age_seconds=0)
    assert result is None, "Should be expired with 0 TTL"
    
    cache_clear("test_cache_expiry")
    return {"status": "pass", "message": "Cache expiry working"}


def test_cache_clear():
    """Test cache clearing with prefix."""
    # Set multiple keys
    cache_set("prefix_a_1", "val1")
    cache_set("prefix_a_2", "val2")
    cache_set("prefix_b_1", "val3")
    
    # Clear only prefix_a
    cleared = cache_clear("prefix_a")
    assert cleared >= 2, f"Should clear at least 2 items, cleared {cleared}"
    
    # prefix_b should still exist
    result = cache_get("prefix_b_1", max_age_seconds=60)
    assert result == "val3", "prefix_b should not be cleared"
    
    cache_clear("prefix_b")
    return {"status": "pass", "message": "Cache clear with prefix working"}


def test_cache_directory_exists():
    """Test that cache directory is accessible."""
    assert CACHE_DIR.exists() or CACHE_DIR.parent.exists(), "Cache dir parent should exist"
    
    # Try creating it
    CACHE_DIR.mkdir(exist_ok=True)
    assert CACHE_DIR.exists(), "Should be able to create cache dir"
    assert CACHE_DIR.is_dir(), "Cache dir should be a directory"
    
    return {"status": "pass", "message": f"Cache directory: {CACHE_DIR}"}


# =============================================================================
# Robots.txt Tests
# =============================================================================

def test_robots_txt_parser_allow_all():
    """Test parsing robots.txt that allows all."""
    content = """
User-agent: *
Allow: /
"""
    rules = parse_robots_txt(content)
    
    assert "allow" in rules, "Should have allow key"
    assert "/" in rules["allow"], "Should allow root"
    return {"status": "pass", "message": "Robots.txt allow-all parsing working"}


def test_robots_txt_parser_disallow():
    """Test parsing robots.txt with disallow rules."""
    content = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /public/
Crawl-delay: 5
"""
    rules = parse_robots_txt(content)
    
    assert "/private/" in rules["disallow"], "Should disallow /private/"
    assert "/admin/" in rules["disallow"], "Should disallow /admin/"
    assert "/public/" in rules["allow"], "Should allow /public/"
    assert rules["crawl_delay"] == 5.0, f"Crawl delay should be 5, got {rules['crawl_delay']}"
    return {"status": "pass", "message": "Robots.txt disallow parsing working"}


def test_robots_txt_is_allowed():
    """Test is_allowed function with real URL."""
    # example.com has no robots.txt restrictions
    allowed, delay = is_allowed("https://example.com/test")
    assert allowed, "example.com should allow all paths"
    return {"status": "pass", "message": "is_allowed() working"}


# =============================================================================
# Rate Limiter Tests
# =============================================================================

def test_rate_limiter_first_request():
    """Test that first request doesn't wait."""
    reset_rate_limits()
    
    waited = wait_for_rate_limit("test-unique-domain-123.com", min_delay=1.0)
    assert waited == 0, f"First request should not wait, waited {waited}"
    return {"status": "pass", "message": "First request no-wait working"}


def test_rate_limiter_second_request():
    """Test that second request waits."""
    reset_rate_limits()
    
    domain = "test-rate-limit-domain.com"
    
    # First request
    wait_for_rate_limit(domain, min_delay=0.3)
    
    # Second request should wait
    start = time.time()
    waited = wait_for_rate_limit(domain, min_delay=0.3)
    elapsed = time.time() - start
    
    assert waited > 0, f"Second request should wait, waited {waited}"
    assert elapsed >= 0.2, f"Should have waited ~0.3s, elapsed {elapsed}"
    return {"status": "pass", "message": f"Rate limiting working (waited {waited:.2f}s)"}


def test_get_domain():
    """Test domain extraction from URL."""
    assert get_domain("https://example.com/path") == "example.com"
    assert get_domain("http://sub.example.com:8080/path") == "sub.example.com:8080"
    assert get_domain("https://test.org") == "test.org"
    return {"status": "pass", "message": "Domain extraction working"}


def test_rate_limiter_reset():
    """Test rate limit reset."""
    domain = "test-reset-domain.com"
    
    # Set up a rate limit
    wait_for_rate_limit(domain, min_delay=1.0)
    
    # Reset
    reset_rate_limits()
    
    # Should not wait now
    waited = wait_for_rate_limit(domain, min_delay=1.0)
    assert waited == 0, f"Should not wait after reset, waited {waited}"
    return {"status": "pass", "message": "Rate limit reset working"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    # Cache tests
    ("cache_key_generation", test_cache_key_generation),
    ("cache_set_and_get", test_cache_set_and_get),
    ("cache_expiry", test_cache_expiry),
    ("cache_clear", test_cache_clear),
    ("cache_directory_exists", test_cache_directory_exists),
    # Robots tests
    ("robots_parser_allow_all", test_robots_txt_parser_allow_all),
    ("robots_parser_disallow", test_robots_txt_parser_disallow),
    ("robots_is_allowed", test_robots_txt_is_allowed),
    # Rate limiter tests
    ("rate_limiter_first_request", test_rate_limiter_first_request),
    ("rate_limiter_second_request", test_rate_limiter_second_request),
    ("get_domain", test_get_domain),
    ("rate_limiter_reset", test_rate_limiter_reset),
]


def run_all(verbose: bool = False) -> dict:
    """Run all utils tests and return results."""
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
    import argparse
    parser = argparse.ArgumentParser(description="Run utils tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    print("Running utils tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
