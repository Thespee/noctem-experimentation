"""Cor Unum service layer — public API for ingestion operations.

All functions are safe to call from Flask route handlers.
"""
from __future__ import annotations
import json

import math
from datetime import datetime

from ..db import get_db
from .artist_fingerprints import (
    check_all_fingerprints as _check_all_fingerprints,
)
from .artist_fingerprints import (
    check_artist_fingerprint as _check_artist_fingerprint,
)
from .artist_fingerprints import list_fingerprint_sources as _list_fingerprint_sources
from .city_tags import LOCAL_CITY_TAG
from .engine import run_full_pipeline, run_ingestion, run_sources_by_class


# --------------------------------------------------------------------------
# Source management
# --------------------------------------------------------------------------

def refresh_source(source_key: str) -> dict:
    """Run the ingestion pipeline for a single source. Returns summary."""
    return run_ingestion(source_key)


def refresh_all_sources() -> dict:
    """Run full ordered pipeline: events -> fingerprint -> internal."""
    return run_full_pipeline()


def refresh_sources_by_class(scanner_class: str) -> dict:
    """Run all enabled sources in one scanner class."""
    return run_sources_by_class(scanner_class)


def get_source_registry() -> list[dict]:
    """Return all source registry rows."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cu_source_registry ORDER BY source_key"
        ).fetchall()
        return [dict(r) for r in rows]


def get_fingerprint_sources() -> list[dict]:
    return _list_fingerprint_sources()


def check_artist_fingerprint(source_key: str, artist_id: int, force: bool = False) -> dict:
    return _check_artist_fingerprint(source_key, artist_id, force=force)


def check_all_artist_fingerprints(source_key: str, limit: int = 50, mode: str = "unchecked") -> dict:
    return _check_all_fingerprints(source_key, limit=limit, mode=mode)


def get_source_status(source_key: str) -> dict | None:
    """Return a single source row or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_source_registry WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        return dict(row) if row else None


def set_source_enabled(source_key: str, enabled: bool) -> dict | None:
    """Toggle a source's enabled flag."""
    with get_db() as conn:
        conn.execute(
            "UPDATE cu_source_registry SET enabled = ? WHERE source_key = ?",
            (1 if enabled else 0, source_key),
        )
    return get_source_status(source_key)


def clear_source_error(source_key: str) -> dict | None:
    """Reset needs_fixing and last_error on a source."""
    with get_db() as conn:
        conn.execute(
            """UPDATE cu_source_registry
               SET needs_fixing = 0, last_error = NULL
               WHERE source_key = ?""",
            (source_key,),
        )
    return get_source_status(source_key)


# --------------------------------------------------------------------------
# Run history
# --------------------------------------------------------------------------

