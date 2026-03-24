"""Context document synthesis and storage for v0.9.4 object memory packs."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..db import get_db

_SNAPSHOT_KEYS = (
    "name",
    "title",
    "status",
    "due_date",
    "due_time",
    "project_id",
    "goal_id",
    "importance",
    "tags",
    "recurrence_rule",
    "start_time",
    "end_time",
    "source",
)


def _json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _object_row(object_id: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM objects WHERE object_id = ?",
            (object_id,),
        ).fetchone()


def _head_version(object_id: str):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT v.*
            FROM object_refs r
            JOIN object_versions v ON v.version_id = r.head_version_id
            WHERE r.object_id = ?
            """,
            (object_id,),
        ).fetchone()


def _recent_versions(object_id: str, limit: int = 5) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT version_id, version_num, snapshot_json, event_id, created_at
            FROM object_versions
            WHERE object_id = ?
            ORDER BY version_num DESC
            LIMIT ?
            """,
            (object_id, max(1, min(int(limit or 5), 50))),
        ).fetchall()
    versions: list[dict[str, Any]] = []
    for row in rows:
        versions.append(
            {
                "version_id": row["version_id"],
                "version_num": row["version_num"],
                "snapshot": _json_loads(row["snapshot_json"], {}),
                "event_id": row["event_id"],
                "created_at": row["created_at"],
            }
        )
    return versions


def _event_rows(event_ids: list[str]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    placeholders = ",".join("?" for _ in event_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT event_id, operation, summary, details_json, created_at
            FROM object_events
            WHERE event_id IN ({placeholders})
            ORDER BY created_at DESC
            """,
            event_ids,
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "event_id": row["event_id"],
                "operation": row["operation"],
                "summary": row["summary"],
                "details": _json_loads(row["details_json"], {}),
                "created_at": row["created_at"],
            }
        )
    return events


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in _SNAPSHOT_KEYS:
        value = snapshot.get(key)
        if value in (None, "", [], {}):
            continue
        compact[key] = value
    return compact


def _summary_for_object(object_id: str, object_type: str, snapshot: dict[str, Any]) -> str:
    label = str(snapshot.get("name") or snapshot.get("title") or object_id)
    state = str(snapshot.get("status") or "").strip()
    if state:
        return f"{object_type}:{label} ({state})"
    return f"{object_type}:{label}"


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {payload.get('summary') or payload.get('object_id')}")
    lines.append("## Object")
    lines.append(f"- id: {payload.get('object_id')}")
    lines.append(f"- type: {payload.get('object_type')}")
    lines.append(f"- typed_id: {payload.get('typed_id')}")
    lines.append(f"- review_state: {payload.get('review_state')}")
    lines.append("## Current Snapshot")
    compact = payload.get("current_compact_snapshot") or {}
    if isinstance(compact, dict) and compact:
        for key, value in compact.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- (no structured snapshot fields)")
    lines.append("## Recent Events")
    events = payload.get("recent_events") or []
    if isinstance(events, list) and events:
        for event in events[:5]:
            if not isinstance(event, dict):
                continue
            summary = event.get("summary") or event.get("operation") or "event"
            lines.append(f"- {event.get('created_at')}: {summary}")
    else:
        lines.append("- (no recent events)")
    return "\n".join(lines)


def build_object_context_doc(object_id: str) -> dict[str, Any] | None:
    object_row = _object_row(object_id)
    if object_row is None:
        return None

    object_type = object_row["object_type"]
    typed_id = object_row["typed_id"]
    review_state = object_row["review_state"]
    metadata = _json_loads(object_row["metadata_json"], {})
    if not isinstance(metadata, dict):
        metadata = {}

    head = _head_version(object_id)
    source_version_id = head["version_id"] if head else None
    source_event_id = head["event_id"] if head else None
    current_snapshot = _json_loads(head["snapshot_json"], {}) if head else {}
    if not isinstance(current_snapshot, dict):
        current_snapshot = {}

    versions = _recent_versions(object_id, limit=5)
    event_ids = [str(item.get("event_id")) for item in versions if item.get("event_id")]
    events = _event_rows(event_ids)
    generated_at = _now_iso()
    summary = _summary_for_object(object_id, object_type, current_snapshot)
    compact_snapshot = _compact_snapshot(current_snapshot)

    context_json = {
        "object_id": object_id,
        "object_type": object_type,
        "typed_id": typed_id,
        "review_state": review_state,
        "metadata": metadata,
        "summary": summary,
        "current_snapshot": current_snapshot,
        "current_compact_snapshot": compact_snapshot,
        "head_version_id": source_version_id,
        "head_event_id": source_event_id,
        "recent_versions": versions,
        "recent_events": events,
        "generated_at": generated_at,
    }
    markdown = _render_markdown(context_json)
    return {
        "object_id": object_id,
        "object_type": object_type,
        "typed_id": typed_id,
        "summary": summary,
        "context_json": context_json,
        "markdown": markdown,
        "source_version_id": source_version_id,
        "source_event_id": source_event_id,
        "generated_at": generated_at,
    }


