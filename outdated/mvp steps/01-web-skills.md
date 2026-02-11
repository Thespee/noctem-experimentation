# Phase 1: Web Skills Implementation Guide

**Objective**: Implement `web_fetch` and `web_search` skills with production-quality features.

**Prerequisites**: 
- Working Noctem installation with `main.py`, `daemon.py`, `skill_runner.py`
- Python 3.11+ with `requests`, `beautifulsoup4` installed
- Understanding of existing skill pattern (see `skills/shell.py` as reference)

---

## Step 1: Create Cache Infrastructure

### 1.1 Create `utils/cache.py`

```python
"""Simple file-based cache with TTL support."""
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Any

CACHE_DIR = Path(__file__).parent.parent / "cache"

def get_cache_key(prefix: str, data: str) -> str:
    """Generate cache key from prefix and data."""
    hash_val = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"{prefix}_{hash_val}"

def cache_get(key: str, max_age_seconds: int) -> Optional[Any]:
    """Retrieve from cache if not expired."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    
    if not cache_file.exists():
        return None
    
    try:
        data = json.loads(cache_file.read_text())
        if time.time() - data["timestamp"] > max_age_seconds:
            cache_file.unlink()  # Expired
            return None
        return data["value"]
    except (json.JSONDecodeError, KeyError):
        return None

def cache_set(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{key}.json"
    cache_file.write_text(json.dumps({
        "timestamp": time.time(),
        "value": value
    }))

def cache_clear(prefix: Optional[str] = None) -> int:
    """Clear cache entries. Returns count deleted."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        if prefix is None or f.stem.startswith(prefix):
            f.unlink()
            count += 1
    return count
```

### 1.2 Create `utils/__init__.py`

```python
from .cache import cache_get, cache_set, cache_clear, get_cache_key
```

### 1.3 Add cache directory to `.gitignore`

Append to `.gitignore`:
```
cache/
```

---

## Step 2: Create Robots.txt Handler

### 2.1 Create `utils/robots.py`

```python
"""Robots.txt parser and checker."""
import requests
from urllib.parse import urlparse
from typing import Dict, Optional
from .cache import cache_get, cache_set, get_cache_key

# In-memory robots.txt cache (lives for session)
_robots_cache: Dict[str, dict] = {}

def parse_robots_txt(content: str, user_agent: str = "*") -> dict:
    """Parse robots.txt content into rules dict."""
    rules = {"disallow": [], "allow": [], "crawl_delay": None}
    current_agent = None
    
    for line in content.split("\n"):
        line = line.strip().lower()
        if line.startswith("#") or not line:
            continue
        
        if line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agent = agent if agent in ["*", user_agent.lower()] else None
        elif current_agent is not None:
            if line.startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules["disallow"].append(path)
            elif line.startswith("allow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules["allow"].append(path)
            elif line.startswith("crawl-delay:"):
                try:
                    rules["crawl_delay"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
    
    return rules

def fetch_robots_txt(base_url: str, timeout: int = 10) -> Optional[dict]:
    """Fetch and parse robots.txt for a domain."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    
    cache_key = get_cache_key("robots", parsed.netloc)
    cached = cache_get(cache_key, max_age_seconds=86400)  # 24h cache
    if cached:
        return cached
    
    try:
        resp = requests.get(robots_url, timeout=timeout)
        if resp.status_code == 200:
            rules = parse_robots_txt(resp.text)
            cache_set(cache_key, rules)
            return rules
    except requests.RequestException:
        pass
    
    return None

def is_allowed(url: str, user_agent: str = "Noctem/1.0") -> tuple[bool, Optional[float]]:
    """
    Check if URL is allowed by robots.txt.
    Returns (is_allowed, crawl_delay).
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    
    rules = fetch_robots_txt(url)
    if rules is None:
        return True, None  # No robots.txt = allowed
    
    # Check allow rules first (more specific)
    for allow_path in rules.get("allow", []):
        if path.startswith(allow_path):
            return True, rules.get("crawl_delay")
    
    # Check disallow rules
    for disallow_path in rules.get("disallow", []):
        if path.startswith(disallow_path):
            return False, rules.get("crawl_delay")
    
    return True, rules.get("crawl_delay")
```

---

## Step 3: Create Rate Limiter

### 3.1 Create `utils/rate_limit.py`

