"""Simple rate limiter for web requests."""
import time
from typing import Dict
from threading import Lock
from urllib.parse import urlparse

# Domain -> last request timestamp
_last_request: Dict[str, float] = {}
_lock = Lock()

DEFAULT_DELAY = 1.0  # 1 second between requests to same domain


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    return urlparse(url).netloc


def wait_for_rate_limit(domain: str, min_delay: float = DEFAULT_DELAY) -> float:
    """
    Block until rate limit allows request to domain.
    Returns the time waited.
    """
    with _lock:
        now = time.time()
        last = _last_request.get(domain, 0)
        wait_time = min_delay - (now - last)
        
        if wait_time > 0:
            time.sleep(wait_time)
            _last_request[domain] = time.time()
            return wait_time
        
        _last_request[domain] = now
        return 0.0


def reset_rate_limits():
    """Reset all rate limit trackers (useful for testing)."""
    global _last_request
    with _lock:
        _last_request = {}
