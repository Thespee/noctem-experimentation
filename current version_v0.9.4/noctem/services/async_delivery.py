"""Async delivery publication helpers for queue-processed assistant outputs."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

import requests

from ..config import Config
from ..db import get_db
from .conversation_service import record_message
from .execution_queue import QUEUE_ITEM_SCHEDULED_JOB, QUEUE_ITEM_USER_MESSAGE

logger = logging.getLogger(__name__)
_SCHEDULED_CHAT_SUPPRESSION_REASON = "scheduled_job_hidden_from_chat_channels"
_TELEGRAM_SEND_ATTEMPTS = 3
_TELEGRAM_SEND_TIMEOUT_SECONDS = 10


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


def _should_suppress_chat_publication(item_type: str) -> bool:
    return str(item_type or "").strip().lower() == QUEUE_ITEM_SCHEDULED_JOB


def _send_telegram_message_with_retries(*, token: str, chat_id: str, text: str) -> tuple[str, str | None]:
    last_error = "telegram_send_failed"
    for attempt in range(_TELEGRAM_SEND_ATTEMPTS):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=_TELEGRAM_SEND_TIMEOUT_SECONDS + attempt * 2,
            )
            if response.ok:
                return "delivered", None

            response_payload = {}
            try:
                loaded = response.json()
                if isinstance(loaded, dict):
                    response_payload = loaded
            except Exception:
                response_payload = {}

            description = str(
                response_payload.get("description")
                or response.text
                or "telegram_send_failed"
            )
            retry_after = (
                (response_payload.get("parameters") or {}).get("retry_after")
                if isinstance(response_payload.get("parameters"), dict)
                else None
            )
            if retry_after:
                description = f"{description} (retry_after={retry_after}s)"
            last_error = description

            status_code = int(response.status_code or 0)
            retryable_status = {408, 409, 425, 429, 500, 502, 503, 504}
            if status_code not in retryable_status:
                break
            if retry_after:
                try:
                    time.sleep(min(max(float(retry_after), 0.2), 3.0))
                    continue
                except Exception:
                    pass
        except Exception as exc:
            last_error = str(exc)
        if attempt < (_TELEGRAM_SEND_ATTEMPTS - 1):
            time.sleep(0.4 * (attempt + 1))
    return "failed", last_error


def _record_delivery(
    *,
    queue_item_id: int | None,
    thread_id: str | None,
    channel: str,
    status: str,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO delivery_publications
            (queue_item_id, thread_id, channel, status, payload_json, error, delivered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(queue_item_id) if queue_item_id is not None else None,
                thread_id,
                str(channel),
                str(status),
                _json_dumps(payload or {}),
                error,
                _now_iso() if status == "delivered" else None,
            ),
        )
        row = conn.execute(
            """
            SELECT id, queue_item_id, thread_id, channel, status, payload_json, error, created_at, delivered_at
            FROM delivery_publications
            WHERE id = last_insert_rowid()
            """
        ).fetchone()
    return {
        "id": int(row["id"]),
        "queue_item_id": row["queue_item_id"],
        "thread_id": row["thread_id"],
        "channel": row["channel"],
        "status": row["status"],
        "payload": _json_loads(row["payload_json"], {}),
        "error": row["error"],
        "created_at": row["created_at"],
        "delivered_at": row["delivered_at"],
    }


def publish_queue_result(queue_item: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    queue_item_id = queue_item.get("id")
    item_type = str(queue_item.get("item_type") or "").strip().lower()
    thread_id = str(result.get("thread_id") or queue_item.get("thread_id") or "").strip() or None
    suppress_chat_channels = _should_suppress_chat_publication(item_type)
    response_text = str(result.get("response") or "").strip()
    if not response_text:
        response_text = str(result.get("error") or "").strip()
    if not response_text:
        return []

    deliveries: list[dict[str, Any]] = []
    payload = {
        "status": result.get("status"),
        "job_name": result.get("job_name"),
        "mode": result.get("mode"),
    }

    if suppress_chat_channels:
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="web",
                status="skipped",
                payload={**payload, "reason": _SCHEDULED_CHAT_SUPPRESSION_REASON},
            )
        )
    elif item_type == QUEUE_ITEM_USER_MESSAGE:
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="web",
                status="skipped",
                payload={**payload, "reason": "already_recorded_in_chat_history"},
            )
        )
    else:
        try:
            record_message(
                content=response_text,
                role="assistant",
                source="web",
                session_id=thread_id or "alfred-main",
                metadata={
                    "delivery": "async",
                    "queue_item_id": queue_item_id,
                    "channel": "web",
                    "status": result.get("status"),
                    "job_name": result.get("job_name"),
                },
            )
            deliveries.append(
                _record_delivery(
                    queue_item_id=queue_item_id,
                    thread_id=thread_id,
                    channel="web",
                    status="delivered",
                    payload=payload,
                )
            )
        except Exception as exc:
            deliveries.append(
                _record_delivery(
                    queue_item_id=queue_item_id,
                    thread_id=thread_id,
                    channel="web",
                    status="failed",
                    payload=payload,
                    error=str(exc),
                )
            )

    if suppress_chat_channels:
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="telegram",
                status="skipped",
                payload={**payload, "reason": _SCHEDULED_CHAT_SUPPRESSION_REASON},
            )
        )
        return deliveries
    token = Config.telegram_token()
    chat_id = Config.telegram_chat_id()
    if not token or not chat_id:
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="telegram",
                status="skipped",
                payload={**payload, "reason": "telegram_not_configured"},
            )
        )
        return deliveries


    try:
        delivery_status, delivery_error = _send_telegram_message_with_retries(
            token=token,
            chat_id=chat_id,
            text=response_text,
        )
        if delivery_status == "delivered":
            deliveries.append(
                _record_delivery(
                    queue_item_id=queue_item_id,
                    thread_id=thread_id,
                    channel="telegram",
                    status="delivered",
                    payload=payload,
                )
            )
        else:
            deliveries.append(
                _record_delivery(
                    queue_item_id=queue_item_id,
                    thread_id=thread_id,
                    channel="telegram",
                    status="failed",
                    payload=payload,
                    error=str(delivery_error or "telegram_send_failed"),
                )
            )
    except Exception as exc:
        logger.debug("Telegram async delivery failed: %s", exc)
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="telegram",
                status="failed",
                payload=payload,
                error=str(exc),
            )
        )
    return deliveries


def publish_review_notification(review_item: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish a review notification to web (conversation record) + Telegram."""
    if not review_item:
        return []

    review_id = review_item.get("review_id") or "unknown"
    reason_code = review_item.get("reason_code") or "manual_review"
    category = review_item.get("category") or reason_code
    payload_data = review_item.get("payload") if isinstance(review_item.get("payload"), dict) else {}
    question = (
        str(payload_data.get("question") or payload_data.get("failure_message") or "").strip()
        or f"Review required ({reason_code})"
    )
    workflow_id = payload_data.get("workflow_id")

    notification_text = (
        f"\u26a0\ufe0f Review needed [{category}]: {question}\n"
        f"Review ID: {review_id}"
        + (f" | Workflow: #{workflow_id}" if workflow_id is not None else "")
        + "\nResolve via /control"
    )

    deliveries: list[dict[str, Any]] = []
    delivery_payload = {
        "review_id": review_id,
        "reason_code": reason_code,
        "category": category,
        "notification_type": "review_notification",
    }

    # web channel — record as assistant message
    try:
        record_message(
            content=notification_text,
            role="assistant",
            source="web",
            session_id="alfred-main",
            metadata={
                "delivery": "review_notification",
                "review_id": review_id,
                "channel": "web",
            },
        )
        deliveries.append(
            _record_delivery(
                queue_item_id=None,
                thread_id=None,
                channel="web",
                status="delivered",
                payload=delivery_payload,
            )
        )
    except Exception as exc:
        deliveries.append(
            _record_delivery(
                queue_item_id=None,
                thread_id=None,
                channel="web",
                status="failed",
                payload=delivery_payload,
                error=str(exc),
            )
        )

    # telegram channel
    token = Config.telegram_token()
    chat_id = Config.telegram_chat_id()
    if not token or not chat_id:
        deliveries.append(
            _record_delivery(
                queue_item_id=None,
                thread_id=None,
                channel="telegram",
                status="skipped",
                payload={**delivery_payload, "reason": "telegram_not_configured"},
            )
        )
        return deliveries

    try:
        delivery_status, delivery_error = _send_telegram_message_with_retries(
            token=token,
            chat_id=chat_id,
            text=notification_text,
        )
        deliveries.append(
            _record_delivery(
                queue_item_id=None,
                thread_id=None,
                channel="telegram",
                status=delivery_status,
                payload=delivery_payload,
                error=delivery_error,
            )
        )
    except Exception as exc:
        logger.debug("Telegram review notification failed: %s", exc)
        deliveries.append(
            _record_delivery(
                queue_item_id=None,
                thread_id=None,
                channel="telegram",
                status="failed",
                payload=delivery_payload,
                error=str(exc),
            )
        )

    return deliveries


