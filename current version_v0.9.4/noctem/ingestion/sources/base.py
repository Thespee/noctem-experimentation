"""Base scraper ABC for Cor Unum event ingestion.

All scrapers share:
- Headless Chromium via Playwright
- Raw HTML capture to data/ingestion_captures/<source_key>/<timestamp>.html
- Structured error recording
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import RawEvent

logger = logging.getLogger(__name__)


def _captures_dir() -> Path:
    """Return the ingestion captures root directory."""
    from ...db import DATA_DIR
    return DATA_DIR / "ingestion_captures"


class BaseScraper(ABC):
    """Abstract base for a single event-source scraper."""

    @property
    @abstractmethod
    def source_key(self) -> str:
        """Unique key matching cu_source_registry.source_key."""

    @property
    @abstractmethod
    def target_url(self) -> str:
        """Starting URL for this scraper."""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> list[RawEvent]:
        """Execute the scraper: launch browser → scrape → capture → return.

        Callers should catch exceptions and record them in the run log.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            # Block images/fonts/media for speed
            page.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,mp4,webm}",
                lambda route: route.abort(),
            )
            try:
                events = self.scrape(page)
            finally:
                # Always capture raw HTML for break detection
                try:
                    self._save_capture(page.content())
                except Exception:
                    pass
                context.close()
                browser.close()
        return events

    # ------------------------------------------------------------------
    # Subclass must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self, page) -> list[RawEvent]:
        """Navigate, extract, and return parsed events.

        `page` is a playwright.sync_api.Page with a live browser context.
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_capture(self, html: str) -> str | None:
        """Write raw HTML to the captures directory. Returns the path."""
        try:
            capture_dir = _captures_dir() / self.source_key
            capture_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = capture_dir / f"{ts}.html"
            path.write_text(html, encoding="utf-8")
            logger.info("Captured raw HTML → %s", path)
            return str(path)
        except Exception as exc:
            logger.warning("Failed to save capture for %s: %s", self.source_key, exc)
            return None
