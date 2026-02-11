"""Robots.txt parser and checker."""
import requests
from urllib.parse import urlparse
from typing import Dict, Optional, Tuple
from .cache import cache_get, cache_set, get_cache_key


def parse_robots_txt(content: str, user_agent: str = "*") -> dict:
    """Parse robots.txt content into rules dict."""
    rules = {"disallow": [], "allow": [], "crawl_delay": None}
    current_agent = None
    user_agent_lower = user_agent.lower()
    
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        
        line_lower = line.lower()
        
        if line_lower.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip().lower()
            # Match our user agent or wildcard
            current_agent = agent if agent in ["*", user_agent_lower] else None
        elif current_agent is not None:
            if line_lower.startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules["disallow"].append(path)
            elif line_lower.startswith("allow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules["allow"].append(path)
            elif line_lower.startswith("crawl-delay:"):
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
    if cached is not None:
        return cached
    
    try:
        resp = requests.get(robots_url, timeout=timeout, headers={
            "User-Agent": "Noctem/1.0"
        })
        if resp.status_code == 200:
            rules = parse_robots_txt(resp.text)
            cache_set(cache_key, rules)
            return rules
        elif resp.status_code == 404:
            # No robots.txt = all allowed
            empty_rules = {"disallow": [], "allow": [], "crawl_delay": None}
            cache_set(cache_key, empty_rules)
            return empty_rules
    except requests.RequestException:
        pass
    
    return None


def is_allowed(url: str, user_agent: str = "Noctem/1.0") -> Tuple[bool, Optional[float]]:
    """
    Check if URL is allowed by robots.txt.
    Returns (is_allowed, crawl_delay).
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    
    rules = fetch_robots_txt(url)
    if rules is None:
        return True, None  # No robots.txt or error = allowed
    
    # Check allow rules first (more specific)
    for allow_path in rules.get("allow", []):
        if path.startswith(allow_path):
            return True, rules.get("crawl_delay")
    
    # Check disallow rules
    for disallow_path in rules.get("disallow", []):
        if disallow_path and path.startswith(disallow_path):
            return False, rules.get("crawl_delay")
    
    return True, rules.get("crawl_delay")
