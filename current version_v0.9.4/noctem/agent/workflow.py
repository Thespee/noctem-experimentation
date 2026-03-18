"""Agent workflow execution for v0.9.3."""
import hashlib
import logging
import uuid

from ..db import get_db
from ..mcp import get_mcp_server
from ..mcp.resolver import resolve_project_target, resolve_scope, resolve_task_target
from ..parser.task_parser import parse_task, format_task_confirmation
from ..services import task_service, project_service
from .audit import log_agent_action, get_agent_actions
from .bulk_edit_parser import BulkEditParseResult, parse_bulk_edit_request, split_bulk_edit_clauses
from .interrupts import create_interrupt, resolve_interrupt, get_pending_interrupts
from .models import AgentWorkflow
from .review_queue import (
    create_review_item,
    list_blocked_workflows,
    list_review_items,
    resolve_reviews_for_interrupt,
)
from .router import classify_intent, IntentType

logger = logging.getLogger(__name__)


def _serialize_task(task) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "project_id": task.project_id,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time.isoformat() if task.due_time else None,
        "importance": task.importance,
        "tags": task.tags,
        "recurrence_rule": task.recurrence_rule,
    }


def _is_affirmative(text: str) -> bool:
    value = (text or "").strip().lower()
    if value in {"y", "yes", "yep", "yeah", "ok", "okay", "confirm", "confirmed", "proceed", "sure"}:
        return True
    return value.startswith("yes ")


def _is_negative(text: str) -> bool:
    value = (text or "").strip().lower()
    if value in {"n", "no", "nope", "cancel", "stop", "abort"}:
        return True
    return value.startswith("no ")


def _merge_resume_text(original_text: str | None, response_text: str) -> str:
    base = (original_text or "").strip()
    delta = (response_text or "").strip()
    if not base:
        return delta
    if not delta:
        return base
    return f"{base} {delta}".strip()


def _review_reason_code(interrupt_type: str, context: dict | None) -> str:
    if interrupt_type == "approve":
        return "approval"
    stage = str((context or {}).get("stage") or "").strip().lower()
    if stage.startswith("clarify") or "ambigu" in stage:
        return "clarification"
    return "manual_review"


def _review_object_id(context: dict | None) -> str | None:
    ctx = context or {}
    explicit_object_id = ctx.get("object_id")
    if isinstance(explicit_object_id, str) and explicit_object_id.strip():
        return explicit_object_id.strip()
    for key, prefix in (("task_id", "task"), ("project_id", "project"), ("goal_id", "goal")):
        value = ctx.get(key)
        try:
            if value is not None:
                return f"{prefix}:{int(value)}"
        except Exception:
            continue
    return None


def _queue_failure_review(workflow_id: int, message: str) -> dict | None:
    lower = (message or "").lower()
    if "verification failed" not in lower:
        return None
    payload = {
        "workflow_id": workflow_id,
        "failure_message": message,
        "source": "agent.workflow",
    }
    return create_review_item(
        reason_code="verification_failure",
        payload=payload,
    )

