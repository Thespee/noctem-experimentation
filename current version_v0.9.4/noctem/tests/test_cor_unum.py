"""Tests for the Cor Unum live music ingestion system.

Covers: schema creation, seeding, dedup, idempotency, fallback venue,
service layer, API endpoints, and run summary recording.
"""
from datetime import date, datetime

import pytest

from .. import db
from ..ingestion.dedup import compute_fingerprint, fuzzy_match_title, is_fuzzy_duplicate
from ..ingestion.models import FALLBACK_VENUE_NAME, RawEvent, SOURCE_REGISTRY_SEEDS
from ..ingestion.engine import _process_one_event, _get_or_create_venue, _get_or_create_artist
EXPECTED_SOURCE_COUNT = len(SOURCE_REGISTRY_SEEDS)


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
        """Cor Unum seeds all configured sources across event/fingerprint/internal classes."""
        with db.get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM cu_source_registry").fetchone()[0]
        assert count == EXPECTED_SOURCE_COUNT

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
        assert count == EXPECTED_SOURCE_COUNT  # no duplicates


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

    def test_same_event_different_source_kept_separate(self):
        """Cor Unum V2 dedupe is source-scoped, so cross-source events remain separate."""
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

        # Source-scoped dedupe means these remain two independent events.
        assert event_count == 2
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
        assert len(sources) == EXPECTED_SOURCE_COUNT
        keys = {s["source_key"] for s in sources}
        assert "ticketmaster_vancouver" in keys
        assert "soundcloud" in keys
        assert "spotify" in keys
        assert "instagram" in keys
        assert "artist_dedupe_janitor" in keys
        assert "event_dedupe_janitor" in keys

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
        assert len(data["sources"]) == EXPECTED_SOURCE_COUNT

    def test_api_run_all_by_class(self, client, monkeypatch):
        monkeypatch.setattr(
            "noctem.ingestion.service.refresh_sources_by_class",
            lambda scanner_class: {
                "scanner_class": scanner_class,
                "sources_run": 2,
                "results": [],
                "total_events_ingested": 0,
                "total_duplicates_skipped": 0,
                "errors": [],
            },
        )
        r = client.post("/api/cor-unum/sources/run-all/event")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]

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

    def test_session_assume_public_and_member(self, client):
        create_member = client.post(
            "/api/cor-unum/members",
            json={"username": "member_one", "display_name": "Member One"},
        )
        assert create_member.status_code == 200
        member = create_member.get_json()["member"]

        public_resp = client.post("/api/cor-unum/session/assume", json={"role": "public"})
        assert public_resp.status_code == 200
        public_session = public_resp.get_json()["session"]
        assert public_session["role"] == "public"
        assert public_session["is_member"] is False

        member_resp = client.post(
            "/api/cor-unum/session/assume",
            json={"role": "member", "member_id": member["id"]},
        )
        assert member_resp.status_code == 200
        member_session = member_resp.get_json()["session"]
        assert member_session["role"] == "member"
        assert member_session["member_id"] == member["id"]
        assert member_session["is_member"] is True

    def test_public_suggestion_accept_updates_event_and_history(self, client):
        with db.get_db() as conn:
            venue_id = conn.execute(
                "INSERT INTO cu_venues (name, is_verified) VALUES ('Test Venue', 1)"
            ).lastrowid
            event_id = conn.execute(
                "INSERT INTO cu_events (title, date, venue_id, description) VALUES (?, ?, ?, ?)",
                ("Original Title", date.today().isoformat(), venue_id, "Original"),
            ).lastrowid

        client.post("/api/cor-unum/session/assume", json={"role": "public"})
        submit = client.post(
            "/api/cor-unum/suggestions",
            json={
                "entity_type": "event",
                "entity_id": event_id,
                "payload": {"title": "Updated From Suggestion"},
            },
        )
        assert submit.status_code == 200
        suggestion = submit.get_json()["suggestion"]
        assert suggestion["status"] == "pending"
        assert suggestion["submitted_role"] == "public"

        client.post("/api/cor-unum/session/assume", json={"role": "admin"})
        resolve = client.post(
            f"/api/cor-unum/suggestions/{suggestion['id']}/resolve",
            json={"decision": "accept", "notes": "looks good"},
        )
        assert resolve.status_code == 200
        resolved = resolve.get_json()["suggestion"]
        assert resolved["status"] == "accepted"

        with db.get_db() as conn:
            title = conn.execute(
                "SELECT title FROM cu_events WHERE id = ?",
                (event_id,),
            ).fetchone()["title"]
        assert title == "Updated From Suggestion"

        detail = client.get(f"/api/cor-unum/events/{event_id}")
        assert detail.status_code == 200
        detail_payload = detail.get_json()
        assert detail_payload["success"] is True
        assert any(h["operation"] == "cor_unum.suggestion.accepted" for h in detail_payload["history"])
        assert any(s["id"] == suggestion["id"] for s in detail_payload["suggestions"])

        history = client.get(f"/api/cor-unum/history/event/{event_id}")
        assert history.status_code == 200
        history_items = history.get_json()["history"]
        assert any(item["operation"] == "cor_unum.suggestion.accepted" for item in history_items)

    def test_upcoming_locality_filters(self, client):
        today = date.today()
        with db.get_db() as conn:
            venue_id = conn.execute(
                "INSERT INTO cu_venues (name, is_verified) VALUES ('Filter Venue', 1)"
            ).lastrowid
            yvr_artist_id = conn.execute(
                "INSERT INTO cu_artists (name, is_canadian, canadian) VALUES ('YVR Artist', 0, 0)"
            ).lastrowid
            canadian_artist_id = conn.execute(
                "INSERT INTO cu_artists (name, is_canadian, canadian) VALUES ('Canadian Artist', 1, 1)"
            ).lastrowid
            foreign_artist_id = conn.execute(
                "INSERT INTO cu_artists (name, is_canadian, canadian) VALUES ('Foreign Artist', 0, 0)"
            ).lastrowid
            conn.execute(
                "INSERT INTO cu_artist_tags (artist_id, tag) VALUES (?, 'YVR')",
                (yvr_artist_id,),
            )

            event_yvr = conn.execute(
                "INSERT INTO cu_events (title, date, venue_id) VALUES (?, ?, ?)",
                ("YVR Event", today.isoformat(), venue_id),
            ).lastrowid
            event_canadian = conn.execute(
                "INSERT INTO cu_events (title, date, venue_id) VALUES (?, ?, ?)",
                ("Canadian Event", today.isoformat(), venue_id),
            ).lastrowid
            event_foreign = conn.execute(
                "INSERT INTO cu_events (title, date, venue_id) VALUES (?, ?, ?)",
                ("Foreign Event", today.isoformat(), venue_id),
            ).lastrowid

            conn.execute(
                "INSERT INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
                (event_yvr, yvr_artist_id),
            )
            conn.execute(
                "INSERT INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
                (event_canadian, canadian_artist_id),
            )
            conn.execute(
                "INSERT INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
                (event_foreign, foreign_artist_id),
            )

        all_events = client.get("/api/cor-unum/upcoming?locality=all").get_json()["events"]
        yvr_events = client.get("/api/cor-unum/upcoming?locality=vancouver").get_json()["events"]
        ca_events = client.get("/api/cor-unum/upcoming?locality=canadian").get_json()["events"]

        assert {e["title"] for e in all_events} == {"YVR Event", "Canadian Event", "Foreign Event"}
        assert {e["title"] for e in yvr_events} == {"YVR Event"}
        assert {e["title"] for e in ca_events} == {"YVR Event", "Canadian Event"}

    def test_expand_member_from_artist(self, client):
        with db.get_db() as conn:
            artist_id = conn.execute(
                "INSERT INTO cu_artists (name) VALUES ('Artist For Member')"
            ).lastrowid

        resp = client.post(
            f"/api/cor-unum/artists/{artist_id}/expand-member",
            json={"username": "artist_member", "display_name": "Artist Member"},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["member"]["artist_id"] == artist_id
        assert payload["member"]["username"] == "artist_member"


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


# =========================================================================
# Instagram/Spotify checker behavior
# =========================================================================

class TestFingerprintCheckers:
    def test_instagram_recheck_all_mode(self, monkeypatch):
        from ..ingestion.instagram import check_instagram_fingerprints

        class _Resp:
            text = "vancouver canada"
            def raise_for_status(self):
                return None

        monkeypatch.setattr("noctem.ingestion.instagram.requests.get", lambda *a, **k: _Resp())

        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO cu_artists (name, instagram_url, instagram_checked_at)
                   VALUES (?, ?, NULL)""",
                ("IG Unchecked", "https://instagram.com/unchecked"),
            )
            conn.execute(
                """INSERT INTO cu_artists (name, instagram_url, instagram_checked_at)
                   VALUES (?, ?, ?)""",
                ("IG Checked", "https://instagram.com/checked", "2026-01-01T00:00:00"),
            )

        unchecked_only = check_instagram_fingerprints(limit=20, recheck_all=False)
        assert unchecked_only["checked"] == 1

        full = check_instagram_fingerprints(limit=20, recheck_all=True)
        assert full["checked"] >= 2

    def test_spotify_recheck_all_mode_and_per_artist_skip(self, monkeypatch):
        from ..ingestion.spotify import (
            check_artist_spotify_fingerprint,
            check_spotify_fingerprints,
        )

        class _Resp:
            text = "yvr british columbia"
            def raise_for_status(self):
                return None

        monkeypatch.setattr("noctem.ingestion.spotify.requests.get", lambda *a, **k: _Resp())

        with db.get_db() as conn:
            cur = conn.execute(
                """INSERT INTO cu_artists (name, spotify_url, spotify_checked_at)
                   VALUES (?, ?, NULL)""",
                ("SP Unchecked", "https://open.spotify.com/artist/unchecked"),
            )
            artist_id = cur.lastrowid
            conn.execute(
                """INSERT INTO cu_artists (name, spotify_url, spotify_checked_at)
                   VALUES (?, ?, ?)""",
                ("SP Checked", "https://open.spotify.com/artist/checked", "2026-01-01T00:00:00"),
            )

        first = check_artist_spotify_fingerprint(artist_id, force=False)
        assert not first.get("skipped", False)
        second = check_artist_spotify_fingerprint(artist_id, force=False)
        assert second.get("skipped", False)

        unchecked_only = check_spotify_fingerprints(limit=20, recheck_all=False)
        assert unchecked_only["checked"] <= 1

        full = check_spotify_fingerprints(limit=20, recheck_all=True)
        assert full["checked"] >= 2

    def test_instagram_discovery_batch_and_single_persists_url(self, monkeypatch):
        from ..ingestion.instagram import (
            check_artist_instagram_fingerprint,
            check_instagram_fingerprints,
        )

        class _Resp:
            text = "vancouver canada"
            def raise_for_status(self):
                return None

        monkeypatch.setattr("noctem.ingestion.instagram.requests.get", lambda *a, **k: _Resp())
        monkeypatch.setattr(
            "noctem.ingestion.instagram.discover_best_profile_url",
            lambda name, source: {
                "candidate_url": f"https://instagram.com/{name.lower().replace(' ', '')}/",
                "confidence_score": 93.0,
                "query": "mock",
            },
        )

        with db.get_db() as conn:
            cur1 = conn.execute(
                """INSERT INTO cu_artists (name, instagram_url, instagram_checked_at)
                   VALUES (?, '', NULL)""",
                ("IG Discover Batch",),
            )
            batch_artist_id = cur1.lastrowid

        batch = check_instagram_fingerprints(limit=20, recheck_all=False)
        assert batch["urls_discovered"] >= 1
        assert batch["checked"] >= 1

        with db.get_db() as conn:
            batch_row = conn.execute(
                "SELECT instagram_url, instagram_checked_at FROM cu_artists WHERE id = ?",
                (batch_artist_id,),
            ).fetchone()
        assert batch_row["instagram_url"]
        assert batch_row["instagram_checked_at"]
        with db.get_db() as conn:
            cur2 = conn.execute(
                """INSERT INTO cu_artists (name, instagram_url, instagram_checked_at)
                   VALUES (?, NULL, NULL)""",
                ("IG Discover Single",),
            )
            single_artist_id = cur2.lastrowid

        single = check_artist_instagram_fingerprint(single_artist_id, force=True)
        assert single.get("error") is None
        assert single["discovered_url"] is True
        assert single["instagram_url"].startswith("https://instagram.com/")

        with db.get_db() as conn:
            single_row = conn.execute(
                "SELECT instagram_url, instagram_checked_at FROM cu_artists WHERE id = ?",
                (single_artist_id,),
            ).fetchone()
        assert single_row["instagram_url"]
        assert single_row["instagram_checked_at"]

    def test_spotify_discovery_batch_and_single_persists_url(self, monkeypatch):
        from ..ingestion.spotify import (
            check_artist_spotify_fingerprint,
            check_spotify_fingerprints,
        )

        class _Resp:
            text = "vancouver british columbia canada"
            def raise_for_status(self):
                return None

        monkeypatch.setattr("noctem.ingestion.spotify.requests.get", lambda *a, **k: _Resp())
        monkeypatch.setattr(
            "noctem.ingestion.spotify.discover_best_profile_url",
            lambda name, source: {
                "candidate_url": "https://open.spotify.com/artist/mock123",
                "confidence_score": 95.0,
                "query": "mock",
            },
        )

        with db.get_db() as conn:
            cur1 = conn.execute(
                """INSERT INTO cu_artists (name, spotify_url, spotify_checked_at)
                   VALUES (?, '', NULL)""",
                ("SP Discover Batch",),
            )
            batch_artist_id = cur1.lastrowid

        batch = check_spotify_fingerprints(limit=20, recheck_all=False)
        assert batch["urls_discovered"] >= 1
        assert batch["checked"] >= 1

        with db.get_db() as conn:
            batch_row = conn.execute(
                "SELECT spotify_url, spotify_checked_at FROM cu_artists WHERE id = ?",
                (batch_artist_id,),
            ).fetchone()
        assert batch_row["spotify_url"]
        assert batch_row["spotify_checked_at"]
        with db.get_db() as conn:
            cur2 = conn.execute(
                """INSERT INTO cu_artists (name, spotify_url, spotify_checked_at)
                   VALUES (?, NULL, NULL)""",
                ("SP Discover Single",),
            )
            single_artist_id = cur2.lastrowid

        single = check_artist_spotify_fingerprint(single_artist_id, force=True)
        assert single.get("error") is None
        assert single["discovered_url"] is True
        assert single["spotify_url"].startswith("https://open.spotify.com/artist/")

        with db.get_db() as conn:
            single_row = conn.execute(
                "SELECT spotify_url, spotify_checked_at FROM cu_artists WHERE id = ?",
                (single_artist_id,),
            ).fetchone()
        assert single_row["spotify_url"]
        assert single_row["spotify_checked_at"]
