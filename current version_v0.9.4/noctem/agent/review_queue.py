"""Manual review queue helpers for interrupted workflows and verification failures."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ..db import get_db

_REASON_CODES = {
    "ambiguity",
    "policy_gate",
    "verification_failure",
    "merge_conflict",
    "manual_review",
    "approval",
    "clarification",
    "plan_review",
}

_REASON_CODE_CATEGORY = {
    "approval": "approval",
    "policy_gate": "approval",
    "clarification": "clarification",
    "ambiguity": "clarification",
    "plan_review": "plan_review",
    "verification_failure": "verification",
    "merge_conflict": "verification",
    "manual_review": "manual_review",
}
_STATUSES = {"pending", "approved", "rejected", "resolved"}


def _json_dumps(payload: Any) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads(payload: str | None) -> Any:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}


def _normalize_reason_code(reason_code: str | None) -> str:
    normalized = str(reason_code or "").strip().lower()
    if normalized in _REASON_CODES:
        return normalized
    return "manual_review"


def _normalize_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in _STATUSES:
        return normalized
    return "pending"


def _review_from_row(row) -> dict[str, Any]:
    payload = _json_loads(row["payload_json"])
    if not isinstance(payload, dict):
        payload = {}
    reason_code = row["reason_code"]
    return {
        "review_id": row["review_id"],
        "object_id": row["object_id"],
        "event_id": row["event_id"],
        "reason_code": reason_code,
        "category": _REASON_CODE_CATEGORY.get(reason_code, "manual_review"),
        "status": row["status"],
        "payload": payload,
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "resolution_notes": row["resolution_notes"],
    }


def _set_object_review_state(object_id: str | None, review_state: str) -> None:
    if not object_id:
        return
    with get_db() as conn:
        conn.execute(
            """
            UPDATE objects
            SET review_state = ?, updated_at = CURRENT_TIMESTAMP
            WHERE object_id = ?
            """,
            (review_state, object_id),
        )


def create_review_item(
    *,
    reason_code: str,
    payload: dict[str, Any] | None = None,
    object_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    review_id = f"review-{uuid.uuid4().hex[:12]}"
    normalized_reason = _normalize_reason_code(reason_code)
    serialized_payload = _json_dumps(payload or {})
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO review_queue
            (review_id, object_id, event_id, reason_code, status, payload_json)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (review_id, object_id, event_id, normalized_reason, serialized_payload),
        )
        row = conn.execute(
            "SELECT * FROM review_queue WHERE review_id = ?",
            (review_id,),
        ).fetchone()
    _set_object_review_state(object_id, "manual_review")
    return _review_from_row(row)


def get_review_item(review_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM review_queue WHERE review_id = ?",
            (review_id,),
        ).fetchone()
    if not row:
        return None
    return _review_from_row(row)


def list_review_items(
    *,
    status: str | None = "pending",
    reason_code: str | None = None,
    workflow_id: int | None = None,
    interrupt_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    normalized_status = None
    if status is not None:
        if str(status).strip().lower() != "all":
            normalized_status = _normalize_status(status)
    if normalized_status:
        clauses.append("status = ?")
        params.append(normalized_status)

    normalized_reason = None
    if reason_code is not None:
        normalized_reason = _normalize_reason_code(reason_code)
    if normalized_reason:
        clauses.append("reason_code = ?")
        params.append(normalized_reason)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit or 100), 1000))

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM review_queue
            {where_clause}
            ORDER BY created_at DESC, review_id DESC
            LIMIT ?
            """,
            [*params, bounded_limit],
        ).fetchall()

    items = [_review_from_row(row) for row in rows]
    if workflow_id is None and interrupt_id is None:
        return items

    filtered: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if workflow_id is not None:
            try:
                if int(payload.get("workflow_id", -1)) != int(workflow_id):
                    continue
            except Exception:
                continue
        if interrupt_id is not None:
            try:
                if int(payload.get("interrupt_id", -1)) != int(interrupt_id):
                    continue
            except Exception:
                continue
        filtered.append(item)
    return filtered


