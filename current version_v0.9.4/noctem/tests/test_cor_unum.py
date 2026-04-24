"""Tests for the Cor Unum live music ingestion system.

Covers: schema creation, seeding, dedup, idempotency, fallback venue,
service layer, API endpoints, and run summary recording.
"""
from datetime import date, datetime

import pytest

from .. import db
from ..ingestion.dedup import compute_fingerprint, fuzzy_match_title, is_fuzzy_duplicate
from ..ingestion.models import FALLBACK_VENUE_NAME, RawEvent
from ..ingestion.engine import _process_one_event, _get_or_create_venue, _get_or_create_artist


# =========================================================================
# Schema & seed tests
# =========================================================================

class TestSchema:
    def test_cu_tables_exist(self):
        """All cu_ tables are created by init_db."""
        with db.get_db() as conn:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cu_%'"
                ).fetchall()
            ]
        expected = {
            "cu_venues", "cu_artists", "cu_events", "cu_event_performers",
            "cu_event_sources", "cu_source_registry", "cu_ingestion_runs",
        }
        assert expected.issubset(set(tables))

    def test_cu_indexes_exist(self):
        with db.get_db() as conn:
            indexes = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_cu_%'"
                ).fetchall()
            ]
        assert len(indexes) >= 5

    def test_seed_sources(self):
        """5 source registry rows seeded on init (4 event + 1 social)."""
        with db.get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM cu_source_registry").fetchone()[0]
        assert count == 5

    def test_seed_fallback_venue(self):
        """'Out in the Wild' venue exists."""
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM cu_venues WHERE name = ?", (FALLBACK_VENUE_NAME,)
            ).fetchone()
        assert row is not None
        assert row["is_verified"] == 1

    def test_migration_idempotent(self):
        """Running init_db twice doesn't break anything."""
        db.init_db()
        with db.get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM cu_source_registry").fetchone()[0]
        assert count == 5  # no duplicates


# =========================================================================
# Dedup tests
# =========================================================================

class TestDedup:
    def test_fingerprint_deterministic(self):
        fp1 = compute_fingerprint("Test Event", date(2026, 5, 1))
        fp2 = compute_fingerprint("Test Event", date(2026, 5, 1))
        assert fp1 == fp2

    def test_fingerprint_case_insensitive(self):
        fp1 = compute_fingerprint("Test Event", date(2026, 5, 1))
        fp2 = compute_fingerprint("TEST EVENT", date(2026, 5, 1))
        assert fp1 == fp2

    def test_fingerprint_different_dates(self):
        fp1 = compute_fingerprint("Test Event", date(2026, 5, 1))
        fp2 = compute_fingerprint("Test Event", date(2026, 5, 2))
        assert fp1 != fp2

    def test_fuzzy_match_similar(self):
        score = fuzzy_match_title(
            "DJ Snake Live at Commodore",
            "DJ Snake - Live at Commodore Ballroom",
        )
        assert score > 70

    def test_fuzzy_match_identical(self):
        assert is_fuzzy_duplicate("Concert Night", "Concert Night")

    def test_fuzzy_match_different(self):
        assert not is_fuzzy_duplicate("Jazz at the Park", "Heavy Metal Bash")


# =========================================================================
# Engine / idempotency tests
# =========================================================================

class TestEngine:
    def _make_raw(self, title="Test Show", event_date=None, venue="The Roxy",
                  artists=None, source_url="https://example.com/event/1"):
        return RawEvent(
            title=title,
            date=event_date or date(2026, 6, 15),
            venue_name=venue,
            artists=artists or [],
            source_url=source_url,
        )

    def test_first_ingest_creates_event(self):
        raw = self._make_raw()
        with db.get_db() as conn:
            result = _process_one_event(conn, raw, "test_source")
        assert result["event_created"] == 1
        assert result["duplicate"] == 0

    def test_same_fingerprint_skipped(self):
        raw = self._make_raw()
        with db.get_db() as conn:
            _process_one_event(conn, raw, "test_source")
            result2 = _process_one_event(conn, raw, "test_source")
        assert result2["duplicate"] == 1
        assert result2["event_created"] == 0

    def test_idempotent_rerun(self):
        """Processing the same batch twice produces no new events."""
        batch = [self._make_raw(title=f"Show {i}") for i in range(3)]
        with db.get_db() as conn:
            for raw in batch:
                _process_one_event(conn, raw, "source_a")
            count_after_first = conn.execute("SELECT COUNT(*) FROM cu_events").fetchone()[0]

            for raw in batch:
                _process_one_event(conn, raw, "source_a")
            count_after_second = conn.execute("SELECT COUNT(*) FROM cu_events").fetchone()[0]

        assert count_after_first == 3
        assert count_after_second == 3

    def test_same_event_different_source_links(self):
        """Same event from two sources creates one event + two event_sources."""
        raw1 = self._make_raw(title="Big Concert at The Roxy Venue", source_url="https://tm.com/1")
        raw2 = RawEvent(
            title="Big Concert at The Roxy",  # fuzzy-similar (score ~88) but different fingerprint
            date=date(2026, 6, 15),
            venue_name="The Roxy",
            source_url="https://eb.com/1",
        )
        with db.get_db() as conn:
            _process_one_event(conn, raw1, "ticketmaster")
            _process_one_event(conn, raw2, "eventbrite")

            event_count = conn.execute("SELECT COUNT(*) FROM cu_events").fetchone()[0]
            source_count = conn.execute("SELECT COUNT(*) FROM cu_event_sources").fetchone()[0]

        # "Big Concert" and "Big Concert!" should fuzzy-match → 1 event, 2 sources
        assert event_count == 1
        assert source_count == 2

    def test_fallback_venue_used_when_empty(self):
        raw = self._make_raw(venue="")
        with db.get_db() as conn:
            _process_one_event(conn, raw, "test_source")
            event = conn.execute("SELECT venue_id FROM cu_events ORDER BY id DESC LIMIT 1").fetchone()
            venue = conn.execute("SELECT name FROM cu_venues WHERE id = ?", (event["venue_id"],)).fetchone()
        assert venue["name"] == FALLBACK_VENUE_NAME

    def test_artists_linked(self):
        raw = self._make_raw(artists=["DJ Alpha", "MC Beta"])
        with db.get_db() as conn:
            _process_one_event(conn, raw, "test_source")
            performers = conn.execute(
                "SELECT COUNT(*) FROM cu_event_performers"
            ).fetchone()[0]
        assert performers == 2

    def test_no_duplicate_artists_on_rerun(self):
        """Re-ingesting same artist names doesn't create duplicates."""
        raw = self._make_raw(title="Show A", artists=["DJ Alpha"])
        raw2 = self._make_raw(title="Show B", artists=["DJ Alpha"])
        with db.get_db() as conn:
            _process_one_event(conn, raw, "source_a")
            _process_one_event(conn, raw2, "source_a")
            artist_count = conn.execute("SELECT COUNT(*) FROM cu_artists WHERE name = 'DJ Alpha'").fetchone()[0]
        assert artist_count == 1