def get_run_summary(source_key: str | None = None, limit: int = 20) -> list[dict]:
    """Return recent ingestion run records."""
    with get_db() as conn:
        if source_key:
            rows = conn.execute(
                """SELECT * FROM cu_ingestion_runs
                   WHERE source_key = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (source_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cu_ingestion_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Paginated data access
# --------------------------------------------------------------------------

def _paginate(conn, query: str, count_query: str, params: tuple,
              page: int, per_page: int) -> dict:
    """Generic pagination helper."""
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page

    total = conn.execute(count_query, params).fetchone()[0]
    rows = conn.execute(
        f"{query} LIMIT ? OFFSET ?", params + (per_page, offset)
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": math.ceil(total / per_page) if per_page else 0,
    }


def get_events(page: int = 1, per_page: int = 50, search: str = "") -> dict:
    """Paginated events with optional title search."""
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            return _paginate(
                conn,
                """SELECT e.*, v.name AS venue_name
                   FROM cu_events e
                   LEFT JOIN cu_venues v ON e.venue_id = v.id
                   WHERE e.title LIKE ?
                   ORDER BY e.date DESC""",
                "SELECT COUNT(*) FROM cu_events WHERE title LIKE ?",
                (like,), page, per_page,
            )
        return _paginate(
            conn,
            """SELECT e.*, v.name AS venue_name
               FROM cu_events e
               LEFT JOIN cu_venues v ON e.venue_id = v.id
               ORDER BY e.date DESC""",
            "SELECT COUNT(*) FROM cu_events",
            (), page, per_page,
        )


def get_artists(page: int = 1, per_page: int = 50, search: str = "",
                local: str = "") -> dict:
    """Paginated artists (excluding aliases) with optional name search and local filter."""
    # Build WHERE clause
    conditions = ["alias_of IS NULL"]
    params: list = []
    if search:
        conditions.append("name LIKE ?")
        params.append(f"%{search}%")
    if local == "local":
        conditions.append(
            "EXISTS (SELECT 1 FROM cu_artist_tags t WHERE t.artist_id = cu_artists.id AND t.tag = ?)"
        )
        params.append(LOCAL_CITY_TAG)
    elif local == "not_local":
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM cu_artist_tags t WHERE t.artist_id = cu_artists.id AND t.tag = ?)"
        )
        params.append(LOCAL_CITY_TAG)
    elif local == "unchecked":
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM cu_artist_tags t WHERE t.artist_id = cu_artists.id AND t.tag = ?)"
        )
        conditions.append("(soundcloud_url IS NULL OR TRIM(soundcloud_url) = '')")
        conditions.append("(instagram_url IS NULL OR TRIM(instagram_url) = '')")
        conditions.append("(spotify_url IS NULL OR TRIM(spotify_url) = '')")
        params.append(LOCAL_CITY_TAG)
    where = " AND ".join(conditions)
    with get_db() as conn:
        return _paginate(
            conn,
            f"SELECT * FROM cu_artists WHERE {where} ORDER BY name",
            f"SELECT COUNT(*) FROM cu_artists WHERE {where}",
            tuple(params), page, per_page,
        )


def get_venues(page: int = 1, per_page: int = 50, search: str = "") -> dict:
    """Paginated venues (excluding aliases) with optional name search."""
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            return _paginate(
                conn,
                "SELECT * FROM cu_venues WHERE alias_of IS NULL AND name LIKE ? ORDER BY name",
                "SELECT COUNT(*) FROM cu_venues WHERE alias_of IS NULL AND name LIKE ?",
                (like,), page, per_page,
            )
        return _paginate(
            conn,
            "SELECT * FROM cu_venues WHERE alias_of IS NULL ORDER BY name",
            "SELECT COUNT(*) FROM cu_venues WHERE alias_of IS NULL",
            (), page, per_page,
        )


def get_event_sources(page: int = 1, per_page: int = 50) -> dict:
    """Paginated event-source records."""
    with get_db() as conn:
        return _paginate(
            conn,
            """SELECT es.*, e.title AS event_title
               FROM cu_event_sources es
               LEFT JOIN cu_events e ON es.event_id = e.id
               ORDER BY es.captured_at DESC""",
            "SELECT COUNT(*) FROM cu_event_sources",
            (), page, per_page,
        )


def get_source_registry_page(page: int = 1, per_page: int = 50) -> dict:
    """Paginated source registry."""
    with get_db() as conn:
        return _paginate(
            conn,
            "SELECT * FROM cu_source_registry ORDER BY source_key",
            "SELECT COUNT(*) FROM cu_source_registry",
            (), page, per_page,
        )


# --------------------------------------------------------------------------
# Detail views
# --------------------------------------------------------------------------

def get_upcoming_events(limit: int = 200) -> list[dict]:
    """Return upcoming events (today onward) with venue + performers + sources."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute(
            """SELECT e.id, e.title, e.date, e.description, e.created_at,
                      v.id AS venue_id, v.name AS venue_name
               FROM cu_events e
               LEFT JOIN cu_venues v ON e.venue_id = v.id
               WHERE e.date >= ?
               ORDER BY e.date ASC
               LIMIT ?""",
            (today, limit),
        ).fetchall()
        events = []
        for r in rows:
            ev = dict(r)
            eid = ev["id"]
            ev["performers"] = [
                dict(a)
                for a in conn.execute(
                    """SELECT a.id, a.name,
                              EXISTS (
                                  SELECT 1 FROM cu_artist_tags t
                                  WHERE t.artist_id = a.id AND t.tag = ?
                              ) AS is_yvr_local
                       FROM cu_artists a
                       JOIN cu_event_performers ep ON a.id = ep.artist_id
                       WHERE ep.event_id = ?""",
                    (LOCAL_CITY_TAG, eid),
                ).fetchall()
            ]
            ev["sources"] = [
                dict(s)
                for s in conn.execute(
                    "SELECT source_type, source_url FROM cu_event_sources WHERE event_id = ?",
                    (eid,),
                ).fetchall()
            ]
            total_artists = len(ev["performers"])
            local_artists = len([p for p in ev["performers"] if p.get("is_yvr_local")])
            ev["local_density_pct"] = round((local_artists / total_artists) * 100, 2) if total_artists else 0.0
            events.append(ev)
        return events


