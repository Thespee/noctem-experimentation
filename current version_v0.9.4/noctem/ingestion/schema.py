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

-- Cor Unum: Favorites stub
CREATE TABLE IF NOT EXISTS cu_favorites (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL REFERENCES cu_events(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id)
);

-- Cor Unum: Artists
CREATE TABLE IF NOT EXISTS cu_artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    bio_link TEXT,
    spotify_url TEXT,
    last_seen TIMESTAMP,
    is_canadian INTEGER,
    canadian INTEGER NOT NULL DEFAULT 0,
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

-- Cor Unum: Artist tags (city tags, e.g., YVR)
CREATE TABLE IF NOT EXISTS cu_artist_tags (
    id INTEGER PRIMARY KEY,
    artist_id INTEGER NOT NULL REFERENCES cu_artists(id),
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(artist_id, tag)
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
-- Cor Unum: trusted member identities linked to artists
CREATE TABLE IF NOT EXISTS cu_members (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    artist_id INTEGER REFERENCES cu_artists(id),
    role TEXT NOT NULL DEFAULT 'member'
        CHECK(role IN ('member', 'admin')),
    is_active INTEGER DEFAULT 1,
    created_by TEXT,
    claimed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Cor Unum: public detail suggestions moderation queue
CREATE TABLE IF NOT EXISTS cu_suggestions (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL
        CHECK(entity_type IN ('event', 'artist')),
    entity_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'accepted', 'rejected')),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_by TEXT,
    submitted_role TEXT,
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    decision_notes TEXT,
    applied_event_id TEXT
);
-- Cor Unum: ignored duplicate candidates (suppresses resurfacing on rescan)
CREATE TABLE IF NOT EXISTS cu_duplicate_ignores (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL, -- artist | event
    source_key TEXT NOT NULL,  -- artist_dedupe_janitor | event_dedupe_janitor
    left_id INTEGER NOT NULL,
    right_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, source_key, left_id, right_id)
);
-- Cor Unum: auto-discovered artist social link candidates (manual review queue)
CREATE TABLE IF NOT EXISTS cu_artist_link_candidates (
    id INTEGER PRIMARY KEY,
    artist_id INTEGER NOT NULL REFERENCES cu_artists(id),
    source_key TEXT NOT NULL, -- instagram | spotify
    candidate_url TEXT NOT NULL,
    confidence_score REAL DEFAULT 0,
    evidence_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_action TEXT,
    UNIQUE(artist_id, source_key, candidate_url)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cu_events_date ON cu_events(date);
CREATE INDEX IF NOT EXISTS idx_cu_events_venue ON cu_events(venue_id);
CREATE INDEX IF NOT EXISTS idx_cu_event_sources_event ON cu_event_sources(event_id);
CREATE INDEX IF NOT EXISTS idx_cu_event_sources_fingerprint ON cu_event_sources(source_fingerprint);
CREATE INDEX IF NOT EXISTS idx_cu_source_registry_key ON cu_source_registry(source_key);
CREATE INDEX IF NOT EXISTS idx_cu_ingestion_runs_source ON cu_ingestion_runs(source_key, started_at);
CREATE INDEX IF NOT EXISTS idx_cu_artist_tags_artist ON cu_artist_tags(artist_id);
CREATE INDEX IF NOT EXISTS idx_cu_artist_tags_tag ON cu_artist_tags(tag);
CREATE INDEX IF NOT EXISTS idx_cu_duplicate_ignores_lookup
    ON cu_duplicate_ignores(entity_type, source_key, left_id, right_id);
CREATE INDEX IF NOT EXISTS idx_cu_artist_link_candidates_lookup
    ON cu_artist_link_candidates(artist_id, source_key, status, confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_cu_members_artist
    ON cu_members(artist_id, is_active);
CREATE INDEX IF NOT EXISTS idx_cu_suggestions_status
    ON cu_suggestions(status, submitted_at);
CREATE INDEX IF NOT EXISTS idx_cu_suggestions_entity
    ON cu_suggestions(entity_type, entity_id, submitted_at);
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
        ("cu_artists", "is_local", "INTEGER"),  # nullable: NULL=unchecked, 0=no, 1=yes
        ("cu_artists", "soundcloud_url", "TEXT"),
        ("cu_artists", "sc_followers", "INTEGER"),  # follower count from SoundCloud
        ("cu_artists", "instagram_url", "TEXT"),
        ("cu_artists", "spotify_url", "TEXT"),
        ("cu_artists", "is_canadian", "INTEGER"),
        ("cu_artists", "instagram_checked_at", "TIMESTAMP"),
        ("cu_artists", "spotify_checked_at", "TIMESTAMP"),
        ("cu_artists", "instagram_last_discovery_attempt_at", "TIMESTAMP"),
        ("cu_artists", "spotify_last_discovery_attempt_at", "TIMESTAMP"),
        ("cu_artists", "instagram_discovery_error", "TEXT"),
        ("cu_artists", "spotify_discovery_error", "TEXT"),
        ("cu_artists", "canadian", "INTEGER NOT NULL DEFAULT 0"),
        ("cu_members", "claimed_at", "TIMESTAMP"),
    ]
    for table, column, col_type in migrations:
        try:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if column not in cols:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {col_type}')
        except Exception:
            pass
    _migrate_local_flag_to_city_tags(conn)
    _backfill_canadian(conn)


def _migrate_local_flag_to_city_tags(conn) -> None:
    """Migrate legacy is_local=1 values to city tag YVR."""
    try:
        conn.execute(
            """INSERT OR IGNORE INTO cu_artist_tags (artist_id, tag)
               SELECT id, 'YVR'
               FROM cu_artists
               WHERE is_local = 1"""
        )
    except Exception:
        pass


def _backfill_canadian(conn) -> None:
    """Normalize canadian/is_canadian values and infer canadian from YVR tags."""
    try:
        conn.execute(
            """UPDATE cu_artists
               SET canadian = COALESCE(canadian, is_canadian, 0)"""
        )
        conn.execute(
            """UPDATE cu_artists
               SET canadian = 1
               WHERE id IN (
                   SELECT artist_id
                   FROM cu_artist_tags
                   WHERE tag = 'YVR'
               )"""
        )
        conn.execute(
            """UPDATE cu_artists
               SET canadian = 0
               WHERE canadian IS NULL"""
        )
        conn.execute(
            """UPDATE cu_artists
               SET is_canadian = canadian
               WHERE is_canadian IS NULL OR is_canadian != canadian"""
        )
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
        conn.execute(
            """UPDATE cu_source_registry
               SET source_label = ?, source_kind = ?, target_url = ?
               WHERE source_key = ?""",
            (src["source_label"], src["source_kind"], src["target_url"], src["source_key"]),
        )

    # Remove stale source keys that no longer exist in seeds
    valid_keys = {s["source_key"] for s in SOURCE_REGISTRY_SEEDS}
    existing = [r[0] for r in conn.execute(
        "SELECT source_key FROM cu_source_registry"
    ).fetchall()]
    for key in existing:
        if key not in valid_keys:
            conn.execute(
                "DELETE FROM cu_source_registry WHERE source_key = ?", (key,)
            )
