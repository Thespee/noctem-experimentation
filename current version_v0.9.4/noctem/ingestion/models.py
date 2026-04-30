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
        "source_kind": "event",
        "target_url": "https://www.ticketmaster.ca/",
    },
    {
        "source_key": "ra_vancouver",
        "source_label": "Resident Advisor Vancouver",
        "source_kind": "event",
        "target_url": "https://ra.co/events/ca/vancouver",
    },
    {
        "source_key": "admitone_vancouver",
        "source_label": "AdmitOne Vancouver",
        "source_kind": "event",
        "target_url": "https://admitone.com/events/vancouver",
    },
    {
        "source_key": "eventbrite_vancouver",
        "source_label": "Eventbrite Vancouver Music",
        "source_kind": "event",
        "target_url": "https://www.eventbrite.ca/b/canada--vancouver/music/",
    },
    {
        "source_key": "soundcloud",
        "source_label": "SoundCloud Fingerprint",
        "source_kind": "fingerprint",
        "target_url": "https://api-v2.soundcloud.com/search/users",
    },
    {
        "source_key": "spotify",
        "source_label": "Spotify Fingerprint",
        "source_kind": "fingerprint",
        "target_url": "https://open.spotify.com/search",
    },
    {
        "source_key": "instagram",
        "source_label": "Instagram Fingerprint",
        "source_kind": "fingerprint",
        "target_url": "https://www.instagram.com/",
    },
    {
        "source_key": "artist_dedupe_janitor",
        "source_label": "Artist Dedupe Janitor",
        "source_kind": "internal",
        "target_url": "internal://artist_dedupe",
    },
    {
        "source_key": "event_dedupe_janitor",
        "source_label": "Event Dedupe Janitor",
        "source_kind": "internal",
        "target_url": "internal://event_dedupe",
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