```python
"""Simple rate limiter for web requests."""
import time
from typing import Dict
from threading import Lock

# Domain -> last request timestamp
_last_request: Dict[str, float] = {}
_lock = Lock()

DEFAULT_DELAY = 1.0  # 1 second between requests to same domain

def wait_for_rate_limit(domain: str, min_delay: float = DEFAULT_DELAY) -> None:
    """Block until rate limit allows request to domain."""
    with _lock:
        now = time.time()
        last = _last_request.get(domain, 0)
        wait_time = min_delay - (now - last)
        
        if wait_time > 0:
            time.sleep(wait_time)
        
        _last_request[domain] = time.time()

def get_domain(url: str) -> str:
    """Extract domain from URL."""
    from urllib.parse import urlparse
    return urlparse(url).netloc
```

---

## Step 4: Implement `web_fetch` Skill

### 4.1 Create `skills/web_fetch.py`

```python
"""
Skill: web_fetch
Fetches a URL and converts HTML to readable text.

Parameters:
  - url (str, required): The URL to fetch
  - selector (str, optional): CSS selector to extract specific content
  - max_length (int, optional): Maximum characters to return (default: 8000)
  - use_cache (bool, optional): Whether to use cache (default: true)
  - cache_ttl (int, optional): Cache TTL in seconds (default: 300)

Returns:
  - success: {"content": "...", "title": "...", "url": "...", "cached": bool}
  - error: {"error": "..."}
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import sys
from pathlib import Path

# Add parent to path for utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache import cache_get, cache_set, get_cache_key
from utils.robots import is_allowed
from utils.rate_limit import wait_for_rate_limit, get_domain

USER_AGENT = "Noctem/1.0 (Personal AI Assistant; +https://github.com/noctem)"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_LENGTH = 8000
DEFAULT_CACHE_TTL = 300  # 5 minutes

def extract_text(soup: BeautifulSoup, selector: str = None) -> str:
    """Extract readable text from HTML."""
    # Remove script, style, nav, footer, header elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        element.decompose()
    
    if selector:
        selected = soup.select(selector)
        if selected:
            text_parts = [el.get_text(separator="\n", strip=True) for el in selected]
            return "\n\n".join(text_parts)
        return ""
    
    # Try to find main content
    main = soup.find("main") or soup.find("article") or soup.find(role="main")
    if main:
        return main.get_text(separator="\n", strip=True)
    
    # Fall back to body
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)
    
    return soup.get_text(separator="\n", strip=True)

def clean_text(text: str) -> str:
    """Clean extracted text."""
    lines = []
    prev_blank = False
    
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            if not prev_blank:
                lines.append("")
                prev_blank = True
        else:
            lines.append(line)
            prev_blank = False
    
    return "\n".join(lines).strip()

def run(url: str, selector: str = None, max_length: int = DEFAULT_MAX_LENGTH,
        use_cache: bool = True, cache_ttl: int = DEFAULT_CACHE_TTL) -> dict:
    """Fetch URL and extract text content."""
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"error": f"Invalid URL scheme: {parsed.scheme}. Must be http or https."}
    
    if not parsed.netloc:
        return {"error": "Invalid URL: missing domain."}
    
    # Check cache first
    cache_key = get_cache_key("fetch", f"{url}:{selector or ''}")
    if use_cache:
        cached = cache_get(cache_key, max_age_seconds=cache_ttl)
        if cached:
            cached["cached"] = True
            return cached
    
    # Check robots.txt
    allowed, crawl_delay = is_allowed(url)
    if not allowed:
        return {"error": f"URL disallowed by robots.txt: {url}"}
    
    # Apply rate limiting
    domain = get_domain(url)
    delay = crawl_delay if crawl_delay else 1.0
    wait_for_rate_limit(domain, min_delay=delay)
    
    # Fetch the page
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.Timeout:
        return {"error": f"Request timed out after {DEFAULT_TIMEOUT}s"}
    except requests.TooManyRedirects:
        return {"error": "Too many redirects"}
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    
    # Check content type
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        return {"error": f"Unsupported content type: {content_type}"}
    
    # Parse and extract
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Get title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    
    # Extract text
    text = extract_text(soup, selector)
    text = clean_text(text)
    
    # Truncate if needed
    truncated = False
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."
        truncated = True
    
    result = {
        "content": text,
        "title": title,
        "url": str(response.url),  # Final URL after redirects
        "cached": False,
        "truncated": truncated,
        "length": len(text)
    }
    
    # Cache the result
    if use_cache:
        cache_set(cache_key, result)
    
    return result
```

