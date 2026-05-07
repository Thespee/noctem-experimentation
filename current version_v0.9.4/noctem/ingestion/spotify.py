"""Spotify fingerprint scanner for Cor Unum artists."""
from __future__ import annotations
from datetime import datetime

import logging
import re
import time

import requests

from ..db import get_db
from .city_tags import set_local_yvr
from .link_discovery import DiscoveryProviderUnavailable, discover_best_profile_url
from .locality import derive_locality_flags

logger = logging.getLogger(__name__)
DISCOVERY_PROVIDER_RETRY_ATTEMPTS = 2
DISCOVERY_PROVIDER_RETRY_SLEEP_SECONDS = 0.35
DISCOVERY_SAMPLE_LIMIT = 5
_DISCOVERY_COLUMN_MIGRATIONS = (
    ("spotify_last_discovery_attempt_at", "TIMESTAMP"),
    ("spotify_discovery_error", "TEXT"),
)


def _ensure_discovery_columns(conn) -> None:
    for column, column_type in _DISCOVERY_COLUMN_MIGRATIONS:
        try:
            conn.execute(f'ALTER TABLE cu_artists ADD COLUMN {column} {column_type}')
        except Exception:
            pass


def _has_discovery_columns(conn) -> bool:
    cols = {r[1] for r in conn.execute('PRAGMA table_info("cu_artists")').fetchall()}
    return {"spotify_last_discovery_attempt_at", "spotify_discovery_error"}.issubset(cols)


def _profile_signals(url: str) -> tuple[bool, bool]:
    if not url:
        return False, False
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        text = resp.text.lower()
    except Exception:
        return False, False
    return derive_locality_flags(text, url)


def _append_unique_sample(values: list[str], value: str, limit: int = DISCOVERY_SAMPLE_LIMIT) -> None:
    item = (value or "").strip()
    if not item or item in values:
        return
    if len(values) >= limit:
        return
    values.append(item)


def _discovery_name_variants(artist_name: str) -> list[str]:
    base = " ".join(str(artist_name or "").split()).strip()
    if not base:
        return []
    variants = [base]
    simplified = re.sub(r"[^A-Za-z0-9\s]", " ", base)
    simplified = " ".join(simplified.split()).strip()
    if simplified and simplified.lower() != base.lower():
        variants.append(simplified)
    return variants[:2]


def _discover_spotify_url(artist_name: str) -> dict:
    variants = _discovery_name_variants(artist_name)
    provider_errors: list[str] = []
    had_live_discovery_response = False
    for variant in variants:
        for attempt in range(1, DISCOVERY_PROVIDER_RETRY_ATTEMPTS + 1):
            try:
                discovered_match = discover_best_profile_url(variant, "spotify")
                had_live_discovery_response = True
                if discovered_match and discovered_match.get("candidate_url"):
                    return {
                        "status": "found",
                        "candidate_url": str(discovered_match.get("candidate_url") or "").strip(),
                        "query": discovered_match.get("query"),
                        "confidence_score": discovered_match.get("confidence_score"),
                        "name_variant": variant,
                    }
                break
            except DiscoveryProviderUnavailable as exc:
                provider_errors.append(str(exc))
                if attempt < DISCOVERY_PROVIDER_RETRY_ATTEMPTS:
                    time.sleep(DISCOVERY_PROVIDER_RETRY_SLEEP_SECONDS * attempt)
                    continue
                break
    if had_live_discovery_response:
        return {
            "status": "no_match_found",
            "name_variants": variants,
        }
    if provider_errors:
        return {
            "status": "provider_unavailable",
            "error": provider_errors[-1],
            "provider_errors": provider_errors[-3:],
            "name_variants": variants,
        }
    return {"status": "no_match_found", "name_variants": variants}

def check_artist_spotify_fingerprint(artist_id: int, force: bool = False) -> dict:
    attempt_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        row = conn.execute(
            """SELECT id, name, alias_of, spotify_url, is_canadian, canadian, spotify_checked_at
               FROM cu_artists WHERE id = ?""",
            (artist_id,),
        ).fetchone()
        if not row:
            return {"error": "Artist not found"}
        if row["alias_of"]:
            return check_artist_spotify_fingerprint(row["alias_of"], force=force)
        spotify_url = (row["spotify_url"] or "").strip()
        discovered = False
        discovered_query = ""
        discovery_name_variant = ""
        if not spotify_url:
            discovery_result = _discover_spotify_url(row["name"])
            discovery_status = str(discovery_result.get("status") or "")
            if discovery_status == "provider_unavailable":
                discovery_error = str(
                    discovery_result.get("error") or "Spotify discovery provider unavailable"
                )
                if has_discovery_cols:
                    conn.execute(
                        """UPDATE cu_artists
                           SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                           WHERE id = ?""",
                        (attempt_at, f"provider_unavailable: {discovery_error}"[:500], artist_id),
                    )
                return {
                    "error": discovery_error,
                    "discovery_error_code": "provider_unavailable",
                }
            if discovery_status == "found" and discovery_result.get("candidate_url"):
                spotify_url = str(discovery_result.get("candidate_url") or "").strip()
                discovered_query = str(discovery_result.get("query") or "")
                discovery_name_variant = str(discovery_result.get("name_variant") or "")
                if has_discovery_cols:
                    conn.execute(
                        """UPDATE cu_artists
                           SET spotify_url = ?, spotify_last_discovery_attempt_at = ?, spotify_discovery_error = NULL
                           WHERE id = ?""",
                        (spotify_url, attempt_at, artist_id),
                    )
                else:
                    conn.execute(
                        "UPDATE cu_artists SET spotify_url = ? WHERE id = ?",
                        (spotify_url, artist_id),
                    )
                discovered = True
            else:
                if has_discovery_cols:
                    conn.execute(
                        """UPDATE cu_artists
                           SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                           WHERE id = ?""",
                        (attempt_at, "no_match_found", artist_id),
                    )
                return {
                    "error": "No Spotify URL found for this artist",
                    "discovery_error_code": "no_match_found",
                }
        artist_name = row["name"]

    is_local, is_canadian = _profile_signals(spotify_url)
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        set_local_yvr(conn, artist_id, is_local)
        if has_discovery_cols:
            conn.execute(
                """UPDATE cu_artists
                       SET is_canadian = ?, canadian = ?,
                       spotify_checked_at = ?,
                       spotify_last_discovery_attempt_at = ?,
                       spotify_discovery_error = NULL
                   WHERE id = ?""",
                (1 if is_canadian else 0, 1 if is_canadian else 0, datetime.utcnow().isoformat(), attempt_at, artist_id),
            )
        else:
            conn.execute(
                "UPDATE cu_artists SET is_canadian = ?, canadian = ?, spotify_checked_at = ? WHERE id = ?",
                (1 if is_canadian else 0, 1 if is_canadian else 0, datetime.utcnow().isoformat(), artist_id),
            )
    return {
        "artist_id": artist_id,
        "artist_name": artist_name,
        "is_local": is_local,
        "is_canadian": is_canadian,
        "spotify_url": spotify_url,
        "discovered_url": discovered,
        "discovery_query": discovered_query,
        "discovery_name_variant": discovery_name_variant,
    }


