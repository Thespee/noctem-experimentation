"""Ingestion engine: scanner dispatch + event processing."""
from __future__ import annotations

import logging
from datetime import datetime

from ..db import get_db
from .dedup import compute_fingerprint, is_fuzzy_duplicate
from .models import FALLBACK_VENUE_NAME
from .scanner_impl import (
    ArtistDedupeJanitorScanner,
    ArtistFingerprintScanner,
    EventDedupeJanitorScanner,
    EventScraperScanner,
)
from .scanners import record_run as _record_run_impl
from .scanners import update_source_status as _update_source_status_impl

logger = logging.getLogger(__name__)

SCANNER_CLASS_EVENTS = "event"
SCANNER_CLASS_FINGERPRINT = "fingerprint"
SCANNER_CLASS_INTERNAL = "internal"
PIPELINE_ORDER = [
    SCANNER_CLASS_EVENTS,
    SCANNER_CLASS_FINGERPRINT,
    SCANNER_CLASS_INTERNAL,
]

_SCANNER_FACTORIES: dict[str, callable] | None = None


def _build_scanner_factories() -> dict[str, callable]:
    from .instagram import check_instagram_fingerprints
    from .soundcloud import check_all_unchecked_artists
    from .sources.admitone import AdmitOneScraper
    from .sources.eventbrite import EventbriteScraper
    from .sources.ra import RAScraper
    from .sources.ticketmaster import TicketmasterScraper
    from .spotify import check_spotify_fingerprints

    return {
        "ticketmaster_vancouver": lambda: EventScraperScanner(
            "ticketmaster_vancouver",
            TicketmasterScraper,
            _process_one_event,
        ),
        "ra_vancouver": lambda: EventScraperScanner(
            "ra_vancouver",
            RAScraper,
            _process_one_event,
        ),
        "admitone_vancouver": lambda: EventScraperScanner(
            "admitone_vancouver",
            AdmitOneScraper,
            _process_one_event,
        ),
        "eventbrite_vancouver": lambda: EventScraperScanner(
            "eventbrite_vancouver",
            EventbriteScraper,
            _process_one_event,
        ),
        "soundcloud": lambda: ArtistFingerprintScanner(
            "soundcloud",
            lambda: check_all_unchecked_artists(limit=120, recheck_all=False),
        ),
        "spotify": lambda: ArtistFingerprintScanner(
            "spotify",
            lambda: check_spotify_fingerprints(limit=20),
        ),
        "instagram": lambda: ArtistFingerprintScanner(
            "instagram",
            lambda: check_instagram_fingerprints(limit=20),
        ),
        "artist_dedupe_janitor": lambda: ArtistDedupeJanitorScanner(),
        "event_dedupe_janitor": lambda: EventDedupeJanitorScanner(),
    }


def _get_scanner_factories() -> dict[str, callable]:
    global _SCANNER_FACTORIES
    if _SCANNER_FACTORIES is None:
        _SCANNER_FACTORIES = _build_scanner_factories()
    return _SCANNER_FACTORIES


def get_scanner(source_key: str):
    factory = _get_scanner_factories().get(source_key)
    if factory is None:
        raise ValueError(f"Unknown source_key: {source_key}")
    return factory()


def run_ingestion(source_key: str) -> dict:
    scanner = get_scanner(source_key)
    return scanner.execute()


def run_social_ingestion(source_key: str) -> dict:
    """Backward-compat shim; social scanners are now fingerprint scanners."""
    return run_ingestion(source_key)


def is_social_source(source_key: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT source_kind FROM cu_source_registry WHERE source_key = ?",
            (source_key,),
        ).fetchone()
    return bool(row and row["source_kind"] == SCANNER_CLASS_FINGERPRINT)