---

## Step 5: Implement `web_search` Skill

### 5.1 Create `skills/web_search.py`

```python
"""
Skill: web_search
Searches the web using DuckDuckGo and returns results.

Parameters:
  - query (str, required): Search query
  - num_results (int, optional): Number of results to return (default: 5, max: 10)
  - use_cache (bool, optional): Whether to use cache (default: true)
  - cache_ttl (int, optional): Cache TTL in seconds (default: 300)

Returns:
  - success: {"results": [{"title": "...", "url": "...", "snippet": "..."}], "query": "..."}
  - error: {"error": "..."}
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache import cache_get, cache_set, get_cache_key
from utils.rate_limit import wait_for_rate_limit

USER_AGENT = "Noctem/1.0 (Personal AI Assistant)"
DDG_URL = "https://html.duckduckgo.com/html/"
DEFAULT_NUM_RESULTS = 5
MAX_RESULTS = 10
DEFAULT_CACHE_TTL = 300  # 5 minutes

def parse_ddg_results(html: str, num_results: int) -> list:
    """Parse DuckDuckGo HTML results page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    
    # DuckDuckGo HTML results are in divs with class "result"
    for result_div in soup.select(".result"):
        if len(results) >= num_results:
            break
        
        # Get title and URL
        title_link = result_div.select_one(".result__a")
        if not title_link:
            continue
        
        title = title_link.get_text(strip=True)
        url = title_link.get("href", "")
        
        # DuckDuckGo uses redirect URLs, extract actual URL
        if "uddg=" in url:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            url = qs.get("uddg", [url])[0]
        
        # Get snippet
        snippet_elem = result_div.select_one(".result__snippet")
        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
        
        if title and url:
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet
            })
    
    return results

def run(query: str, num_results: int = DEFAULT_NUM_RESULTS,
        use_cache: bool = True, cache_ttl: int = DEFAULT_CACHE_TTL) -> dict:
    """Search the web using DuckDuckGo."""
    
    # Validate inputs
    if not query or not query.strip():
        return {"error": "Search query cannot be empty"}
    
    query = query.strip()
    num_results = min(max(1, num_results), MAX_RESULTS)
    
    # Check cache
    cache_key = get_cache_key("search", f"{query}:{num_results}")
    if use_cache:
        cached = cache_get(cache_key, max_age_seconds=cache_ttl)
        if cached:
            cached["cached"] = True
            return cached
    
    # Rate limit for DuckDuckGo
    wait_for_rate_limit("duckduckgo.com", min_delay=2.0)  # Be nice to DDG
    
    # Make request
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        # DuckDuckGo HTML endpoint uses POST
        data = {"q": query, "b": ""}
        response = requests.post(DDG_URL, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        
    except requests.Timeout:
        return {"error": "Search request timed out"}
    except requests.RequestException as e:
        return {"error": f"Search request failed: {str(e)}"}
    
    # Parse results
    results = parse_ddg_results(response.text, num_results)
    
    if not results:
        # Try to detect if we got a CAPTCHA or error page
        if "robot" in response.text.lower() or "captcha" in response.text.lower():
            return {"error": "Rate limited by DuckDuckGo. Try again later."}
        return {"results": [], "query": query, "cached": False, "message": "No results found"}
    
    result = {
        "results": results,
        "query": query,
        "cached": False,
        "count": len(results)
    }
    
    # Cache results
    if use_cache:
        cache_set(cache_key, result)
    
    return result
```

---

## Step 6: Register Skills in System

### 6.1 Update `daemon.py` Planning Prompt

Find the system prompt in `daemon.py` and add the new skills to the available skills list:

```python
# Add to the skills description in the planning prompt:
"""
- web_fetch: Fetch a URL and extract text content
  Parameters: url (required), selector (optional CSS selector), max_length (default 8000)
  Example: {"skill": "web_fetch", "params": {"url": "https://example.com/page"}}
  
- web_search: Search the web using DuckDuckGo
  Parameters: query (required), num_results (default 5, max 10)
  Example: {"skill": "web_search", "params": {"query": "python asyncio tutorial"}}
"""
```

### 6.2 Update `skill_runner.py` to Load New Skills

