"""Conversation grounding state persistence backed by object/version history."""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from ..db import get_db

OBJECT_TYPE_CONVERSATION_STATE = "conversation_state"


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


def _object_id(thread_id: str) -> str:
    cleaned = str(thread_id or "").strip()
    if not cleaned:
        raise ValueError("thread_id is required")
    return f"{OBJECT_TYPE_CONVERSATION_STATE}:{cleaned}"


def _default_state(thread_id: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "last_scope_ref": None,
        "last_task_ids": [],
        "date_anchors": {},
        "last_operation": None,
        "updated_at": None,
        "source": None,
    }


def _normalize_state(thread_id: str, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    state = _default_state(thread_id)
    if isinstance(snapshot, dict):
        state.update(snapshot)
    state["thread_id"] = thread_id
    if not isinstance(state.get("last_task_ids"), list):
        state["last_task_ids"] = []
    if not isinstance(state.get("date_anchors"), dict):
        state["date_anchors"] = {}
    return state


def _state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    keys = set(before.keys()) | set(after.keys())
    diff: dict[str, dict[str, Any]] = {}
    for key in sorted(keys):
        if before.get(key) == after.get(key):
            continue
        diff[key] = {
            "before": before.get(key),
            "after": after.get(key),
        }
    return diff


def _record_event(
    *,
    operation: str,
    summary: str,
    details: dict[str, Any],
    object_id: str,
    correlation_id: str | None = None,
) -> str:
    event_id = f"audit-{uuid.uuid4().hex[:12]}"
    with get_db() as conn:
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
                _json_dumps(details),
                _json_dumps([]),
                correlation_id,
                _now_iso(),
            ),
        )
    return event_id


def _upsert_object_row(object_id: str, *, source: str | None) -> None:
    now_iso = _now_iso()
    metadata = {"source": source} if source else {}
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO objects (object_id, object_type, typed_id, metadata_json, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?, ?)
            ON CONFLICT(object_id) DO UPDATE SET
                object_type = excluded.object_type,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (object_id, OBJECT_TYPE_CONVERSATION_STATE, _json_dumps(metadata), now_iso, now_iso),
        )


def _head_snapshot(object_id: str) -> tuple[dict[str, Any] | None, str | None, int]:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT v.version_id, v.version_num, v.snapshot_json
            FROM object_refs r
            LEFT JOIN object_versions v ON v.version_id = r.head_version_id
            WHERE r.object_id = ?
            """,
            (object_id,),
        ).fetchone()
    if row is None:
        return None, None, 0
    snapshot = _json_loads(row["snapshot_json"], {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    return snapshot, row["version_id"], int(row["version_num"] or 0)


def _persist_state_version(
    *,
    object_id: str,
    snapshot: dict[str, Any],
    parent_version_id: str | None,
    parent_version_num: int,
    event_id: str,
    source: str | None,
) -> str:
    version_id = f"ov-{uuid.uuid4().hex[:16]}"
    now_iso = _now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO object_versions
            (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                object_id,
                int(parent_version_num) + 1,
                _json_dumps(snapshot),
                parent_version_id,
                event_id,
                source or "conversation",
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
    return version_id


def get_conversation_state(thread_id: str) -> dict[str, Any]:
    object_id = _object_id(thread_id)
    snapshot, _parent_id, _parent_num = _head_snapshot(object_id)
    return _normalize_state(thread_id, snapshot)


def record_grounding_read(
    *,
    thread_id: str,
    source: str,
    message_text: str | None = None,
    resolved: dict[str, Any] | None = None,
) -> str:
    state = get_conversation_state(thread_id)
    object_id = _object_id(thread_id)
    return _record_event(
        operation="conversation_state.read",
        summary="Grounding state consulted",
        details={
            "object_id": object_id,
            "thread_id": thread_id,
            "source": source,
            "message_text": message_text,
            "resolved": resolved or {},
            "state_snapshot": state,
        },
        object_id=object_id,
    )


def update_conversation_state(
    *,
    thread_id: str,
    source: str,
    updates: dict[str, Any],
    summary: str = "Grounding state updated",
    reason: str | None = None,
) -> dict[str, Any]:
    if not isinstance(updates, dict) or not updates:
        return get_conversation_state(thread_id)

    object_id = _object_id(thread_id)
    _upsert_object_row(object_id, source=source)
    previous_snapshot, parent_version_id, parent_version_num = _head_snapshot(object_id)
    before_state = _normalize_state(thread_id, previous_snapshot)
    after_state = deepcopy(before_state)
    after_state.update(deepcopy(updates))
    after_state["thread_id"] = thread_id
    after_state["source"] = source
    after_state["updated_at"] = _now_iso()
    after_state = _normalize_state(thread_id, after_state)
    diff = _state_diff(before_state, after_state)
    if not diff:
        return after_state

    event_id = _record_event(
        operation="conversation_state.update",
        summary=summary,
        details={
            "object_id": object_id,
            "thread_id": thread_id,
            "source": source,
            "reason": reason,
            "before_snapshot": before_state,
            "after_snapshot": after_state,
            "diff": diff,
        },
        object_id=object_id,
    )
    _persist_state_version(
        object_id=object_id,
        snapshot=after_state,
        parent_version_id=parent_version_id,
        parent_version_num=parent_version_num,
        event_id=event_id,
        source=source,
    )
    return after_state