def run_sources_by_class(scanner_class: str) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT source_key
               FROM cu_source_registry
               WHERE enabled = 1 AND source_kind = ?
               ORDER BY source_key""",
            (scanner_class,),
        ).fetchall()
    results = [run_ingestion(r["source_key"]) for r in rows]
    return {
        "scanner_class": scanner_class,
        "sources_run": len(results),
        "results": results,
        "total_events_ingested": sum(r.get("events_ingested", 0) for r in results),
        "total_duplicates_skipped": sum(r.get("duplicates_skipped", 0) for r in results),
        "errors": [r for r in results if r.get("status") == "error"],
    }


def run_full_pipeline() -> dict:
    class_results = [run_sources_by_class(scanner_class) for scanner_class in PIPELINE_ORDER]
    all_results = []
    for cls in class_results:
        all_results.extend(cls.get("results", []))
    return {
        "pipeline_order": PIPELINE_ORDER,
        "class_results": class_results,
        "sources_run": sum(c.get("sources_run", 0) for c in class_results),
        "results": all_results,
        "total_events_ingested": sum(r.get("events_ingested", 0) for r in all_results),
        "total_duplicates_skipped": sum(r.get("duplicates_skipped", 0) for r in all_results),
        "errors": [r for r in all_results if r.get("status") == "error"],
    }


def _process_one_event(conn, raw, source_key: str) -> dict:
    """Process a single raw event with source-scoped dedupe."""
    result = {
        "event_created": 0,
        "artists_created": 0,
        "venue_created": 0,
        "duplicate": 0,
        "updated": 0,
    }

    fingerprint = compute_fingerprint(raw.title, raw.date)

    # Source-scoped exact fingerprint duplicate
    existing_fp = conn.execute(
        """SELECT id, event_id
           FROM cu_event_sources
           WHERE source_fingerprint = ? AND source_type = ?""",
        (fingerprint, source_key),
    ).fetchone()
    if existing_fp:
        event_id = existing_fp["event_id"]
        _update_event_if_better(conn, event_id, raw)
        _link_performers(conn, event_id, raw.artists)
        result["duplicate"] = 1
        result["updated"] = 1
        return result

    venue_name = raw.venue_name.strip() if raw.venue_name else ""
    if not venue_name:
        venue_name = FALLBACK_VENUE_NAME
    venue_id = _get_or_create_venue(conn, venue_name)
    if venue_name != FALLBACK_VENUE_NAME:
        existing_venue = conn.execute(
            "SELECT id FROM cu_venues WHERE name = ? AND id != ?",
            (venue_name, venue_id),
        ).fetchone()
        if not existing_venue:
            result["venue_created"] = 1

    # Source-scoped fuzzy duplicate candidates (same date among this source only)
    date_str = raw.date.isoformat()
    same_date_events = conn.execute(
        """SELECT e.id, e.title
           FROM cu_events e
           JOIN cu_event_sources es ON es.event_id = e.id
           WHERE e.date = ? AND es.source_type = ?
           GROUP BY e.id, e.title""",
        (date_str, source_key),
    ).fetchall()

    matched_event_id = None
    for row in same_date_events:
        if is_fuzzy_duplicate(raw.title, row["title"]):
            matched_event_id = row["id"]
            break

    if matched_event_id:
        conn.execute(
            """INSERT INTO cu_event_sources
               (event_id, source_type, source_url, source_fingerprint, captured_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                matched_event_id,
                source_key,
                raw.source_url,
                fingerprint,
                datetime.utcnow().isoformat(),
            ),
        )
        _update_event_if_better(conn, matched_event_id, raw)
        result["duplicate"] = 1
    else:
        cursor = conn.execute(
            "INSERT INTO cu_events (title, date, venue_id, description) VALUES (?, ?, ?, ?)",
            (
                raw.title,
                date_str,
                venue_id,
                raw.description[:2000] if raw.description else "",
            ),
        )
        new_event_id = cursor.lastrowid
        result["event_created"] = 1
        conn.execute(
            """INSERT INTO cu_event_sources
               (event_id, source_type, source_url, source_fingerprint, captured_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                new_event_id,
                source_key,
                raw.source_url,
                fingerprint,
                datetime.utcnow().isoformat(),
            ),
        )
        matched_event_id = new_event_id

    result["artists_created"] = _link_performers(conn, matched_event_id, raw.artists)
    return result


def _update_event_if_better(conn, event_id: int, raw) -> None:
    if not raw.description:
        return
    existing = conn.execute(
        "SELECT description FROM cu_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    old_desc = (existing["description"] or "") if existing else ""
    if len(raw.description.strip()) > len(old_desc.strip()):
        conn.execute(
            "UPDATE cu_events SET description = ? WHERE id = ?",
            (raw.description[:2000], event_id),
        )


def _link_performers(conn, event_id: int, artist_names: list[str]) -> int:
    count = 0
    for artist_name in artist_names:
        artist_name = artist_name.strip()
        if not artist_name:
            continue
        artist_id = _get_or_create_artist(conn, artist_name)
        conn.execute(
            "INSERT OR IGNORE INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
            (event_id, artist_id),
        )
        count += 1
    return count


def _get_or_create_venue(conn, name: str) -> int:
    row = conn.execute(
        "SELECT id, alias_of FROM cu_venues WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return row["alias_of"] or row["id"]
    cursor = conn.execute("INSERT INTO cu_venues (name) VALUES (?)", (name,))
    return cursor.lastrowid


def _get_or_create_artist(conn, name: str) -> int:
    row = conn.execute(
        "SELECT id, alias_of FROM cu_artists WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        canonical_id = row["alias_of"] or row["id"]
        conn.execute(
            "UPDATE cu_artists SET last_seen = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), canonical_id),
        )
        return canonical_id
    cursor = conn.execute(
        "INSERT INTO cu_artists (name, last_seen) VALUES (?, ?)",
        (name, datetime.utcnow().isoformat()),
    )
    return cursor.lastrowid


def _record_run(summary: dict, started_at: datetime) -> None:
    """Backward-compatible wrapper for tests."""
    _record_run_impl(summary, started_at)


def _update_source_status(source_key: str, status: str, error: str | None) -> None:
    """Backward-compatible wrapper."""
    _update_source_status_impl(source_key, status, error)