def _create_workflow(workflow_type: str, text: str, source: str) -> tuple[int, str]:
    thread_id = uuid.uuid4().hex
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_workflows (workflow_type, thread_id, status, current_node, source, input_text, updated_at)
            VALUES (?, ?, 'active', 'captured', ?, ?, CURRENT_TIMESTAMP)
            """,
            (workflow_type, thread_id, source, text),
        )
        return cursor.lastrowid, thread_id


def _update_workflow(
    workflow_id: int,
    *,
    status: str | None = None,
    current_node: str | None = None,
    output_text: str | None = None,
    error_message: str | None = None,
    complete: bool = False,
) -> None:
    updates = ["updated_at = CURRENT_TIMESTAMP"]
    params: list = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if current_node is not None:
        updates.append("current_node = ?")
        params.append(current_node)
    if output_text is not None:
        updates.append("output_text = ?")
        params.append(output_text)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if complete:
        updates.append("completed_at = CURRENT_TIMESTAMP")

    params.append(workflow_id)
    with get_db() as conn:
        conn.execute(
            f"UPDATE agent_workflows SET {', '.join(updates)} WHERE id = ?",
            params,
        )


def _resolve_target_task(text: str, *, include_done: bool = False) -> dict:
    return resolve_task_target(
        text,
        include_done=include_done,
        priority_index_limit=20,
        candidate_limit=5,
    )


def _candidate_options(candidates: list[dict], *, limit: int = 3) -> list[str]:
    options: list[str] = []
    for row in candidates[: max(1, limit)]:
        task_id = row.get("task_id")
        name = row.get("name") or "Unnamed task"
        score = row.get("score")
        if task_id is None:
            continue
        if isinstance(score, (int, float)):
            options.append(f"{task_id}: {name} (score {score:.2f})")
        else:
            options.append(f"{task_id}: {name}")
    return options


def _idempotency_key(workflow_id: int, operation: str, seed: str) -> str:
    digest = hashlib.sha1((seed or "").encode("utf-8")).hexdigest()[:12]
    return f"wf-{workflow_id}-{operation}-{digest}"

def _compact_overdue_response(tasks: list[dict], *, max_items: int = 12) -> str:
    count = len(tasks)
    if count == 0:
        return "You have 0 overdue task(s)."
    items: list[str] = []
    for row in tasks[:max_items]:
        name = str(row.get("name") or f"task #{row.get('id') or '?'}").strip()
        due_date = row.get("due_date")
        if due_date:
            items.append(f"{name} ({due_date})")
        else:
            items.append(name)
    overflow = count - len(items)
    suffix = f" (+{overflow} more)" if overflow > 0 else ""
    return f"You have {count} overdue task(s): " + "; ".join(items) + suffix



def _interrupt(
    workflow_id: int,
    *,
    interrupt_type: str = "clarify",
    question: str,
    options: list[str] | None = None,
    context: dict | None = None,
    reasoning: str | None = None,
) -> dict:
    interrupt_id = create_interrupt(
        workflow_id=workflow_id,
        interrupt_type=interrupt_type,
        question=question,
        options=options,
        context=context,
    )
    review_item = None
    try:
        review_item = create_review_item(
            reason_code=_review_reason_code(interrupt_type, context),
            object_id=_review_object_id(context),
            event_id=(context or {}).get("event_id"),
            payload={
                "workflow_id": workflow_id,
                "interrupt_id": interrupt_id,
                "interrupt_type": interrupt_type,
                "question": question,
                "context": context or {},
                "options": list(options or []),
                "source": "agent.workflow",
            },
        )
    except Exception as exc:
        logger.warning("Unable to persist review item for interrupt %s: %s", interrupt_id, exc)

    # Publish dual-channel notification for the new review item.
    notification_deliveries = []
    if review_item:
        try:
            from ..services.async_delivery import publish_review_notification
            notification_deliveries = publish_review_notification(review_item)
        except Exception as exc:
            logger.warning("Unable to publish review notification for interrupt %s: %s", interrupt_id, exc)

    _update_workflow(workflow_id, status="interrupted", current_node="pending_review")
    log_agent_action(
        workflow_id,
        "interrupted",
        input_data=context,
        output_data={
            "interrupt_id": interrupt_id,
            "question": question,
            "review_id": review_item.get("review_id") if review_item else None,
            "notification_count": len(notification_deliveries),
        },
        decision_reasoning=reasoning or "Missing/ambiguous fields require user clarification",
    )
    return {
        "workflow_id": workflow_id,
        "status": "interrupted",
        "response": question,
        "review": review_item,
        "interrupt": {
            "id": interrupt_id,
            "type": interrupt_type,
            "question": question,
            "options": options or [],
            "review_id": review_item.get("review_id") if review_item else None,
        },
    }


def _complete(workflow_id: int, response: str, output: dict | None = None) -> dict:
    _update_workflow(
        workflow_id,
        status="completed",
        current_node="committed",
        output_text=response,
        complete=True,
    )
    log_agent_action(
        workflow_id,
        "committed",
        output_data=output or {"response": response},
        decision_reasoning="Workflow completed successfully",
    )
    return {
        "workflow_id": workflow_id,
        "status": "completed",
        "response": response,
        **(output or {}),
    }


def _fail(workflow_id: int, message: str) -> dict:
    review_item = None
    try:
        review_item = _queue_failure_review(workflow_id, message)
    except Exception as exc:
        logger.warning("Unable to persist failure review item for workflow %s: %s", workflow_id, exc)
    _update_workflow(
        workflow_id,
        status="failed",
        current_node="failed",
        error_message=message,
        output_text=message,
        complete=True,
    )
    log_agent_action(
        workflow_id,
        "failed",
        output_data={
            "error": message,
            "review_id": review_item.get("review_id") if review_item else None,
        },
        decision_reasoning="Workflow failed",
    )
    return {
        "workflow_id": workflow_id,
        "status": "failed",
        "response": message,
        "error": message,
        "review": review_item,
    }


def _handle_add_task(workflow_id: int, text: str, allow_interrupt: bool) -> dict:
    _update_workflow(workflow_id, current_node="executing")
    parsed = parse_task(text)
    if not parsed.name or not any(ch.isalnum() for ch in parsed.name):
        if allow_interrupt:
            return _interrupt(
                workflow_id,
                question="I need a bit more detail. What task should I create?",
                options=["Add task with due date", "Add task without due date"],
                context={
                    "intent": IntentType.ADD_TASK.value,
                    "stage": "clarify_add_task",
                    "original_text": text,
                },
            )
        return _fail(workflow_id, "Unable to parse task details from response.")

    project_id = None
    if parsed.project_name:
        project = project_service.get_project_by_name(parsed.project_name)
        if project:
            project_id = project.id
    
    due_date_val = parsed.due_date.isoformat() if parsed.due_date else None
    due_time_val = parsed.due_time.isoformat() if parsed.due_time else None

    mcp_server = get_mcp_server()
    create_result = mcp_server.call_tool(
        "tasks.create",
        {
            "name": parsed.name,
            "project_id": project_id,
            "due_date": due_date_val,
            "due_time": due_time_val,
            "importance": parsed.importance,
            "tags": parsed.tags,
            "recurrence_rule": parsed.recurrence_rule,
        },
        context={"source": "agent.workflow", "workflow_id": workflow_id},
    )
    if not create_result.get("ok"):
        return _fail(workflow_id, "Unable to create task through MCP.")
    task_payload = create_result["result"].get("task")
    if not isinstance(task_payload, dict) or task_payload.get("id") is None:
        return _fail(workflow_id, "Task creation did not return a valid task payload.")
    response = format_task_confirmation(parsed)
    log_agent_action(
        workflow_id,
        "executed",
        input_data={"intent": IntentType.ADD_TASK.value, "text": text},
        output_data={"task_id": task_payload.get("id"), "mutation_backend": "mcp"},
        decision_reasoning="Task parsed and created via MCP tool contract",
    )
    return _complete(
        workflow_id,
        response,
        output={"task": task_payload},
    )


def _handle_complete_task(workflow_id: int, text: str) -> dict:
    resolution = _resolve_target_task(text, include_done=False)
    task = resolution.get("selected_task")
    if resolution.get("ambiguous"):
        options = _candidate_options(resolution.get("candidates") or [], limit=4)
        return _interrupt(
            workflow_id,
            question="I found multiple close task matches. Which one should I complete?",
            options=options or ["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.COMPLETE_TASK.value,
                "stage": "clarify_complete_target",
                "original_text": text,
                "resolver_ambiguity": resolution.get("ambiguity_reason"),
                "resolver_candidates": resolution.get("candidates"),
            },
        )

    if not task:
        return _interrupt(
            workflow_id,
            question="I couldn't find that task. Which task should be completed?",
            options=["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.COMPLETE_TASK.value,
                "stage": "clarify_complete_target",
                "original_text": text,
            },
        )

    _update_workflow(workflow_id, current_node="executing")
    mcp_server = get_mcp_server()
    complete_result = mcp_server.call_tool(
        "tasks.complete",
        {"task_id": task.id},
        context={"source": "agent.workflow", "workflow_id": workflow_id},
    )
    if not complete_result.get("ok"):
        return _fail(workflow_id, "Unable to complete the selected task.")
    complete_payload = complete_result["result"]
    updated_task_payload = complete_payload.get("task")
    if not isinstance(updated_task_payload, dict):
        return _fail(workflow_id, "Task completion did not return a valid task payload.")
    if complete_payload.get("verified") is False:
        return _fail(workflow_id, "Task completion verification failed.")

    response = f"✓ Completed: {updated_task_payload.get('name', task.name)}"
    log_agent_action(
        workflow_id,
        "executed",
        input_data={
            "intent": IntentType.COMPLETE_TASK.value,
            "task_id": task.id,
            "resolver_method": resolution.get("selected_method"),
            "resolver_confidence": resolution.get("confidence"),
            "mutation_backend": "mcp",
        },
        output_data={
            "task_id": updated_task_payload.get("id"),
            "status": updated_task_payload.get("status"),
            "verified": complete_payload.get("verified"),
        },
        decision_reasoning="Task completion command executed through MCP contract",
    )
    return _complete(workflow_id, response, output={"task": updated_task_payload})


def _handle_skip_task(workflow_id: int, text: str) -> dict:
    resolution = _resolve_target_task(text, include_done=False)
    task = resolution.get("selected_task")
    if resolution.get("ambiguous"):
        options = _candidate_options(resolution.get("candidates") or [], limit=4)
        return _interrupt(
            workflow_id,
            question="I found multiple close task matches. Which one should be deferred?",
            options=options or ["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.SKIP_TASK.value,
                "stage": "clarify_skip_target",
                "original_text": text,
                "resolver_ambiguity": resolution.get("ambiguity_reason"),
                "resolver_candidates": resolution.get("candidates"),
            },
        )
    if not task:
        return _interrupt(
            workflow_id,
            question="I couldn't find that task to skip. Which task should be deferred?",
            options=["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.SKIP_TASK.value,
                "stage": "clarify_skip_target",
                "original_text": text,
            },
        )

    _update_workflow(workflow_id, current_node="executing")
    mcp_server = get_mcp_server()
    skip_result = mcp_server.call_tool(
        "tasks.skip",
        {"task_id": task.id},
        context={"source": "agent.workflow", "workflow_id": workflow_id},
    )
    if not skip_result.get("ok"):
        return _fail(workflow_id, "Unable to skip the selected task.")
    skip_payload = skip_result["result"]
    updated_task_payload = skip_payload.get("task")
    if not isinstance(updated_task_payload, dict):
        return _fail(workflow_id, "Task skip did not return a valid task payload.")

    response = f"⏭️ Skipped: {updated_task_payload.get('name', task.name)}"
    log_agent_action(
        workflow_id,
        "executed",
        input_data={
            "intent": IntentType.SKIP_TASK.value,
            "task_id": task.id,
            "resolver_method": resolution.get("selected_method"),
            "resolver_confidence": resolution.get("confidence"),
            "mutation_backend": "mcp",
        },
        output_data={
            "task_id": updated_task_payload.get("id"),
            "due_date": updated_task_payload.get("due_date"),
        },
        decision_reasoning="Task defer command executed through MCP contract",
    )
    return _complete(workflow_id, response, output={"task": updated_task_payload})


def _execute_delete_task(
    workflow_id: int,
    task_id: int,
    task_name_hint: str | None = None,
    *,
    preview_id: str | None = None,
) -> dict:
    _update_workflow(workflow_id, current_node="executing")
    task = task_service.get_task(task_id)
    task_name = task.name if task else (task_name_hint or f"task #{task_id}")
    mcp_server = get_mcp_server()

    active_preview_id = preview_id
    if not active_preview_id:
        preview_result = mcp_server.call_tool(
            "tasks.preview_delete",
            {"task_id": task_id},
            context={"source": "agent.workflow", "workflow_id": workflow_id},
        )
        if not preview_result.get("ok"):
            return _fail(workflow_id, "Unable to prepare delete preview.")
        active_preview_id = preview_result["result"]["preview_id"]

    commit_result = mcp_server.call_tool(
        "tasks.commit_delete",
        {
            "preview_id": active_preview_id,
            "approved": True,
            "idempotency_key": _idempotency_key(
                workflow_id,
                "delete",
                f"{task_id}:{active_preview_id}",
            ),
        },
        context={"source": "agent.workflow", "workflow_id": workflow_id},
    )
    if not commit_result.get("ok"):
        return _fail(workflow_id, "Unable to delete the selected task.")

    commit_payload = commit_result["result"]
    verified_count = int(commit_payload.get("verified_affected_count", 0))
    if verified_count < 1:
        return _fail(workflow_id, "Delete commit verification failed.")

    deleted_task_ids = list(commit_payload.get("verified_affected_task_ids") or [])
    deleted_task_id = int(deleted_task_ids[0]) if deleted_task_ids else task_id
    response = f"🗑️ Deleted: {task_name}"
    log_agent_action(
        workflow_id,
        "executed",
        input_data={
            "intent": IntentType.DELETE_TASK.value,
            "task_id": task_id,
            "preview_id": active_preview_id,
        },
        output_data={
            "task_id": deleted_task_id,
            "deleted": True,
            "verified_affected_count": verified_count,
            "idempotency_key": commit_payload.get("idempotency_key"),
            "idempotent_replay": commit_payload.get("idempotent_replay"),
        },
        decision_reasoning="Task delete committed via MCP preview/commit flow",
    )
    return _complete(workflow_id, response, output={"deleted_task_id": deleted_task_id})


def _handle_delete_task(workflow_id: int, text: str) -> dict:
    resolution = _resolve_target_task(text, include_done=True)
    task = resolution.get("selected_task")
    if resolution.get("ambiguous"):
        options = _candidate_options(resolution.get("candidates") or [], limit=4)
        return _interrupt(
            workflow_id,
            question="I found multiple close task matches. Which one should be deleted?",
            options=options or ["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.DELETE_TASK.value,
                "stage": "clarify_delete_target",
                "original_text": text,
                "resolver_ambiguity": resolution.get("ambiguity_reason"),
                "resolver_candidates": resolution.get("candidates"),
            },
        )
    if not task:
        return _interrupt(
            workflow_id,
            question="I couldn't find that task to delete. Which task should be removed?",
            options=["Provide task name", "Provide task ID"],
            context={
                "intent": IntentType.DELETE_TASK.value,
                "stage": "clarify_delete_target",
                "original_text": text,
            },
        )
    mcp_server = get_mcp_server()
    preview_result = mcp_server.call_tool(
        "tasks.preview_delete",
        {"task_id": task.id},
        context={"source": "agent.workflow", "workflow_id": workflow_id},
    )
    if not preview_result.get("ok"):
        return _fail(workflow_id, "Unable to prepare delete preview.")
    preview = preview_result["result"]

    return _interrupt(
        workflow_id,
        interrupt_type="approve",
        question=f"Delete task '{task.name}'? This is destructive. Reply yes or no.",
        options=["yes", "no"],
        context={
            "intent": IntentType.DELETE_TASK.value,
            "stage": "confirm_delete",
            "task_id": task.id,
            "task_name": task.name,
            "preview_id": preview.get("preview_id"),
            "preview_policy": preview.get("policy_gates"),
            "resolver_method": resolution.get("selected_method"),
            "resolver_confidence": resolution.get("confidence"),
        },
        reasoning="Destructive action requires explicit user approval",
    )


def _handle_bulk_add(workflow_id: int, text: str) -> dict:
    _update_workflow(workflow_id, current_node="executing")
    raw_items = [s.strip() for s in text.replace(";", "\n").splitlines() if s.strip()]
    created = []
    mcp_server = get_mcp_server()
    for item in raw_items:
        parsed = parse_task(item)
        if not parsed.name or not any(ch.isalnum() for ch in parsed.name):
            continue
        due_date_val = parsed.due_date.isoformat() if parsed.due_date else None
        due_time_val = parsed.due_time.isoformat() if parsed.due_time else None
        create_result = mcp_server.call_tool(
            "tasks.create",
            {
                "name": parsed.name,
                "due_date": due_date_val,
                "due_time": due_time_val,
                "importance": parsed.importance,
                "tags": parsed.tags,
                "recurrence_rule": parsed.recurrence_rule,
            },
            context={"source": "agent.workflow", "workflow_id": workflow_id},
        )
        if not create_result.get("ok"):
            continue
        task_payload = create_result["result"].get("task")
        if isinstance(task_payload, dict):
            created.append(task_payload)

    if not created:
        return _interrupt(
            workflow_id,
            question="I couldn't parse any valid tasks in that batch. Can you provide one per line?",
            options=["Retry with line-separated tasks"],
            context={
                "intent": IntentType.BULK_ADD.value,
                "stage": "clarify_bulk_add",
                "original_text": text,
            },
        )

    log_agent_action(
        workflow_id,
        "executed",
        input_data={"intent": IntentType.BULK_ADD.value, "count": len(raw_items)},
        output_data={"created_count": len(created), "mutation_backend": "mcp"},
        decision_reasoning="Bulk task creation executed through MCP contract",
    )
    return _complete(
        workflow_id,
        f"✓ Added {len(created)} tasks.",
        output={"tasks": created},
    )

def _resolve_bulk_edit_scope(parsed: BulkEditParseResult) -> tuple[list, str, dict]:
    scope_resolution = resolve_scope(
        scope_type=parsed.scope_type,
        source_project_name=parsed.source_project_name,
        source_due_date=parsed.source_due_date,
        task_names=list(parsed.task_names),
    )
    tasks = list(scope_resolution.get("_task_objects") or [])
    scope_ref = scope_resolution.get("scope_ref") or "unknown"
    return tasks, scope_ref, scope_resolution


def _handle_bulk_edit(
    workflow_id: int,
    text: str,
    allow_interrupt: bool = True,
    *,
    approval_override: bool = False,
) -> dict:
    clauses = split_bulk_edit_clauses(text) or [text]
    _update_workflow(workflow_id, current_node="executing")

    total_updated = 0
    updated_task_ids: list[int] = []
    clause_summaries: list[str] = []
    execution_details: list[dict] = []
    mcp_server = get_mcp_server()

    for clause in clauses:
        parsed = parse_bulk_edit_request(clause)
        if not parsed.has_scope():
            if allow_interrupt:
                return _interrupt(
                    workflow_id,
                    question="I couldn't determine which task group to update. Try: 'move everything in Interview project to today'.",
                    options=["Move all tasks from <project> to today", "Delay everything from today"],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "clarify_bulk_edit_scope",
                        "original_text": text,
                    },
                )
            return _fail(workflow_id, f"Bulk edit scope not resolved for: {clause}")

        tasks_to_update, scope_ref, scope_meta = _resolve_bulk_edit_scope(parsed)
        if scope_meta.get("ambiguous"):
            if allow_interrupt:
                ambiguity_details = scope_meta.get("ambiguity_details") or []
                options: list[str] = []
                for detail in ambiguity_details[:3]:
                    if isinstance(detail, dict) and detail.get("query"):
                        options.append(f"Clarify: {detail['query']}")
                    elif isinstance(detail, dict) and detail.get("name"):
                        options.append(f"Use project: {detail['name']}")
                return _interrupt(
                    workflow_id,
                    question="I found ambiguous scope targets for this bulk edit. Can you clarify the exact scope?",
                    options=options or ["Clarify task names", "Clarify project scope"],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "clarify_bulk_edit_targets",
                        "original_text": text,
                        "scope_resolution": {
                            "scope_ref": scope_meta.get("scope_ref"),
                            "ambiguity_reason": scope_meta.get("ambiguity_reason"),
                            "ambiguity_details": ambiguity_details,
                            "candidates_by_name": scope_meta.get("candidates_by_name"),
                        },
                    },
                )
            return _fail(workflow_id, f"Bulk edit scope is ambiguous for clause: {clause}")
        unresolved_names = list(scope_meta.get("unresolved_names") or [])
        if unresolved_names:
            if allow_interrupt:
                return _interrupt(
                    workflow_id,
                    question="I couldn't resolve every task name in that bulk edit scope. Which exact tasks should be changed?",
                    options=unresolved_names[:4],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "clarify_bulk_edit_targets",
                        "original_text": text,
                        "scope_resolution": {
                            "scope_ref": scope_meta.get("scope_ref"),
                            "unresolved_names": unresolved_names,
                            "candidates_by_name": scope_meta.get("candidates_by_name"),
                        },
                    },
                )
            return _fail(workflow_id, f"Unresolved task names in bulk scope: {', '.join(unresolved_names)}")
        if not tasks_to_update:
            if allow_interrupt:
                return _interrupt(
                    workflow_id,
                    question="I couldn't find matching active tasks for that edit. Which tasks should be changed?",
                    options=["Move all tasks from <project> to today", "Move task A and task B to project <name>"],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "clarify_bulk_edit_targets",
                        "original_text": text,
                    },
                )
            return _fail(workflow_id, f"No matching active tasks found for: {clause}")

        target_project = None
        if parsed.target_project_name:
            project_resolution = resolve_project_target(parsed.target_project_name)
            if project_resolution.get("ambiguous"):
                if allow_interrupt:
                    options = [
                        f"{row.get('project_id')}: {row.get('name')}"
                        for row in (project_resolution.get("candidates") or [])[:4]
                        if row.get("project_id") is not None and row.get("name")
                    ]
                    return _interrupt(
                        workflow_id,
                        question=f"I found multiple destination projects matching '{parsed.target_project_name}'. Which project should I use?",
                        options=options or ["Provide destination project"],
                        context={
                            "intent": IntentType.BULK_EDIT.value,
                            "stage": "clarify_bulk_edit_destination",
                            "original_text": text,
                            "destination_project_candidates": project_resolution.get("candidates"),
                        },
                    )
                return _fail(workflow_id, f"Destination project is ambiguous: {parsed.target_project_name}")
            target_project = project_resolution.get("selected_project")
            if not target_project:
                if allow_interrupt:
                    return _interrupt(
                        workflow_id,
                        question=f"I couldn't find destination project '{parsed.target_project_name}'. Which project should I use?",
                        options=["Provide destination project"],
                        context={
                            "intent": IntentType.BULK_EDIT.value,
                            "stage": "clarify_bulk_edit_destination",
                            "original_text": text,
                        },
                    )
                return _fail(workflow_id, f"Destination project not found: {parsed.target_project_name}")

        updates = {}
        if parsed.target_due_date is not None:
            updates["due_date"] = parsed.target_due_date
        if parsed.target_due_time is not None:
            updates["due_time"] = parsed.target_due_time
        if target_project is not None:
            updates["project_id"] = target_project.id

        if not updates:
            if allow_interrupt:
                return _interrupt(
                    workflow_id,
                    question="I understood the scope but not the update target. Should I change due date, project, or both?",
                    options=["Set due date", "Set destination project", "Set both"],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "clarify_bulk_edit_updates",
                        "original_text": text,
                    },
                )
            return _fail(workflow_id, f"No valid updates found for: {clause}")

        preview_call = mcp_server.call_tool(
            "tasks.preview_bulk_update",
            {
                "task_ids": [task.id for task in tasks_to_update],
                "updates": {
                    "due_date": parsed.target_due_date.isoformat() if parsed.target_due_date else None,
                    "due_time": parsed.target_due_time.isoformat() if parsed.target_due_time else None,
                    "project_id": target_project.id if target_project else None,
                },
                "scope_ref": scope_ref,
            },
            context={"source": "agent.workflow", "workflow_id": workflow_id},
        )
        if not preview_call.get("ok"):
            return _fail(workflow_id, f"Unable to create bulk edit preview for: {clause}")
        preview_payload = preview_call["result"]
        preview_id = preview_payload.get("preview_id")
        requires_approval = bool(preview_payload.get("requires_approval"))
        if requires_approval and not approval_override:
            if allow_interrupt:
                return _interrupt(
                    workflow_id,
                    interrupt_type="approve",
                    question=(
                        f"This bulk edit will update {int(preview_payload.get('affected_count', 0))} task(s). "
                        "Approve this update? Reply yes or no."
                    ),
                    options=["yes", "no"],
                    context={
                        "intent": IntentType.BULK_EDIT.value,
                        "stage": "confirm_bulk_edit",
                        "original_text": text,
                        "preview_clause": clause,
                        "preview_id": preview_id,
                        "preview_scope_ref": preview_payload.get("scope_ref"),
                        "preview_affected_count": preview_payload.get("affected_count"),
                        "preview_policy": preview_payload.get("policy_gates"),
                    },
                    reasoning="Bulk edit exceeds auto-commit threshold and requires explicit approval",
                )
            return _fail(workflow_id, "Bulk edit requires approval before commit.")

        commit_call = mcp_server.call_tool(
            "tasks.commit_bulk_update",
            {
                "preview_id": preview_id,
                "approved": bool(approval_override or not requires_approval),
                "idempotency_key": _idempotency_key(
                    workflow_id,
                    "bulk_update",
                    f"{clause}:{preview_id}",
                ),
            },
            context={"source": "agent.workflow", "workflow_id": workflow_id},
        )
        if not commit_call.get("ok"):
            return _fail(workflow_id, f"Bulk edit commit failed for: {clause}")
        commit_payload = commit_call["result"]
        clause_updated_ids = list(commit_payload.get("verified_affected_task_ids") or [])
        clause_updated_count = len(clause_updated_ids)
        if clause_updated_count == 0:
            continue

        total_updated += clause_updated_count
        updated_task_ids.extend(clause_updated_ids)
        change_parts = []
        if parsed.target_due_date is not None:
            change_parts.append(f"due {parsed.target_due_date.isoformat()}")
        if parsed.target_due_time is not None:
            change_parts.append(f"at {parsed.target_due_time.strftime('%H:%M')}")
        if target_project is not None:
            change_parts.append(f"project /{target_project.name}")

        clause_summaries.append(f"{clause_updated_count} task(s) → {', '.join(change_parts)}")
        execution_details.append(
            {
                "clause": clause,
                "scope_ref": scope_ref,
                "updated_count": clause_updated_count,
                "updated_task_ids": clause_updated_ids,
                "changes": {
                    "due_date": parsed.target_due_date.isoformat() if parsed.target_due_date else None,
                    "due_time": parsed.target_due_time.isoformat() if parsed.target_due_time else None,
                    "project_id": target_project.id if target_project else None,
                },
                "preview_id": preview_id,
                "commit_idempotency_key": commit_payload.get("idempotency_key"),
                "idempotent_replay": commit_payload.get("idempotent_replay"),
                "scope_resolution": {
                    "scope_ref": scope_meta.get("scope_ref"),
                    "matched_count": scope_meta.get("matched_count"),
                    "ambiguous": scope_meta.get("ambiguous"),
                    "ambiguity_reason": scope_meta.get("ambiguity_reason"),
                    "unresolved_names": scope_meta.get("unresolved_names"),
                },
                "parser": parsed.parser,
                "confidence": parsed.confidence,
            }
        )

    if total_updated == 0:
        return _fail(workflow_id, "Bulk edit did not update any tasks.")

    if len(clause_summaries) == 1:
        response = f"✓ Updated {clause_summaries[0]}."
    else:
        response = f"✓ Applied {len(clause_summaries)} edits; updated {total_updated} task(s).\n" + "\n".join(
            f"{idx + 1}) {summary}" for idx, summary in enumerate(clause_summaries)
        )

    unique_updated_task_ids = list(dict.fromkeys(updated_task_ids))
    log_agent_action(
        workflow_id,
        "executed",
        input_data={
            "intent": IntentType.BULK_EDIT.value,
            "text": text,
            "clauses": clauses,
        },
        output_data={
            "updated_count": total_updated,
            "updated_task_ids": unique_updated_task_ids,
            "details": execution_details,
        },
        decision_reasoning="Structured bulk edit parser applied updates across one or more clauses",
    )
    return _complete(
        workflow_id,
        response,
        output={
            "updated_count": total_updated,
            "updated_task_ids": unique_updated_task_ids,
        },
    )


def _handle_query(workflow_id: int, text: str) -> dict:
    _update_workflow(workflow_id, current_node="executing")
    lower = text.lower()
    wants_overdue_detail = (
        "overdue" in lower
        and any(token in lower for token in ("list", "show", "tell", "what", "which", "those", "are"))
        and "today" not in lower
    )
    if wants_overdue_detail:
        overdue_rows: list[dict] = []
        query_backend = "legacy"
        mcp_correlation_id = None
        try:
            mcp_server = get_mcp_server()
            overdue_result = mcp_server.call_tool(
                "tasks.list_overdue",
                {},
                context={"source": "agent.workflow", "workflow_id": workflow_id},
            )
            if overdue_result.get("ok"):
                overdue_rows = list(overdue_result["result"].get("tasks") or [])
                query_backend = "mcp"
                mcp_correlation_id = overdue_result.get("correlation_id")
            else:
                raise RuntimeError("MCP overdue query returned error envelope")
        except Exception as exc:
            logger.warning("MCP overdue detail fallback triggered: %s", exc)
            overdue_rows = [_serialize_task(task) for task in task_service.get_overdue_tasks()]
        response = _compact_overdue_response(overdue_rows)
        overdue_ids = [int(row["id"]) for row in overdue_rows if row.get("id") is not None]
        log_agent_action(
            workflow_id,
            "executed",
            input_data={"intent": IntentType.QUERY.value, "query_type": "overdue_detail"},
            output_data={
                "overdue_count": len(overdue_rows),
                "overdue_task_ids": overdue_ids,
                "query_backend": query_backend,
                "mcp_correlation_id": mcp_correlation_id,
            },
            decision_reasoning="Provided compact overdue task detail list",
        )
        return _complete(
            workflow_id,
            response,
            output={
                "overdue_count": len(overdue_rows),
                "overdue_task_ids": overdue_ids,
            },
        )

    if "today" in lower or "due today" in lower:
        today_count = 0
        overdue_count = 0
        query_backend = "legacy"
        mcp_correlation_ids: list[str] = []

        try:
            mcp_server = get_mcp_server()
            today_result = mcp_server.call_tool(
                "tasks.list_today",
                {},
                context={"source": "agent.workflow", "workflow_id": workflow_id},
            )
            overdue_result = mcp_server.call_tool(
                "tasks.list_overdue",
                {},
                context={"source": "agent.workflow", "workflow_id": workflow_id},
            )
            if today_result.get("ok") and overdue_result.get("ok"):
                today_count = int(today_result["result"].get("count", 0))
                overdue_count = int(overdue_result["result"].get("count", 0))
                query_backend = "mcp"
                if today_result.get("correlation_id"):
                    mcp_correlation_ids.append(today_result["correlation_id"])
                if overdue_result.get("correlation_id"):
                    mcp_correlation_ids.append(overdue_result["correlation_id"])
            else:
                raise RuntimeError("MCP query call returned error envelope")
        except Exception as exc:
            logger.warning("MCP query fallback triggered: %s", exc)
            today_count = len(task_service.get_tasks_due_today())
            overdue_count = len(task_service.get_overdue_tasks())
        response = (
            f"You have {today_count} task(s) due today"
            f" and {overdue_count} overdue."
        )
        log_agent_action(
            workflow_id,
            "executed",
            input_data={"intent": IntentType.QUERY.value, "query_type": "today_summary"},
            output_data={
                "today_count": today_count,
                "overdue_count": overdue_count,
                "query_backend": query_backend,
                "mcp_correlation_ids": mcp_correlation_ids,
            },
            decision_reasoning="Provided task summary for today's workload",
        )
        return _complete(
            workflow_id,
            response,
            output={
                "today_count": today_count,
                "overdue_count": overdue_count,
            },
        )

    if "inbox" in lower or "unassigned" in lower or "no due" in lower:
        unassigned_count = 0
        query_backend = "legacy"
        mcp_correlation_id = None
        try:
            mcp_server = get_mcp_server()
            inbox_result = mcp_server.call_tool(
                "tasks.list_inbox",
                {},
                context={"source": "agent.workflow", "workflow_id": workflow_id},
            )
            if inbox_result.get("ok"):
                unassigned_count = int(inbox_result["result"].get("count", 0))
                query_backend = "mcp"
                mcp_correlation_id = inbox_result.get("correlation_id")
            else:
                raise RuntimeError("MCP inbox query returned error envelope")
        except Exception as exc:
            logger.warning("MCP inbox fallback triggered: %s", exc)
            unassigned_count = len(task_service.get_tasks_without_due_date())

        response = f"You have {unassigned_count} unassigned task(s) with no due date."
        log_agent_action(
            workflow_id,
            "executed",
            input_data={"intent": IntentType.QUERY.value, "query_type": "inbox_summary"},
            output_data={
                "unassigned_count": unassigned_count,
                "query_backend": query_backend,
                "mcp_correlation_id": mcp_correlation_id,
            },
            decision_reasoning="Provided no-due-date task summary",
        )
        return _complete(
            workflow_id,
            response,
            output={"unassigned_count": unassigned_count},
        )

    response = "I can add, complete, skip, delete, bulk edit, and summarize tasks. Try: 'buy milk tomorrow' or 'move all tasks from Home to today'."
    log_agent_action(
        workflow_id,
        "executed",
        input_data={"intent": IntentType.QUERY.value},
        output_data={"response": response},
        decision_reasoning="Query fallback response",
    )
    return _complete(workflow_id, response)


def submit_input(text: str, source: str = "web") -> dict:
    """Create and execute a new agent workflow from user input."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Input text is required")

    route = classify_intent(cleaned)
    logger.debug(
        "INTENT_ROUTE: intent=%s confidence=%.2f classifier=%s text=%s",
        route.intent.value,
        route.confidence,
        route.classifier,
        cleaned,
    )
    workflow_id, thread_id = _create_workflow(route.intent.value, cleaned, source)

    log_agent_action(
        workflow_id,
        "captured",
        input_data={"text": cleaned, "source": source},
        output_data={"thread_id": thread_id},
    )
    log_agent_action(
        workflow_id,
        "planned",
        input_data={"text": cleaned},
        output_data={
            "intent": route.intent.value,
            "confidence": route.confidence,
            "classifier": route.classifier,
        },
        decision_reasoning=route.reasoning,
    )
    _update_workflow(workflow_id, current_node="planned")

    if route.intent == IntentType.ADD_TASK:
        result = _handle_add_task(workflow_id, cleaned, allow_interrupt=True)
    elif route.intent == IntentType.BULK_ADD:
        result = _handle_bulk_add(workflow_id, cleaned)
    elif route.intent == IntentType.BULK_EDIT:
        result = _handle_bulk_edit(workflow_id, cleaned, allow_interrupt=True)
    elif route.intent == IntentType.COMPLETE_TASK:
        result = _handle_complete_task(workflow_id, cleaned)
    elif route.intent == IntentType.SKIP_TASK:
        result = _handle_skip_task(workflow_id, cleaned)
    elif route.intent == IntentType.DELETE_TASK:
        result = _handle_delete_task(workflow_id, cleaned)
    else:
        result = _handle_query(workflow_id, cleaned)

    result.setdefault("intent", route.intent.value)
    result.setdefault("intent_classifier", route.classifier)
    result.setdefault("intent_confidence", route.confidence)
    return result