def get_event_detail(event_id: int) -> dict | None:
    """Return a single event with venue, performers, sources, and description."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT e.*, v.name AS venue_name, v.address AS venue_address,
                      v.url AS venue_url
               FROM cu_events e
               LEFT JOIN cu_venues v ON e.venue_id = v.id
               WHERE e.id = ?""",
            (event_id,),
        ).fetchone()
        if not row:
            return None
        ev = dict(row)
        ev["performers"] = [
            dict(a)
            for a in conn.execute(
                """SELECT a.id, a.name, a.bio_link,
                          EXISTS (
                              SELECT 1 FROM cu_artist_tags t
                              WHERE t.artist_id = a.id AND t.tag = ?
                          ) AS is_yvr_local
                   FROM cu_artists a
                   JOIN cu_event_performers ep ON a.id = ep.artist_id
                   WHERE ep.event_id = ?""",
                (LOCAL_CITY_TAG, event_id),
            ).fetchall()
        ]
        ev["sources"] = [
            dict(s)
            for s in conn.execute(
                "SELECT * FROM cu_event_sources WHERE event_id = ?",
                (event_id,),
            ).fetchall()
        ]
        total_artists = len(ev["performers"])
        local_artists = len([p for p in ev["performers"] if p.get("is_yvr_local")])
        ev["local_density_pct"] = round((local_artists / total_artists) * 100, 2) if total_artists else 0.0
        return ev


def get_artist_detail(artist_id: int) -> dict | None:
    """Return an artist with events and aliases. Follows alias_of redirect."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_artists WHERE id = ?", (artist_id,)
        ).fetchone()
        if not row:
            return None
        artist = dict(row)
        # If this is an alias, redirect to canonical
        if artist.get("alias_of"):
            artist["redirect_to"] = artist["alias_of"]
            return artist
        artist["city_tags"] = [
            r["tag"]
            for r in conn.execute(
                "SELECT tag FROM cu_artist_tags WHERE artist_id = ? ORDER BY tag",
                (artist_id,),
            ).fetchall()
        ]
        artist["is_yvr_local"] = LOCAL_CITY_TAG in set(artist["city_tags"])
        artist["events"] = [
            dict(r)
            for r in conn.execute(
                """SELECT e.id, e.title, e.date, v.name AS venue_name
                   FROM cu_events e
                   JOIN cu_event_performers ep ON e.id = ep.event_id
                   LEFT JOIN cu_venues v ON e.venue_id = v.id
                   WHERE ep.artist_id = ?
                   ORDER BY e.date DESC""",
                (artist_id,),
            ).fetchall()
        ]
        artist["aliases"] = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name FROM cu_artists WHERE alias_of = ?",
                (artist_id,),
            ).fetchall()
        ]
        return artist


def get_venue_detail(venue_id: int) -> dict | None:
    """Return a venue with events and aliases. Follows alias_of redirect."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not row:
            return None
        venue = dict(row)
        if venue.get("alias_of"):
            venue["redirect_to"] = venue["alias_of"]
            return venue
        venue["events"] = [
            dict(r)
            for r in conn.execute(
                """SELECT e.id, e.title, e.date
                   FROM cu_events e
                   WHERE e.venue_id = ?
                   ORDER BY e.date DESC""",
                (venue_id,),
            ).fetchall()
        ]
        venue["aliases"] = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name FROM cu_venues WHERE alias_of = ?",
                (venue_id,),
            ).fetchall()
        ]
        return venue


# --------------------------------------------------------------------------
# Merge / alias operations
# --------------------------------------------------------------------------

