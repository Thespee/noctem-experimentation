"""AdmitOne Vancouver scraper.

AdmitOne renders event listings at /events/vancouver.
We use Playwright to load the page and parse event cards from the DOM.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)


class AdmitOneScraper(BaseScraper):
    source_key = "admitone_vancouver"
    target_url = "https://admitone.com/events/vancouver"

    def scrape(self, page) -> list[RawEvent]:
        logger.info("AdmitOne: navigating to %s", self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4000)

        events: list[RawEvent] = []

        # AdmitOne typically lists events as cards/links with title, date, venue
        cards = page.query_selector_all(
            "a[href*='/events/'], .event-card, .event-item, "
            "[class*='event'], article"
        )
        seen_urls: set[str] = set()
        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                # Only process actual event detail links
                if "/events/" not in href or href.rstrip("/") == self.target_url.rstrip("/"):
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
                    if not event_date:
                        parsed = _try_parse_date(line)
                        if parsed:
                            event_date = parsed
                            continue
                    if not venue_name and not line.startswith("$") and not line.isdigit():
                        venue_name = line

                if not event_date:
                    # Try datetime attribute on child elements
                    time_el = card.query_selector("time, [datetime]")
                    if time_el:
                        raw = time_el.get_attribute("datetime") or time_el.inner_text()
                        event_date = _try_parse_date(raw)

                if not event_date:
                    continue  # skip events with no parseable date

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


def _try_parse_date(text: str) -> date | None:
    """Parse common date formats seen on AdmitOne."""
    if not text:
        return None
    text = text.strip()
    for fmt in (
        "%B %d, %Y",       # "April 15, 2026"
        "%b %d, %Y",       # "Apr 15, 2026"
        "%A, %B %d, %Y",   # "Tuesday, April 15, 2026"
        "%a, %b %d, %Y",   # "Tue, Apr 15, 2026"
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:50], fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    # "Apr 15" without year
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(text[:20], fmt)
            return parsed.replace(year=date.today().year).date()
        except ValueError:
            continue
    return None
