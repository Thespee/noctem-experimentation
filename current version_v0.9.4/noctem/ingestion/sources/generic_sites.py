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

def _clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).replace("\xa0", " ")).strip()


_DATE_SNIPPET_PATTERNS = (
    r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[APMapm]{2})?)",
    r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+\d{1,2}\s+[A-Za-z]{3,9}(?:,?\s+\d{4})?(?:\s+\d{1,2}:\d{2}\s*[APMapm]{2})?)",
    r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[APMapm]{2})?)",
    r"([A-Za-z]{3,9}\s+\d{1,2}\s+\d{1,2}:\d{2}\s*[APMapm]{2})",
)


def _parse_date(raw: str, default_year: int | None = None, _allow_search: bool = True) -> date | None:
    if not raw:
        return None
    year = int(default_year or datetime.utcnow().year)
    value = _clean_text(raw)
    value = value.replace("@", " ")
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"(?i)\bevent starts\b", " ", value)
    value = re.sub(r"(?i)\bstarts\b", " ", value)
    value = _clean_text(value)

    year_aware_formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%a %b %d, %Y",
        "%A %b %d, %Y",
        "%a %B %d, %Y",
        "%A %B %d, %Y",
        "%a %b %d %Y",
        "%A %b %d %Y",
        "%a %B %d %Y",
        "%A %B %d %Y",
        "%a %d %b %Y",
        "%A %d %b %Y",
        "%a %d %B %Y",
        "%A %d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%a %b %d, %Y %I:%M%p",
        "%A %b %d, %Y %I:%M%p",
        "%a %b %d, %Y %I:%M %p",
        "%A %b %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M%p",
        "%B %d, %Y %I:%M%p",
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%b %d %Y %I:%M%p",
        "%B %d %Y %I:%M%p",
        "%b %d %Y %I:%M %p",
        "%B %d %Y %I:%M %p",
        "%a %d %b %Y %I:%M%p",
        "%A %d %b %Y %I:%M%p",
        "%a %d %B %Y %I:%M%p",
        "%A %d %B %Y %I:%M%p",
        "%a %d %b %Y %I:%M %p",
        "%A %d %b %Y %I:%M %p",
        "%a %d %B %Y %I:%M %p",
        "%A %d %B %Y %I:%M %p",
    )
    for fmt in year_aware_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    no_year_formats = (
        "%b %d %I:%M%p",
        "%B %d %I:%M%p",
        "%b %d, %I:%M%p",
        "%B %d, %I:%M%p",
        "%b %d %I:%M %p",
        "%B %d %I:%M %p",
        "%b %d, %I:%M %p",
        "%B %d, %I:%M %p",
        "%b %d",
        "%B %d",
        "%a %d %b",
        "%A %d %b",
        "%a %d %B",
        "%A %d %B",
        "%a %d %b %I:%M%p",
        "%A %d %b %I:%M%p",
        "%a %d %B %I:%M%p",
        "%A %d %B %I:%M%p",
        "%a %d %b %I:%M %p",
        "%A %d %b %I:%M %p",
        "%a %d %B %I:%M %p",
        "%A %d %B %I:%M %p",
    )
    for fmt in no_year_formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return date(year, parsed.month, parsed.day)
        except ValueError:
            continue

    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None

    if _allow_search:
        for pattern in _DATE_SNIPPET_PATTERNS:
            snippet_match = re.search(pattern, value, flags=re.IGNORECASE)
            if not snippet_match:
                continue
            parsed = _parse_date(
                snippet_match.group(1),
                default_year=year,
                _allow_search=False,
            )
            if parsed:
                return parsed
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


def _is_vancouver_location(*values: str) -> bool:
    text = " ".join(_clean_text(v).lower() for v in values if v)
    if not text:
        return False
    return ("vancouver" in text) or (re.search(r"\byvr\b", text) is not None)


