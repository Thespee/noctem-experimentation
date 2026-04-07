"""Eventbrite Vancouver Music scraper.

Strategy: Load the music events page for Vancouver and extract from
application/ld+json (schema.org Event data). Falls back to DOM parsing.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)


class EventbriteScraper(BaseScraper):
    source_key = "eventbrite_vancouver"
    target_url = "https://www.eventbrite.ca/b/canada--vancouver/music/"

    def scrape(self, page) -> list[RawEvent]:
        logger.info("Eventbrite: navigating to %s", self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(5000)

        events: list[RawEvent] = []

        # --- Strategy 1: ld+json ---
        ld_events = self._extract_ld_json(page)
        if ld_events:
            events.extend(ld_events)
            logger.info("Eventbrite: extracted %d events from ld+json", len(ld_events))
            return events

        # --- Strategy 2: DOM ---
        events.extend(self._extract_dom(page))
        logger.info("Eventbrite: extracted %d events from DOM", len(events))
        return events

    def _extract_ld_json(self, page) -> list[RawEvent]:
        results: list[RawEvent] = []
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.inner_text())
            except (json.JSONDecodeError, Exception):
                continue

            # Eventbrite wraps events in ItemList -> itemListElement -> ListItem -> item
            event_dicts = []
            if isinstance(data, list):
                event_dicts = data
            elif isinstance(data, dict):
                if data.get("@type") == "ItemList":
                    for li in data.get("itemListElement", []):
                        inner = li.get("item", li)
                        if isinstance(inner, dict):
                            event_dicts.append(inner)
                elif data.get("@type") in ("Event", "MusicEvent"):
                    event_dicts.append(data)

            for item in event_dicts:
                try:
                    title = (item.get("name") or "").strip()
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
                        for p in (item.get("performer") or [])
                        if isinstance(p, dict) and p.get("name")
                    ]
                    source_url = item.get("url", "")
                    results.append(RawEvent(
                        title=title,
                        date=event_date,
                        venue_name=venue_name,
                        artists=artists,
                        description=(item.get("description") or "")[:500],
                        source_url=source_url,
                    ))
                except Exception as exc:
                    logger.debug("Eventbrite ld+json parse error: %s", exc)
        return results

    def _extract_dom(self, page) -> list[RawEvent]:
        """Fallback: parse event cards from rendered HTML."""
        results: list[RawEvent] = []
        cards = page.query_selector_all(
            "a[href*='eventbrite.ca/e/'], "
            "[class*='event-card'], "
            "article[class*='event']"
        )
        seen: set[str] = set()
        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                if href in seen or not href:
                    continue
                seen.add(href)
                full_url = href if href.startswith("http") else f"https://www.eventbrite.ca{href}"

                title_el = card.query_selector("h2, h3, [class*='title']")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    text_lines = [l.strip() for l in card.inner_text().split("\n") if l.strip()]
                    title = text_lines[0] if text_lines else ""
                if not title:
                    continue

                date_el = card.query_selector("time, [datetime], [class*='date']")
                raw_date = ""
                if date_el:
                    raw_date = date_el.get_attribute("datetime") or date_el.inner_text()
                event_date = _parse_date(raw_date)
                if not event_date:
                    continue

                venue_el = card.query_selector("[class*='venue'], [class*='location']")
                venue_name = venue_el.inner_text().strip() if venue_el else ""

                results.append(RawEvent(
                    title=title,
                    date=event_date,
                    venue_name=venue_name,
                    source_url=full_url,
                ))
            except Exception as exc:
                logger.debug("Eventbrite DOM parse error: %s", exc)
        return results


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:len(fmt) + 5], fmt).date()
        except (ValueError, IndexError):
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None