def check_spotify_fingerprints(limit: int = 30, recheck_all: bool = False) -> dict:
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        if recheck_all or int(limit) <= 0:
            rows = conn.execute(
                """SELECT id, name, spotify_url
                   FROM cu_artists
                   WHERE alias_of IS NULL
                     AND (spotify_url IS NULL OR TRIM(spotify_url) = '')
                   ORDER BY RANDOM()"""
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name, spotify_url
                   FROM cu_artists
                   WHERE alias_of IS NULL
                     AND (spotify_url IS NULL OR TRIM(spotify_url) = '')
                   ORDER BY RANDOM()
                   LIMIT ?""",
                (limit,),
            ).fetchall()
    result = {
        "checked": 0,
        "local": 0,
        "not_local": 0,
        "canadian": 0,
        "errors": 0,
        "urls_discovered": 0,
        "no_match_found": 0,
        "discovery_provider_errors": 0,
        "no_match_examples": [],
        "provider_error_examples": [],
        "error_message": None,
    }
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        for row in rows:
            attempt_at = datetime.utcnow().isoformat()
            spotify_url = (row["spotify_url"] or "").strip()
            if not spotify_url:
                discovery_result = _discover_spotify_url(row["name"])
                discovery_status = str(discovery_result.get("status") or "")
                if discovery_status == "found" and discovery_result.get("candidate_url"):
                    spotify_url = str(discovery_result.get("candidate_url") or "").strip()
                    if has_discovery_cols:
                        conn.execute(
                            """UPDATE cu_artists
                               SET spotify_url = ?, spotify_last_discovery_attempt_at = ?, spotify_discovery_error = NULL
                               WHERE id = ?""",
                            (spotify_url, attempt_at, row["id"]),
                        )
                    else:
                        conn.execute(
                            "UPDATE cu_artists SET spotify_url = ? WHERE id = ?",
                            (spotify_url, row["id"]),
                        )
                    result["urls_discovered"] += 1
                elif discovery_status == "provider_unavailable":
                    discovery_error = str(
                        discovery_result.get("error") or "Spotify discovery provider unavailable"
                    )
                    if has_discovery_cols:
                        conn.execute(
                            """UPDATE cu_artists
                               SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                               WHERE id = ?""",
                            (attempt_at, f"provider_unavailable: {discovery_error}"[:500], row["id"]),
                        )
                    result["errors"] += 1
                    result["discovery_provider_errors"] += 1
                    _append_unique_sample(
                        result["provider_error_examples"],
                        f"{row['name']}: {discovery_error[:120]}",
                    )
                    continue
                else:
                    if has_discovery_cols:
                        conn.execute(
                            """UPDATE cu_artists
                               SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                               WHERE id = ?""",
                            (attempt_at, "no_match_found", row["id"]),
                        )
                    result["errors"] += 1
                    result["no_match_found"] += 1
                    _append_unique_sample(result["no_match_examples"], str(row["name"] or ""))
                    continue
            result["checked"] += 1
            is_local, is_canadian = _profile_signals(spotify_url)
            set_local_yvr(conn, row["id"], is_local)
            if has_discovery_cols:
                conn.execute(
                    """UPDATE cu_artists
                       SET is_canadian = ?, canadian = ?,
                           spotify_checked_at = ?,
                           spotify_discovery_error = NULL
                       WHERE id = ?""",
                    (1 if is_canadian else 0, 1 if is_canadian else 0, datetime.utcnow().isoformat(), row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE cu_artists SET is_canadian = ?, canadian = ?, spotify_checked_at = ? WHERE id = ?",
                    (1 if is_canadian else 0, 1 if is_canadian else 0, datetime.utcnow().isoformat(), row["id"]),
                )
            if is_local:
                result["local"] += 1
            else:
                result["not_local"] += 1
            if is_canadian:
                result["canadian"] += 1
    if not result["no_match_examples"]:
        result.pop("no_match_examples")
    if not result["provider_error_examples"]:
        result.pop("provider_error_examples")
    if not result["error_message"]:
        result.pop("error_message")
    return result

