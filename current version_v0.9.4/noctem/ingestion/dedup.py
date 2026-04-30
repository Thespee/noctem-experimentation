"""Deduplication utilities for Cor Unum event ingestion.

Two strategies:
1. Deterministic fingerprint — sha256(normalized_title + date_iso).
   Stored in cu_event_sources.source_fingerprint for exact-match skipping.
2. Fuzzy fallback — rapidfuzz token_sort_ratio on title, same date.
   Used to link a new source to an existing event when the fingerprint
   doesn't match but the event is clearly the same.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_STRIP_RE = re.compile(r"[^a-z0-9 ]")


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = _STRIP_RE.sub("", text)
    text = " ".join(text.split())
    return text


# ---------------------------------------------------------------------------
# Deterministic fingerprint
# ---------------------------------------------------------------------------

def compute_fingerprint(title: str, event_date: date) -> str:
    """Return a hex digest fingerprint for an event.

    Uses sha256(normalized_title + "|" + date_iso).
    """
    norm = _normalize(title)
    raw = f"{norm}|{event_date.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

FUZZY_THRESHOLD = 85  # token_sort_ratio score (0-100)


def fuzzy_match_title(candidate: str, existing: str) -> float:
    """Return a similarity score (0-100) between two event titles.

    Uses rapidfuzz token_sort_ratio which is insensitive to word order.
    Returns 0.0 if rapidfuzz is unavailable.
    """
    cand = _normalize(candidate)
    exist = _normalize(existing)
    try:
        from rapidfuzz.fuzz import token_sort_ratio
        return token_sort_ratio(cand, exist)
    except ImportError:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, cand, exist).ratio() * 100.0


def is_fuzzy_duplicate(candidate_title: str, existing_title: str) -> bool:
    """Return True if the candidate is a fuzzy duplicate of the existing event."""
    return fuzzy_match_title(candidate_title, existing_title) >= FUZZY_THRESHOLD
