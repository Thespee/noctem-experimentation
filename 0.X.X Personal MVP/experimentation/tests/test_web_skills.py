#!/usr/bin/env python3
"""Tests for web_fetch and web_search skills."""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills import web_fetch, web_search
from skill_runner import run_skill


def test_web_fetch_basic():
    """Test basic URL fetch."""
    result = web_fetch.run("https://example.com")
    assert "content" in result, f"Expected content, got: {result}"
    assert "error" not in result, f"Got error: {result.get('error')}"
    assert "Example Domain" in result.get("title", ""), "Expected 'Example Domain' in title"
    print("✓ web_fetch basic test passed")


def test_web_fetch_invalid_url():
    """Test invalid URL handling."""
    result = web_fetch.run("not-a-url")
    assert "error" in result, "Expected error for invalid URL"
    print("✓ web_fetch invalid URL test passed")


def test_web_fetch_via_skill_runner():
    """Test web_fetch through skill runner."""
    result = run_skill("web_fetch", {"url": "https://example.com"})
    assert result.success, f"Expected success, got error: {result.error}"
    assert "Example Domain" in result.output, "Expected 'Example Domain' in output"
    print("✓ web_fetch via skill_runner test passed")


def test_web_fetch_cache():
    """Test caching behavior."""
    from utils.cache import cache_clear
    cache_clear("fetch")  # Clear fetch cache
    
    # First fetch
    result1 = web_fetch.run("https://example.com", use_cache=True)
    assert not result1.get("cached"), "First fetch should not be cached"
    
    # Second fetch should be cached
    result2 = web_fetch.run("https://example.com", use_cache=True)
    assert result2.get("cached"), "Second fetch should be cached"
    print("✓ web_fetch cache test passed")


def test_web_search_basic():
    """Test basic search."""
    result = web_search.run("python programming tutorial")
    
    # May fail due to rate limiting, so be lenient
    if "error" in result:
        print(f"⚠ web_search got error (may be rate limited): {result['error']}")
        return
    
    assert "results" in result, f"Expected results, got: {result}"
    if result["results"]:
        print(f"✓ web_search basic test passed ({len(result['results'])} results)")
    else:
        print("⚠ web_search returned no results (may be rate limited)")


def test_web_search_empty_query():
    """Test empty query handling."""
    result = web_search.run("")
    assert "error" in result, "Expected error for empty query"
    print("✓ web_search empty query test passed")


def test_web_search_via_skill_runner():
    """Test web_search through skill runner."""
    result = run_skill("web_search", {"query": "linux kernel"})
    
    # May fail due to rate limiting
    if not result.success and "rate" in result.error.lower():
        print("⚠ web_search via skill_runner: rate limited")
        return
    
    assert result.success, f"Expected success, got error: {result.error}"
    print("✓ web_search via skill_runner test passed")


def test_robots_txt():
    """Test robots.txt checking."""
    from utils.robots import is_allowed, fetch_robots_txt
    
    # Example.com should allow everything
    allowed, delay = is_allowed("https://example.com/test")
    assert allowed, "example.com should allow all paths"
    print("✓ robots.txt test passed")


def test_rate_limiter():
    """Test rate limiting."""
    from utils.rate_limit import wait_for_rate_limit, reset_rate_limits
    import time
    
    reset_rate_limits()
    
    # First request should not wait
    start = time.time()
    waited = wait_for_rate_limit("test-domain.com", min_delay=0.5)
    assert waited == 0, "First request should not wait"
    
    # Second request should wait
    waited = wait_for_rate_limit("test-domain.com", min_delay=0.5)
    assert waited > 0, "Second request should wait"
    
    print("✓ rate limiter test passed")


if __name__ == "__main__":
    print("Running web skills tests...\n")
    
    test_web_fetch_basic()
    test_web_fetch_invalid_url()
    test_web_fetch_via_skill_runner()
    test_web_fetch_cache()
    test_robots_txt()
    test_rate_limiter()
    
    print("\n--- Search tests (may be rate limited) ---\n")
    
    test_web_search_empty_query()
    test_web_search_basic()
    test_web_search_via_skill_runner()
    
    print("\n✓ All tests completed!")