def merge_artists(duplicate_id: int, canonical_id: int) -> dict:
    """Merge a duplicate artist into a canonical one.

    Moves all event_performer links, sets alias_of, returns summary.
    """
    if duplicate_id == canonical_id:
        return {"error": "Cannot merge an artist into itself"}
    with get_db() as conn:
        # Verify both exist
        dup = conn.execute("SELECT id, name FROM cu_artists WHERE id = ?", (duplicate_id,)).fetchone()
        canon = conn.execute("SELECT id, name FROM cu_artists WHERE id = ?", (canonical_id,)).fetchone()
        if not dup or not canon:
            return {"error": "Artist not found"}
        # Move performer links
        conn.execute(
            """UPDATE OR IGNORE cu_event_performers
               SET artist_id = ? WHERE artist_id = ?""",
            (canonical_id, duplicate_id),
        )
        # Remove any leftover duplicate links (from IGNORE)
        conn.execute(
            "DELETE FROM cu_event_performers WHERE artist_id = ?",
            (duplicate_id,),
        )
        # Set alias
        conn.execute(
            "UPDATE cu_artists SET alias_of = ? WHERE id = ?",
            (canonical_id, duplicate_id),
        )
        return {
            "merged": True,
            "duplicate": {"id": dup["id"], "name": dup["name"]},
            "canonical": {"id": canon["id"], "name": canon["name"]},
        }


def merge_venues(duplicate_id: int, canonical_id: int) -> dict:
    """Merge a duplicate venue into a canonical one.

    Moves all event venue references, sets alias_of, returns summary.
    """
    if duplicate_id == canonical_id:
        return {"error": "Cannot merge a venue into itself"}
    with get_db() as conn:
        dup = conn.execute("SELECT id, name FROM cu_venues WHERE id = ?", (duplicate_id,)).fetchone()
        canon = conn.execute("SELECT id, name FROM cu_venues WHERE id = ?", (canonical_id,)).fetchone()
        if not dup or not canon:
            return {"error": "Venue not found"}
        # Move event references
        conn.execute(
            "UPDATE cu_events SET venue_id = ? WHERE venue_id = ?",
            (canonical_id, duplicate_id),
        )
        # Set alias
        conn.execute(
            "UPDATE cu_venues SET alias_of = ? WHERE id = ?",
            (canonical_id, duplicate_id),
        )
        return {
            "merged": True,
            "duplicate": {"id": dup["id"], "name": dup["name"]},
            "canonical": {"id": canon["id"], "name": canon["name"]},
        }


def search_artists_for_merge(query: str, exclude_id: int | None = None) -> list[dict]:
    """Search canonical artists for the merge picker."""
    with get_db() as conn:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT id, name FROM cu_artists
               WHERE alias_of IS NULL AND name LIKE ? AND id != ?
               ORDER BY name LIMIT 20""",
            (like, exclude_id or -1),
        ).fetchall()
        return [dict(r) for r in rows]


def search_venues_for_merge(query: str, exclude_id: int | None = None) -> list[dict]:
    """Search canonical venues for the merge picker."""
    with get_db() as conn:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT id, name FROM cu_venues
               WHERE alias_of IS NULL AND name LIKE ? AND id != ?
               ORDER BY name LIMIT 20""",
            (like, exclude_id or -1),
        ).fetchall()
        return [dict(r) for r in rows]


def merge_events(duplicate_id: int, canonical_id: int) -> dict:
    """Merge a duplicate event into a canonical one."""
    if duplicate_id == canonical_id:
        return {"error": "Cannot merge an event into itself"}
    with get_db() as conn:
        dup = conn.execute(
            "SELECT id, title, date FROM cu_events WHERE id = ?",
            (duplicate_id,),
        ).fetchone()
        canon = conn.execute(
            "SELECT id, title, date FROM cu_events WHERE id = ?",
            (canonical_id,),
        ).fetchone()
        if not dup or not canon:
            return {"error": "Event not found"}
        conn.execute(
            """INSERT OR IGNORE INTO cu_event_performers (event_id, artist_id)
               SELECT ?, artist_id FROM cu_event_performers WHERE event_id = ?""",
            (canonical_id, duplicate_id),
        )
        conn.execute("DELETE FROM cu_event_performers WHERE event_id = ?", (duplicate_id,))
        conn.execute("UPDATE cu_event_sources SET event_id = ? WHERE event_id = ?", (canonical_id, duplicate_id))
        conn.execute("DELETE FROM cu_events WHERE id = ?", (duplicate_id,))
        return {
            "merged": True,
            "duplicate": {"id": dup["id"], "title": dup["title"], "date": dup["date"]},
            "canonical": {"id": canon["id"], "title": canon["title"], "date": canon["date"]},
        }


