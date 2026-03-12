"""Unified durable execution queue helpers."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from statistics import median
from typing import Any

from ..db import get_db

QUEUE_STATUS_QUEUED = "queued"
QUEUE_STATUS_PROCESSING = "processing"
QUEUE_STATUS_COMPLETED = "completed"
QUEUE_STATUS_FAILED = "failed"
QUEUE_STATUS_REVIEW_BLOCKED = "review_blocked"
QUEUE_STATUS_CANCELLED = "cancelled"

QUEUE_ITEM_USER_MESSAGE = "user_message"
QUEUE_ITEM_SCHEDULED_JOB = "scheduled_job"
QUEUE_ITEM_REVIEW_RESUME = "review_resume"
QUEUE_ITEM_SYSTEM_RETRY = "system_retry"


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


def _coerce_status(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if value in {
        QUEUE_STATUS_QUEUED,
        QUEUE_STATUS_PROCESSING,
        QUEUE_STATUS_COMPLETED,
        QUEUE_STATUS_FAILED,
        QUEUE_STATUS_REVIEW_BLOCKED,
        QUEUE_STATUS_CANCELLED,
    }:
        return value
    return QUEUE_STATUS_QUEUED


def _queue_item_from_row(row, *, include_payload: bool = True) -> dict[str, Any]:
    payload = _json_loads(row["payload_json"], {}) if include_payload else None
    stale_context = _json_loads(row["stale_context_json"], {}) if include_payload else None
    result = _json_loads(row["result_json"], {}) if include_payload else None
    item = {
        "id": int(row["id"]),
        "item_type": row["item_type"],
        "source": row["source"],
        "thread_id": row["thread_id"],
        "status": row["status"],
        "attempt_count": int(row["attempt_count"] or 0),
        "idempotency_key": row["idempotency_key"],
        "priority_rank": int(row["priority_rank"] or 100),
        "available_at": row["available_at"],
        "review_created_at": row["review_created_at"],
        "last_error": row["last_error"],
        "locked_by": row["locked_by"],
        "locked_at": row["locked_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
    }
    if include_payload:
        item["payload"] = payload if isinstance(payload, dict) else {}
        item["stale_context"] = stale_context if isinstance(stale_context, dict) else {}
        item["result"] = result if isinstance(result, dict) else {}
    return item


def has_retryable_queue_items() -> bool:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM execution_queue
            WHERE status = 'queued'
              AND COALESCE(last_error, '') != ''
            LIMIT 1
            """
        ).fetchone()
    return row is not None