class GenericMusicEventsScraper(BaseScraper):
    allowed_domains: set[str] = set()

    def __init__(self):
        self._diagnostics: dict[str, object] = {}

    def get_diagnostics(self) -> dict:
        return dict(self._diagnostics)

    def _reset_diagnostics(self) -> None:
        self._diagnostics = {
            "ld_json_scripts": 0,
            "ld_json_event_nodes": 0,
            "dom_candidate_cards": 0,
            "dom_title_missing": 0,
            "dom_date_parse_failures": 0,
            "filtered_non_vancouver": 0,
            "dom_events_parsed": 0,
            "events_before_dedupe": 0,
            "events_after_dedupe": 0,
        }

    def _increment_diag(self, key: str, delta: int = 1) -> None:
        self._diagnostics[key] = int(self._diagnostics.get(key) or 0) + int(delta)

    def scrape(self, page) -> list[RawEvent]:
        self._reset_diagnostics()
        logger.info("%s: navigating to %s", self.source_key, self.target_url)
        page.goto(self.target_url, wait_until="domcontentloaded", timeout=35_000)
        page.wait_for_timeout(4500)
        self._prepare_page_for_extraction(page)

        events = self._extract_ld_json(page)
        events.extend(self._extract_dom(page))
        deduped: dict[tuple[str, str, str], RawEvent] = {}
        for event in events:
            key = (
                event.title.strip().lower(),
                event.date.isoformat(),
                (event.source_url or "").strip().lower(),
            )
            deduped[key] = event
        output = list(deduped.values())
        self._diagnostics["events_before_dedupe"] = len(events)
        self._diagnostics["events_after_dedupe"] = len(output)
        if not output:
            dom_candidates = int(self._diagnostics.get("dom_candidate_cards") or 0)
            external_listing = bool(self._diagnostics.get("external_listing_url"))
            if dom_candidates > 0 or external_listing:
                self._diagnostics["zero_yield_should_error"] = True
                if external_listing:
                    self._diagnostics["zero_yield_reason"] = (
                        f"{self.source_key}: external listing detected but 0 events parsed"
                    )
                else:
                    self._diagnostics["zero_yield_reason"] = (
                        f"{self.source_key}: parsed 0 events from {dom_candidates} candidate cards"
                    )
        logger.info("%s: extracted %d events", self.source_key, len(output))
        return output

    def _prepare_page_for_extraction(self, page) -> None:
        return None

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
        self._diagnostics["ld_json_scripts"] = len(scripts)
        node_count = 0
        for script in scripts:
            try:
                data = json.loads(script.inner_text())
            except Exception:
                continue
            for node in _collect_event_nodes(data):
                node_count += 1
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
        self._diagnostics["ld_json_event_nodes"] = node_count
        return results
    def _extract_first_text(self, node, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            try:
                el = node.query_selector(selector)
            except Exception:
                el = None
            if not el:
                continue
            text = _clean_text(el.inner_text())
            if text:
                return text
        return ""

    def _build_event_from_card(
        self,
        card,
        *,
        title_selectors: tuple[str, ...] | None = None,
        date_selectors: tuple[str, ...] | None = None,
        venue_selectors: tuple[str, ...] | None = None,
        link_selector: str = "a[href]",
    ) -> RawEvent | None:
        title_selectors = title_selectors or (
            "h1",
            "h2",
            "h3",
            "h4",
            "[class*='title']",
            "[class*='Title']",
            "[class*='subtitle']",
            "[class*='name']",
        )
        date_selectors = date_selectors or (
            "time",
            "[datetime]",
            "[class*='date']",
            "[class*='Date']",
        )
        venue_selectors = venue_selectors or (
            "[class*='venue']",
            "[class*='Venue']",
            "[class*='location']",
            "[class*='Location']",
        )
        try:
            href = card.get_attribute("href")
        except Exception:
            href = None
        if not href and link_selector:
            try:
                link_el = card.query_selector(link_selector)
            except Exception:
                link_el = None
            if link_el:
                try:
                    href = link_el.get_attribute("href")
                except Exception:
                    href = None
        source_url = self._normalize_url(href)

        title = self._extract_first_text(card, title_selectors)
        if not title:
            try:
                lines = [_clean_text(line) for line in card.inner_text().split("\n")]
            except Exception:
                lines = []
            for line in lines:
                if not line:
                    continue
                lowered = line.lower()
                if lowered in {"purchase", "buy tickets", "find tickets", "more details"}:
                    continue
                if _parse_date(line):
                    continue
                title = line
                break
        if not title:
            self._increment_diag("dom_title_missing")
            return None

        event_date: date | None = None
        for selector in date_selectors:
            try:
                date_el = card.query_selector(selector)
            except Exception:
                date_el = None
            if not date_el:
                continue
            candidate = ""
            try:
                candidate = date_el.get_attribute("datetime") or ""
            except Exception:
                candidate = ""
            if not candidate:
                try:
                    candidate = date_el.inner_text() or ""
                except Exception:
                    candidate = ""
            parsed = _parse_date(candidate)
            if parsed:
                event_date = parsed
                break
        if not event_date:
            try:
                event_date = _parse_date(card.inner_text())
            except Exception:
                event_date = None
        if not event_date:
            self._increment_diag("dom_date_parse_failures")
            return None

        venue_name = self._extract_first_text(card, venue_selectors)
        return RawEvent(
            title=title,
            date=event_date,
            venue_name=venue_name,
            source_url=source_url,
        )

    def _collect_events_from_cards(self, cards, **card_kwargs) -> list[RawEvent]:
        results: list[RawEvent] = []
        seen: set[tuple[str, str, str]] = set()
        for card in cards:
            try:
                parsed = self._build_event_from_card(card, **card_kwargs)
            except Exception:
                parsed = None
            if not parsed:
                continue
            key = (
                parsed.title.strip().lower(),
                parsed.date.isoformat(),
                (parsed.source_url or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(parsed)
        self._diagnostics["dom_events_parsed"] = len(results)
        return results

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all(
            "a[href*='event'], a[href*='events'], article[class*='event'], div[class*='event-card'], div[class*='eventItem'], li[class*='event']"
        )
        self._diagnostics["dom_candidate_cards"] = len(cards)
        return self._collect_events_from_cards(cards)


class DenizensScraper(GenericMusicEventsScraper):
    source_key = "denizens_yvr"
    target_url = "https://www.denizensyvr.com/events?utm_content=link_in_bio"
    allowed_domains = {"denizensyvr.com", "tickettailor.com"}

    def _prepare_page_for_extraction(self, page) -> None:
        listing_url = ""
        script_widget = page.query_selector("script[data-url*='tickettailor.com/all-tickets']")
        if script_widget:
            listing_url = script_widget.get_attribute("data-url") or ""
        if not listing_url:
            iframe = page.query_selector("iframe[src*='tickettailor.com/all-tickets']")
            if iframe:
                listing_url = iframe.get_attribute("src") or ""
        listing_url = listing_url.strip()
        if not listing_url:
            return
        self._diagnostics["external_listing_url"] = listing_url
        try:
            page.goto(listing_url, wait_until="domcontentloaded", timeout=35_000)
            page.wait_for_timeout(5000)
        except Exception as exc:
            self._diagnostics["external_listing_error"] = str(exc)[:300]

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all(
            "div.listing a[href*='/checkout/view-event/'], a.ignore-params[href*='/checkout/view-event/'], article[class*='event'], li[class*='event'], div[class*='event'], a[href*='/events/'], a[href*='/all-tickets/']"
        )
        self._diagnostics["dom_candidate_cards"] = len(cards)
        return self._collect_events_from_cards(
            cards,
            title_selectors=(".event_name", "[class*='event_name']", "h1", "h2", "h3", "[class*='title']"),
            date_selectors=(".event_date", "[class*='event_date']", "time", "[datetime]", "[class*='date']", "[class*='Date']"),
            link_selector="",
        )


class DigitalMotionScraper(GenericMusicEventsScraper):
    source_key = "digital_motion_bc"
    target_url = "https://digitalmotionbc.ca/events/"
    allowed_domains = {"digitalmotionbc.ca"}

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all("a[href*='/event-detail']")
        self._diagnostics["dom_candidate_cards"] = len(cards)
        return self._collect_events_from_cards(
            cards,
            title_selectors=("h3", "[class*='title']", "h2"),
            date_selectors=("[class*='event-details']", "[class*='date']", "time", "[datetime]"),
            link_selector="a[href*='/event-detail']",
        )


class OrangeTicketsScraper(GenericMusicEventsScraper):
    source_key = "orange_tickets"
    target_url = "https://orangetickets.ca/?utm_source=ig&utm_medium=social&utm_content=link_in_bio"
    allowed_domains = {"orangetickets.ca"}

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all("div.product.custom-height, div.product")
        self._diagnostics["dom_candidate_cards"] = len(cards)
        results: list[RawEvent] = []
        seen: set[tuple[str, str, str]] = set()
        for card in cards:
            try:
                href_el = card.query_selector("h2 a[href*='detalles_evento.php'], a[href*='detalles_evento.php']")
                href = href_el.get_attribute("href") if href_el else ""
                source_url = self._normalize_url(href)
                title = self._extract_first_text(card, ("h2 a", "h2", "h3 a", "h3"))
                if not title:
                    self._increment_diag("dom_title_missing")
                    continue
                meta_ps = card.query_selector_all("ul li p")
                meta_lines = [_clean_text(p.inner_text()) for p in meta_ps if _clean_text(p.inner_text())]
                event_date: date | None = None
                venue_name = ""
                for line in meta_lines:
                    parsed = _parse_date(line)
                    if parsed and not event_date:
                        event_date = parsed
                        continue
                    if not venue_name:
                        lowered = line.lower()
                        if lowered not in {"purchase", "buy tickets", "find tickets"}:
                            venue_name = line
                if not _is_vancouver_location(" ".join(meta_lines), card.inner_text()):
                    self._increment_diag("filtered_non_vancouver")
                    continue
                if not event_date:
                    event_date = _parse_date(card.inner_text())
                if not event_date:
                    self._increment_diag("dom_date_parse_failures")
                    continue
                event = RawEvent(
                    title=title,
                    date=event_date,
                    venue_name=venue_name,
                    source_url=source_url,
                )
                key = (
                    event.title.strip().lower(),
                    event.date.isoformat(),
                    (event.source_url or "").strip().lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(event)
            except Exception:
                continue
        self._diagnostics["dom_events_parsed"] = len(results)
        return results


class TicketLeaderConcertsScraper(GenericMusicEventsScraper):
    source_key = "ticketleader_concerts"
    target_url = "https://www.ticketleader.ca/events/category/concerts"
    allowed_domains = {"ticketleader.ca"}

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all("div.eventItem")
        self._diagnostics["dom_candidate_cards"] = len(cards)
        return self._collect_events_from_cards(
            cards,
            title_selectors=("h3.title a", "h3.title", "h3 a", "h3"),
            date_selectors=("div.date", "[class*='date']", "time", "[datetime]"),
            venue_selectors=("div.location", "[class*='venue']", "[class*='location']"),
            link_selector="h3 a, a[href*='/events/detail/']",
        )


class TicketWebCanadaScraper(GenericMusicEventsScraper):
    source_key = "ticketweb_ca"
    target_url = "https://www.ticketweb.ca/"
    allowed_domains = {"ticketweb.ca"}

    def _extract_dom(self, page) -> list[RawEvent]:
        cards = page.query_selector_all(
            "ul.list-venue-events li.list-group-item.ng-scope, ul.list-venue-events li.list-group-item"
        )
        self._diagnostics["dom_candidate_cards"] = len(cards)
        return self._collect_events_from_cards(
            cards,
            title_selectors=("span.list-group-item-text", "span[class*='subTitle']", "a[title]"),
            date_selectors=("small.small-l", "small[class*='small-l']", "[class*='date']"),
            link_selector="a[href*='/event/']",
        )
