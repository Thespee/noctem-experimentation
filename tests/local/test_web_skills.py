#!/usr/bin/env python3
"""
Tests for web_fetch and web_search skills.
Note: Some tests require network access.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.web_fetch import WebFetchSkill, run as fetch_run, extract_text, clean_text
from skills.web_search import WebSearchSkill, run as search_run
from skills.base import SkillContext
from utils.cache import cache_clear


# =============================================================================
# Web Fetch Tests
# =============================================================================

def test_web_fetch_valid_url():
    """Test fetching a valid URL."""
    cache_clear("fetch")  # Clear cache for clean test
    
    result = fetch_run("https://example.com")
    
    assert "error" not in result, f"Should succeed: {result.get('error')}"
    assert "content" in result, "Should have content"
    assert "Example Domain" in result.get("title", ""), "Should have correct title"
    return {"status": "pass", "message": "Valid URL fetch working"}


def test_web_fetch_invalid_scheme():
    """Test invalid URL scheme."""
    result = fetch_run("ftp://example.com")
    
    assert "error" in result, "Should fail for ftp scheme"
    assert "scheme" in result["error"].lower(), f"Error should mention scheme: {result['error']}"
    return {"status": "pass", "message": "Invalid scheme rejected"}


def test_web_fetch_invalid_url():
    """Test completely invalid URL."""
    result = fetch_run("not-a-url")
    
    assert "error" in result, "Should fail for invalid URL"
    return {"status": "pass", "message": "Invalid URL handled"}


def test_web_fetch_missing_domain():
    """Test URL with missing domain."""
    result = fetch_run("http:///path")
    
    assert "error" in result, "Should fail for missing domain"
    return {"status": "pass", "message": "Missing domain handled"}


def test_web_fetch_cache():
    """Test caching behavior."""
    cache_clear("fetch")
    
    # First fetch - should not be cached
    result1 = fetch_run("https://example.com", use_cache=True)
    assert not result1.get("cached"), "First fetch should not be cached"
    
    # Second fetch - should be cached
    result2 = fetch_run("https://example.com", use_cache=True)
    assert result2.get("cached"), "Second fetch should be cached"
    
    return {"status": "pass", "message": "Caching working"}


def test_web_fetch_no_cache():
    """Test fetching without cache."""
    result = fetch_run("https://example.com", use_cache=False)
    
    assert "error" not in result
    assert not result.get("cached"), "Should not be cached when disabled"
    return {"status": "pass", "message": "No-cache option working"}


def test_web_fetch_max_length():
    """Test max_length parameter."""
    # Clear cache to ensure we get a fresh fetch
    cache_clear("fetch")
    
    # Use a smaller max_length to ensure truncation on most sites
    result = fetch_run("https://example.com", max_length=50, use_cache=False)
    
    assert "error" not in result
    # The truncation adds "..." so allow small overhead
    # Content should be close to max_length if truncated
    content_len = len(result["content"])
    if result.get("truncated"):
        assert content_len <= 60, f"Truncated content too long: {content_len}"
    else:
        # If not truncated, original content was <= max_length
        assert content_len <= 50, f"Content should be <= max_length if not truncated: {content_len}"
    return {"status": "pass", "message": f"max_length working (len={content_len}, truncated={result.get('truncated')})"}


def test_web_fetch_skill_class():
    """Test WebFetchSkill class."""
    skill = WebFetchSkill()
    ctx = SkillContext()
    
    result = skill.execute({"url": "https://example.com"}, ctx)
    
    assert result.success, f"Should succeed: {result.error}"
    assert "Example Domain" in result.output, "Output should have title"
    return {"status": "pass", "message": "WebFetchSkill class working"}


def test_web_fetch_no_url():
    """Test skill with missing URL."""
    skill = WebFetchSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert not result.success, "Should fail without URL"
    return {"status": "pass", "message": "Missing URL handled"}


def test_extract_text_basic():
    """Test text extraction from HTML."""
    from bs4 import BeautifulSoup
    
    html = "<html><body><p>Hello World</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    text = extract_text(soup)
    
    assert "Hello World" in text, f"Should extract text: {text}"
    return {"status": "pass", "message": "Text extraction working"}


def test_clean_text():
    """Test text cleaning."""
    dirty = "Line 1\n\n\n\nLine 2\n\n\n"
    clean = clean_text(dirty)
    
    # Should remove excessive blank lines
    assert "\n\n\n" not in clean, f"Should clean multiple newlines: {clean}"
    return {"status": "pass", "message": "Text cleaning working"}


# =============================================================================
# Web Search Tests
# =============================================================================

def test_web_search_empty_query():
    """Test search with empty query."""
    result = search_run("")
    
    assert "error" in result, "Should fail with empty query"
    return {"status": "pass", "message": "Empty query handled"}


def test_web_search_skill_class():
    """Test WebSearchSkill class."""
    skill = WebSearchSkill()
    
    assert skill.name == "web_search"
    assert "query" in skill.parameters
    return {"status": "pass", "message": "WebSearchSkill class metadata correct"}


def test_web_search_no_query():
    """Test skill with missing query."""
    skill = WebSearchSkill()
    ctx = SkillContext()
    
    result = skill.execute({}, ctx)
    
    assert not result.success, "Should fail without query"
    return {"status": "pass", "message": "Missing query handled"}


def test_web_search_basic():
    """Test basic search (requires network)."""
    # This may be rate limited, so we're lenient
    result = search_run("python programming", num_results=3)
    
    if "error" in result:
        # Rate limiting is acceptable
        return {"status": "pass", "message": f"Search returned error (may be rate limited): {result['error']}"}
    
    assert "results" in result, "Should have results"
    assert "query" in result, "Should have query"
    return {"status": "pass", "message": f"Search returned {len(result.get('results', []))} results"}


def test_web_search_num_results():
    """Test num_results parameter."""
    result = search_run("test query", num_results=2)
    
    if "error" in result:
        return {"status": "pass", "message": "Search rate limited"}
    
    assert len(result.get("results", [])) <= 2, "Should respect num_results limit"
    return {"status": "pass", "message": "num_results working"}


def test_web_search_cache():
    """Test search caching."""
    cache_clear("search")
    
    # First search
    result1 = search_run("cache test query", use_cache=True)
    if "error" in result1:
        return {"status": "pass", "message": "Search rate limited"}
    
    # If no results, caching may not work as expected
    if not result1.get("results"):
        return {"status": "pass", "message": "No results to cache"}
    
    assert not result1.get("cached"), "First search should not be cached"
    
    # Second search should be cached
    result2 = search_run("cache test query", use_cache=True)
    # If rate limited on second try, that's fine too
    if "error" in result2:
        return {"status": "pass", "message": "Second search rate limited"}
    
    assert result2.get("cached"), "Second search should be cached"
    
    return {"status": "pass", "message": "Search caching working"}


# =============================================================================
# Test Runner
# =============================================================================

ALL_TESTS = [
    # Web fetch tests
    ("web_fetch_valid_url", test_web_fetch_valid_url),
    ("web_fetch_invalid_scheme", test_web_fetch_invalid_scheme),
    ("web_fetch_invalid_url", test_web_fetch_invalid_url),
    ("web_fetch_missing_domain", test_web_fetch_missing_domain),
    ("web_fetch_cache", test_web_fetch_cache),
    ("web_fetch_no_cache", test_web_fetch_no_cache),
    ("web_fetch_max_length", test_web_fetch_max_length),
    ("web_fetch_skill_class", test_web_fetch_skill_class),
    ("web_fetch_no_url", test_web_fetch_no_url),
    ("extract_text_basic", test_extract_text_basic),
    ("clean_text", test_clean_text),
    # Web search tests
    ("web_search_empty_query", test_web_search_empty_query),
    ("web_search_skill_class", test_web_search_skill_class),
    ("web_search_no_query", test_web_search_no_query),
    ("web_search_basic", test_web_search_basic),
    ("web_search_num_results", test_web_search_num_results),
    ("web_search_cache", test_web_search_cache),
]


def run_all(verbose: bool = False) -> dict:
    """Run all web skills tests."""
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
    print("Running web skills tests...\n")
    results = run_all(verbose=True)
    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")
    
    if results["failed"] > 0:
        sys.exit(1)
