"""Data models and constants for the Cor Unum ingestion system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


FALLBACK_VENUE_NAME = "Out in the Wild"

SOURCE_REGISTRY_SEEDS = [
    {
        "source_key": "ticketmaster_vancouver",
        "source_label": "Ticketmaster Vancouver",
        "source_kind": "web",
        "target_url": "https://www.ticketmaster.ca/",
    },
    {
        "source_key": "ra_vancouver",
        "source_label": "Resident Advisor Vancouver",
        "source_kind": "web",
        "target_url": "https://ra.co/events/ca/vancouver",
    },
    {
        "source_key": "admitone_vancouver",
        "source_label": "AdmitOne Vancouver",
        "source_kind": "web",
        "target_url": "https://admitone.com/events/vancouver",
    },
    {
        "source_key": "eventbrite_vancouver",
        "source_label": "Eventbrite Vancouver Music",
        "source_kind": "web",
        "target_url": "https://www.eventbrite.ca/b/canada--vancouver/music/",
    },
    {
        "source_key": "soundcloud",
        "source_label": "SoundCloud Locality",
        "source_kind": "social",
        "target_url": "https://api-v2.soundcloud.com/search/users",
    },
]


@dataclass
class RawEvent:
    """A single event as parsed from a scraper before dedup/storage."""

    title: str
    date: date
    venue_name: str = ""
    artists: list[str] = field(default_factory=list)
    description: str = ""
    source_url: str = ""