def list_delivery_publications(
    *,
    queue_item_id: int | None = None,
    channel: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit or 100), 500))
    clauses: list[str] = []
    params: list[Any] = []
    if queue_item_id is not None:
        clauses.append("queue_item_id = ?")
        params.append(int(queue_item_id))
    if channel:
        clauses.append("channel = ?")
        params.append(str(channel).strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, queue_item_id, thread_id, channel, status, payload_json, error, created_at, delivered_at
            FROM delivery_publications
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            [*params, bounded_limit],
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "queue_item_id": row["queue_item_id"],
            "thread_id": row["thread_id"],
            "channel": row["channel"],
            "status": row["status"],
            "payload": _json_loads(row["payload_json"], {}),
            "error": row["error"],
            "created_at": row["created_at"],
            "delivered_at": row["delivered_at"],
        }
        for row in rows
    ]


def delivery_metrics() -> dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT channel, status, COUNT(*) AS count
            FROM delivery_publications
            GROUP BY channel, status
            """
        ).fetchall()
    by_channel: dict[str, dict[str, int]] = {}
    for row in rows:
        channel = str(row["channel"] or "")
        status = str(row["status"] or "")
        count = int(row["count"] or 0)
        by_channel.setdefault(channel, {})
        by_channel[channel][status] = count
    return {
        "total": sum(sum(status_map.values()) for status_map in by_channel.values()),
        "by_channel": by_channel,
    }
