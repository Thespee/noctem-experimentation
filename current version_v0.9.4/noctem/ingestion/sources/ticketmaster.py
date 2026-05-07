"""Ticketmaster Vancouver scraper with diagnostics and validation guardrails."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

from ..models import RawEvent
from .base import BaseScraper

logger = logging.getLogger(__name__)

_DISCOVER_URL = (
    "https://www.ticketmaster.ca/discover/vancouver"
    "?categoryId=KZFzniwnSyZfZ7v7nJ"
)
_MAX_PAGES = 3
_VANCOUVER_TERMS = ("vancouver", "yvr", "british columbia", " bc", "canada")
_FAILURE_MODES = [
    "ticketmaster_api_or_html_shape_drift",
    "ld_json_schema_changes",
    "date_format_changes",
    "pagination_surface_changes",
    "venue_or_location_text_missing",
]


def ticketmaster_failure_modes() -> list[str]:
    return list(_FAILURE_MODES)


def build_ticketmaster_validation_report(events: list[RawEvent], diagnostics: dict | None = None) -> dict:
    diagnostics = diagnostics or {}
    total = len(events)
    with_urls = len([event for event in events if (event.source_url or "").strip()])
    with_venues = len([event for event in events if (event.venue_name or "").strip()])
    warnings: list[str] = []
    if total == 0:
        warnings.append("no_events_extracted")
    if total > 0 and with_urls == 0:
        warnings.append("no_ticket_urls")
    if total > 0 and with_venues == 0:
        warnings.append("no_venue_names")
    if int(diagnostics.get("dom_fallback_pages", 0)) > 0:
        warnings.append("dom_fallback_used")
    if int(diagnostics.get("non_vancouver_filtered", 0)) > max(10, total):
        warnings.append("high_non_vancouver_filter_rate")
    return {
        "events_extracted": total,
        "events_with_source_url": with_urls,
        "events_with_venue": with_venues,
        "warnings": warnings,
        "failure_modes": ticketmaster_failure_modes(),
    }


class TicketmasterScraper(BaseScraper):
    source_key = "ticketmaster_vancouver"
    target_url = "https://www.ticketmaster.ca/"

    def __init__(self):
        self._diagnostics: dict[str, int | dict] = {
            "pages_visited": 0,
            "ld_json_events_seen": 0,
            "dom_events_seen": 0,
            "invalid_date_dropped": 0,
            "missing_title_dropped": 0,
            "non_vancouver_filtered": 0,
            "dom_fallback_pages": 0,
        }

    def get_diagnostics(self) -> dict:
        return dict(self._diagnostics)

    def scrape(self, page) -> list[RawEvent]:
        collected: dict[tuple[str, str, str], RawEvent] = {}
        for page_num in range(1, _MAX_PAGES + 1):
            url = _DISCOVER_URL if page_num == 1 else f"{_DISCOVER_URL}&page={page_num}"
            self._diagnostics["pages_visited"] = int(self._diagnostics["pages_visited"]) + 1
            logger.info("Ticketmaster: navigating to %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(4500)

            page_events = self._extract_ld_json(page)
            if not page_events:
                self._diagnostics["dom_fallback_pages"] = int(self._diagnostics["dom_fallback_pages"]) + 1
                page_events = self._extract_dom(page)
            if not page_events and page_num > 1:
                break
            for event in page_events:
                key = (
                    event.title.strip().lower(),
                    event.date.isoformat(),
                    (event.source_url or "").strip().lower(),
                )
                collected[key] = event

        events = list(collected.values())
        self._diagnostics["validation"] = build_ticketmaster_validation_report(events, diagnostics=self._diagnostics)
        logger.info("Ticketmaster: extracted %d Vancouver events", len(events))
        return events

    def _extract_ld_json(self, page) -> list[RawEvent]:
        results: list[RawEvent] = []
        scripts = page.query_selector_all('script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.inner_text())
            except Exception:
                continue
            for item in _collect_event_nodes(data):
                self._diagnostics["ld_json_events_seen"] = int(self._diagnostics["ld_json_events_seen"]) + 1
                try:
                    title = str(item.get("name") or "").strip()
                    event_date = _parse_date(str(item.get("startDate") or ""))
                    if not title:
                        self._diagnostics["missing_title_dropped"] = int(self._diagnostics["missing_title_dropped"]) + 1
                        continue
                    if not event_date:
                        self._diagnostics["invalid_date_dropped"] = int(self._diagnostics["invalid_date_dropped"]) + 1
                        continue
                    location_blob = _extract_location_blob(item.get("location"))
                    if not _is_vancouver_location(location_blob):
                        self._diagnostics["non_vancouver_filtered"] = int(self._diagnostics["non_vancouver_filtered"]) + 1
                        continue
                    results.append(
                        RawEvent(
                            title=title,
                            date=event_date,
                            venue_name=_extract_location_name(item.get("location")),
                            artists=_extract_performers(item),
                            description=str(item.get("description") or "")[:2000],
                            source_url=_normalize_url(item.get("url")),
                        )
                    )
                except Exception as exc:
                    logger.debug("Ticketmaster ld+json parse error: %s", exc)
        return results

    def _extract_dom(self, page) -> list[RawEvent]:
        results: list[RawEvent] = []
        cards = page.query_selector_all("[data-testid='event-list-link'], li[data-id], a[href*='/event/']")
        for card in cards:
            try:
                self._diagnostics["dom_events_seen"] = int(self._diagnostics["dom_events_seen"]) + 1
                title_el = card.query_selector("h3, h2, [class*='title'], span")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    self._diagnostics["missing_title_dropped"] = int(self._diagnostics["missing_title_dropped"]) + 1
                    continue
                date_el = card.query_selector("time, [datetime], [class*='date']")
                raw_date = date_el.get_attribute("datetime") if date_el else ""
                if date_el and not raw_date:
                    raw_date = date_el.inner_text()
                event_date = _parse_date(raw_date or "")
                if not event_date:
                    self._diagnostics["invalid_date_dropped"] = int(self._diagnostics["invalid_date_dropped"]) + 1
                    continue
                venue_el = card.query_selector("[class*='venue'], [class*='location']")
                venue_name = venue_el.inner_text().strip() if venue_el else ""
                if not _is_vancouver_location(venue_name):
                    self._diagnostics["non_vancouver_filtered"] = int(self._diagnostics["non_vancouver_filtered"]) + 1
                    continue
                href = card.get_attribute("href") or ""
                results.append(
                    RawEvent(
                        title=title,
                        date=event_date,
                        venue_name=venue_name,
                        source_url=_normalize_url(href),
                    )
                )
            except Exception as exc:
                logger.debug("Ticketmaster DOM parse error: %s", exc)
        return results


def _collect_event_nodes(data) -> list[dict]:
    if isinstance(data, list):
        out: list[dict] = []
        for item in data:
            out.extend(_collect_event_nodes(item))
        return out
    if not isinstance(data, dict):
        return []
    out: list[dict] = []
    node_type = str(data.get("@type") or "").strip()
    if node_type in {"MusicEvent", "Event"}:
        out.append(data)
    if node_type == "ItemList":
        for entry in data.get("itemListElement") or []:
            if isinstance(entry, dict):
                out.extend(_collect_event_nodes(entry.get("item", entry)))
    for key in ("events", "event", "item", "items", "@graph"):
        nested = data.get(key)
        if nested:
            out.extend(_collect_event_nodes(nested))
    return out


def _extract_performers(item: dict) -> list[str]:
    value = item.get("performer") or item.get("performers") or []
    names: list[str] = []
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        if name:
            names.append(name)
    elif isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                name = str(entry.get("name") or "").strip()
                if name:
                    names.append(name)
            elif isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
    elif isinstance(value, str) and value.strip():
        names.append(value.strip())
    return names


def _extract_location_name(location) -> str:
    if not isinstance(location, dict):
        return ""
    return str(location.get("name") or "").strip()


def _extract_location_blob(location) -> str:
    if not isinstance(location, dict):
        return ""
    parts = [str(location.get("name") or ""), str(location.get("address") or "")]
    address = location.get("address")
    if isinstance(address, dict):
        parts.extend(
            [
                str(address.get("addressLocality") or ""),
                str(address.get("addressRegion") or ""),
                str(address.get("addressCountry") or ""),
            ]
        )
    return " ".join(part for part in parts if part).strip()


def _is_vancouver_location(text: str | None) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return True
    return any(term in value for term in _VANCOUVER_TERMS)


def _normalize_url(raw: str | None) -> str:
    return urljoin("https://www.ticketmaster.ca", str(raw or "").strip())


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
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        pass
    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None
