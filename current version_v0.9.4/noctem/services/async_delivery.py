"""Async delivery publication helpers for queue-processed assistant outputs."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import requests

from ..config import Config
from ..db import get_db
from .conversation_service import record_message
from .execution_queue import QUEUE_ITEM_USER_MESSAGE

logger = logging.getLogger(__name__)


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
    source = str(queue_item.get("source") or "").strip().lower()
    thread_id = str(result.get("thread_id") or queue_item.get("thread_id") or "").strip() or None
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

    if item_type == QUEUE_ITEM_USER_MESSAGE:
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

    if item_type == QUEUE_ITEM_USER_MESSAGE and source == "telegram":
        deliveries.append(
            _record_delivery(
                queue_item_id=queue_item_id,
                thread_id=thread_id,
                channel="telegram",
                status="skipped",
                payload={**payload, "reason": "already_replied_inline"},
            )
        )
        return deliveries

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": response_text},
            timeout=10,
        )
        if response.ok:
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
            error_message = str((response.json() or {}).get("description") or response.text or "telegram_send_failed")
            deliveries.append(
                _record_delivery(
                    queue_item_id=queue_item_id,
                    thread_id=thread_id,
                    channel="telegram",
                    status="failed",
                    payload=payload,
                    error=error_message,
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