def enqueue_item(
    *,
    item_type: str,
    payload: dict[str, Any],
    source: str | None = None,
    thread_id: str | None = None,
    idempotency_key: str | None = None,
    priority_rank: int = 100,
    available_at: str | None = None,
    review_created_at: str | None = None,
    stale_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_payload = payload if isinstance(payload, dict) else {}
    queue_idempotency = idempotency_key or f"queue-{uuid.uuid4().hex[:16]}"
    now_iso = _now_iso()
    available_val = available_at or now_iso
    with get_db() as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM execution_queue
            WHERE idempotency_key = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (queue_idempotency,),
        ).fetchone()
        if existing is not None:
            return _queue_item_from_row(existing)
        conn.execute(
            """
            INSERT INTO execution_queue
            (
                item_type,
                source,
                thread_id,
                payload_json,
                status,
                attempt_count,
                idempotency_key,
                priority_rank,
                available_at,
                review_created_at,
                stale_context_json,
                created_at
            )
            VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item_type or "").strip() or QUEUE_ITEM_SYSTEM_RETRY,
                source,
                thread_id,
                _json_dumps(normalized_payload),
                queue_idempotency,
                int(priority_rank),
                available_val,
                review_created_at,
                _json_dumps(stale_context or {}),
                now_iso,
            ),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = last_insert_rowid()"
        ).fetchone()
    return _queue_item_from_row(row)


def enqueue_user_message(
    *,
    source: str,
    thread_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return enqueue_item(
        item_type=QUEUE_ITEM_USER_MESSAGE,
        source=source,
        thread_id=thread_id,
        payload={
            "content": str(content or "").strip(),
            "metadata": metadata or {},
        },
        idempotency_key=idempotency_key,
        priority_rank=100,
    )


def enqueue_scheduled_job(
    *,
    job_name: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return enqueue_item(
        item_type=QUEUE_ITEM_SCHEDULED_JOB,
        source="scheduler",
        thread_id=None,
        payload={
            "job_name": str(job_name or "").strip(),
            "payload": payload or {},
        },
        idempotency_key=idempotency_key,
        priority_rank=200,
    )


def enqueue_review_resume(
    *,
    workflow_id: int,
    review_id: str,
    resolution: str,
    thread_id: str | None = None,
    source: str = "review",
    review_created_at: str | None = None,
) -> dict[str, Any]:
    return enqueue_item(
        item_type=QUEUE_ITEM_REVIEW_RESUME,
        source=source,
        thread_id=thread_id,
        payload={
            "workflow_id": int(workflow_id),
            "review_id": str(review_id),
            "resolution": str(resolution or "").strip(),
        },
        idempotency_key=f"review-resume-{review_id}",
        priority_rank=0,
        review_created_at=review_created_at or _now_iso(),
    )


def list_queue_items(
    *,
    status: str | None = None,
    limit: int = 100,
    include_payload: bool = True,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit or 100), 1000))
    params: list[Any] = []
    where = ""
    if status is not None and str(status).strip().lower() != "all":
        where = "WHERE status = ?"
        params.append(_coerce_status(status))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM execution_queue
            {where}
            ORDER BY
                CASE
                    WHEN status = 'queued' THEN 0
                    WHEN status = 'processing' THEN 1
                    WHEN status = 'review_blocked' THEN 2
                    WHEN status = 'failed' THEN 3
                    ELSE 4
                END ASC,
                priority_rank ASC,
                datetime(COALESCE(review_created_at, created_at)) ASC,
                id ASC
            LIMIT ?
            """,
            [*params, bounded_limit],
        ).fetchall()
    return [_queue_item_from_row(row, include_payload=include_payload) for row in rows]


def claim_next_item(worker_id: str) -> dict[str, Any] | None:
    worker = str(worker_id or "").strip() or "worker"
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM execution_queue
            WHERE status = 'queued'
              AND datetime(available_at) <= datetime('now')
            ORDER BY priority_rank ASC, datetime(COALESCE(review_created_at, created_at)) ASC, id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        now_iso = _now_iso()
        result = conn.execute(
            """
            UPDATE execution_queue
            SET status = 'processing',
                attempt_count = attempt_count + 1,
                locked_by = ?,
                locked_at = ?,
                started_at = COALESCE(started_at, ?)
            WHERE id = ? AND status = 'queued'
            """,
            (worker, now_iso, now_iso, int(row["id"])),
        )
        if int(result.rowcount or 0) <= 0:
            return None
        claimed = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(row["id"]),),
        ).fetchone()
    return _queue_item_from_row(claimed)


def mark_item_completed(item_id: int, result_payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE execution_queue
            SET status = 'completed',
                result_json = ?,
                completed_at = ?,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = ?
            """,
            (_json_dumps(result_payload or {}), _now_iso(), int(item_id)),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    if not row:
        return None
    return _queue_item_from_row(row)


def mark_item_review_blocked(
    item_id: int,
    *,
    reason: str,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    blocked_payload = {"reason": str(reason or "").strip(), **(extra_payload or {})}
    with get_db() as conn:
        conn.execute(
            """
            UPDATE execution_queue
            SET status = 'review_blocked',
                result_json = ?,
                last_error = ?,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = ?
            """,
            (_json_dumps(blocked_payload), str(reason or ""), int(item_id)),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    if not row:
        return None
    return _queue_item_from_row(row)


def mark_item_retryable_failure(
    item_id: int,
    *,
    error: str,
    available_at: str | None = None,
) -> dict[str, Any] | None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE execution_queue
            SET status = 'queued',
                available_at = ?,
                last_error = ?,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = ?
            """,
            (available_at or _now_iso(), str(error or ""), int(item_id)),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    if not row:
        return None
    return _queue_item_from_row(row)


def mark_item_failed(item_id: int, *, error: str) -> dict[str, Any] | None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE execution_queue
            SET status = 'failed',
                last_error = ?,
                completed_at = ?,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = ?
            """,
            (str(error or ""), _now_iso(), int(item_id)),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    if not row:
        return None
    return _queue_item_from_row(row)


def cancel_item(item_id: int, *, reason: str | None = None) -> dict[str, Any] | None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE execution_queue
            SET status = 'cancelled',
                last_error = ?,
                completed_at = ?,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = ?
            """,
            (str(reason or ""), _now_iso(), int(item_id)),
        )
        row = conn.execute(
            "SELECT * FROM execution_queue WHERE id = ?",
            (int(item_id),),
        ).fetchone()
    if not row:
        return None
    return _queue_item_from_row(row)


