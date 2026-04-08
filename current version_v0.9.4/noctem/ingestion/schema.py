"""Additive schema definitions for Cor Unum ingestion tables.

All tables are prefixed `cu_` to avoid collisions with existing Noctem tables
(especially the wiki `sources` table).
"""
from __future__ import annotations


CU_SCHEMA = """
-- Cor Unum: Venues
CREATE TABLE IF NOT EXISTS cu_venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    address TEXT,
    url TEXT,
    is_verified INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cor Unum: Artists
CREATE TABLE IF NOT EXISTS cu_artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    bio_link TEXT,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cor Unum: Events
CREATE TABLE IF NOT EXISTS cu_events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    date DATE NOT NULL,
    venue_id INTEGER REFERENCES cu_venues(id),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cor Unum: Event ↔ Artist link
CREATE TABLE IF NOT EXISTS cu_event_performers (
    event_id INTEGER NOT NULL REFERENCES cu_events(id),
    artist_id INTEGER NOT NULL REFERENCES cu_artists(id),
    UNIQUE(event_id, artist_id)
);

-- Cor Unum: Event provenance / source evidence
CREATE TABLE IF NOT EXISTS cu_event_sources (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES cu_events(id),
    source_type TEXT,
    source_url TEXT,
    raw_capture_path TEXT,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_fingerprint TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cor Unum: Source registry (control plane for scrapers)
CREATE TABLE IF NOT EXISTS cu_source_registry (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    source_label TEXT,
    source_kind TEXT,
    target_url TEXT,
    enabled INTEGER DEFAULT 1,
    last_run_at TIMESTAMP,
    last_status TEXT,
    last_error TEXT,
    needs_fixing INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cor Unum: Ingestion run log
CREATE TABLE IF NOT EXISTS cu_ingestion_runs (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT DEFAULT 'running',
    events_ingested INTEGER DEFAULT 0,
    artists_added INTEGER DEFAULT 0,
    venues_added INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    error_message TEXT,
    raw_summary_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cu_events_date ON cu_events(date);
CREATE INDEX IF NOT EXISTS idx_cu_events_venue ON cu_events(venue_id);
CREATE INDEX IF NOT EXISTS idx_cu_event_sources_event ON cu_event_sources(event_id);
CREATE INDEX IF NOT EXISTS idx_cu_event_sources_fingerprint ON cu_event_sources(source_fingerprint);
CREATE INDEX IF NOT EXISTS idx_cu_source_registry_key ON cu_source_registry(source_key);
CREATE INDEX IF NOT EXISTS idx_cu_ingestion_runs_source ON cu_ingestion_runs(source_key, started_at);
"""


def init_cu_schema(conn) -> None:
    """Create Cor Unum tables (idempotent).

    Call this from db.init_db() after the main schema is applied.
    """
    conn.executescript(CU_SCHEMA)
    _migrate_cu_columns(conn)


def _migrate_cu_columns(conn) -> None:
    """Add columns to existing cu_ tables (safe to run repeatedly)."""
    migrations = [
        ("cu_artists", "alias_of", "INTEGER REFERENCES cu_artists(id)"),
        ("cu_venues", "alias_of", "INTEGER REFERENCES cu_venues(id)"),
    ]
    for table, column, col_type in migrations:
        try:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if column not in cols:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {col_type}')
        except Exception:
            pass


def seed_cu_data(conn) -> None:
    """Seed initial source registry rows and the fallback venue.

    Safe to call repeatedly — uses INSERT OR IGNORE.
    """
    from .models import FALLBACK_VENUE_NAME, SOURCE_REGISTRY_SEEDS

    # Fallback venue
    conn.execute(
        "INSERT OR IGNORE INTO cu_venues (name, is_verified) VALUES (?, 1)",
        (FALLBACK_VENUE_NAME,),
    )

    # Source registry seeds
    for src in SOURCE_REGISTRY_SEEDS:
        conn.execute(
            """INSERT OR IGNORE INTO cu_source_registry
               (source_key, source_label, source_kind, target_url, enabled)
               VALUES (?, ?, ?, ?, 1)""",
            (src["source_key"], src["source_label"], src["source_kind"], src["target_url"]),
        )
