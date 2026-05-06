"""Shared locality classification helpers for Cor Unum artist enrichment."""
from __future__ import annotations

import re

_CANADIAN_PROVINCE_TERMS = (
    "bc",
    "british columbia",
    "alberta",
    "saskatchewan",
    "manitoba",
    "ontario",
    "quebec",
    "nova scotia",
    "new brunswick",
    "newfoundland",
    "labrador",
    "prince edward island",
    "pei",
    "yukon",
    "northwest territories",
    "nunavut",
)

_CANADIAN_CITY_TERMS = (
    "vancouver",
    "victoria",
    "kelowna",
    "burnaby",
    "surrey",
    "richmond",
    "toronto",
    "montreal",
    "calgary",
    "edmonton",
    "ottawa",
    "winnipeg",
    "halifax",
    "quebec city",
    "hamilton",
)


def _normalized(text: str | None) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""
    return re.sub(r"\s+", " ", value)


def is_vancouver_locality(text: str | None) -> bool:
    value = _normalized(text)
    if not value:
        return False
    return any(term in value for term in ("vancouver", "yvr", "metro vancouver"))


def is_canadian_locality(text: str | None) -> bool:
    value = _normalized(text)
    if not value:
        return False
    if is_vancouver_locality(value):
        return True
    if "canada" in value:
        return True
    if any(term in value for term in _CANADIAN_PROVINCE_TERMS):
        return True
    if any(term in value for term in _CANADIAN_CITY_TERMS):
        return True
    return False


def derive_locality_flags(*texts: str | None) -> tuple[bool, bool]:
    """Return (is_vancouver_local, is_canadian) derived from one or more text fields."""
    local = False
    canadian = False
    for text in texts:
        if not text:
            continue
        if is_vancouver_locality(text):
            local = True
        if is_canadian_locality(text):
            canadian = True
    if local:
        canadian = True
    return local, canadian