def get_workflow_status(workflow_id: int) -> dict | None:
    """Get current workflow record with actions and pending interrupts."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM agent_workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()
    if not row:
        return None

    workflow = AgentWorkflow.from_row(row).to_dict()
    pending_interrupts = get_pending_interrupts(workflow_id)
    pending_reviews = list_review_items(status="pending", workflow_id=workflow_id, limit=200)
    blocked_rows = [row for row in list_blocked_workflows(limit=500) if row.get("workflow_id") == workflow_id]
    return {
        "workflow": workflow,
        "actions": get_agent_actions(workflow_id),
        "pending_interrupts": pending_interrupts,
        "pending_reviews": pending_reviews,
        "blocked": bool(pending_interrupts) or bool(pending_reviews),
        "blocked_workflow": blocked_rows[0] if blocked_rows else None,
    }


def resume_workflow(workflow_id: int, resolution: str) -> dict | None:
    """Resume an interrupted workflow with user-provided resolution text."""
    decision = (resolution or "").strip()
    if not decision:
        raise ValueError("Resolution is required")

    pending = get_pending_interrupts(workflow_id)
    if not pending:
        return None

    interrupt = pending[0]
    interrupt_id = int(interrupt["id"])
    resolve_interrupt(interrupt_id, decision)
    _update_workflow(workflow_id, status="active", current_node="resumed")
    log_agent_action(
        workflow_id,
        "resumed",
        input_data={"interrupt_id": interrupt_id, "resolution": decision},
        output_data={},
        decision_reasoning="User provided interrupt resolution",
    )
    def _finalize_with_review(result: dict, *, review_status: str = "resolved", notes: str | None = None) -> dict:
        try:
            resolve_reviews_for_interrupt(
                interrupt_id,
                status=review_status,
                resolution_notes=notes or decision,
            )
        except Exception as exc:
            logger.warning("Unable to resolve review items for interrupt %s: %s", interrupt_id, exc)
        return result

    context = interrupt.get("context") or {}
    intent = context.get("intent")
    stage = context.get("stage")
    original_text = (context.get("original_text") or "").strip()

    if intent == IntentType.ADD_TASK.value:
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_add_task(workflow_id, combined, allow_interrupt=False))
    if intent == IntentType.COMPLETE_TASK.value:
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_complete_task(workflow_id, combined))
    if intent == IntentType.SKIP_TASK.value:
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_skip_task(workflow_id, combined))
    if intent == IntentType.DELETE_TASK.value:
        if stage == "confirm_delete":
            task_id = context.get("task_id")
            task_name = context.get("task_name")
            preview_id = context.get("preview_id")
            if _is_affirmative(decision):
                return _finalize_with_review(
                    _execute_delete_task(
                        workflow_id,
                        int(task_id),
                        task_name_hint=task_name,
                        preview_id=preview_id,
                    ),
                    review_status="approved",
                )
            if _is_negative(decision):
                cancelled_response = f"Canceled deletion of: {task_name or f'task #{task_id}'}"
                log_agent_action(
                    workflow_id,
                    "executed",
                    input_data={"intent": IntentType.DELETE_TASK.value, "task_id": task_id},
                    output_data={"task_id": task_id, "deleted": False, "cancelled": True},
                    decision_reasoning="User rejected destructive action",
                )
                return _finalize_with_review(
                    _complete(workflow_id, cancelled_response, output={"deleted_task_id": None}),
                    review_status="rejected",
                )
            refined_delete_text = _merge_resume_text(original_text, decision)
            return _finalize_with_review(
                _handle_delete_task(workflow_id, refined_delete_text),
                notes=f"Refined approval response: {decision}",
            )
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_delete_task(workflow_id, combined))
    if intent == IntentType.BULK_ADD.value:
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_bulk_add(workflow_id, combined))
    if intent == IntentType.BULK_EDIT.value:
        if stage == "confirm_bulk_edit":
            if _is_affirmative(decision):
                replay_text = original_text or context.get("original_text") or ""
                return _finalize_with_review(
                    _handle_bulk_edit(
                        workflow_id,
                        replay_text,
                        allow_interrupt=False,
                        approval_override=True,
                    ),
                    review_status="approved",
                )
            if _is_negative(decision):
                cancelled_response = "Canceled bulk edit."
                log_agent_action(
                    workflow_id,
                    "executed",
                    input_data={"intent": IntentType.BULK_EDIT.value},
                    output_data={"updated_count": 0, "cancelled": True},
                    decision_reasoning="User rejected bulk edit approval request",
                )
                return _finalize_with_review(
                    _complete(workflow_id, cancelled_response, output={"updated_count": 0, "updated_task_ids": []}),
                    review_status="rejected",
                )
            refined_bulk_text = _merge_resume_text(original_text, decision)
            return _finalize_with_review(
                _handle_bulk_edit(
                    workflow_id,
                    refined_bulk_text,
                    allow_interrupt=True,
                    approval_override=False,
                ),
                notes=f"Refined approval response: {decision}",
            )
        combined = _merge_resume_text(original_text, decision)
        return _finalize_with_review(_handle_bulk_edit(workflow_id, combined, allow_interrupt=False))
    if intent == IntentType.QUERY.value:
        return _finalize_with_review(_handle_query(workflow_id, decision))

    return _finalize_with_review(_complete(workflow_id, "✓ Workflow resumed."))


def list_pending_interrupts() -> list[dict]:
    """List all unresolved agent interrupts."""
    interrupts = get_pending_interrupts()
    pending_reviews = list_review_items(status="pending", limit=1000)
    reviews_by_interrupt: dict[int, list[dict]] = {}
    reviews_by_workflow: dict[int, list[dict]] = {}
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
    for interrupt in interrupts:
        interrupt_id = int(interrupt.get("id"))
        workflow_id = int(interrupt.get("workflow_id"))
        attached = reviews_by_interrupt.get(interrupt_id) or reviews_by_workflow.get(workflow_id) or []
        interrupt["reviews"] = attached
        if attached:
            interrupt["review_id"] = attached[0].get("review_id")
    return interrupts
