"""SoundCloud locality checker for Cor Unum artists.

Uses the SoundCloud API (Client Credentials OAuth flow) to search for
artists and check if their profile city contains 'Vancouver'.
"""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timedelta

import requests

from ..config import Config
from ..db import get_db

logger = logging.getLogger(__name__)

# Token cache (module-level, refreshed when expired)
_token: str | None = None
_token_expires_at: datetime | None = None

_SC_CONFIG_PREFIX = "cu_soundcloud_"


# --------------------------------------------------------------------------
# Config helpers
# --------------------------------------------------------------------------

def get_sc_config() -> dict:
    """Return SoundCloud config (client_id, client_secret)."""
    return {
        "client_id": Config.get(f"{_SC_CONFIG_PREFIX}client_id", ""),
        "client_secret": Config.get(f"{_SC_CONFIG_PREFIX}client_secret", ""),
    }


def save_sc_config(client_id: str, client_secret: str) -> None:
    """Save SoundCloud credentials to the config table."""
    Config.set(f"{_SC_CONFIG_PREFIX}client_id", client_id)
    Config.set(f"{_SC_CONFIG_PREFIX}client_secret", client_secret)
    Config.clear_cache()
    # Invalidate cached token
    global _token, _token_expires_at
    _token = None
    _token_expires_at = None


# --------------------------------------------------------------------------
# OAuth token management
# --------------------------------------------------------------------------

def _get_token() -> str | None:
    """Get a valid access token, refreshing if needed."""
    global _token, _token_expires_at

    if _token and _token_expires_at and datetime.utcnow() < _token_expires_at:
        return _token

    cfg = get_sc_config()
    client_id = cfg.get("client_id", "").strip()
    client_secret = cfg.get("client_secret", "").strip()
    if not client_id or not client_secret:
        logger.warning("SoundCloud credentials not configured")
        return None

    try:
        # Client Credentials flow with Basic auth header
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = requests.post(
            "https://secure.soundcloud.com/oauth/token",
            headers={
                "Accept": "application/json; charset=utf-8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {creds}",
            },
            data="grant_type=client_credentials",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        _token_expires_at = datetime.utcnow() + timedelta(seconds=max(expires_in - 60, 60))
        logger.info("SoundCloud token acquired, expires in %ds", expires_in)
        return _token
    except Exception as exc:
        logger.error("SoundCloud token request failed: %s", exc)
        _token = None
        _token_expires_at = None
        return None


# --------------------------------------------------------------------------
# Artist locality check
# --------------------------------------------------------------------------

def check_artist_locality(artist_id: int) -> dict:
    """Check if an artist is from Vancouver via SoundCloud.

    Searches SoundCloud for the artist name, checks if any matching
    user's city contains 'vancouver' (case-insensitive).

    Returns: {"is_local": bool|None, "soundcloud_url": str|None, "city": str|None}
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, alias_of FROM cu_artists WHERE id = ?",
            (artist_id,),
        ).fetchone()
        if not row:
            return {"error": "Artist not found"}
        # Follow alias
        if row["alias_of"]:
            return check_artist_locality(row["alias_of"])
        artist_name = row["name"]

    token = _get_token()
    if not token:
        return {"error": "SoundCloud credentials not configured or token failed"}

    try:
        resp = requests.get(
            "https://api.soundcloud.com/users",
            params={"q": artist_name, "limit": 5},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        users = resp.json()
        if isinstance(users, dict):
            users = users.get("collection", [])
    except Exception as exc:
        logger.error("SoundCloud search failed for '%s': %s", artist_name, exc)
        return {"error": str(exc)}

    # Check each result for Vancouver in city
    is_local = False
    sc_url = None
    city_found = None

    for user in users:
        user_name = (user.get("username") or "").strip()
        user_city = (user.get("city") or "").strip()
        permalink = user.get("permalink_url") or ""

        # Name match: check if the SoundCloud username is close to our artist name
        if not _names_match(artist_name, user_name):
            continue

        sc_url = permalink
        city_found = user_city
        if "vancouver" in user_city.lower():
            is_local = True
            break

    # Store result
    with get_db() as conn:
        conn.execute(
            """UPDATE cu_artists SET is_local = ?, soundcloud_url = ?
               WHERE id = ?""",
            (1 if is_local else 0, sc_url, artist_id),
        )

    return {
        "artist_id": artist_id,
        "artist_name": artist_name,
        "is_local": is_local,
        "soundcloud_url": sc_url,
        "city": city_found,
    }


def check_all_unchecked_artists(limit: int = 50) -> dict:
    """Batch-check all artists where is_local IS NULL.

    Returns summary with counts.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name FROM cu_artists
               WHERE is_local IS NULL AND alias_of IS NULL
               ORDER BY last_seen DESC NULLS LAST
               LIMIT ?""",
            (limit,),
        ).fetchall()

    results = {"checked": 0, "local": 0, "not_local": 0, "errors": 0}
    for row in rows:
        time.sleep(0.3)  # polite rate limiting
        result = check_artist_locality(row["id"])
        results["checked"] += 1
        if result.get("error"):
            results["errors"] += 1
        elif result.get("is_local"):
            results["local"] += 1
        else:
            results["not_local"] += 1

    return results


def _names_match(our_name: str, sc_name: str) -> bool:
    """Loose check if a SoundCloud username matches our artist name."""
    a = our_name.lower().strip()
    b = sc_name.lower().strip()
    if not a or not b:
        return False
    # Exact or containment
    if a == b or a in b or b in a:
        return True
    # Strip common suffixes/prefixes and retry
    for suffix in (" (ca)", " (vancouver)", " dj", "dj "):
        a2 = a.replace(suffix, "").strip()
        if a2 and (a2 == b or a2 in b or b in a2):
            return True
    return False
