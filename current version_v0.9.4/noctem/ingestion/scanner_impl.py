"""Concrete scanner implementations for Cor Unum scanner classes."""
from __future__ import annotations

from datetime import datetime

from ..db import get_db
from .dedup import fuzzy_match_title
from .scanners import BaseIngestionScanner


class EventScraperScanner(BaseIngestionScanner):
    scanner_class = "event"
    report_type = "events"

    def __init__(self, source_key: str, scraper_cls, process_event_fn):
        self.source_key = source_key
        self._scraper_cls = scraper_cls
        self._process_event_fn = process_event_fn

    def perform(self) -> dict:
        scraper = self._scraper_cls()
        raw_events = scraper.run()
        summary = {
            "events_scraped": len(raw_events),
            "events_ingested": 0,
            "artists_added": 0,
            "venues_added": 0,
            "duplicates_skipped": 0,
        }
        diagnostics_fn = getattr(scraper, "get_diagnostics", None)
        if callable(diagnostics_fn):
            try:
                diagnostics = diagnostics_fn()
                if diagnostics:
                    summary["diagnostics"] = diagnostics
            except Exception:
                pass
        with get_db() as conn:
            for raw in raw_events:
                result = self._process_event_fn(conn, raw, self.source_key)
                summary["events_ingested"] += result.get("event_created", 0)
                summary["artists_added"] += result.get("artists_created", 0)
                summary["venues_added"] += result.get("venue_created", 0)
                summary["duplicates_skipped"] += result.get("duplicate", 0)
        return summary


class ArtistFingerprintScanner(BaseIngestionScanner):
    scanner_class = "fingerprint"
    report_type = "fingerprint"

    def __init__(self, source_key: str, run_fn):
        self.source_key = source_key
        self._run_fn = run_fn

    def perform(self) -> dict:
        result = self._run_fn()
        summary = {
            "checked": int(result.get("checked", 0)),
            "local_yvr": int(result.get("local", 0)),
            "not_local_yvr": int(result.get("not_local", 0)),
            "canadian": int(result.get("canadian", 0)),
            "errors": int(result.get("errors", 0)),
        }
        if "urls_discovered" in result:
            summary["urls_discovered"] = int(result.get("urls_discovered", 0))
        if result.get("error_message"):
            summary["error_message"] = str(result["error_message"])[:1000]
        elif summary["checked"] == 0 and summary["errors"] > 0:
            summary["error_message"] = (
                f"{self.source_key} fingerprint scan found 0 successful checks "
                f"and {summary['errors']} errors"
            )
        return summary


class ArtistDedupeJanitorScanner(BaseIngestionScanner):
    source_key = "artist_dedupe_janitor"
    scanner_class = "internal"
    report_type = "internal"

    def perform(self) -> dict:
        rows = []
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, name FROM cu_artists WHERE alias_of IS NULL ORDER BY id"
            ).fetchall()
        normalized: dict[str, list[dict]] = {}
        for row in rows:
            base = row["name"].strip().lower()
            for token in ("(live)", "(dj set)", " dj set", " - live", " live"):
                base = base.replace(token, "")
            base = " ".join(base.split())
            normalized.setdefault(base, []).append({"id": row["id"], "name": row["name"]})
        potential_matches = []
        for group in normalized.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    left = group[i]
                    right = group[j]
                    score = round(float(fuzzy_match_title(left["name"], right["name"])), 2)
                    potential_matches.append(
                        {
                            "left_artist_id": left["id"],
                            "left_artist_name": left["name"],
                            "right_artist_id": right["id"],
                            "right_artist_name": right["name"],
                            "title_match_pct": score,
                        }
                    )
        return {
            "potential_matches_count": len(potential_matches),
            "title_match_pct_avg": round(
                sum(m["title_match_pct"] for m in potential_matches) / len(potential_matches), 2
            ) if potential_matches else 0.0,
            "potential_matches": potential_matches[:100],
        }


class EventDedupeJanitorScanner(BaseIngestionScanner):
    source_key = "event_dedupe_janitor"
    scanner_class = "internal"
    report_type = "internal"

    def perform(self) -> dict:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT e.id, e.title, e.date, e.venue_id, v.name AS venue_name
                   FROM cu_events e
                   LEFT JOIN cu_venues v ON v.id = e.venue_id
                   ORDER BY e.date ASC, e.venue_id ASC, e.id ASC"""
            ).fetchall()
        by_date_venue: dict[tuple[str, int | None], list[dict]] = {}
        for row in rows:
            key = (row["date"], row["venue_id"])
            by_date_venue.setdefault(key, []).append(dict(row))
        potential_matches = []
        for group in by_date_venue.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    left = group[i]
                    right = group[j]
                    score = round(float(fuzzy_match_title(left["title"], right["title"])), 2)
                    potential_matches.append(
                        {
                            "left_event_id": left["id"],
                            "left_title": left["title"],
                            "right_event_id": right["id"],
                            "right_title": right["title"],
                            "date": left["date"],
                            "venue_name": left["venue_name"],
                            "title_match_pct": score,
                        }
                    )
        return {
            "potential_matches_count": len(potential_matches),
            "title_match_pct_avg": round(
                sum(m["title_match_pct"] for m in potential_matches) / len(potential_matches), 2
            ) if potential_matches else 0.0,
            "potential_matches": potential_matches[:150],
        }

