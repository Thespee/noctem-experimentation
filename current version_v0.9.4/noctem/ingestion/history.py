"""Cor Unum entity history tracking on top of Noctem object/event/version tables."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def object_id_for(entity_type: str, entity_id: int) -> str:
    return f"cu_{entity_type}:{int(entity_id)}"


def object_type_for(entity_type: str) -> str:
    return f"cu_{entity_type}"


def snapshot_event(conn, event_id: int) -> dict | None:
    row = conn.execute(
        """SELECT e.id, e.title, e.date, e.venue_id, e.description, e.created_at,
                  v.name AS venue_name
           FROM cu_events e
           LEFT JOIN cu_venues v ON v.id = e.venue_id
           WHERE e.id = ?""",
        (event_id,),
    ).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["performers"] = [
        dict(r)
        for r in conn.execute(
            """SELECT a.id, a.name
               FROM cu_event_performers ep
               JOIN cu_artists a ON a.id = ep.artist_id
               WHERE ep.event_id = ?
               ORDER BY a.name""",
            (event_id,),
        ).fetchall()
    ]
    payload["sources"] = [
        dict(r)
        for r in conn.execute(
            """SELECT id, source_type, source_url, source_fingerprint, captured_at
               FROM cu_event_sources
               WHERE event_id = ?
               ORDER BY id""",
            (event_id,),
        ).fetchall()
    ]
    return payload


def snapshot_artist(conn, artist_id: int) -> dict | None:
    row = conn.execute(
        """SELECT id, name, bio_link, soundcloud_url, instagram_url, spotify_url,
                  sc_followers, is_canadian, canadian, alias_of, created_at, last_seen
           FROM cu_artists
           WHERE id = ?""",
        (artist_id,),
    ).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["city_tags"] = [
        r["tag"]
        for r in conn.execute(
            "SELECT tag FROM cu_artist_tags WHERE artist_id = ? ORDER BY tag",
            (artist_id,),
        ).fetchall()
    ]
    payload["event_ids"] = [
        r["event_id"]
        for r in conn.execute(
            "SELECT event_id FROM cu_event_performers WHERE artist_id = ? ORDER BY event_id",
            (artist_id,),
        ).fetchall()
    ]
    return payload


def snapshot_venue(conn, venue_id: int) -> dict | None:
    row = conn.execute(
        """SELECT id, name, address, url, is_verified, alias_of, created_at
           FROM cu_venues
           WHERE id = ?""",
        (venue_id,),
    ).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["event_ids"] = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM cu_events WHERE venue_id = ? ORDER BY date, id",
            (venue_id,),
        ).fetchall()
    ]
    return payload


def snapshot_for_entity(conn, entity_type: str, entity_id: int) -> dict | None:
    normalized = str(entity_type or "").strip().lower()
    if normalized == "event":
        return snapshot_event(conn, entity_id)
    if normalized == "artist":
        return snapshot_artist(conn, entity_id)
    if normalized == "venue":
        return snapshot_venue(conn, entity_id)
    return None


def _ensure_object_row(conn, *, object_id: str, object_type: str, typed_id: int, now_iso: str) -> None:
    conn.execute(
        """
        INSERT INTO objects (object_id, object_type, typed_id, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(object_id) DO UPDATE SET
            object_type = excluded.object_type,
            typed_id = excluded.typed_id,
            updated_at = excluded.updated_at
        """,
        (object_id, object_type, typed_id, None, now_iso, now_iso),
    )


def record_entity_change(
    conn,
    *,
    entity_type: str,
    entity_id: int,
    operation: str,
    summary: str,
    actor: str,
    details: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = str(entity_type or "").strip().lower()
    typed_id = int(entity_id)
    object_id = object_id_for(normalized, typed_id)
    object_type = object_type_for(normalized)
    now_iso = _now_iso()
    snapshot_payload = snapshot if snapshot is not None else snapshot_for_entity(conn, normalized, typed_id)
    if snapshot_payload is None:
        snapshot_payload = {"id": typed_id, "deleted": True}
    snapshot_json = _json_dumps(snapshot_payload)

    event_id = f"cu-event-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO object_events
        (event_id, operation, summary, details_json, undo_actions_json, correlation_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            operation,
            summary,
            _json_dumps(details or {}),
            _json_dumps([]),
            None,
            now_iso,
        ),
    )

    _ensure_object_row(conn, object_id=object_id, object_type=object_type, typed_id=typed_id, now_iso=now_iso)
    head = conn.execute(
        """
        SELECT v.version_id, v.version_num, v.snapshot_json
        FROM object_refs r
        LEFT JOIN object_versions v ON v.version_id = r.head_version_id
        WHERE r.object_id = ?
        """,
        (object_id,),
    ).fetchone()
    if head and head["snapshot_json"] == snapshot_json:
        conn.execute(
            "UPDATE objects SET updated_at = ? WHERE object_id = ?",
            (now_iso, object_id),
        )
        return {"event_id": event_id, "version_id": head["version_id"], "object_id": object_id}

    parent_version_id = head["version_id"] if head else None
    next_version_num = int(head["version_num"]) + 1 if head and head["version_num"] is not None else 1
    version_id = f"cu-version-{uuid.uuid4().hex[:16]}"
    conn.execute(
        """
        INSERT INTO object_versions
        (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id,
            object_id,
            next_version_num,
            snapshot_json,
            parent_version_id,
            event_id,
            actor,
            now_iso,
        ),
    )
    conn.execute(
        """
        INSERT INTO object_refs (object_id, head_version_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(object_id) DO UPDATE SET
            head_version_id = excluded.head_version_id,
            updated_at = excluded.updated_at
        """,
        (object_id, version_id, now_iso),
    )
    conn.execute(
        "UPDATE objects SET updated_at = ? WHERE object_id = ?",
        (now_iso, object_id),
    )
    return {"event_id": event_id, "version_id": version_id, "object_id": object_id}


def list_entity_history(conn, *, entity_type: str, entity_id: int, limit: int = 40) -> list[dict]:
    object_id = object_id_for(entity_type, entity_id)
    bounded_limit = max(1, min(int(limit), 200))
    rows = conn.execute(
        """
        SELECT v.version_id, v.version_num, v.snapshot_json, v.parent_version_id,
               v.event_id, v.created_by, v.created_at,
               e.operation, e.summary, e.details_json
        FROM object_versions v
        LEFT JOIN object_events e ON e.event_id = v.event_id
        WHERE v.object_id = ?
        ORDER BY v.version_num DESC
        LIMIT ?
        """,
        (object_id, bounded_limit),
    ).fetchall()
    history: list[dict] = []
    for row in rows:
        history.append(
            {
                "object_id": object_id,
                "version_id": row["version_id"],
                "version_num": row["version_num"],
                "parent_version_id": row["parent_version_id"],
                "event_id": row["event_id"],
                "operation": row["operation"],
                "summary": row["summary"],
                "details": _json_loads(row["details_json"], {}),
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "snapshot": _json_loads(row["snapshot_json"], {}),
            }
        )
    return history
