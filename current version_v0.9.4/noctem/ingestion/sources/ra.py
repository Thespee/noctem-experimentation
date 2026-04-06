"""Resident Advisor (ra.co) Vancouver scraper.

RA is a React SPA. The events page at /events/ca/vancouver renders
event cards with title, venue, date. We wait for the page to hydrate,
then extract from the DOM.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)


class RAScraper(BaseScraper):
    source_key = "ra_vancouver"
    target_url = "https://ra.co/events/ca/vancouver"

    def scrape(self, page) -> list[RawEvent]:
        logger.info("RA: navigating to %s", self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=30_000)
        # RA is a React SPA — wait for event list to render
        page.wait_for_timeout(5000)

        events: list[RawEvent] = []
        # RA renders event items as <li> elements with an <a> link per event
        # Each card contains: date header, event title, venue, attendance count
        cards = page.query_selector_all("li a[href*='/events/']")
        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                # Skip non-event links (e.g. /events/ca/vancouver itself)
                if not re.search(r"/events/\d+", href):
                    continue

                text = card.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) < 2:
                    continue

                title = ""
                venue_name = ""
                event_date = None

                # Parse the lines: typically [title, venue, attendance] or similar
                # Date headers appear outside the card — we try to find them
                for line in lines:
                    parsed = _try_parse_date(line)
                    if parsed:
                        event_date = parsed
                        continue
                    if not title:
                        title = line
                    elif not venue_name:
                        # Skip attendance numbers like "760"
                        if not line.isdigit():
                            venue_name = line

                if not title:
                    continue

                # If we didn't find a date in the card, try the parent section
                if not event_date:
                    parent = card.evaluate_handle("el => el.closest('div, section')")
                    if parent:
                        try:
                            parent_text = parent.as_element().inner_text()
                            for line in parent_text.split("\n"):
                                parsed = _try_parse_date(line.strip())
                                if parsed:
                                    event_date = parsed
                                    break
                        except Exception:
                            pass

                if not event_date:
                    event_date = date.today()  # fallback

                source_url = href if href.startswith("http") else f"https://ra.co{href}"
                events.append(RawEvent(
                    title=title,
                    date=event_date,
                    venue_name=venue_name if venue_name != "TBA" else "",
                    source_url=source_url,
                ))
            except Exception as exc:
                logger.debug("RA parse error: %s", exc)

        logger.info("RA: extracted %d events", len(events))
        return events


def _try_parse_date(text: str) -> date | None:
    """Try to parse RA-style dates like 'Sat, 21 Feb' or 'Sat, Apr 19, 2025'."""
    if not text:
        return None
    # Full date with year: "Sat, Apr 19, 2025"
    for fmt in (
        "%a, %b %d, %Y",
        "%a, %d %b %Y",
        "%a, %d %b",
        "%a, %b %d",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.year < 2000:
                parsed = parsed.replace(year=date.today().year)
            return parsed.date()
        except ValueError:
            continue
    # Regex: find month-day-year patterns
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None
