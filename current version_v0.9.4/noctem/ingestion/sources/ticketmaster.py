"""Ticketmaster Vancouver scraper.

Strategy: Navigate to the Ticketmaster.ca discover/concerts page for
Vancouver, which embeds structured ld+json MusicEvent data in the HTML.
The search page is blocked by Akamai CAPTCHA, but the discover page loads.
Falls back to DOM parsing if ld+json is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)

# The discover page embeds ld+json MusicEvent data and isn't blocked
_DISCOVER_URL = (
    "https://www.ticketmaster.ca/discover/vancouver"
    "?categoryId=KZFzniwnSyZfZ7v7nJ"  # Concerts category
)


class TicketmasterScraper(BaseScraper):
    source_key = "ticketmaster_vancouver"
    target_url = "https://www.ticketmaster.ca/"

    def scrape(self, page) -> list[RawEvent]:
        logger.info("Ticketmaster: navigating to discover page")
        page.goto(_DISCOVER_URL, wait_until="domcontentloaded", timeout=30_000)
        # Wait for page content including ld+json to load
        page.wait_for_timeout(5000)

        events: list[RawEvent] = []

        # --- Strategy 1: ld+json ---
        ld_events = self._extract_ld_json(page)
        if ld_events:
            events.extend(ld_events)
            logger.info("Ticketmaster: extracted %d events from ld+json", len(ld_events))
            return events

        # --- Strategy 2: DOM parsing ---
        events.extend(self._extract_dom(page))
        logger.info("Ticketmaster: extracted %d events from DOM", len(events))
        return events

    # ------------------------------------------------------------------

    def _extract_ld_json(self, page) -> list[RawEvent]:
        """Parse schema.org events from ld+json script tags."""
        results: list[RawEvent] = []
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.inner_text())
            except (json.JSONDecodeError, Exception):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") not in ("MusicEvent", "Event"):
                    continue
                try:
                    title = item.get("name", "").strip()
                    start = item.get("startDate", "")
                    event_date = _parse_date(start)
                    if not title or not event_date:
                        continue
                    venue_name = ""
                    loc = item.get("location") or {}
                    if isinstance(loc, dict):
                        venue_name = loc.get("name", "")
                    artists = [
                        p.get("name", "")
                        for p in (item.get("performer") or item.get("performers") or [])
                        if isinstance(p, dict) and p.get("name")
                    ]
                    source_url = item.get("url", "")
                    results.append(RawEvent(
                        title=title,
                        date=event_date,
                        venue_name=venue_name,
                        artists=artists,
                        description=item.get("description", ""),
                        source_url=source_url,
                    ))
                except Exception as exc:
                    logger.debug("Ticketmaster ld+json parse error: %s", exc)
        return results

    def _extract_dom(self, page) -> list[RawEvent]:
        """Fallback: parse event cards from the rendered DOM."""
        results: list[RawEvent] = []
        cards = page.query_selector_all("[data-testid='event-list-link'], li[data-id]")
        for card in cards:
            try:
                title_el = card.query_selector("h3, [class*='title'], span")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    continue
                date_el = card.query_selector("[class*='date'], time, [datetime]")
                raw_date = ""
                if date_el:
                    raw_date = date_el.get_attribute("datetime") or date_el.inner_text()
                event_date = _parse_date(raw_date)
                if not event_date:
                    continue
                venue_el = card.query_selector("[class*='venue'], [class*='location']")
                venue_name = venue_el.inner_text().strip() if venue_el else ""
                href = card.get_attribute("href") or ""
                source_url = href if href.startswith("http") else f"https://www.ticketmaster.ca{href}"
                results.append(RawEvent(
                    title=title,
                    date=event_date,
                    venue_name=venue_name,
                    source_url=source_url,
                ))
            except Exception as exc:
                logger.debug("Ticketmaster DOM parse error: %s", exc)
        return results


def _parse_date(raw: str) -> date | None:
    """Try to parse a date from various formats."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:len(fmt) + 5], fmt).date()
        except (ValueError, IndexError):
            continue
    # Regex fallback: find YYYY-MM-DD
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None
