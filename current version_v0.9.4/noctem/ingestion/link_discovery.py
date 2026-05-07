"""Auto-discovery + manual review queue for artist social links."""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

from ..db import get_db

_USER_AGENT = "Mozilla/5.0 (Noctem Cor Unum Link Discovery)"
_SUPPORTED_SOURCES = {"instagram", "spotify"}
_SEARCH_TIMEOUT_DDG = (4, 8)
_SEARCH_TIMEOUT_JINA = (4, 12)
_SEARCH_TIMEOUT_BING = (4, 8)
_PROVIDER_COOLDOWN_SECONDS = 180
_provider_state: dict[str, dict[str, float | int]] = {}

logger = logging.getLogger(__name__)


class DiscoveryProviderUnavailable(RuntimeError):
    """Raised when web discovery search providers are temporarily unavailable."""


def _get_provider_state(name: str) -> dict[str, float | int]:
    state = _provider_state.get(name)
    if state is None:
        state = {"disabled_until": 0.0, "failures": 0}
        _provider_state[name] = state
    return state


def _provider_retry_wait_seconds(name: str) -> int:
    state = _get_provider_state(name)
    remaining = int(round(float(state.get("disabled_until", 0.0)) - time.time()))
    return max(remaining, 0)


def _record_provider_success(name: str) -> None:
    state = _get_provider_state(name)
    state["disabled_until"] = 0.0
    state["failures"] = 0


def _record_provider_failure(name: str) -> None:
    state = _get_provider_state(name)
    state["failures"] = int(state.get("failures", 0)) + 1
    state["disabled_until"] = time.time() + _PROVIDER_COOLDOWN_SECONDS


def _canonical_artist_id(conn, artist_id: int) -> int | None:
    row = conn.execute(
        "SELECT id, alias_of FROM cu_artists WHERE id = ?",
        (artist_id,),
    ).fetchone()
    if not row:
        return None
    return row["alias_of"] or row["id"]


def _decode_bing_redirect_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        return ""
    payload = token[2:] if token.startswith("a1") else token
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return decoded if decoded.startswith("http") else ""


def _extract_redirect_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    raw_url = html.unescape(raw_url).strip()
    parsed = urlparse(raw_url)
    host = (parsed.netloc or "").lower()
    if "duckduckgo.com" in host and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query or "")
        candidate = (qs.get("uddg") or [""])[0]
        return unquote(candidate) if candidate else ""
    if "bing.com" in host and parsed.path.startswith("/ck/a"):
        qs = parse_qs(parsed.query or "")
        token = (qs.get("u") or [""])[0]
        return _decode_bing_redirect_token(token)
    return raw_url


def _normalize_candidate_url(source_key: str, raw_url: str) -> str:
    url = _extract_redirect_url(raw_url).strip()
    if not url.startswith("http"):
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path or ""
    if source_key == "instagram":
        if host not in {"instagram.com"}:
            return ""
        first_seg = (path.strip("/").split("/") or [""])[0].lower()
        if first_seg in {"p", "reel", "stories", "explore", "accounts", "about"}:
            return ""
        if not first_seg:
            return ""
        return f"https://instagram.com/{first_seg}/"
    if source_key == "spotify":
        if host not in {"open.spotify.com", "spotify.com"}:
            return ""
        parts = [p for p in path.split("/") if p]
        artist_id = ""
        if len(parts) >= 2 and parts[0] == "artist":
            artist_id = parts[1]
        elif len(parts) >= 3 and parts[0].startswith("intl-") and parts[1] == "artist":
            artist_id = parts[2]
        if not artist_id:
            return ""
        artist_id = re.sub(r"[^A-Za-z0-9]", "", artist_id.strip())
        if not artist_id:
            return ""
        return f"https://open.spotify.com/artist/{artist_id}"
    return ""


def _search_duckduckgo_html(query: str, limit: int = 8) -> list[str]:
    resp = requests.get(
        "https://duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": _USER_AGENT},
        timeout=_SEARCH_TIMEOUT_DDG,
    )
    resp.raise_for_status()
    hrefs = re.findall(r'href="([^"]+)"', resp.text)
    urls: list[str] = []
    for href in hrefs:
        extracted = _extract_redirect_url(href)
        if extracted.startswith("http"):
            urls.append(extracted)
        if len(urls) >= limit:
            break
    return urls


