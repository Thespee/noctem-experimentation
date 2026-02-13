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