# =========================================================================
# Service layer tests
# =========================================================================

class TestService:
    def test_get_source_registry(self):
        from ..ingestion.service import get_source_registry
        sources = get_source_registry()
        assert len(sources) == 5
        keys = {s["source_key"] for s in sources}
        assert "ticketmaster_vancouver" in keys
        assert "soundcloud" in keys

    def test_set_source_enabled(self):
        from ..ingestion.service import set_source_enabled, get_source_status
        set_source_enabled("ticketmaster_vancouver", False)
        status = get_source_status("ticketmaster_vancouver")
        assert status["enabled"] == 0

        set_source_enabled("ticketmaster_vancouver", True)
        status = get_source_status("ticketmaster_vancouver")
        assert status["enabled"] == 1

    def test_clear_source_error(self):
        from ..ingestion.service import clear_source_error
        with db.get_db() as conn:
            conn.execute(
                "UPDATE cu_source_registry SET needs_fixing = 1, last_error = 'test error' WHERE source_key = 'ra_vancouver'"
            )
        result = clear_source_error("ra_vancouver")
        assert result["needs_fixing"] == 0
        assert result["last_error"] is None

    def test_paginated_events(self):
        from ..ingestion.service import get_events
        result = get_events(page=1, per_page=10)
        assert "items" in result
        assert "total" in result
        assert "page" in result

    def test_paginated_artists(self):
        from ..ingestion.service import get_artists
        result = get_artists(page=1, per_page=10)
        assert "items" in result

    def test_paginated_venues(self):
        from ..ingestion.service import get_venues
        result = get_venues(page=1, per_page=10)
        assert "items" in result
        # Fallback venue should be present
        assert result["total"] >= 1

    def test_run_summary_empty(self):
        from ..ingestion.service import get_run_summary
        runs = get_run_summary(limit=10)
        assert isinstance(runs, list)


# =========================================================================
# API endpoint tests
# =========================================================================

class TestAPI:
    @pytest.fixture
    def client(self):
        from ..web.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_cor_unum_page_renders(self, client):
        r = client.get("/cor-unum")
        assert r.status_code == 200
        assert b"Cor Unum" in r.data

    def test_api_sources(self, client):
        r = client.get("/api/cor-unum/sources")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]
        assert len(data["sources"]) == 5

    def test_api_runs(self, client):
        r = client.get("/api/cor-unum/runs")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]

    def test_api_events(self, client):
        r = client.get("/api/cor-unum/events")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]
        assert "items" in data

    def test_api_artists(self, client):
        r = client.get("/api/cor-unum/artists")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_api_venues(self, client):
        r = client.get("/api/cor-unum/venues")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_api_event_sources(self, client):
        r = client.get("/api/cor-unum/event-sources")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_api_source_registry(self, client):
        r = client.get("/api/cor-unum/source-registry")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_api_toggle_enabled(self, client):
        r = client.patch(
            "/api/cor-unum/sources/ticketmaster_vancouver/enabled",
            json={"enabled": False},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]
        assert data["source"]["enabled"] == 0

    def test_api_clear_error(self, client):
        r = client.patch("/api/cor-unum/sources/ra_vancouver/clear-error")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_db_subpages_render(self, client):
        for path in [
            "/cor-unum/db/events",
            "/cor-unum/db/artists",
            "/cor-unum/db/venues",
            "/cor-unum/db/event-sources",
            "/cor-unum/db/source-registry",
        ]:
            r = client.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"


# =========================================================================
# Run summary tests
# =========================================================================

class TestRunSummary:
    def test_run_recorded_after_engine(self):
        """Ingestion runs are recorded in cu_ingestion_runs."""
        from ..ingestion.engine import _record_run

        summary = {
            "source_key": "test_source",
            "status": "success",
            "events_ingested": 5,
            "artists_added": 3,
            "venues_added": 1,
            "duplicates_skipped": 2,
            "error_message": None,
        }
        _record_run(summary, datetime.utcnow())

        from ..ingestion.service import get_run_summary
        runs = get_run_summary(source_key="test_source")
        assert len(runs) >= 1
        latest = runs[0]
        assert latest["source_key"] == "test_source"
        assert latest["events_ingested"] == 5