def _search_duckduckgo_via_jina(query: str, limit: int = 8) -> list[str]:
    target = f"http://duckduckgo.com/html/?q={quote(query)}"
    resp = requests.get(
        f"https://r.jina.ai/{target}",
        headers={"User-Agent": _USER_AGENT},
        timeout=_SEARCH_TIMEOUT_JINA,
    )
    resp.raise_for_status()
    links = re.findall(r"\((https?://[^)\s]+)\)", resp.text)
    urls: list[str] = []
    for raw in links:
        extracted = _extract_redirect_url(raw)
        if extracted.startswith("http"):
            urls.append(extracted)
        if len(urls) >= limit:
            break
    return urls


def _search_bing_html(query: str, limit: int = 8) -> list[str]:
    resp = requests.get(
        "https://www.bing.com/search",
        params={"q": query},
        headers={"User-Agent": _USER_AGENT},
        timeout=_SEARCH_TIMEOUT_BING,
    )
    resp.raise_for_status()
    chunks = resp.text.split('<li class="b_algo"')
    urls: list[str] = []
    for chunk in chunks[1:]:
        match = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"', chunk, re.IGNORECASE)
        if not match:
            continue
        extracted = _extract_redirect_url(match.group(1))
        if extracted.startswith("http"):
            urls.append(extracted)
        if len(urls) >= limit:
            break
    return urls


def _search_providers() -> tuple[tuple[str, callable], ...]:
    return (
        ("duckduckgo_via_jina", _search_duckduckgo_via_jina),
        ("duckduckgo_html", _search_duckduckgo_html),
        ("bing_html", _search_bing_html),
    )


def _search_web(query: str, limit: int = 8) -> list[str]:
    had_live_provider = False
    cooldowns: list[int] = []
    errors: list[str] = []
    for provider_name, provider_fn in _search_providers():
        wait_seconds = _provider_retry_wait_seconds(provider_name)
        if wait_seconds > 0:
            cooldowns.append(wait_seconds)
            continue
        try:
            urls = provider_fn(query, limit=limit)
            had_live_provider = True
            _record_provider_success(provider_name)
            if urls:
                return urls
        except requests.RequestException as exc:
            _record_provider_failure(provider_name)
            logger.warning(
                "Web discovery request failed for provider=%s query=%r: %s",
                provider_name,
                query,
                exc,
            )
            errors.append(provider_name)
        except Exception as exc:
            _record_provider_failure(provider_name)
            logger.warning(
                "Unexpected discovery error for provider=%s query=%r: %s",
                provider_name,
                query,
                exc,
            )
            errors.append(provider_name)
    if had_live_provider:
        return []
    retry_wait = min(cooldowns) if cooldowns else _PROVIDER_COOLDOWN_SECONDS
    if errors:
        raise DiscoveryProviderUnavailable(
            f"Web discovery providers temporarily unavailable ({', '.join(errors)}); retry in ~{retry_wait}s"
        )
    raise DiscoveryProviderUnavailable(
        f"Web discovery providers temporarily unavailable; retry in ~{retry_wait}s"
    )


