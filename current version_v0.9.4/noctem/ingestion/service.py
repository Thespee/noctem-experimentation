"""Cor Unum service layer — public API for ingestion operations.

All functions are safe to call from Flask route handlers.
"""
from __future__ import annotations

import math
from datetime import datetime

from ..db import get_db
from .engine import run_ingestion


# --------------------------------------------------------------------------
# Source management
# --------------------------------------------------------------------------

def refresh_source(source_key: str) -> dict:
    """Run the ingestion pipeline for a single source. Returns summary."""
    return run_ingestion(source_key)


def refresh_all_sources() -> dict:
    """Run ingestion for all enabled sources. Returns aggregate summary."""
    sources = get_source_registry()
    results = []
    for src in sources:
        if not src.get("enabled"):
            continue
        result = run_ingestion(src["source_key"])
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


def get_artists(page: int = 1, per_page: int = 50, search: str = "") -> dict:
    """Paginated artists with optional name search."""
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            return _paginate(
                conn,
                "SELECT * FROM cu_artists WHERE name LIKE ? ORDER BY name",
                "SELECT COUNT(*) FROM cu_artists WHERE name LIKE ?",
                (like,), page, per_page,
            )
        return _paginate(
            conn,
            "SELECT * FROM cu_artists ORDER BY name",
            "SELECT COUNT(*) FROM cu_artists",
            (), page, per_page,
        )


def get_venues(page: int = 1, per_page: int = 50, search: str = "") -> dict:
    """Paginated venues with optional name search."""
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            return _paginate(
                conn,
                "SELECT * FROM cu_venues WHERE name LIKE ? ORDER BY name",
                "SELECT COUNT(*) FROM cu_venues WHERE name LIKE ?",
                (like,), page, per_page,
            )
        return _paginate(
            conn,
            "SELECT * FROM cu_venues ORDER BY name",
            "SELECT COUNT(*) FROM cu_venues",
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
    """Return an artist with all their linked events."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_artists WHERE id = ?", (artist_id,)
        ).fetchone()
        if not row:
            return None
        artist = dict(row)
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
        return artist


def get_venue_detail(venue_id: int) -> dict | None:
    """Return a venue with all events held there."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not row:
            return None
        venue = dict(row)
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
        return venue
