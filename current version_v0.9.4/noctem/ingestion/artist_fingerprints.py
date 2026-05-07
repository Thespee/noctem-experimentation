"""Unified artist fingerprint checker registry for Cor Unum."""
from __future__ import annotations

from .instagram import (
    check_artist_instagram_fingerprint,
    check_instagram_fingerprints,
)
from .soundcloud import (
    check_all_unchecked_artists as check_soundcloud_fingerprints,
)
from .soundcloud import (
    check_artist_locality as check_artist_soundcloud_fingerprint,
)
from .spotify import (
    check_artist_spotify_fingerprint,
    check_spotify_fingerprints,
)


_FINGERPRINT_REGISTRY: dict[str, dict] = {
    "soundcloud": {
        "label": "SoundCloud",
        "url_field": "soundcloud_url",
        "check_artist_fn": check_artist_soundcloud_fingerprint,
        "check_all_fn": check_soundcloud_fingerprints,
    },
    "instagram": {
        "label": "Instagram",
        "url_field": "instagram_url",
        "check_artist_fn": check_artist_instagram_fingerprint,
        "check_all_fn": check_instagram_fingerprints,
    },
    "spotify": {
        "label": "Spotify",
        "url_field": "spotify_url",
        "check_artist_fn": check_artist_spotify_fingerprint,
        "check_all_fn": check_spotify_fingerprints,
    },
}


def list_fingerprint_sources() -> list[dict]:
    return [
        {
            "source_key": key,
            "label": entry["label"],
            "url_field": entry["url_field"],
        }
        for key, entry in _FINGERPRINT_REGISTRY.items()
    ]


def check_artist_fingerprint(source_key: str, artist_id: int, force: bool = False) -> dict:
    entry = _FINGERPRINT_REGISTRY.get(source_key)
    if not entry:
        return {"error": f"Unknown fingerprint source: {source_key}"}
    result = entry["check_artist_fn"](artist_id, force=force)
    if isinstance(result, dict):
        result.setdefault("source_key", source_key)
    return result


def check_all_fingerprints(source_key: str, limit: int = 30, mode: str = "unchecked") -> dict:
    entry = _FINGERPRINT_REGISTRY.get(source_key)
    if not entry:
        return {"error": f"Unknown fingerprint source: {source_key}"}
    normalized_mode = (mode or "").strip().lower()
    recheck_all = normalized_mode in {"all", "all_empty"} or int(limit) <= 0
    result = entry["check_all_fn"](limit=limit, recheck_all=recheck_all)
    if isinstance(result, dict):
        result.setdefault("source_key", source_key)
    return result
