"""Queue-first runtime for chat/task execution."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..db import get_db
from ..services.async_delivery import publish_queue_result
from ..services.ics_import import refresh_all_urls
from ..services.object_context_docs import synthesize_stale_context_docs
from ..services.conversation_service import resolve_thread_id
from ..services.conversation_grounding import (
    get_conversation_state,
    record_grounding_read,
    update_conversation_state,
)
from ..services.execution_queue import (
    QUEUE_ITEM_PLAN_STEP,
    QUEUE_ITEM_REVIEW_RESUME,
    QUEUE_ITEM_SCHEDULED_JOB,
    QUEUE_ITEM_USER_MESSAGE,
    claim_next_item,
    enqueue_user_message,
    mark_item_completed,
    mark_item_failed,
    mark_item_review_blocked,
    mark_item_retryable_failure,
    update_item_processing_progress,
)
from ..voice.processing import process_pending_voice_journals
from .chat_orchestrator import process_chat_message as _process_chat_message_direct
from .review_queue import create_review_item
from .workflow import resume_workflow

logger = logging.getLogger(__name__)


def _is_reference_heavy(text: str) -> bool:
    lower = str(text or "").strip().lower()
    if not lower:
        return False
    return any(
        token in lower
        for token in (
            "those",
            "them",
            "that day",
            "that wednesday",
            "same tasks",
            "same day",
        )
    )


def _resolve_with_grounding(text: str, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return raw, {}
    if raw.startswith(".") or raw.startswith("/"):
        return raw, {}

    lower = raw.lower()
    scope_ref = str(state.get("last_scope_ref") or "").strip().lower()
    resolved: dict[str, Any] = {}
    rewritten = raw

    if "those" in lower and "task" in lower and scope_ref:
        if scope_ref == "overdue":
            rewritten = "what are my overdue tasks?"
            resolved["scope_ref"] = "overdue"
        elif scope_ref == "today":
            rewritten = "what are my tasks for today?"
            resolved["scope_ref"] = "today"
        elif scope_ref in {"inbox", "unassigned"}:
            rewritten = "what are my inbox tasks?"
            resolved["scope_ref"] = "inbox"

    anchors = state.get("date_anchors") if isinstance(state.get("date_anchors"), dict) else {}
    anchor_date = str(anchors.get("last_referenced_date") or "").strip()
    if anchor_date and any(token in lower for token in ("that day", "that wednesday", "same day")):
        rewritten = f"{raw} ({anchor_date})"
        resolved["date_anchor"] = anchor_date

    return rewritten, resolved


def _derive_grounding_updates(raw_message: str, result: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    lower = str(raw_message or "").strip().lower()

    if resolved.get("scope_ref"):
        updates["last_scope_ref"] = resolved.get("scope_ref")

    if "today" in lower:
        updates.setdefault("last_scope_ref", "today")
    elif "overdue" in lower:
        updates.setdefault("last_scope_ref", "overdue")
    elif "inbox" in lower or "unassigned" in lower:
        updates.setdefault("last_scope_ref", "inbox")

    task_payload = result.get("task") if isinstance(result.get("task"), dict) else None
    if task_payload and task_payload.get("id") is not None:
        try:
            updates["last_task_ids"] = [int(task_payload["id"])]
        except Exception:
            pass

    if isinstance(result.get("updated_task_ids"), list) and result["updated_task_ids"]:
        cleaned: list[int] = []
        for item in result["updated_task_ids"]:
            try:
                cleaned.append(int(item))
            except Exception:
                continue
        if cleaned:
            updates["last_task_ids"] = cleaned

    if isinstance(result.get("overdue_task_ids"), list) and result["overdue_task_ids"]:
        cleaned: list[int] = []
        for item in result["overdue_task_ids"]:
            try:
                cleaned.append(int(item))
            except Exception:
                continue
        if cleaned:
            updates["last_task_ids"] = cleaned
            updates.setdefault("last_scope_ref", "overdue")

    anchor_date = resolved.get("date_anchor")
    if anchor_date:
        anchors = {"last_referenced_date": anchor_date}
        updates["date_anchors"] = anchors

    intent = result.get("intent")
    if isinstance(intent, str) and intent.strip():
        updates["last_operation"] = intent.strip()
    elif result.get("status") == "completed":
        updates["last_operation"] = "completed"

    return updates


def _stale_context_requires_review(item: dict[str, Any], state: dict[str, Any], raw_message: str) -> bool:
    stale_context = item.get("stale_context") if isinstance(item.get("stale_context"), dict) else {}
    enqueued_updated_at = str(stale_context.get("grounding_updated_at") or "").strip()
    current_updated_at = str(state.get("updated_at") or "").strip()
    if not enqueued_updated_at or not current_updated_at:
        return False
    if enqueued_updated_at == current_updated_at:
        return False
    return _is_reference_heavy(raw_message)


def _process_user_message_item(item: dict[str, Any]) -> dict[str, Any]:
    queue_item_id = int(item["id"])
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    raw_message = str(payload.get("content") or "").strip()
    source = str(item.get("source") or payload.get("source") or "web").strip() or "web"
    thread_id = str(item.get("thread_id") or payload.get("thread_id") or "").strip()
    if not raw_message:
        result = {
            "response": "No message content provided.",
            "status": "failed",
            "error": "empty_content",
            "queue_item_id": queue_item_id,
        }
        mark_item_failed(queue_item_id, error="empty_content")
        return result

    state = get_conversation_state(thread_id)
    resolved_message, resolved = _resolve_with_grounding(raw_message, state)
    record_grounding_read(
        thread_id=thread_id,
        source=source,
        message_text=raw_message,
        resolved=resolved,
    )

    if _stale_context_requires_review(item, state, raw_message):
        review = create_review_item(
            reason_code="clarification",
            payload={
                "queue_item_id": queue_item_id,
                "thread_id": thread_id,
                "original_message": raw_message,
                "resolved_message": resolved_message,
                "reason": "stale_context_reference",
            },
        )
        try:
            from ..services.async_delivery import publish_review_notification
            publish_review_notification(review)
        except Exception as exc:
            logger.warning("Unable to publish review notification for stale context: %s", exc)
        mark_item_review_blocked(
            queue_item_id,
            reason="stale_context_reference",
            extra_payload={"review_id": review.get("review_id")},
        )
        return {
            "response": "This queued request needs review before execution due to stale conversational context.",
            "status": "review_blocked",
            "review": review,
            "queue_item_id": queue_item_id,
            "thread_id": thread_id,
            "mode": "review_blocked",
        }
    latest_progress: dict[str, Any] = {}

    def _on_model_progress(progress: dict[str, Any]) -> None:
        if not isinstance(progress, dict):
            return
        latest_progress.clear()
        latest_progress.update(progress)
        update_item_processing_progress(
            queue_item_id,
            progress_payload={
                **latest_progress,
                "queue_item_id": queue_item_id,
                "thread_id": thread_id,
                "source": source,
            },
        )

    try:
        direct_result = _process_chat_message_direct(
            resolved_message,
            source=source,
            thread_id=thread_id,
            progress_callback=_on_model_progress,
        )
        if not isinstance(direct_result, dict):
            direct_result = {"response": str(direct_result), "status": "completed"}
        elif not str(direct_result.get("status") or "").strip():
            direct_result = {**direct_result, "status": "completed"}
        if latest_progress:
            direct_result = {
                **direct_result,
                "model_progress": dict(latest_progress),
            }
        # When the workflow was interrupted and a review item was created,
        # suppress the approval prompt in chat — approvals happen in Control.
        if (
            str(direct_result.get("status") or "").strip() == "interrupted"
            and isinstance(direct_result.get("review"), dict)
        ):
            review_id = direct_result["review"].get("review_id") or "pending"
            direct_result = {
                **direct_result,
                "response": f"\u2709\ufe0f Sent to review queue (ID: {review_id}). Approve or reject via the Control tab.",
            }
        updates = _derive_grounding_updates(raw_message, direct_result, resolved)
        if updates:
            update_conversation_state(
                thread_id=thread_id,
                source=source,
                updates=updates,
                summary="Grounding updated from queued user message execution",
                reason=f"queue_item:{queue_item_id}",
            )
        final_result = {**direct_result, "queue_item_id": queue_item_id}
        mark_item_completed(queue_item_id, final_result)
        final_result["deliveries"] = publish_queue_result(item, final_result)
        return final_result
    except Exception as exc:
        logger.exception("Queue user message item failed (%s)", queue_item_id)
        mark_item_retryable_failure(queue_item_id, error=str(exc))
        return {
            "response": "Queued request failed; it will be retried.",
            "status": "queued",
            "error": str(exc),
            "queue_item_id": queue_item_id,
            "thread_id": thread_id,
            "mode": "retry_queued",
        }


def _process_review_resume_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    workflow_id = payload.get("workflow_id")
    resolution = str(payload.get("resolution") or "").strip()
    if workflow_id is None or not resolution:
        mark_item_failed(int(item["id"]), error="invalid_review_resume_payload")
        return {
            "status": "failed",
            "error": "invalid_review_resume_payload",
            "queue_item_id": item["id"],
        }
    try:
        resumed = resume_workflow(int(workflow_id), resolution)
    except Exception as exc:
        mark_item_retryable_failure(int(item["id"]), error=str(exc))
        return {
            "status": "queued",
            "error": str(exc),
            "queue_item_id": item["id"],
        }
    result = {
        **(resumed or {"status": "completed", "response": "Review resume processed."}),
        "queue_item_id": item["id"],
    }
    mark_item_completed(int(item["id"]), result)
    result["deliveries"] = publish_queue_result(item, result)
    return result


def _process_scheduled_job_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    job_name = str(payload.get("job_name") or "").strip()
    job_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    normalized_job = job_name.strip().lower()

    summary: dict[str, Any] = {}
    status = "completed"
    error = None
    try:
        if normalized_job == "voice_transcription":
            max_items = max(1, min(int(job_payload.get("max_items") or 2), 50))
            processed = process_pending_voice_journals(max_items=max_items)
            summary = {"processed_count": int(processed), "max_items": max_items}
        elif normalized_job == "context_doc_refresh":
            max_items = max(1, min(int(job_payload.get("max_items") or 6), 100))
            summary = synthesize_stale_context_docs(max_items=max_items)
            if not isinstance(summary, dict):
                summary = {"result": summary, "max_items": max_items}
        elif normalized_job == "ics_refresh":
            refreshed = refresh_all_urls()
            summary = refreshed if isinstance(refreshed, dict) else {"result": refreshed}
        elif normalized_job == "queue_retry_scan":
            max_items = max(1, min(int(job_payload.get("max_items") or 80), 500))
            retried_results = process_execution_queue(
                worker_id="queue-retry-scan",
                max_items=max_items,
            )
            summary = {
                "max_items": max_items,
                "processed_count": len(retried_results),
                "processed_status_counts": {
                    "completed": len([r for r in retried_results if str(r.get("status")) == "completed"]),
                    "queued": len([r for r in retried_results if str(r.get("status")) == "queued"]),
                    "failed": len([r for r in retried_results if str(r.get("status")) == "failed"]),
                    "review_blocked": len([r for r in retried_results if str(r.get("status")) == "review_blocked"]),
                },
            }
        else:
            summary = {"message": f"No handler for scheduled job '{job_name}'"}
    except Exception as exc:
        status = "queued"
        error = str(exc)
        logger.exception("Scheduled queue job failed (%s)", job_name)

    if error is not None:
        mark_item_retryable_failure(int(item["id"]), error=error)
        failed_result = {
            "status": status,
            "error": error,
            "queue_item_id": item["id"],
            "job_name": job_name,
            "summary": summary,
        }
        failed_result["deliveries"] = publish_queue_result(item, failed_result)
        return failed_result
    result = {
        "status": status,
        "response": f"Scheduled job executed: {job_name}",
        "queue_item_id": item["id"],
        "job_name": job_name,
        "summary": summary,
    }
    mark_item_completed(int(item["id"]), result)
    result["deliveries"] = publish_queue_result(item, result)
    return result


def _process_plan_step_item(item: dict[str, Any]) -> dict[str, Any]:
    """Execute a single plan step via the workflow system."""
    from .plan_tracker import approve_plan_step, complete_plan_step, fail_plan_step
    from .workflow import submit_input

    queue_item_id = int(item["id"])
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    step_id = payload.get("step_id")
    description = str(payload.get("description") or "").strip()

    if not step_id or not description:
        mark_item_failed(queue_item_id, error="invalid_plan_step_payload")
        return {"status": "failed", "error": "invalid_plan_step_payload", "queue_item_id": queue_item_id}

    approve_plan_step(int(step_id))
    try:
        result = submit_input(description, source="plan_step")
        status = str(result.get("status") or "completed")
        if status in ("completed", "interrupted"):
            complete_plan_step(int(step_id), result=result)
            mark_item_completed(queue_item_id, result)
            result["deliveries"] = publish_queue_result(item, result)
            return {**result, "queue_item_id": queue_item_id}
        else:
            fail_plan_step(int(step_id), error=result.get("error") or "step_execution_failed")
            mark_item_failed(queue_item_id, error=result.get("error") or "step_execution_failed")
            return {**result, "queue_item_id": queue_item_id}
    except Exception as exc:
        fail_plan_step(int(step_id), error=str(exc))
        mark_item_retryable_failure(queue_item_id, error=str(exc))
        return {"status": "queued", "error": str(exc), "queue_item_id": queue_item_id}


def process_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    item_type = str(item.get("item_type") or "").strip().lower()
    if item_type == QUEUE_ITEM_USER_MESSAGE:
        return _process_user_message_item(item)
    if item_type == QUEUE_ITEM_REVIEW_RESUME:
        return _process_review_resume_item(item)
    if item_type == QUEUE_ITEM_SCHEDULED_JOB:
        return _process_scheduled_job_item(item)
    if item_type == QUEUE_ITEM_PLAN_STEP:
        return _process_plan_step_item(item)
    result = {
        "status": "failed",
        "error": f"unsupported_queue_item_type:{item_type}",
        "queue_item_id": item.get("id"),
    }
    mark_item_failed(int(item["id"]), error=result["error"])
    return result


def process_execution_queue(
    *,
    worker_id: str = "queue-runtime",
    max_items: int = 20,
    stop_on_item_id: int | None = None,
) -> list[dict[str, Any]]:
    bounded_max = max(1, min(int(max_items or 20), 500))
    results: list[dict[str, Any]] = []
    for _ in range(bounded_max):
        item = claim_next_item(worker_id)
        if item is None:
            break
        result = process_queue_item(item)
        results.append(result)
        if stop_on_item_id is not None and int(item["id"]) == int(stop_on_item_id):
            break
    return results


def process_chat_message_via_queue(
    message: str,
    *,
    source: str = "web",
    thread_id: str | None = None,
    max_drain_items: int = 50,
) -> dict[str, Any]:
    raw = str(message or "").strip()
    if not raw:
        raise ValueError("Empty message")
    resolved_thread = resolve_thread_id(source=source, thread_id=thread_id)
    state = get_conversation_state(resolved_thread)
    queued = enqueue_user_message(
        source=source,
        thread_id=resolved_thread,
        content=raw,
        metadata={"mode": "queued"},
        idempotency_key=None,
    )
    # Preserve stale-context snapshot used for execution-time guards.
    stale_context = queued.get("stale_context") if isinstance(queued.get("stale_context"), dict) else {}
    stale_context["grounding_updated_at"] = state.get("updated_at")
    with get_db() as conn:
        conn.execute(
            "UPDATE execution_queue SET stale_context_json = ? WHERE id = ?",
            (json.dumps(stale_context, ensure_ascii=False), int(queued["id"])),
        )

    results = process_execution_queue(
        worker_id=f"{source}-inline",
        max_items=max_drain_items,
        stop_on_item_id=int(queued["id"]),
    )
    for result in reversed(results):
        if int(result.get("queue_item_id") or -1) == int(queued["id"]):
            return {
                **result,
                "thread_id": result.get("thread_id") or resolved_thread,
                "mode": result.get("mode") or "queued_processed",
            }
    return {
        "response": "Message queued for asynchronous processing.",
        "status": "queued",
        "queue_item_id": queued["id"],
        "thread_id": resolved_thread,
        "mode": "queued_pending",
    }
