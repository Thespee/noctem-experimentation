"""Generic web scanners for promoter/ticket sites with schema.org-first parsing."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    value = raw.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _collect_event_nodes(node) -> list[dict]:
    items: list[dict] = []
    if isinstance(node, list):
        for value in node:
            items.extend(_collect_event_nodes(value))
        return items
    if not isinstance(node, dict):
        return items
    node_type = str(node.get("@type") or "").strip()
    if node_type in {"Event", "MusicEvent"}:
        items.append(node)
    if node_type == "ItemList":
        for entry in node.get("itemListElement") or []:
            if isinstance(entry, dict):
                items.extend(_collect_event_nodes(entry.get("item", entry)))
    for key in ("event", "events", "item", "items", "@graph"):
        child = node.get(key)
        if child:
            items.extend(_collect_event_nodes(child))
    return items


def _performer_names(value) -> list[str]:
    if isinstance(value, dict):
        return [str(value.get("name") or "").strip()] if value.get("name") else []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_performer_names(item))
        return [n for n in names if n]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


class GenericMusicEventsScraper(BaseScraper):
    allowed_domains: set[str] = set()

    def scrape(self, page) -> list[RawEvent]:
        logger.info("%s: navigating to %s", self.source_key, self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=35_000)
        page.wait_for_timeout(4500)

        events = self._extract_ld_json(page)
        if not events:
            events = self._extract_dom(page)
        deduped: dict[tuple[str, str, str], RawEvent] = {}
        for event in events:
            key = (
                event.title.strip().lower(),
                event.date.isoformat(),
                (event.source_url or "").strip().lower(),
            )
            deduped[key] = event
        output = list(deduped.values())
        logger.info("%s: extracted %d events", self.source_key, len(output))
        return output

    def _normalize_url(self, href: str | None) -> str:
        raw = (href or "").strip()
        if not raw:
            return ""
        full = urljoin(self.target_url, raw)
        parsed = urlparse(full)
        host = (parsed.netloc or "").lower()
        if self.allowed_domains and not any(host.endswith(domain) for domain in self.allowed_domains):
            return ""
        return full

    def _extract_ld_json(self, page) -> list[RawEvent]:
        results: list[RawEvent] = []
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.inner_text())
            except Exception:
                continue
            for node in _collect_event_nodes(data):
                title = str(node.get("name") or "").strip()
                event_date = _parse_date(str(node.get("startDate") or ""))
                if not title or not event_date:
                    continue
                location = node.get("location") or {}
                venue_name = ""
                if isinstance(location, dict):
                    venue_name = str(location.get("name") or "").strip()
                source_url = self._normalize_url(node.get("url"))
                performers = _performer_names(node.get("performer") or node.get("performers"))
                results.append(
                    RawEvent(
                        title=title,
                        date=event_date,
                        venue_name=venue_name,
                        artists=performers,
                        description=str(node.get("description") or "")[:2000],
                        source_url=source_url,
                    )
                )
        return results

    def _extract_dom(self, page) -> list[RawEvent]:
        results: list[RawEvent] = []
        cards = page.query_selector_all(
            "a[href*='event'], a[href*='events'], article[class*='event'], div[class*='event-card']"
        )
        seen_urls: set[str] = set()
        for card in cards:
            try:
                href = card.get_attribute("href")
                source_url = self._normalize_url(href)
                if source_url and source_url in seen_urls:
                    continue
                title_el = card.query_selector("h1, h2, h3, h4, [class*='title']")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    lines = [line.strip() for line in card.inner_text().split("\n") if line.strip()]
                    title = lines[0] if lines else ""
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
                if source_url:
                    seen_urls.add(source_url)
                results.append(
                    RawEvent(
                        title=title,
                        date=event_date,
                        venue_name=venue_name,
                        source_url=source_url,
                    )
                )
            except Exception:
                continue
        return results


class DenizensScraper(GenericMusicEventsScraper):
    source_key = "denizens_yvr"
    target_url = "https://www.denizensyvr.com/events?utm_content=link_in_bio"
    allowed_domains = {"denizensyvr.com"}


class DigitalMotionScraper(GenericMusicEventsScraper):
    source_key = "digital_motion_bc"
    target_url = "https://digitalmotionbc.ca/events/"
    allowed_domains = {"digitalmotionbc.ca"}


class OrangeTicketsScraper(GenericMusicEventsScraper):
    source_key = "orange_tickets"
    target_url = "https://orangetickets.ca/?utm_source=ig&utm_medium=social&utm_content=link_in_bio"
    allowed_domains = {"orangetickets.ca"}


class TicketLeaderConcertsScraper(GenericMusicEventsScraper):
    source_key = "ticketleader_concerts"
    target_url = "https://www.ticketleader.ca/events/category/concerts"
    allowed_domains = {"ticketleader.ca"}


class TicketWebCanadaScraper(GenericMusicEventsScraper):
    source_key = "ticketweb_ca"
    target_url = "https://www.ticketweb.ca/"
    allowed_domains = {"ticketweb.ca"}
