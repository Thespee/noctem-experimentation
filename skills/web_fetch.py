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
from urllib.parse import urlparse
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
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
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
        # Allow application/xhtml+xml as well
        if "xhtml" not in content_type:
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


# Skill class wrapper for integration with Noctem framework
from typing import Dict
from .base import Skill, SkillResult, SkillContext, register_skill


@register_skill
class WebFetchSkill(Skill):
    """Fetch and extract text from web URLs."""
    
    name = "web_fetch"
    description = "Fetch a URL and extract its text content. Use for reading web pages, articles, documentation, etc."
    parameters = {
        "url": "string - the URL to fetch",
        "selector": "string (optional) - CSS selector to extract specific content",
        "max_length": "int (optional, default 8000) - maximum characters to return"
    }
    
    def run(self, params: Dict, context: SkillContext) -> SkillResult:
        url = params.get("url", "")
        selector = params.get("selector")
        max_length = params.get("max_length", DEFAULT_MAX_LENGTH)
        
        if not url:
            return SkillResult(success=False, output="", error="No URL provided")
        
        result = run(url, selector=selector, max_length=max_length)
        
        if "error" in result:
            return SkillResult(
                success=False,
                output="",
                error=result["error"]
            )
        
        output = f"Title: {result.get('title', 'Unknown')}\n\n{result['content']}"
        
        return SkillResult(
            success=True,
            output=output,
            data=result
        )


# Allow running directly for testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = run(sys.argv[1])
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python web_fetch.py <url>")
