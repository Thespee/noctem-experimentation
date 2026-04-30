"""Spotify fingerprint scanner for Cor Unum artists."""
from __future__ import annotations
from datetime import datetime, timedelta

import logging

import requests

from ..db import get_db
from .city_tags import is_local_yvr, set_local_yvr
from .link_discovery import DiscoveryProviderUnavailable, discover_best_profile_url

logger = logging.getLogger(__name__)
DISCOVERY_RETRY_BACKOFF_HOURS = 24
_DISCOVERY_COLUMN_MIGRATIONS = (
    ("spotify_last_discovery_attempt_at", "TIMESTAMP"),
    ("spotify_discovery_error", "TEXT"),
)


def _discovery_retry_cutoff_iso() -> str:
    return (datetime.utcnow() - timedelta(hours=DISCOVERY_RETRY_BACKOFF_HOURS)).isoformat()


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
    is_local = "vancouver" in text or "yvr" in text
    is_canadian = is_local or "canada" in text or "british columbia" in text
    return is_local, is_canadian

def check_artist_spotify_fingerprint(artist_id: int, force: bool = False) -> dict:
    attempt_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        row = conn.execute(
            """SELECT id, name, alias_of, spotify_url, is_canadian, spotify_checked_at
               FROM cu_artists WHERE id = ?""",
            (artist_id,),
        ).fetchone()
        if not row:
            return {"error": "Artist not found"}
        if row["alias_of"]:
            return check_artist_spotify_fingerprint(row["alias_of"], force=force)
        spotify_url = (row["spotify_url"] or "").strip()
        discovered = False
        if not spotify_url:
            try:
                discovered_match = discover_best_profile_url(row["name"], "spotify")
            except DiscoveryProviderUnavailable as exc:
                if has_discovery_cols:
                    conn.execute(
                        """UPDATE cu_artists
                           SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                           WHERE id = ?""",
                        (attempt_at, str(exc)[:500], artist_id),
                    )
                return {"error": str(exc)}
            if discovered_match and discovered_match.get("candidate_url"):
                spotify_url = discovered_match["candidate_url"].strip()
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
                return {"error": "No Spotify URL found for this artist"}
        checked_at = row["spotify_checked_at"]
        if not force and checked_at:
            cached_local = is_local_yvr(conn, artist_id)
            return {
                "artist_id": artist_id,
                "artist_name": row["name"],
                "is_local": cached_local,
                "is_canadian": row["is_canadian"],
                "checked_at": checked_at,
                "spotify_url": spotify_url,
                "skipped": True,
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
                   SET is_canadian = ?,
                       spotify_checked_at = ?,
                       spotify_last_discovery_attempt_at = ?,
                       spotify_discovery_error = NULL
                   WHERE id = ?""",
                (1 if is_canadian else 0, datetime.utcnow().isoformat(), attempt_at, artist_id),
            )
        else:
            conn.execute(
                "UPDATE cu_artists SET is_canadian = ?, spotify_checked_at = ? WHERE id = ?",
                (1 if is_canadian else 0, datetime.utcnow().isoformat(), artist_id),
            )
    return {
        "artist_id": artist_id,
        "artist_name": artist_name,
        "is_local": is_local,
        "is_canadian": is_canadian,
        "spotify_url": spotify_url,
        "discovered_url": discovered,
    }


def check_spotify_fingerprints(limit: int = 150, recheck_all: bool = False) -> dict:
    retry_cutoff = _discovery_retry_cutoff_iso()
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        if recheck_all:
            rows = conn.execute(
                """SELECT id, name, spotify_url
                   FROM cu_artists
                   WHERE alias_of IS NULL
                   ORDER BY last_seen DESC NULLS LAST
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        elif has_discovery_cols:
            rows = conn.execute(
                """SELECT id, name, spotify_url
                   FROM cu_artists
                   WHERE alias_of IS NULL
                     AND spotify_checked_at IS NULL
                     AND (
                       spotify_last_discovery_attempt_at IS NULL
                       OR spotify_last_discovery_attempt_at < ?
                     )
                   ORDER BY last_seen DESC NULLS LAST
                   LIMIT ?""",
                (retry_cutoff, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name, spotify_url
                   FROM cu_artists
                   WHERE alias_of IS NULL
                     AND spotify_checked_at IS NULL
                   ORDER BY last_seen DESC NULLS LAST
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
        "error_message": None,
    }
    with get_db() as conn:
        _ensure_discovery_columns(conn)
        has_discovery_cols = _has_discovery_columns(conn)
        for row in rows:
            attempt_at = datetime.utcnow().isoformat()
            spotify_url = (row["spotify_url"] or "").strip()
            if not spotify_url:
                try:
                    discovered_match = discover_best_profile_url(row["name"], "spotify")
                except DiscoveryProviderUnavailable as exc:
                    result["error_message"] = str(exc)
                    logger.warning("Aborting spotify fingerprint run: %s", exc)
                    break
                if discovered_match and discovered_match.get("candidate_url"):
                    spotify_url = discovered_match["candidate_url"].strip()
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
                else:
                    if has_discovery_cols:
                        conn.execute(
                            """UPDATE cu_artists
                               SET spotify_last_discovery_attempt_at = ?, spotify_discovery_error = ?
                               WHERE id = ?""",
                            (attempt_at, "no_match_found", row["id"]),
                        )
                    result["errors"] += 1
                    continue
            result["checked"] += 1
            is_local, is_canadian = _profile_signals(spotify_url)
            set_local_yvr(conn, row["id"], is_local)
            if has_discovery_cols:
                conn.execute(
                    """UPDATE cu_artists
                       SET is_canadian = ?,
                           spotify_checked_at = ?,
                           spotify_discovery_error = NULL
                       WHERE id = ?""",
                    (1 if is_canadian else 0, datetime.utcnow().isoformat(), row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE cu_artists SET is_canadian = ?, spotify_checked_at = ? WHERE id = ?",
                    (1 if is_canadian else 0, datetime.utcnow().isoformat(), row["id"]),
                )
            if is_local:
                result["local"] += 1
            else:
                result["not_local"] += 1
            if is_canadian:
                result["canadian"] += 1
    if not result["error_message"]:
        result.pop("error_message")
    return result

