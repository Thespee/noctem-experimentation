"""SoundCloud locality checker for Cor Unum artists.

Uses the SoundCloud api-v2 endpoint with a public client_id extracted
from SoundCloud's frontend JS bundles.  No OAuth credentials needed.

Search strategy:
  1. Unfiltered search — look for name matches whose city contains 'vancouver'
  2. Location-filtered search (filter.place=vancouver) — catch profiles that
     didn't surface in the unfiltered pass
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

import requests

from ..config import Config
from ..db import get_db
from .city_tags import is_local_yvr, set_local_yvr
from .locality import derive_locality_flags

logger = logging.getLogger(__name__)

_SC_CONFIG_PREFIX = "cu_soundcloud_"

# Cached public client_id (extracted from SoundCloud JS bundles)
_public_client_id: str | None = None
_public_client_id_expires: datetime | None = None
_CLIENT_ID_TTL = timedelta(hours=6)
def _invalidate_public_client_id_cache() -> None:
    global _public_client_id, _public_client_id_expires
    _public_client_id = None
    _public_client_id_expires = None


# --------------------------------------------------------------------------
# Config helpers (shared settings)
# --------------------------------------------------------------------------

def get_sc_config() -> dict:
    """Return SoundCloud scraper settings."""
    raw_mf = Config.get(f"{_SC_CONFIG_PREFIX}min_followers", "0")
    raw_sl = Config.get(f"{_SC_CONFIG_PREFIX}search_limit", "5")
    try:
        min_f = int(raw_mf)
    except (ValueError, TypeError):
        min_f = 0
    try:
        search_l = int(raw_sl)
    except (ValueError, TypeError):
        search_l = 5
    return {
        "min_followers": max(0, min_f),
        "search_limit": max(1, min(search_l, 50)),
    }


def save_sc_config(*, min_followers: int | None = None,
                   search_limit: int | None = None) -> None:
    """Save SoundCloud scraper settings."""
    if min_followers is not None:
        Config.set(f"{_SC_CONFIG_PREFIX}min_followers", str(max(0, min_followers)))
    if search_limit is not None:
        Config.set(f"{_SC_CONFIG_PREFIX}search_limit", str(max(1, min(search_limit, 50))))
    Config.clear_cache()


# --------------------------------------------------------------------------
# Public client_id extraction
# --------------------------------------------------------------------------

def _get_public_client_id() -> str | None:
    """Extract a fresh public client_id from SoundCloud's JS bundles.

    SoundCloud embeds a client_id in their compiled JS assets.
    We fetch the homepage, find the script bundle URLs, then regex for
    the client_id string.  Result is cached for several hours.
    """
    global _public_client_id, _public_client_id_expires

    if (_public_client_id
            and _public_client_id_expires
            and datetime.utcnow() < _public_client_id_expires):
        return _public_client_id

    try:
        page = requests.get(
            "https://soundcloud.com",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        page.raise_for_status()

        # Find JS bundle URLs
        script_urls = re.findall(
            r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"',
            page.text,
        )
        if not script_urls:
            logger.warning("No SoundCloud JS bundles found on homepage")
            return None

        # Check the last few bundles (client_id is usually in one of the later ones)
        for url in reversed(script_urls[-5:]):
            try:
                js = requests.get(url, timeout=15).text
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js)
                if match:
                    _public_client_id = match.group(1)
                    _public_client_id_expires = datetime.utcnow() + _CLIENT_ID_TTL
                    logger.info("Extracted SoundCloud public client_id: %s…",
                                _public_client_id[:8])
                    return _public_client_id
            except Exception:
                continue

        logger.warning("Could not extract client_id from SoundCloud JS bundles")
        return None
    except Exception as exc:
        logger.error("Failed to fetch SoundCloud homepage: %s", exc)
        return None


# --------------------------------------------------------------------------
# api-v2 search
# --------------------------------------------------------------------------

def _search_users(query: str, limit: int = 5,
                  filter_place: str | None = None) -> list[dict] | None:
    """Search SoundCloud api-v2 for user profiles."""
    max_attempts = 4
    for attempt in range(max_attempts):
        client_id = _get_public_client_id()
        if not client_id:
            return None
        params: dict = {"q": query, "limit": limit, "client_id": client_id}
        if filter_place:
            params["filter.place"] = filter_place
        try:
            resp = requests.get(
                "https://api-v2.soundcloud.com/search/users",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://soundcloud.com/",
                    "Origin": "https://soundcloud.com",
                },
                timeout=10,
            )
            if resp.status_code in (401, 403):
                if attempt < max_attempts - 1:
                    _invalidate_public_client_id_cache()
                    time.sleep(0.3 * (attempt + 1))
                    continue
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt < max_attempts - 1:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                logger.error(
                    "SoundCloud api-v2 search failed for '%s': HTTP %s",
                    query,
                    resp.status_code,
                )
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("collection", [])
        except Exception as exc:
            if attempt < max_attempts - 1:
                _invalidate_public_client_id_cache()
                time.sleep(0.4 * (attempt + 1))
                continue
            logger.error("SoundCloud api-v2 search failed for '%s': %s", query, exc)
            return None
    return None


# --------------------------------------------------------------------------
# Name matching
# --------------------------------------------------------------------------

def _names_match(our_name: str, sc_name: str) -> bool:
    """Loose check if a SoundCloud username matches our artist name."""
    a = our_name.lower().strip()
    b = sc_name.lower().strip()
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    for suffix in (" (ca)", " (vancouver)", " dj", "dj "):
        a2 = a.replace(suffix, "").strip()
        if a2 and (a2 == b or a2 in b or b in a2):
            return True
    return False


# --------------------------------------------------------------------------
# Single artist locality check
# --------------------------------------------------------------------------

def check_artist_locality(artist_id: int, force: bool = False) -> dict:
    """Check if an artist is from Vancouver via SoundCloud api-v2.

    Two-pass search:
      1. Unfiltered — look for name matches with city containing 'vancouver'
      2. Location-filtered (filter.place=vancouver) — catches profiles that
         the unfiltered search may have ranked lower

    force=True bypasses existing fingerprint skip checks (for manual rechecks).

    Returns: {"is_local": bool, "soundcloud_url": str|None, ...}
    """
    with get_db() as conn:
        row = conn.execute(
            """SELECT id, name, alias_of, soundcloud_url, is_canadian, canadian
               FROM cu_artists WHERE id = ?""",
            (artist_id,),
        ).fetchone()
        if not row:
            return {"error": "Artist not found"}
        if row["alias_of"]:
            return check_artist_locality(row["alias_of"], force=force)
        if not force and row["soundcloud_url"]:
            cached_local = is_local_yvr(conn, artist_id)
            return {"artist_id": artist_id, "artist_name": row["name"],
                    "is_local": cached_local, "skipped": True}
        artist_name = row["name"]

    cfg = get_sc_config()
    min_followers = cfg["min_followers"]
    search_limit = cfg["search_limit"]

    # Collect all name-matched candidates across both passes, deduped by URL
    candidates: dict[str, dict] = {}  # permalink_url -> user info
    api_failed = False

    # Pass 1: unfiltered search
    # Pass 2: location-filtered search
    for filter_place in [None, "vancouver"]:
        users = _search_users(artist_name, limit=search_limit,
                              filter_place=filter_place)
        if users is None:
            api_failed = True
            continue

        for user in users:
            user_name = (user.get("username") or "").strip()
            full_name = (user.get("full_name") or "").strip()
            user_city = (user.get("city") or "").strip()
            permalink = user.get("permalink_url") or ""
            followers = user.get("followers_count", 0) or 0

            if not permalink:
                continue
            if not (_names_match(artist_name, user_name) or
                    _names_match(artist_name, full_name)):
                continue
            if followers < min_followers:
                continue

            # Keep highest-follower entry per profile
            if (permalink not in candidates
                    or followers > candidates[permalink]["followers"]):
                candidates[permalink] = {
                    "permalink_url": permalink,
                    "city": user_city,
                    "followers": followers,
                    "is_vancouver": "vancouver" in user_city.lower(),
                }
    if not candidates and api_failed:
        return {"error": "SoundCloud API unavailable"}

    # Pick best match: prefer Vancouver locals, then highest followers
    local_matches = [c for c in candidates.values() if c["is_vancouver"]]
    other_matches = [c for c in candidates.values() if not c["is_vancouver"]]

    best = None
    is_local = False
    if local_matches:
        best = max(local_matches, key=lambda c: c["followers"])
        is_local = True
    elif other_matches:
        best = max(other_matches, key=lambda c: c["followers"])

    sc_url = best["permalink_url"] if best else None
    city_found = best["city"] if best else None
    followers_found = best["followers"] if best else None
    local_from_city, canadian_from_city = derive_locality_flags(city_found)
    is_local = bool(is_local or local_from_city)
    is_canadian = bool(canadian_from_city or is_local)

    # Store result
    with get_db() as conn:
        set_local_yvr(conn, artist_id, is_local)
        conn.execute(
            """UPDATE cu_artists
               SET soundcloud_url = ?, sc_followers = ?, is_canadian = ?, canadian = ?
               WHERE id = ?""",
            (sc_url, followers_found, 1 if is_canadian else 0, 1 if is_canadian else 0, artist_id),
        )

    return {
        "artist_id": artist_id,
        "artist_name": artist_name,
        "is_local": is_local,
        "soundcloud_url": sc_url,
        "city": city_found,
        "followers": followers_found,
        "is_canadian": is_canadian,
    }


# --------------------------------------------------------------------------
# Batch check
# --------------------------------------------------------------------------

def check_all_unchecked_artists(limit: int = 50,
                                recheck_all: bool = False) -> dict:
    """Batch-check artists via SoundCloud api-v2.

    recheck_all=False: artists not yet checked by SoundCloud (no stored URL).
    recheck_all=True: recheck all canonical artists.
    """
    with get_db() as conn:
        if recheck_all:
            rows = conn.execute(
                """SELECT id, name FROM cu_artists
                   WHERE alias_of IS NULL
                   ORDER BY last_seen DESC NULLS LAST
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name FROM cu_artists
                   WHERE alias_of IS NULL
                     AND (soundcloud_url IS NULL OR TRIM(soundcloud_url) = '')
                   ORDER BY last_seen DESC NULLS LAST
                   LIMIT ?""",
                (limit,),
            ).fetchall()
    results = {"checked": 0, "local": 0, "not_local": 0, "canadian": 0, "errors": 0}
    for row in rows:
        time.sleep(0.3)
        result = check_artist_locality(row["id"])
        results["checked"] += 1
        if result.get("error"):
            results["errors"] += 1
        elif result.get("is_local"):
            results["local"] += 1
        else:
            results["not_local"] += 1
        if result.get("is_canadian"):
            results["canadian"] += 1

    return results