def _normalize_pair(left_id: int, right_id: int) -> tuple[int, int]:
    left = int(left_id)
    right = int(right_id)
    return (left, right) if left < right else (right, left)


def ignore_duplicate_candidate(entity_type: str, source_key: str, left_id: int, right_id: int) -> dict:
    if entity_type not in {"artist", "event"}:
        return {"error": "Invalid entity_type"}
    a, b = _normalize_pair(left_id, right_id)
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO cu_duplicate_ignores
               (entity_type, source_key, left_id, right_id)
               VALUES (?, ?, ?, ?)""",
            (entity_type, source_key, a, b),
        )
    return {"ok": True, "entity_type": entity_type, "source_key": source_key, "left_id": a, "right_id": b}


def _load_ignored_pairs(entity_type: str, source_key: str) -> set[tuple[int, int]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT left_id, right_id
               FROM cu_duplicate_ignores
               WHERE entity_type = ? AND source_key = ?""",
            (entity_type, source_key),
        ).fetchall()
    return {(int(r["left_id"]), int(r["right_id"])) for r in rows}


def _latest_run_summary(source_key: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            """SELECT raw_summary_json
               FROM cu_ingestion_runs
               WHERE source_key = ?
               ORDER BY started_at DESC
               LIMIT 1""",
            (source_key,),
        ).fetchone()
    if not row:
        return {}
    raw = row["raw_summary_json"]
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def get_duplicate_candidates() -> dict:
    artist_source = "artist_dedupe_janitor"
    event_source = "event_dedupe_janitor"
    artist_ignored = _load_ignored_pairs("artist", artist_source)
    event_ignored = _load_ignored_pairs("event", event_source)

    artist_rows = (_latest_run_summary(artist_source).get("potential_matches") or [])
    event_rows = (_latest_run_summary(event_source).get("potential_matches") or [])

    artists: list[dict] = []
    for row in artist_rows:
        left_id = int(row.get("left_artist_id") or 0)
        right_id = int(row.get("right_artist_id") or 0)
        if left_id <= 0 or right_id <= 0:
            continue
        if _normalize_pair(left_id, right_id) in artist_ignored:
            continue
        artists.append(
            {
                "left_id": left_id,
                "left_name": row.get("left_artist_name") or "",
                "right_id": right_id,
                "right_name": row.get("right_artist_name") or "",
                "title_match_pct": float(row.get("title_match_pct") or 0.0),
            }
        )

    events: list[dict] = []
    for row in event_rows:
        left_id = int(row.get("left_event_id") or 0)
        right_id = int(row.get("right_event_id") or 0)
        if left_id <= 0 or right_id <= 0:
            continue
        if _normalize_pair(left_id, right_id) in event_ignored:
            continue
        events.append(
            {
                "left_id": left_id,
                "left_title": row.get("left_title") or "",
                "right_id": right_id,
                "right_title": row.get("right_title") or "",
                "date": row.get("date"),
                "venue_name": row.get("venue_name") or "",
                "title_match_pct": float(row.get("title_match_pct") or 0.0),
            }
        )

    artists.sort(key=lambda r: r["title_match_pct"], reverse=True)
    events.sort(key=lambda r: r["title_match_pct"], reverse=True)
    return {
        "artists": artists,
        "events": events,
        "artists_count": len(artists),
        "events_count": len(events),
    }


def rescan_duplicate_candidates(kind: str = "all") -> dict:
    kind_norm = (kind or "all").strip().lower()
    if kind_norm == "artists":
        keys = ["artist_dedupe_janitor"]
    elif kind_norm == "events":
        keys = ["event_dedupe_janitor"]
    else:
        keys = ["artist_dedupe_janitor", "event_dedupe_janitor"]
    results = [refresh_source(k) for k in keys]
    return {"kind": kind_norm, "sources_run": len(results), "results": results}