def resolve_review_item(
    review_id: str,
    *,
    status: str = "resolved",
    resolution_notes: str | None = None,
) -> dict[str, Any] | None:
    normalized_status = _normalize_status(status)
    if normalized_status == "pending":
        raise ValueError("Cannot resolve a review item back to pending status")

    with get_db() as conn:
        conn.execute(
            """
            UPDATE review_queue
            SET status = ?, resolved_at = CURRENT_TIMESTAMP, resolution_notes = ?
            WHERE review_id = ? AND status = 'pending'
            """,
            (normalized_status, resolution_notes, review_id),
        )
        row = conn.execute(
            "SELECT * FROM review_queue WHERE review_id = ?",
            (review_id,),
        ).fetchone()
    if not row:
        return None

    item = _review_from_row(row)
    if item.get("status") != "pending":
        _set_object_review_state(item.get("object_id"), "resolved")
    return item


def resolve_reviews_for_interrupt(
    interrupt_id: int,
    *,
    status: str = "resolved",
    resolution_notes: str | None = None,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    candidates = list_review_items(status="pending", interrupt_id=interrupt_id, limit=500)
    for item in candidates:
        updated = resolve_review_item(
            item["review_id"],
            status=status,
            resolution_notes=resolution_notes,
        )
        if updated is not None:
            resolved.append(updated)
    return resolved


def resolve_reviews_for_workflow(
    workflow_id: int,
    *,
    status: str = "resolved",
    resolution_notes: str | None = None,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    candidates = list_review_items(status="pending", workflow_id=workflow_id, limit=500)
    for item in candidates:
        updated = resolve_review_item(
            item["review_id"],
            status=status,
            resolution_notes=resolution_notes,
        )
        if updated is not None:
            resolved.append(updated)
    return resolved


def list_blocked_workflows(*, limit: int = 100) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit or 100), 500))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                w.id AS workflow_id,
                w.workflow_type,
                w.status AS workflow_status,
                w.current_node,
                w.thread_id,
                w.input_text,
                w.updated_at,
                i.id AS interrupt_id,
                i.interrupt_type,
                i.question,
                i.options,
                i.context,
                i.created_at AS interrupted_at
            FROM agent_interrupts i
            JOIN agent_workflows w ON w.id = i.workflow_id
            WHERE i.resolved_at IS NULL
            ORDER BY i.created_at ASC, i.id ASC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()

    pending_reviews = list_review_items(status="pending", limit=1000)
    reviews_by_interrupt: dict[int, list[dict[str, Any]]] = {}
    reviews_by_workflow: dict[int, list[dict[str, Any]]] = {}
    for review in pending_reviews:
        payload = review.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        interrupt_id = payload.get("interrupt_id")
        workflow_id = payload.get("workflow_id")
        try:
            if interrupt_id is not None:
                reviews_by_interrupt.setdefault(int(interrupt_id), []).append(review)
        except Exception:
            pass
        try:
            if workflow_id is not None:
                reviews_by_workflow.setdefault(int(workflow_id), []).append(review)
        except Exception:
            pass

    blocked: list[dict[str, Any]] = []
    for row in rows:
        context = _json_loads(row["context"])
        if not isinstance(context, dict):
            context = {}
        options = _json_loads(row["options"])
        if not isinstance(options, list):
            options = []
        interrupt_id = int(row["interrupt_id"])
        workflow_id = int(row["workflow_id"])
        reviews = reviews_by_interrupt.get(interrupt_id) or reviews_by_workflow.get(workflow_id) or []
        blocked.append(
            {
                "workflow_id": workflow_id,
                "workflow_type": row["workflow_type"],
                "workflow_status": row["workflow_status"],
                "current_node": row["current_node"],
                "thread_id": row["thread_id"],
                "input_text": row["input_text"],
                "updated_at": row["updated_at"],
                "interrupt": {
                    "id": interrupt_id,
                    "type": row["interrupt_type"],
                    "question": row["question"],
                    "options": options,
                    "context": context,
                    "created_at": row["interrupted_at"],
                },
                "reviews": reviews,
            }
        )
    return blocked
