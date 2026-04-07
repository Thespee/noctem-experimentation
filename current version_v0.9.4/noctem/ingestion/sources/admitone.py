"""AdmitOne Vancouver scraper.

AdmitOne renders event listings at /events/vancouver.
We use Playwright to load the page and parse event cards from the DOM.

Card text structure (pipe = newline):
  Title | [subtitle] | Mon, Apr 6, 2026, 8:00 p.m. | Vogue Theatre, Vancouver | Get tickets
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)

# Lines to skip when looking for venue
_SKIP_LINES = {"get tickets", "tickets not available", "free", "see more events",
               "explore more events", "explore more headliner events",
               "upcoming events", "more events"}


class AdmitOneScraper(BaseScraper):
    source_key = "admitone_vancouver"
    target_url = "https://admitone.com/events/vancouver"

    def scrape(self, page) -> list[RawEvent]:
        logger.info("AdmitOne: navigating to %s", self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4000)

        events: list[RawEvent] = []

        cards = page.query_selector_all('a[href*="/events/"]')
        seen_urls: set[str] = set()
        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                # Must be a detail link with an ID-like slug at the end
                # e.g. /events/vancouver/pro/concerts/.../69053f8a23bab7085db83500
                if not re.search(r"/events/.+/.+/", href):
                    continue
                # Skip section links like /events/vancouver/pro
                parts = [p for p in href.strip("/").split("/") if p]
                if len(parts) < 4:
                    continue

                full_url = href if href.startswith("http") else f"https://admitone.com{href}"
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                text = card.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue

                title = lines[0]
                venue_name = ""
                event_date = None

                for line in lines[1:]:
                    if line.lower() in _SKIP_LINES:
                        continue
                    if not event_date:
                        parsed = _try_parse_date(line)
                        if parsed:
                            event_date = parsed
                            continue
                    # After date is found, next non-junk line is venue
                    if event_date and not venue_name:
                        if not line.startswith("$") and not line.isdigit():
                            venue_name = _clean_venue(line)

                if not event_date:
                    continue

                events.append(RawEvent(
                    title=title,
                    date=event_date,
                    venue_name=venue_name,
                    source_url=full_url,
                ))
            except Exception as exc:
                logger.debug("AdmitOne parse error: %s", exc)

        logger.info("AdmitOne: extracted %d events", len(events))
        return events


def _clean_venue(text: str) -> str:
    """Strip trailing city from venue name, e.g. 'Vogue Theatre, Vancouver' -> 'Vogue Theatre'."""
    # Remove trailing ", City" or ", City, Province" patterns
    cleaned = re.sub(r",\s*(Vancouver|Burnaby|Surrey|Richmond|BC|Canada).*$", "", text, flags=re.IGNORECASE)
    return cleaned.strip()


def _try_parse_date(text: str) -> date | None:
    """Parse AdmitOne date formats like 'Mon, Apr 6, 2026, 8:00 p.m.'."""
    if not text:
        return None
    text = text.strip()

    # Strategy 1: regex extract "Mon, Apr 6, 2026" from "Mon, Apr 6, 2026, 8:00 p.m."
    m = re.match(
        r"(?:\w+,\s+)?"           # optional day name + comma
        r"(\w+ \d{1,2},\s*\d{4})",  # "Apr 6, 2026"
        text,
    )
    if m:
        date_part = m.group(1)
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue

    # Strategy 2: ISO date
    m2 = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m2:
        try:
            return datetime.strptime(m2.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass

    return None
