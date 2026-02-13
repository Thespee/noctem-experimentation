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
from urllib.parse import quote_plus, parse_qs, urlparse, unquote
import sys
import re
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache import cache_get, cache_set, get_cache_key
from utils.rate_limit import wait_for_rate_limit

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DEFAULT_NUM_RESULTS = 5
MAX_RESULTS = 10
DEFAULT_CACHE_TTL = 300  # 5 minutes


def extract_url_from_ddg_redirect(redirect_url: str) -> str:
    """Extract the actual URL from DuckDuckGo's redirect URL."""
    if not redirect_url:
        return ""
    
    # DuckDuckGo uses uddg parameter for the actual URL
    if "uddg=" in redirect_url:
        parsed = urlparse(redirect_url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    
    # Sometimes it's a direct link
    if redirect_url.startswith("http"):
        return redirect_url
    
    return redirect_url


def parse_ddg_results(html: str, num_results: int) -> list:
    """Parse DuckDuckGo HTML results page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    
    # Find all links in the results area
    links_div = soup.find("div", id="links")
    if not links_div:
        links_div = soup
    
    # Look for result divs/links with various selectors
    for link in links_div.find_all("a", href=True):
        if len(results) >= num_results:
            break
        
        href = link.get("href", "")
        text = link.get_text(strip=True)
        
        # Skip DDG internal/ad links
        if not href or "duckduckgo.com" in href:
            continue
        if href.startswith("/") or href.startswith("#"):
            continue
        
        # Extract real URL if it's a redirect
        url = extract_url_from_ddg_redirect(href)
        if not url or not url.startswith("http"):
            continue
        
        # Skip if no meaningful title
        if not text or len(text) < 5:
            continue
        
        # Skip ads/sponsored
        parent = link.find_parent("div")
        if parent:
            parent_class = " ".join(parent.get("class", []))
            if "ad" in parent_class.lower() or "sponsor" in parent_class.lower():
                continue
        
        # Try to find snippet
        snippet = ""
        snippet_elem = link.find_next_sibling(class_=re.compile("snippet|desc", re.I))
        if not snippet_elem and parent:
            snippet_elem = parent.find(class_=re.compile("snippet|desc", re.I))
        if snippet_elem:
            snippet = snippet_elem.get_text(strip=True)
        
        # Avoid duplicates
        if any(r["url"] == url for r in results):
            continue
        
        results.append({
            "title": text,
            "url": url,
            "snippet": snippet
        })
    
    return results


def search_ddg(query: str, num_results: int) -> list:
    """Search using DuckDuckGo HTML endpoint with session."""
    session = requests.Session()
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    session.headers.update(headers)
    
    # First visit the main page to get cookies
    try:
        session.get("https://duckduckgo.com/", timeout=10)
    except:
        pass
    
    time.sleep(0.5)  # Brief delay
    
    # Now search
    try:
        response = session.post(
            DDG_HTML_URL,
            data={"q": query, "b": ""},
            timeout=15,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            return parse_ddg_results(response.text, num_results)
    except Exception:
        pass
    
    return []


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
    
    # Rate limit for DuckDuckGo (be nice)
    wait_for_rate_limit("duckduckgo.com", min_delay=2.0)
    
    # Try to get results
    results = search_ddg(query, num_results)
    
    if not results:
        return {
            "results": [],
            "query": query,
            "cached": False,
            "message": "No results found. DuckDuckGo may be rate limiting."
        }
    
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


# Skill class wrapper for integration with Noctem framework
from typing import Dict
from .base import Skill, SkillResult, SkillContext, register_skill


@register_skill
class WebSearchSkill(Skill):
    """Search the web using DuckDuckGo."""
    
    name = "web_search"
    description = "Search the web and return results with titles, URLs, and snippets. Use for finding information, researching topics, looking up documentation, etc."
    parameters = {
        "query": "string - the search query",
        "num_results": "int (optional, default 5) - number of results to return (max 10)"
    }
    
    def run(self, params: Dict, context: SkillContext) -> SkillResult:
        query = params.get("query", "")
        num_results = params.get("num_results", DEFAULT_NUM_RESULTS)
        
        if not query:
            return SkillResult(success=False, output="", error="No search query provided")
        
        result = run(query, num_results=num_results)
        
        if "error" in result:
            return SkillResult(
                success=False,
                output="",
                error=result["error"]
            )
        
        # Format results for output
        results = result.get("results", [])
        if not results:
            return SkillResult(
                success=True,
                output="No results found for that query.",
                data=result
            )
        
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r.get('snippet'):
                lines.append(f"   {r['snippet'][:150]}...")
            lines.append("")
        
        return SkillResult(
            success=True,
            output="\n".join(lines),
            data=result
        )


# Allow running directly for testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = run(query)
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python web_search.py <query>")
