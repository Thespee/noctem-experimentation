"""Resident Advisor (ra.co) Vancouver scraper.

RA uses DataDome bot protection that blocks headless browsers.
Instead, we use RA's internal GraphQL API directly via HTTP requests,
which is the same API their React frontend calls.

Vancouver area ID = 39 (discovered via area lookup query).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import requests

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://ra.co/graphql"
_VANCOUVER_AREA_ID = 39

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ra.co/events/ca/vancouver",
    "Origin": "https://ra.co",
}

_EVENT_LISTING_QUERY = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
    eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
        data {
            event {
                id
                title
                date
                startTime
                contentUrl
                venue {
                    id
                    name
                    address
                }
                artists {
                    id
                    name
                }
            }
        }
        totalResults
    }
}
"""


class RAScraper(BaseScraper):
    source_key = "ra_vancouver"
    target_url = "https://ra.co/events/ca/vancouver"

    def run(self) -> list[RawEvent]:
        """Override run() — no browser needed, use GraphQL API directly."""
        return self.scrape(page=None)

    def scrape(self, page) -> list[RawEvent]:
        """Fetch upcoming Vancouver events from RA's GraphQL API."""
        today = date.today()
        end_date = today + timedelta(days=60)

        all_events: list[RawEvent] = []
        page_num = 1
        max_pages = 5  # safety limit

        while page_num <= max_pages:
            logger.info("RA GraphQL: fetching page %d", page_num)
            variables = {
                "filters": {
                    "areas": {"eq": _VANCOUVER_AREA_ID},
                    "listingDate": {
                        "gte": today.isoformat(),
                        "lte": end_date.isoformat(),
                    },
                },
                "pageSize": 50,
                "page": page_num,
            }

            try:
                resp = requests.post(
                    _GRAPHQL_URL,
                    json={"query": _EVENT_LISTING_QUERY, "variables": variables},
                    headers=_HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("RA GraphQL request failed: %s", exc)
                break

            listings = data.get("data", {}).get("eventListings", {})
            items = listings.get("data", [])
            total = listings.get("totalResults", 0)

            if not items:
                break

            for item in items:
                event = item.get("event") or {}
                parsed = self._parse_event(event)
                if parsed:
                    all_events.append(parsed)

            # Check if there are more pages
            if len(all_events) >= total or len(items) < 50:
                break
            page_num += 1

        logger.info("RA: extracted %d events via GraphQL", len(all_events))
        return all_events

    def _parse_event(self, event: dict) -> RawEvent | None:
        """Parse a single GraphQL event object into a RawEvent."""
        title = (event.get("title") or "").strip()
        if not title:
            return None

        # Parse date
        raw_date = event.get("date") or event.get("startTime") or ""
        event_date = self._parse_date(raw_date)
        if not event_date:
            return None

        venue = event.get("venue") or {}
        venue_name = (venue.get("name") or "").strip()
        # RA uses "TBA" for secret/unannounced venues
        if venue_name.upper() in ("TBA", "TBA - VANCOUVER", ""):
            venue_name = ""

        artists = [
            a.get("name", "").strip()
            for a in (event.get("artists") or [])
            if a.get("name", "").strip()
        ]

        content_url = event.get("contentUrl") or ""
        source_url = f"https://ra.co{content_url}" if content_url else ""

        return RawEvent(
            title=title,
            date=event_date,
            venue_name=venue_name,
            artists=artists,
            source_url=source_url,
        )

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        if not raw:
            return None
        # RA dates: "2026-04-11T00:00:00.000"
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            pass
        # Fallback: extract YYYY-MM-DD
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            return None