def upsert_object_context_doc(doc: dict[str, Any]) -> dict[str, Any]:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO object_context_docs
            (object_id, object_type, typed_id, summary, context_json, markdown, source_version_id, source_event_id, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_id) DO UPDATE SET
                object_type = excluded.object_type,
                typed_id = excluded.typed_id,
                summary = excluded.summary,
                context_json = excluded.context_json,
                markdown = excluded.markdown,
                source_version_id = excluded.source_version_id,
                source_event_id = excluded.source_event_id,
                generated_at = excluded.generated_at
            """,
            (
                doc["object_id"],
                doc["object_type"],
                doc.get("typed_id"),
                doc.get("summary"),
                _json_dumps(doc.get("context_json") or {}),
                doc.get("markdown"),
                doc.get("source_version_id"),
                doc.get("source_event_id"),
                doc.get("generated_at") or _now_iso(),
            ),
        )
        row = conn.execute(
            """
            SELECT object_id, object_type, typed_id, summary, context_json, markdown, source_version_id, source_event_id, generated_at
            FROM object_context_docs
            WHERE object_id = ?
            """,
            (doc["object_id"],),
        ).fetchone()
    return {
        "object_id": row["object_id"],
        "object_type": row["object_type"],
        "typed_id": row["typed_id"],
        "summary": row["summary"],
        "context_json": _json_loads(row["context_json"], {}),
        "markdown": row["markdown"],
        "source_version_id": row["source_version_id"],
        "source_event_id": row["source_event_id"],
        "generated_at": row["generated_at"],
    }


def synthesize_object_context_doc(object_id: str) -> dict[str, Any] | None:
    doc = build_object_context_doc(object_id)
    if doc is None:
        return None
    return upsert_object_context_doc(doc)


def list_stale_object_ids(*, limit: int = 25) -> list[str]:
    bounded_limit = max(1, min(int(limit or 25), 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT o.object_id
            FROM objects o
            LEFT JOIN object_context_docs d ON d.object_id = o.object_id
            WHERE
                d.object_id IS NULL
                OR datetime(COALESCE(o.updated_at, o.created_at)) > datetime(d.generated_at)
            ORDER BY datetime(COALESCE(o.updated_at, o.created_at)) DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return [str(row["object_id"]) for row in rows if row["object_id"]]


def has_stale_context_docs() -> bool:
    return len(list_stale_object_ids(limit=1)) > 0


def synthesize_stale_context_docs(*, max_items: int = 5) -> dict[str, Any]:
    stale_ids = list_stale_object_ids(limit=max_items)
    generated: list[str] = []
    failed: list[dict[str, str]] = []
    for object_id in stale_ids:
        try:
            stored = synthesize_object_context_doc(object_id)
            if stored is not None:
                generated.append(object_id)
        except Exception as exc:
            failed.append({"object_id": object_id, "error": str(exc)})
    return {
        "checked_count": len(stale_ids),
        "generated_count": len(generated),
        "generated_object_ids": generated,
        "failed": failed,
    }


def get_object_context_doc(object_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT object_id, object_type, typed_id, summary, context_json, markdown, source_version_id, source_event_id, generated_at
            FROM object_context_docs
            WHERE object_id = ?
            """,
            (object_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "object_id": row["object_id"],
        "object_type": row["object_type"],
        "typed_id": row["typed_id"],
        "summary": row["summary"],
        "context_json": _json_loads(row["context_json"], {}),
        "markdown": row["markdown"],
        "source_version_id": row["source_version_id"],
        "source_event_id": row["source_event_id"],
        "generated_at": row["generated_at"],
    }


def list_object_context_docs(*, limit: int = 25, object_type: str | None = None) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit or 25), 200))
    params: list[Any] = []
    where_clause = ""
    if object_type:
        where_clause = "WHERE object_type = ?"
        params.append(str(object_type).strip().lower())
    params.append(bounded_limit)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT object_id, object_type, typed_id, summary, context_json, markdown, source_version_id, source_event_id, generated_at
            FROM object_context_docs
            {where_clause}
            ORDER BY datetime(generated_at) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [
        {
            "object_id": row["object_id"],
            "object_type": row["object_type"],
            "typed_id": row["typed_id"],
            "summary": row["summary"],
            "context_json": _json_loads(row["context_json"], {}),
            "markdown": row["markdown"],
            "source_version_id": row["source_version_id"],
            "source_event_id": row["source_event_id"],
            "generated_at": row["generated_at"],
        }
        for row in rows
    ]
