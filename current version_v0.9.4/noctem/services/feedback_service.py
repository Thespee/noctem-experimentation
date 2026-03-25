"""Singleton feedback document service.

Maintains exactly one feedback_doc object in the object-core tables.
New entries are prepended (newest first) with &&& delimiters.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from ..db import get_db

_OBJECT_TYPE = "feedback_doc"
_SINGLETON_OBJECT_ID = "feedback_doc:1"
_DELIMITER = "&&&"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _ensure_singleton(conn) -> str:
    """Ensure the singleton feedback_doc object + initial version exist. Returns object_id."""
    row = conn.execute(
        "SELECT object_id FROM objects WHERE object_id = ?",
        (_SINGLETON_OBJECT_ID,),
    ).fetchone()
    if row:
        return _SINGLETON_OBJECT_ID

    now = _now_iso()
    # Create the object row
    conn.execute(
        """
        INSERT INTO objects (object_id, object_type, typed_id, metadata_json, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (_SINGLETON_OBJECT_ID, _OBJECT_TYPE, _json_dumps({"singleton": True}), now, now),
    )
    # Create genesis version with empty body
    version_id = f"ov-{uuid.uuid4().hex[:16]}"
    snapshot = {"body": ""}
    conn.execute(
        """
        INSERT INTO object_versions
        (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
        VALUES (?, ?, 1, ?, NULL, NULL, 'system', ?)
        """,
        (version_id, _SINGLETON_OBJECT_ID, _json_dumps(snapshot), now),
    )
    # Set head ref
    conn.execute(
        """
        INSERT INTO object_refs (object_id, head_version_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(object_id) DO UPDATE SET
            head_version_id = excluded.head_version_id,
            updated_at = excluded.updated_at
        """,
        (_SINGLETON_OBJECT_ID, version_id, now),
    )
    return _SINGLETON_OBJECT_ID


def _get_head_body(conn) -> tuple[str, str | None, int]:
    """Return (body_text, head_version_id, head_version_num) for the singleton."""
    _ensure_singleton(conn)
    row = conn.execute(
        """
        SELECT v.version_id, v.version_num, v.snapshot_json
        FROM object_refs r
        JOIN object_versions v ON v.version_id = r.head_version_id
        WHERE r.object_id = ?
        """,
        (_SINGLETON_OBJECT_ID,),
    ).fetchone()
    if not row:
        return "", None, 0
    try:
        snapshot = json.loads(row["snapshot_json"])
    except Exception:
        snapshot = {}
    body = snapshot.get("body", "") if isinstance(snapshot, dict) else ""
    return body, row["version_id"], int(row["version_num"])


def _commit_body(conn, body: str, parent_version_id: str | None, parent_version_num: int, source: str = "fast_path") -> str:
    """Write a new version with the given body. Returns the new version_id."""
    now = _now_iso()
    version_id = f"ov-{uuid.uuid4().hex[:16]}"
    next_num = parent_version_num + 1
    snapshot = {"body": body}

    # Record an event
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO object_events (event_id, operation, summary, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event_id, "feedback_doc.update", "Feedback doc updated", _json_dumps({"source": source}), now),
    )

    conn.execute(
        """
        INSERT INTO object_versions
        (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (version_id, _SINGLETON_OBJECT_ID, next_num, _json_dumps(snapshot), parent_version_id, event_id, source, now),
    )
    conn.execute(
        """
        INSERT INTO object_refs (object_id, head_version_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(object_id) DO UPDATE SET
            head_version_id = excluded.head_version_id,
            updated_at = excluded.updated_at
        """,
        (_SINGLETON_OBJECT_ID, version_id, now),
    )
    conn.execute(
        """
        UPDATE objects SET updated_at = ? WHERE object_id = ?
        """,
        (now, _SINGLETON_OBJECT_ID),
    )
    return version_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepend_feedback(text: str, *, source: str = "fast_path") -> dict[str, Any]:
    """Prepend *text* to the singleton feedback doc. Returns status dict."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_feedback"}

    with get_db() as conn:
        body, head_vid, head_vnum = _get_head_body(conn)
        existing = body.strip()
        if not existing:
            # First entry: surround with &&& above and below for consistency
            new_body = _DELIMITER + "\n" + text + "\n" + _DELIMITER
        elif existing.startswith(_DELIMITER):
            # Existing already opens with &&&; it acts as the "below" delimiter
            new_body = _DELIMITER + "\n" + text + "\n" + existing
        else:
            # Existing has no leading delimiter; add &&& on both sides of new entry
            new_body = _DELIMITER + "\n" + text + "\n" + _DELIMITER + "\n" + existing
        vid = _commit_body(conn, new_body, head_vid, head_vnum, source=source)

    return {"ok": True, "version_id": vid}


def get_feedback_text() -> str:
    """Return the full raw text of the feedback doc."""
    with get_db() as conn:
        body, _, _ = _get_head_body(conn)
    return body


def save_feedback_body(body: str, *, source: str = "web") -> dict[str, Any]:
    """Overwrite the singleton feedback doc with *body* as-is. Returns status dict."""
    with get_db() as conn:
        _, head_vid, head_vnum = _get_head_body(conn)
        vid = _commit_body(conn, body, head_vid, head_vnum, source=source)
    return {"ok": True, "version_id": vid}


def export_feedback() -> dict[str, Any]:
    """Export the feedback doc content for downstream consumption."""
    with get_db() as conn:
        body, head_vid, head_vnum = _get_head_body(conn)
    return {
        "object_id": _SINGLETON_OBJECT_ID,
        "version_id": head_vid,
        "version_num": head_vnum,
        "body": body,
    }
