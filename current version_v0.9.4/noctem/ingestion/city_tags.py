"""City-tag helpers for Cor Unum artists."""
from __future__ import annotations


LOCAL_CITY_TAG = "YVR"


def set_city_tag(conn, artist_id: int, tag: str, enabled: bool) -> None:
    """Add or remove a city tag for an artist."""
    if enabled:
        conn.execute(
            "INSERT OR IGNORE INTO cu_artist_tags (artist_id, tag) VALUES (?, ?)",
            (artist_id, tag),
        )
    else:
        conn.execute(
            "DELETE FROM cu_artist_tags WHERE artist_id = ? AND tag = ?",
            (artist_id, tag),
        )


def set_local_yvr(conn, artist_id: int, is_local: bool) -> None:
    """Set YVR local tag for an artist."""
    set_city_tag(conn, artist_id, LOCAL_CITY_TAG, is_local)


def is_local_yvr(conn, artist_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM cu_artist_tags WHERE artist_id = ? AND tag = ? LIMIT 1",
        (artist_id, LOCAL_CITY_TAG),
    ).fetchone()
    return row is not None

