"""Ingestion engine: scrape → parse → dedupe → store.

Orchestrates the full pipeline for a single source.
All DB writes happen in a single transaction per source for atomicity.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from ..db import get_db
from .dedup import compute_fingerprint, is_fuzzy_duplicate
from .models import FALLBACK_VENUE_NAME, RawEvent

logger = logging.getLogger(__name__)

# Scraper registry: source_key → scraper class
_SCRAPER_MAP: dict[str, type] | None = None


def _get_scraper_map():
    global _SCRAPER_MAP
    if _SCRAPER_MAP is None:
        from .sources.ticketmaster import TicketmasterScraper
        from .sources.ra import RAScraper
        from .sources.admitone import AdmitOneScraper
        from .sources.eventbrite import EventbriteScraper

        _SCRAPER_MAP = {
            "ticketmaster_vancouver": TicketmasterScraper,
            "ra_vancouver": RAScraper,
            "admitone_vancouver": AdmitOneScraper,
            "eventbrite_vancouver": EventbriteScraper,
        }
    return _SCRAPER_MAP


def get_scraper(source_key: str):
    """Return an instantiated scraper for the given source_key."""
    scraper_map = _get_scraper_map()
    cls = scraper_map.get(source_key)
    if cls is None:
        raise ValueError(f"Unknown source_key: {source_key}")
    return cls()


def run_ingestion(source_key: str) -> dict:
    """Run the full ingestion pipeline for a single source.

    Returns a summary dict with counts and status.
    """
    started_at = datetime.utcnow()
    summary = {
        "source_key": source_key,
        "started_at": started_at.isoformat(),
        "status": "running",
        "events_ingested": 0,
        "artists_added": 0,
        "venues_added": 0,
        "duplicates_skipped": 0,
        "error_message": None,
    }

    try:
        scraper = get_scraper(source_key)
        raw_events = scraper.run()
        logger.info("Source %s returned %d raw events", source_key, len(raw_events))
    except Exception as exc:
        summary["status"] = "error"
        summary["error_message"] = str(exc)[:1000]
        _record_run(summary, started_at)
        _update_source_status(source_key, "error", str(exc)[:500])
        return summary

    # Process raw events in a single transaction
    try:
        with get_db() as conn:
            for raw in raw_events:
                result = _process_one_event(conn, raw, source_key)
                summary["events_ingested"] += result.get("event_created", 0)
                summary["artists_added"] += result.get("artists_created", 0)
                summary["venues_added"] += result.get("venue_created", 0)
                summary["duplicates_skipped"] += result.get("duplicate", 0)
    except Exception as exc:
        summary["status"] = "error"
        summary["error_message"] = str(exc)[:1000]
        _record_run(summary, started_at)
        _update_source_status(source_key, "error", str(exc)[:500])
        return summary

    summary["status"] = "success"
    _record_run(summary, started_at)
    _update_source_status(source_key, "success", None)
    return summary


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _process_one_event(conn, raw: RawEvent, source_key: str) -> dict:
    """Process a single raw event: dedupe, store, link performers.

    Returns a dict of what was created/skipped.
    """
    result = {"event_created": 0, "artists_created": 0, "venue_created": 0, "duplicate": 0}

    fingerprint = compute_fingerprint(raw.title, raw.date)

    # Check exact fingerprint duplicate
    existing_fp = conn.execute(
        "SELECT id, event_id FROM cu_event_sources WHERE source_fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    if existing_fp:
        result["duplicate"] = 1
        return result

    # Get-or-create venue
    venue_name = raw.venue_name.strip() if raw.venue_name else ""
    if not venue_name:
        venue_name = FALLBACK_VENUE_NAME
    venue_id = _get_or_create_venue(conn, venue_name)
    if venue_name != FALLBACK_VENUE_NAME:
        # Check if this was a new venue
        existing_venue = conn.execute(
            "SELECT id FROM cu_venues WHERE name = ? AND id != ?",
            (venue_name, venue_id),
        ).fetchone()
        if not existing_venue:
            result["venue_created"] = 1  # approximation

    # Fuzzy match against existing events on same date
    date_str = raw.date.isoformat()
    same_date_events = conn.execute(
        "SELECT id, title FROM cu_events WHERE date = ?",
        (date_str,),
    ).fetchall()

    matched_event_id = None
    for row in same_date_events:
        if is_fuzzy_duplicate(raw.title, row["title"]):
            matched_event_id = row["id"]
            break

    if matched_event_id:
        # Link as additional source on existing event
        conn.execute(
            """INSERT INTO cu_event_sources
               (event_id, source_type, source_url, source_fingerprint, captured_at)
               VALUES (?, ?, ?, ?, ?)""",
            (matched_event_id, source_key, raw.source_url, fingerprint,
             datetime.utcnow().isoformat()),
        )
    else:
        # Create new event
        cursor = conn.execute(
            "INSERT INTO cu_events (title, date, venue_id, description) VALUES (?, ?, ?, ?)",
            (raw.title, date_str, venue_id, raw.description[:2000] if raw.description else ""),
        )
        new_event_id = cursor.lastrowid
        result["event_created"] = 1

        # Link source
        conn.execute(
            """INSERT INTO cu_event_sources
               (event_id, source_type, source_url, source_fingerprint, captured_at)
               VALUES (?, ?, ?, ?, ?)""",
            (new_event_id, source_key, raw.source_url, fingerprint,
             datetime.utcnow().isoformat()),
        )
        matched_event_id = new_event_id

    # Get-or-create artists and link as performers
    for artist_name in raw.artists:
        artist_name = artist_name.strip()
        if not artist_name:
            continue
        artist_id = _get_or_create_artist(conn, artist_name)
        conn.execute(
            "INSERT OR IGNORE INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
            (matched_event_id, artist_id),
        )
        result["artists_created"] += 1  # rough count; includes existing

    return result


def _get_or_create_venue(conn, name: str) -> int:
    """Return venue ID, creating if necessary."""
    row = conn.execute("SELECT id FROM cu_venues WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute("INSERT INTO cu_venues (name) VALUES (?)", (name,))
    return cursor.lastrowid


def _get_or_create_artist(conn, name: str) -> int:
    """Return artist ID, creating if necessary."""
    row = conn.execute("SELECT id FROM cu_artists WHERE name = ?", (name,)).fetchone()
    if row:
        conn.execute(
            "UPDATE cu_artists SET last_seen = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO cu_artists (name, last_seen) VALUES (?, ?)",
        (name, datetime.utcnow().isoformat()),
    )
    return cursor.lastrowid


def _record_run(summary: dict, started_at: datetime) -> None:
    """Write a cu_ingestion_runs record."""
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO cu_ingestion_runs
                   (source_key, started_at, finished_at, status,
                    events_ingested, artists_added, venues_added,
                    duplicates_skipped, error_message, raw_summary_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary["source_key"],
                    started_at.isoformat(),
                    datetime.utcnow().isoformat(),
                    summary["status"],
                    summary["events_ingested"],
                    summary["artists_added"],
                    summary["venues_added"],
                    summary["duplicates_skipped"],
                    summary.get("error_message"),
                    json.dumps(summary),
                ),
            )
    except Exception as exc:
        logger.error("Failed to record ingestion run: %s", exc)


def _update_source_status(source_key: str, status: str, error: str | None) -> None:
    """Update cu_source_registry with latest run status."""
    try:
        with get_db() as conn:
            conn.execute(
                """UPDATE cu_source_registry
                   SET last_run_at = ?, last_status = ?, last_error = ?,
                       needs_fixing = ?
                   WHERE source_key = ?""",
                (
                    datetime.utcnow().isoformat(),
                    status,
                    error,
                    1 if status == "error" else 0,
                    source_key,
                ),
            )
    except Exception as exc:
        logger.error("Failed to update source status for %s: %s", source_key, exc)
