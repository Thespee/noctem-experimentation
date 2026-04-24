"""Cor Unum service layer — public API for ingestion operations.

All functions are safe to call from Flask route handlers.
"""
from __future__ import annotations

import math
from datetime import datetime

from ..db import get_db
from .engine import is_social_source, run_ingestion, run_social_ingestion


# --------------------------------------------------------------------------
# Source management
# --------------------------------------------------------------------------

def refresh_source(source_key: str) -> dict:
    """Run the ingestion pipeline for a single source. Returns summary."""
    if is_social_source(source_key):
        return run_social_ingestion(source_key)
    return run_ingestion(source_key)


def refresh_all_sources() -> dict:
    """Run ingestion for all enabled sources. Returns aggregate summary."""
    sources = get_source_registry()
    results = []
    for src in sources:
        if not src.get("enabled"):
            continue
        result = refresh_source(src["source_key"])
        results.append(result)
    return {
        "sources_run": len(results),
        "results": results,
        "total_events_ingested": sum(r.get("events_ingested", 0) for r in results),
        "total_duplicates_skipped": sum(r.get("duplicates_skipped", 0) for r in results),
        "errors": [r for r in results if r.get("status") == "error"],
    }


def get_source_registry() -> list[dict]:
    """Return all source registry rows."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM cu_source_registry ORDER BY source_key"
        ).fetchall()
        return [dict(r) for r in rows]


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
        conditions.append("is_local = 1")
    elif local == "not_local":
        conditions.append("is_local = 0")
    elif local == "unchecked":
        conditions.append("is_local IS NULL")
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
                    """SELECT a.id, a.name FROM cu_artists a
                       JOIN cu_event_performers ep ON a.id = ep.artist_id
                       WHERE ep.event_id = ?""",
                    (eid,),
                ).fetchall()
            ]
            ev["sources"] = [
                dict(s)
                for s in conn.execute(
                    "SELECT source_type, source_url FROM cu_event_sources WHERE event_id = ?",
                    (eid,),
                ).fetchall()
            ]
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
                """SELECT a.id, a.name, a.bio_link FROM cu_artists a
                   JOIN cu_event_performers ep ON a.id = ep.artist_id
                   WHERE ep.event_id = ?""",
                (event_id,),
            ).fetchall()
        ]
        ev["sources"] = [
            dict(s)
            for s in conn.execute(
                "SELECT * FROM cu_event_sources WHERE event_id = ?",
                (event_id,),
            ).fetchall()
        ]
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