The existing `skill_runner.py` should auto-discover skills in the `skills/` directory. Verify it uses dynamic import:

```python
# In skill_runner.py, ensure this pattern exists:
def load_skill(skill_name: str):
    module = importlib.import_module(f"skills.{skill_name}")
    return module.run
```

---

## Step 7: Create Test Script

### 7.1 Create `tests/test_web_skills.py`

```python
"""Tests for web_fetch and web_search skills."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills import web_fetch, web_search

def test_web_fetch_basic():
    """Test basic URL fetch."""
    result = web_fetch.run("https://example.com")
    assert "content" in result, f"Expected content, got: {result}"
    assert "error" not in result, f"Got error: {result.get('error')}"
    assert "Example Domain" in result.get("title", ""), "Expected Example Domain in title"
    print("✓ web_fetch basic test passed")

def test_web_fetch_invalid_url():
    """Test invalid URL handling."""
    result = web_fetch.run("not-a-url")
    assert "error" in result, "Expected error for invalid URL"
    print("✓ web_fetch invalid URL test passed")

def test_web_fetch_cache():
    """Test caching behavior."""
    # First fetch
    result1 = web_fetch.run("https://example.com", use_cache=True)
    assert not result1.get("cached"), "First fetch should not be cached"
    
    # Second fetch should be cached
    result2 = web_fetch.run("https://example.com", use_cache=True)
    assert result2.get("cached"), "Second fetch should be cached"
    print("✓ web_fetch cache test passed")

def test_web_search_basic():
    """Test basic search."""
    result = web_search.run("python programming")
    assert "results" in result, f"Expected results, got: {result}"
    assert "error" not in result, f"Got error: {result.get('error')}"
    assert len(result["results"]) > 0, "Expected at least one result"
    print("✓ web_search basic test passed")

def test_web_search_empty_query():
    """Test empty query handling."""
    result = web_search.run("")
    assert "error" in result, "Expected error for empty query"
    print("✓ web_search empty query test passed")

if __name__ == "__main__":
    print("Running web skills tests...\n")
    
    test_web_fetch_basic()
    test_web_fetch_invalid_url()
    test_web_fetch_cache()
    test_web_search_basic()
    test_web_search_empty_query()
    
    print("\n✓ All tests passed!")
```

---

## Step 8: Integration Testing

### 8.1 Manual Integration Test

1. Start Noctem: `python main.py`

2. Send test message via Signal:
   ```
   search for "ubuntu systemd tutorial" and summarize the first result
   ```

3. Expected behavior:
   - Daemon calls `web_search` with query
   - Gets results list
   - Calls `web_fetch` on first result URL
   - Summarizes content
   - Responds via Signal

### 8.2 Verify Error Handling

Test these edge cases:
- URL that returns 404
- URL that times out (use a slow endpoint)
- URL blocked by robots.txt
- Search with no results
- Rapid repeated requests (rate limiting)

---

## Step 9: Documentation

### 9.1 Update README.md

Add to the Skills section:

```markdown
### Web Skills

**web_fetch** - Fetch and extract text from URLs
- Respects robots.txt
- Rate limiting (1 req/sec per domain)
- Smart HTML-to-text conversion
- Caching (5 min default)

**web_search** - Search the web via DuckDuckGo
- No API key required
- Returns title, URL, snippet
- Caching (5 min default)
```

---

## Completion Checklist

- [ ] `utils/cache.py` created and tested
- [ ] `utils/robots.py` created and tested
- [ ] `utils/rate_limit.py` created and tested
- [ ] `utils/__init__.py` created
- [ ] `skills/web_fetch.py` created and tested
- [ ] `skills/web_search.py` created and tested
- [ ] `daemon.py` prompt updated with new skills
- [ ] `tests/test_web_skills.py` passes all tests
- [ ] Integration test via Signal works
- [ ] README updated
- [ ] Cache directory added to .gitignore

---

## Troubleshooting

### "No module named 'utils'"
- Check that `utils/__init__.py` exists
- Check `sys.path.insert` in skill files

### DuckDuckGo returns empty results
- May be rate limited; wait 5 minutes
- Check if response contains "robot" or "captcha"

### robots.txt blocking everything
- Some sites block all bots; this is expected
- Return clear error message to user

### Cache not working
- Check that `cache/` directory exists and is writable
- Verify JSON files are being created