def _score_candidate(artist_name: str, source_key: str, url: str, query: str) -> float:
    score = 50.0
    parsed = urlparse(url)
    path_lower = (parsed.path or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", artist_name.lower()) if len(t) >= 3]
    token_hits = sum(1 for t in tokens if t in path_lower)
    score += min(30.0, token_hits * 10.0)
    if source_key == "spotify" and "/artist/" in path_lower:
        score += 10.0
    if source_key == "instagram" and path_lower.count("/") <= 2:
        score += 10.0
    if "vancouver" in query.lower():
        score += 3.0
    return round(min(score, 100.0), 2)


def _queries_for(source_key: str, artist_name: str) -> list[str]:
    if source_key == "instagram":
        return [
            f'site:instagram.com "{artist_name}" music',
            f'site:instagram.com "{artist_name}" vancouver',
        ]
    if source_key == "spotify":
        return [
            f'site:open.spotify.com/artist "{artist_name}"',
            f'site:open.spotify.com "{artist_name}" music',
            f'"{artist_name}" "open.spotify.com/artist"',
        ]
    return []


def discover_best_profile_url(artist_name: str, source_key: str) -> dict | None:
    source_key = (source_key or "").strip().lower()
    if source_key not in _SUPPORTED_SOURCES or not artist_name.strip():
        return None
    best: dict | None = None
    seen: set[str] = set()
    for query in _queries_for(source_key, artist_name.strip()):
        for raw_url in _search_web(query, limit=12):
            normalized = _normalize_candidate_url(source_key, raw_url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            score = _score_candidate(artist_name, source_key, normalized, query)
            if best is None or score > best["confidence_score"]:
                best = {
                    "candidate_url": normalized,
                    "confidence_score": score,
                    "query": query,
                }
                if score >= 70.0:
                    return best
    return best


def discover_artist_link_candidates(
    artist_id: int,
    source_keys: tuple[str, ...] = ("instagram", "spotify"),
    max_per_source: int = 5,
) -> dict:
    source_keys = tuple(k for k in source_keys if k in _SUPPORTED_SOURCES)
    if not source_keys:
        return {"error": "No supported sources requested"}
    with get_db() as conn:
        canonical_id = _canonical_artist_id(conn, artist_id)
        if not canonical_id:
            return {"error": "Artist not found"}
        row = conn.execute(
            "SELECT id, name FROM cu_artists WHERE id = ?",
            (canonical_id,),
        ).fetchone()
        artist_name = row["name"]
        created = 0
        per_source: dict[str, int] = {}
        for source_key in source_keys:
            seen: set[str] = set()
            source_created = 0
            try:
                for query in _queries_for(source_key, artist_name):
                    for raw_url in _search_web(query, limit=12):
                        normalized = _normalize_candidate_url(source_key, raw_url)
                        if not normalized or normalized in seen:
                            continue
                        seen.add(normalized)
                        confidence = _score_candidate(artist_name, source_key, normalized, query)
                        evidence = json.dumps({"query": query, "raw_url": raw_url}, ensure_ascii=False)
                        conn.execute(
                            """INSERT OR IGNORE INTO cu_artist_link_candidates
                               (artist_id, source_key, candidate_url, confidence_score, evidence_json)
                               VALUES (?, ?, ?, ?, ?)""",
                            (canonical_id, source_key, normalized, confidence, evidence),
                        )
                        if conn.execute("SELECT changes()").fetchone()[0] > 0:
                            created += 1
                            source_created += 1
                        if source_created >= max_per_source:
                            break
                    if source_created >= max_per_source:
                        break
            except DiscoveryProviderUnavailable as exc:
                return {
                    "artist_id": canonical_id,
                    "created": created,
                    "per_source": per_source,
                    "error": str(exc),
                }
            per_source[source_key] = source_created
    return {
        "artist_id": canonical_id,
        "created": created,
        "per_source": per_source,
    }


def list_artist_link_candidates(artist_id: int, status: str | None = "pending") -> list[dict]:
    with get_db() as conn:
        canonical_id = _canonical_artist_id(conn, artist_id)
        if not canonical_id:
            return []
        if status:
            rows = conn.execute(
                """SELECT * FROM cu_artist_link_candidates
                   WHERE artist_id = ? AND status = ?
                   ORDER BY confidence_score DESC, discovered_at DESC""",
                (canonical_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM cu_artist_link_candidates
                   WHERE artist_id = ?
                   ORDER BY status ASC, confidence_score DESC, discovered_at DESC""",
                (canonical_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def review_artist_link_candidate(candidate_id: int, action: str) -> dict:
    action = (action or "").strip().lower()
    if action not in {"approve", "reject"}:
        return {"error": "action must be approve or reject"}
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cu_artist_link_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if not row:
            return {"error": "Candidate not found"}
        source_key = row["source_key"]
        if source_key not in _SUPPORTED_SOURCES:
            return {"error": "Unsupported source key"}
        now_iso = datetime.utcnow().isoformat()
        if action == "approve":
            url_col = "instagram_url" if source_key == "instagram" else "spotify_url"
            checked_col = "instagram_checked_at" if source_key == "instagram" else "spotify_checked_at"
            conn.execute(
                f"UPDATE cu_artists SET {url_col} = ?, {checked_col} = NULL WHERE id = ?",
                (row["candidate_url"], row["artist_id"]),
            )
            conn.execute(
                """UPDATE cu_artist_link_candidates
                   SET status = 'rejected', reviewed_at = ?, reviewed_action = 'superseded'
                   WHERE artist_id = ? AND source_key = ? AND status = 'pending' AND id != ?""",
                (now_iso, row["artist_id"], source_key, candidate_id),
            )
            status = "approved"
        else:
            status = "rejected"
        conn.execute(
            """UPDATE cu_artist_link_candidates
               SET status = ?, reviewed_at = ?, reviewed_action = ?
               WHERE id = ?""",
            (status, now_iso, action, candidate_id),
        )
        updated = conn.execute(
            "SELECT * FROM cu_artist_link_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        return {"candidate": dict(updated), "action": action}