def queue_metrics() -> dict[str, Any]:
    with get_db() as conn:
        counts_rows = conn.execute(
            """
            SELECT status, item_type, COUNT(*) AS count
            FROM execution_queue
            GROUP BY status, item_type
            """
        ).fetchall()
        queued_rows = conn.execute(
            """
            SELECT created_at, item_type
            FROM execution_queue
            WHERE status = 'queued'
            ORDER BY datetime(created_at) ASC
            """
        ).fetchall()
        review_rows = conn.execute(
            """
            SELECT created_at
            FROM execution_queue
            WHERE status = 'review_blocked'
            """
        ).fetchall()
        retryable_rows = conn.execute(
            """
            SELECT id
            FROM execution_queue
            WHERE status = 'queued'
              AND COALESCE(last_error, '') != ''
            """
        ).fetchall()

    now = datetime.utcnow()
    queued_ages_minutes: list[float] = []
    oldest_queued_age_minutes = None
    oldest_scheduled_age_minutes = None
    scheduled_ages: list[float] = []
    for row in queued_rows:
        try:
            created_dt = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            if created_dt.tzinfo is not None:
                created_dt = created_dt.replace(tzinfo=None)
        except Exception:
            continue
        age_min = max(0.0, (now - created_dt).total_seconds() / 60.0)
        queued_ages_minutes.append(age_min)
        if oldest_queued_age_minutes is None or age_min > oldest_queued_age_minutes:
            oldest_queued_age_minutes = age_min
        if row["item_type"] == QUEUE_ITEM_SCHEDULED_JOB:
            scheduled_ages.append(age_min)
            if oldest_scheduled_age_minutes is None or age_min > oldest_scheduled_age_minutes:
                oldest_scheduled_age_minutes = age_min

    review_ages: list[float] = []
    for row in review_rows:
        try:
            created_dt = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            if created_dt.tzinfo is not None:
                created_dt = created_dt.replace(tzinfo=None)
        except Exception:
            continue
        review_ages.append(max(0.0, (now - created_dt).total_seconds() / 60.0))

    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for row in counts_rows:
        status = str(row["status"] or "")
        item_type = str(row["item_type"] or "")
        count = int(row["count"] or 0)
        by_status[status] = by_status.get(status, 0) + count
        by_class[item_type] = by_class.get(item_type, 0) + count

    return {
        "total_count": sum(by_status.values()),
        "by_status": by_status,
        "by_class": by_class,
        "queued_count": by_status.get(QUEUE_STATUS_QUEUED, 0),
        "processing_count": by_status.get(QUEUE_STATUS_PROCESSING, 0),
        "review_blocked_count": by_status.get(QUEUE_STATUS_REVIEW_BLOCKED, 0),
        "queued_oldest_age_minutes": oldest_queued_age_minutes,
        "queued_median_age_minutes": median(queued_ages_minutes) if queued_ages_minutes else None,
        "scheduled_oldest_age_minutes": oldest_scheduled_age_minutes,
        "scheduled_queued_count": by_class.get(QUEUE_ITEM_SCHEDULED_JOB, 0),
        "review_blocked_avg_age_minutes": (sum(review_ages) / len(review_ages)) if review_ages else None,
        "retryable_with_errors_count": len(retryable_rows),
    }
