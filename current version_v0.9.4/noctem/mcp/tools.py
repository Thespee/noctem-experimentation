"""MCP tools for Noctem (read + write, Phase 4)."""
from __future__ import annotations
from datetime import date
from datetime import datetime, time, timedelta
from typing import Any
import json
import uuid
from contextvars import ContextVar

from .. import __version__
from ..db import get_db
from ..services import goal_service, project_service, task_service
from .resolver import resolve_scope, resolve_task_target
from .contracts import (
    DEFAULT_MCP_CAPABILITIES,
    MCP_SCHEMA_VERSION,
    MCP_SERVER_VERSION,
    MCP_TOOL_CONTRACT_VERSION,
    MCPTool,
    MCPToolDefinition,
    MCPRequestContext,
)
from .registry import MCPToolRegistry
MAX_BULK_AUTO_COMMIT = 1

_PREVIEW_STORE: dict[str, dict[str, Any]] = {}
_COMMIT_RESULT_STORE: dict[tuple[str, str], dict[str, Any]] = {}
_AUDIT_EVENTS: list[dict[str, Any]] = []
_UNDO_PREVIEW_STORE: dict[str, dict[str, Any]] = {}
_CURRENT_MCP_CONTEXT: ContextVar[MCPRequestContext | None] = ContextVar("mcp_request_context", default=None)


def push_request_context(context: MCPRequestContext):
    return _CURRENT_MCP_CONTEXT.set(context)


def pop_request_context(token):
    _CURRENT_MCP_CONTEXT.reset(token)


def _current_correlation_id() -> str | None:
    context = _CURRENT_MCP_CONTEXT.get()
    if context is None:
        return None
    return context.correlation_id


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _object_type_for_operation(operation: str) -> str | None:
    op = str(operation or "").strip().lower()
    if op.startswith("tasks.") or op.startswith("dependencies.") or op.startswith("subtasks."):
        return "task"
    if op.startswith("projects."):
        return "project"
    if op.startswith("goals."):
        return "goal"
    return None


def _hydrate_snapshot_from_id(object_type: str, typed_id: int) -> dict[str, Any] | None:
    if object_type == "task":
        task = task_service.get_task(int(typed_id))
        return _task_payload(task) if task else None
    if object_type == "project":
        project = project_service.get_project(int(typed_id))
        return _project_payload(project) if project else None
    if object_type == "goal":
        goal = goal_service.get_goal(int(typed_id))
        return _goal_payload(goal) if goal else None
    return None


def _extract_snapshots_for_event(operation: str, details: dict[str, Any]) -> list[dict[str, Any]]:
    object_type = _object_type_for_operation(operation)
    if object_type is None:
        return []
    snapshots: list[dict[str, Any]] = []
    for key in ("task", "project", "goal", "before", "after"):
        value = details.get(key)
        if isinstance(value, dict):
            snapshots.append(value)
    for key in ("tasks", "before_tasks", "after_tasks"):
        value = details.get(key)
        if isinstance(value, list):
            snapshots.extend(item for item in value if isinstance(item, dict))

    if not snapshots:
        id_keys = ("verified_affected_task_ids", "affected_task_ids", "task_ids", "project_id", "goal_id", "task_id")
        candidate_ids: list[int] = []
        for key in id_keys:
            value = details.get(key)
            if isinstance(value, list):
                for item in value:
                    try:
                        candidate_ids.append(int(item))
                    except Exception:
                        continue
            else:
                try:
                    if value is not None:
                        candidate_ids.append(int(value))
                except Exception:
                    continue
        for typed_id in list(dict.fromkeys(candidate_ids)):
            snapshot = _hydrate_snapshot_from_id(object_type, typed_id)
            if snapshot:
                snapshots.append(snapshot)

    deduped: dict[int, dict[str, Any]] = {}
    for snapshot in snapshots:
        try:
            typed_id = int(snapshot.get("id"))
        except Exception:
            continue
        deduped[typed_id] = snapshot
    return list(deduped.values())


def _persist_object_version(
    *,
    object_type: str,
    snapshot: dict[str, Any],
    event_id: str,
    correlation_id: str | None,
) -> None:
    try:
        typed_id = int(snapshot.get("id"))
    except Exception:
        return
    object_id = f"{object_type}:{typed_id}"
    now_iso = datetime.utcnow().isoformat() + "Z"
    snapshot_json = _json_dumps(snapshot)
    with get_db() as conn:
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
            return
        parent_version_id = head["version_id"] if head else None
        next_version = int(head["version_num"]) + 1 if head and head["version_num"] is not None else 1
        version_id = f"ov-{uuid.uuid4().hex[:16]}"
        created_by = correlation_id or "mcp"
        conn.execute(
            """
            INSERT INTO object_versions
            (version_id, object_id, version_num, snapshot_json, parent_version_id, event_id, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, object_id, next_version, snapshot_json, parent_version_id, event_id, created_by, now_iso),
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


def _store_preview(operation: str, payload: dict[str, Any]) -> str:
    preview_id = f"preview-{operation}-{uuid.uuid4().hex[:12]}"
    preview_payload = {
        "preview_id": preview_id,
        "operation": operation,
        "created_at": datetime.utcnow().isoformat() + "Z",
        **payload,
    }
    _PREVIEW_STORE[preview_id] = preview_payload
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO mutation_previews (preview_id, operation, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(preview_id) DO UPDATE SET
                    operation = excluded.operation,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    preview_id,
                    operation,
                    _json_dumps(preview_payload),
                    str(preview_payload.get("created_at") or datetime.utcnow().isoformat() + "Z"),
                ),
            )
    except Exception:
        pass
    return preview_id


def _get_preview(preview_id: str, expected_operation: str) -> dict[str, Any] | None:
    preview = _PREVIEW_STORE.get(preview_id)
    if preview is None:
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT operation, payload_json FROM mutation_previews WHERE preview_id = ?",
                    (preview_id,),
                ).fetchone()
            if row:
                loaded = _json_loads(row["payload_json"], {})
                if isinstance(loaded, dict):
                    preview = {"preview_id": preview_id, "operation": row["operation"], **loaded}
                    _PREVIEW_STORE[preview_id] = preview
        except Exception:
            preview = None
    if not preview:
        return None
    if preview.get("operation") != expected_operation:
        return None
    return preview


def _idempotent_result(operation: str, idempotency_key: str | None) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    cached = _COMMIT_RESULT_STORE.get((operation, idempotency_key))
    if cached is not None:
        return dict(cached)
    try:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM mutation_commit_results
                WHERE operation = ? AND idempotency_key = ?
                """,
                (operation, idempotency_key),
            ).fetchone()
        if row:
            loaded = _json_loads(row["result_json"], {})
            if isinstance(loaded, dict):
                _COMMIT_RESULT_STORE[(operation, idempotency_key)] = dict(loaded)
                return dict(loaded)
    except Exception:
        pass
    return None


def _remember_commit_result(operation: str, idempotency_key: str | None, result: dict[str, Any]) -> None:
    if not idempotency_key:
        return
    _COMMIT_RESULT_STORE[(operation, idempotency_key)] = dict(result)
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO mutation_commit_results (operation, idempotency_key, result_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(operation, idempotency_key) DO UPDATE SET
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (operation, idempotency_key, _json_dumps(result), datetime.utcnow().isoformat() + "Z"),
            )
    except Exception:
        pass


def _record_audit_event(
    *,
    operation: str,
    summary: str,
    details: dict[str, Any],
    undo_actions: list[dict[str, Any]] | None = None,
) -> str:
    event_id = f"audit-{uuid.uuid4().hex[:12]}"
    payload = {
        "event_id": event_id,
        "operation": operation,
        "summary": summary,
        "details": details,
        "undo_actions": list(undo_actions or []),
        "correlation_id": _current_correlation_id(),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    _AUDIT_EVENTS.append(payload)
    if len(_AUDIT_EVENTS) > 1000:
        del _AUDIT_EVENTS[:200]
    try:
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
                    _json_dumps(payload["undo_actions"]),
                    payload.get("correlation_id"),
                    payload["created_at"],
                ),
            )
    except Exception:
        pass

    object_type = _object_type_for_operation(operation)
    if object_type:
        snapshots = _extract_snapshots_for_event(operation, details)
        if not snapshots:
            for action in list(undo_actions or []):
                snapshot = action.get("snapshot") if isinstance(action, dict) else None
                if isinstance(snapshot, dict):
                    snapshots.append(snapshot)
        for snapshot in snapshots:
            try:
                _persist_object_version(
                    object_type=object_type,
                    snapshot=snapshot,
                    event_id=event_id,
                    correlation_id=payload.get("correlation_id"),
                )
            except Exception:
                continue
    return event_id


def _audit_event_from_row(row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "operation": row["operation"],
        "summary": row["summary"],
        "details": _json_loads(row["details_json"], {}),
        "undo_actions": _json_loads(row["undo_actions_json"], []),
        "correlation_id": row["correlation_id"] if "correlation_id" in row.keys() else None,
        "created_at": row["created_at"],
    }


def _list_audit_events(limit: int, operation: str | None = None) -> list[dict[str, Any]]:
    try:
        with get_db() as conn:
            if operation:
                rows = conn.execute(
                    """
                    SELECT event_id, operation, summary, details_json, undo_actions_json, correlation_id, created_at
                    FROM object_events
                    WHERE lower(operation) = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (operation.lower(), max(0, limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_id, operation, summary, details_json, undo_actions_json, correlation_id, created_at
                    FROM object_events
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (max(0, limit),),
                ).fetchall()
        return [_audit_event_from_row(row) for row in rows]
    except Exception:
        events = list(reversed(_AUDIT_EVENTS))
        if operation:
            events = [event for event in events if str(event.get("operation") or "").strip().lower() == operation.lower()]
        return events[: max(0, limit)]


def _get_audit_event(event_id: str) -> dict[str, Any] | None:
    try:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT event_id, operation, summary, details_json, undo_actions_json, correlation_id, created_at
                FROM object_events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        if row:
            return _audit_event_from_row(row)
    except Exception:
        pass
    return next((item for item in _AUDIT_EVENTS if item.get("event_id") == event_id), None)


def _store_undo_preview(event_id: str, undo_actions: list[dict[str, Any]]) -> str:
    undo_id = f"undo-{uuid.uuid4().hex[:12]}"
    payload = {
        "undo_id": undo_id,
        "event_id": event_id,
        "undo_actions": list(undo_actions),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    _UNDO_PREVIEW_STORE[undo_id] = payload
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO undo_previews (undo_id, event_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(undo_id) DO UPDATE SET
                    event_id = excluded.event_id,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (undo_id, event_id, _json_dumps(payload), payload["created_at"]),
            )
    except Exception:
        pass
    return undo_id


def _get_undo_preview(undo_id: str) -> dict[str, Any] | None:
    preview = _UNDO_PREVIEW_STORE.get(undo_id)
    if preview:
        return preview
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT payload_json FROM undo_previews WHERE undo_id = ?",
                (undo_id,),
            ).fetchone()
        if row:
            loaded = _json_loads(row["payload_json"], {})
            if isinstance(loaded, dict):
                _UNDO_PREVIEW_STORE[undo_id] = loaded
                return loaded
    except Exception:
        pass
    return None

def _snapshot_project(project) -> dict[str, Any]:
    return _project_payload(project)

def _snapshot_goal(goal) -> dict[str, Any]:
    return _goal_payload(goal)

def _restore_task_snapshot(snapshot: dict[str, Any]) -> int | None:
    task_id_raw = snapshot.get("id")
    task_id = int(task_id_raw) if task_id_raw is not None else None
    due_date = _parse_date(snapshot.get("due_date")) if snapshot.get("due_date") is not None else None
    due_time = _parse_time(snapshot.get("due_time")) if snapshot.get("due_time") is not None else None
    if task_id is not None and task_service.get_task(task_id):
        updated = task_service.update_task(
            task_id,
            name=snapshot.get("name"),
            project_id=snapshot.get("project_id"),
            status=snapshot.get("status"),
            due_date=due_date,
            due_time=due_time,
            importance=snapshot.get("importance"),
            tags=list(snapshot.get("tags") or []),
            recurrence_rule=snapshot.get("recurrence_rule"),
        )
        return updated.id if updated else None
    created = task_service.create_task(
        name=str(snapshot.get("name") or "").strip() or "Restored task",
        project_id=snapshot.get("project_id"),
        due_date=due_date,
        due_time=due_time,
        importance=snapshot.get("importance"),
        tags=list(snapshot.get("tags") or []),
        recurrence_rule=snapshot.get("recurrence_rule"),
    )
    status = str(snapshot.get("status") or "").strip().lower()
    if status and status != "not_started":
        task_service.update_task(created.id, status=status)
    return created.id if created else None

def _restore_project_snapshot(snapshot: dict[str, Any]) -> int | None:
    project_id_raw = snapshot.get("id")
    project_id = int(project_id_raw) if project_id_raw is not None else None
    start_date = _parse_date(snapshot.get("start_date")) if snapshot.get("start_date") is not None else None
    end_date = _parse_date(snapshot.get("end_date")) if snapshot.get("end_date") is not None else None
    if project_id is not None and project_service.get_project(project_id):
        project = project_service.update_project(
            project_id,
            name=snapshot.get("name"),
            goal_id=snapshot.get("goal_id"),
            status=snapshot.get("status"),
            summary=snapshot.get("summary"),
            start_date=start_date,
            end_date=end_date,
        )
        return project.id if project else None
    project = project_service.create_project(
        name=str(snapshot.get("name") or "").strip() or "Restored project",
        goal_id=snapshot.get("goal_id"),
        summary=snapshot.get("summary"),
        status=snapshot.get("status") or "in_progress",
        start_date=start_date,
        end_date=end_date,
    )
    return project.id if project else None

def _restore_goal_snapshot(snapshot: dict[str, Any]) -> int | None:
    goal_id_raw = snapshot.get("id")
    goal_id = int(goal_id_raw) if goal_id_raw is not None else None
    if goal_id is not None and goal_service.get_goal(goal_id):
        goal = goal_service.update_goal(
            goal_id,
            name=snapshot.get("name"),
            goal_type=snapshot.get("type"),
            description=snapshot.get("description"),
            archived=bool(snapshot.get("archived", False)),
        )
        return goal.id if goal else None
    goal = goal_service.create_goal(
        name=str(snapshot.get("name") or "").strip() or "Restored goal",
        goal_type=snapshot.get("type") or "bigger_goal",
        description=snapshot.get("description"),
    )
    if bool(snapshot.get("archived", False)):
        goal_service.archive_goal(goal.id)
    return goal.id if goal else None

def _apply_undo_action(action: dict[str, Any]) -> bool:
    action_type = str(action.get("type") or "").strip().lower()
    if action_type == "delete_task":
        task_id = action.get("task_id")
        return bool(task_id is not None and task_service.delete_task(int(task_id)))
    if action_type == "restore_task_snapshot":
        snapshot = dict(action.get("snapshot") or {})
        return _restore_task_snapshot(snapshot) is not None
    if action_type == "delete_project":
        project_id = action.get("project_id")
        return bool(project_id is not None and project_service.delete_project(int(project_id)))
    if action_type == "restore_project_snapshot":
        snapshot = dict(action.get("snapshot") or {})
        return _restore_project_snapshot(snapshot) is not None
    if action_type == "delete_goal":
        goal_id = action.get("goal_id")
        return bool(goal_id is not None and goal_service.delete_goal(int(goal_id)))
    if action_type == "restore_goal_snapshot":
        snapshot = dict(action.get("snapshot") or {})
        return _restore_goal_snapshot(snapshot) is not None
    return False


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return time.fromisoformat(text)


def _task_payload(task) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "project_id": task.project_id,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time.isoformat() if task.due_time else None,
        "importance": task.importance,
        "tags": task.tags or [],
        "recurrence_rule": task.recurrence_rule,
    }
def _project_payload(project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "goal_id": project.goal_id,
        "status": project.status,
        "summary": project.summary,
        "start_date": project.start_date.isoformat() if isinstance(project.start_date, date) else project.start_date,
        "end_date": project.end_date.isoformat() if isinstance(project.end_date, date) else project.end_date,
    }

def _goal_payload(goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "name": goal.name,
        "type": goal.type,
        "description": goal.description,
        "archived": bool(goal.archived),
    }


def _list_payload(tasks: list) -> dict[str, Any]:
    rows = [_task_payload(task) for task in tasks]
    return {
        "count": len(rows),
        "task_ids": [row["id"] for row in rows],
        "tasks": rows,
    }

def _project_list_payload(projects: list) -> dict[str, Any]:
    rows = [_project_payload(project) for project in projects]
    return {
        "count": len(rows),
        "project_ids": [row["id"] for row in rows],
        "projects": rows,
    }

def _goal_list_payload(goals: list) -> dict[str, Any]:
    rows = [_goal_payload(goal) for goal in goals]
    return {
        "count": len(rows),
        "goal_ids": [row["id"] for row in rows],
        "goals": rows,
    }
def _normalize_tags(values: list[Any] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        tag = str(raw).strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
    return normalized

def _task_tags(task) -> list[str]:
    return _normalize_tags(list(task.tags or []))


def _tool_tasks_get(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task = task_service.get_task(int(arguments["task_id"]))
    return {"task": _task_payload(task) if task else None}


def _tool_tasks_list(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    include_done = bool(arguments.get("include_done", False))
    limit = int(arguments.get("limit", 200))
    tasks = task_service.get_all_tasks(include_done=include_done)
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)


def _tool_tasks_list_today(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return _list_payload(task_service.get_tasks_due_today())


def _tool_tasks_list_overdue(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return _list_payload(task_service.get_overdue_tasks())


def _tool_tasks_list_inbox(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return _list_payload(task_service.get_tasks_without_due_date())

def _tool_tasks_list_upcoming(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    days = int(arguments.get("days", 7))
    limit = int(arguments.get("limit", 200))
    include_done = bool(arguments.get("include_done", False))
    start = date.today()
    end = start + timedelta(days=max(days, 0))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if task.due_date is not None and start <= task.due_date <= end
    ]
    tasks.sort(key=lambda row: (row.due_date or date.max, row.due_time or time.max))
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)

def _tool_tasks_list_completed(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    limit = int(arguments.get("limit", 200))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=True)
        if (task.status or "").lower() == "done"
    ]
    tasks.sort(
        key=lambda row: (
            row.completed_at.isoformat() if isinstance(row.completed_at, datetime) else str(row.completed_at or ""),
            row.id or 0,
        ),
        reverse=True,
    )
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)

def _tool_tasks_list_recurring(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    include_done = bool(arguments.get("include_done", False))
    limit = int(arguments.get("limit", 200))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if bool((task.recurrence_rule or "").strip())
    ]
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)

def _tool_tasks_list_by_ids(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_ids = list(arguments.get("task_ids") or [])
    ids = list(dict.fromkeys(int(task_id) for task_id in raw_ids))
    include_done = bool(arguments.get("include_done", False))
    tasks: list[Any] = []
    for task_id in ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if not include_done and (task.status or "").lower() in {"done", "canceled"}:
            continue
        tasks.append(task)
    return _list_payload(tasks)

def _tool_tasks_search(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip().lower()
    if not query:
        raise ValueError("query is required")
    include_done = bool(arguments.get("include_done", False))
    limit = int(arguments.get("limit", 200))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if query in (task.name or "").lower()
    ]
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)

def _tool_tasks_list_by_project(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project_id = int(arguments["project_id"])
    include_done = bool(arguments.get("include_done", False))
    tasks = task_service.get_project_tasks(project_id)
    if not include_done:
        tasks = [task for task in tasks if (task.status or "").lower() not in {"done", "canceled"}]
    return _list_payload(tasks)

def _tool_tasks_list_by_goal(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal_id = int(arguments["goal_id"])
    include_done = bool(arguments.get("include_done", False))
    projects = project_service.get_all_projects(goal_id=goal_id)
    seen: set[int] = set()
    tasks: list[Any] = []
    for project in projects:
        for task in task_service.get_project_tasks(project.id):
            if task.id in seen:
                continue
            if not include_done and (task.status or "").lower() in {"done", "canceled"}:
                continue
            seen.add(task.id)
            tasks.append(task)
    return _list_payload(tasks)

def _tool_tasks_list_by_status(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    status = str(arguments.get("status") or "").strip().lower()
    if not status:
        raise ValueError("status is required")
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=True)
        if (task.status or "").strip().lower() == status
    ]
    return _list_payload(tasks)

def _tool_tasks_list_by_priority(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    min_importance = float(arguments.get("min_importance", 0.0))
    include_done = bool(arguments.get("include_done", False))
    limit = int(arguments.get("limit", 200))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if (task.importance or 0.0) >= min_importance
    ]
    tasks.sort(key=lambda row: (row.importance or 0.0), reverse=True)
    if limit >= 0:
        tasks = tasks[:limit]
    return _list_payload(tasks)

def _tool_tasks_list_by_date_range(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    start_date = _parse_date(str(arguments.get("start_date") or ""))
    end_date = _parse_date(str(arguments.get("end_date") or ""))
    if start_date is None or end_date is None:
        raise ValueError("start_date and end_date are required")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    include_done = bool(arguments.get("include_done", False))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if task.due_date is not None and start_date <= task.due_date <= end_date
    ]
    tasks.sort(key=lambda row: (row.due_date or date.max, row.due_time or time.max))
    return _list_payload(tasks)

def _tool_tasks_list_by_tag(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    tag = str(arguments.get("tag") or "").strip().lower()
    if not tag:
        raise ValueError("tag is required")
    include_done = bool(arguments.get("include_done", False))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if any(tag == str(value).strip().lower() for value in (task.tags or []))
    ]
    return _list_payload(tasks)

def _tool_tasks_list_blocked(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    include_done = bool(arguments.get("include_done", False))
    tasks = [
        task
        for task in task_service.get_all_tasks(include_done=include_done)
        if any(str(value).strip().lower() == "blocked" for value in (task.tags or []))
    ]
    return _list_payload(tasks)

def _tool_tasks_list_stale(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    days = int(arguments.get("days", 14))
    cutoff = date.today() - timedelta(days=max(days, 0))
    include_done = bool(arguments.get("include_done", False))
    tasks = []
    for task in task_service.get_all_tasks(include_done=include_done):
        created_at = task.created_at
        if isinstance(created_at, datetime):
            created_date = created_at.date()
        elif isinstance(created_at, str):
            try:
                created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
            except Exception:
                continue
        else:
            continue
        if created_date <= cutoff and task.due_date is None:
            tasks.append(task)
    return _list_payload(tasks)

def _tool_tasks_rename(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, name=name)
    if updated is None:
        raise RuntimeError("task rename failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task rename verification failed")
    _record_audit_event(
        operation="tasks.rename",
        summary=f"Renamed task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": refreshed.name == name, "task": _task_payload(refreshed)}

def _tool_tasks_set_due(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    due_date = _parse_date(str(arguments.get("due_date") or ""))
    due_time_raw = arguments.get("due_time")
    due_time = _parse_time(str(due_time_raw)) if due_time_raw is not None else None
    if due_date is None:
        raise ValueError("due_date is required")
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, due_date=due_date, due_time=due_time)
    if updated is None:
        raise RuntimeError("task due update failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task due update verification failed")
    verified = refreshed.due_date == due_date and (due_time_raw is None or refreshed.due_time == due_time)
    _record_audit_event(
        operation="tasks.set_due",
        summary=f"Set due date for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_tasks_clear_due(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, due_date=None, due_time=None)
    if updated is None:
        raise RuntimeError("task clear due failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task clear due verification failed")
    verified = refreshed.due_date is None and refreshed.due_time is None
    _record_audit_event(
        operation="tasks.clear_due",
        summary=f"Cleared due date for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_tasks_set_priority(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    importance = float(arguments["importance"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, importance=importance)
    if updated is None:
        raise RuntimeError("task priority update failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task priority verification failed")
    _record_audit_event(
        operation="tasks.set_priority",
        summary=f"Set priority for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": refreshed.importance == importance, "task": _task_payload(refreshed)}

def _tool_tasks_set_tags(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    tags = _normalize_tags(list(arguments.get("tags") or []))
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, tags=tags)
    if updated is None:
        raise RuntimeError("task set tags failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task set tags verification failed")
    verified = _task_tags(refreshed) == tags
    _record_audit_event(
        operation="tasks.set_tags",
        summary=f"Set tags for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_tasks_add_tags(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    tags_to_add = _normalize_tags(list(arguments.get("tags") or []))
    if not tags_to_add:
        raise ValueError("tags are required")
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    existing_tags = _task_tags(before) if before else []
    merged = _normalize_tags(existing_tags + tags_to_add)
    updated = task_service.update_task(task_id, tags=merged)
    if updated is None:
        raise RuntimeError("task add tags failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task add tags verification failed")
    verified = all(tag.lower() in {value.lower() for value in _task_tags(refreshed)} for tag in tags_to_add)
    _record_audit_event(
        operation="tasks.add_tags",
        summary=f"Added tags for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed), "added_tags": tags_to_add},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_tasks_remove_tags(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    tags_to_remove = _normalize_tags(list(arguments.get("tags") or []))
    if not tags_to_remove:
        raise ValueError("tags are required")
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    removal_keys = {tag.lower() for tag in tags_to_remove}
    remaining = [tag for tag in (_task_tags(before) if before else []) if tag.lower() not in removal_keys]
    updated = task_service.update_task(task_id, tags=remaining)
    if updated is None:
        raise RuntimeError("task remove tags failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task remove tags verification failed")
    refreshed_keys = {tag.lower() for tag in _task_tags(refreshed)}
    verified = not any(tag in refreshed_keys for tag in removal_keys)
    _record_audit_event(
        operation="tasks.remove_tags",
        summary=f"Removed tags for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed), "removed_tags": tags_to_remove},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_tasks_assign_project(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    project_id_raw = arguments.get("project_id")
    project_id = int(project_id_raw) if project_id_raw is not None else None
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, project_id=project_id)
    if updated is None:
        raise RuntimeError("task project assignment failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task project assignment verification failed")
    _record_audit_event(
        operation="tasks.assign_project",
        summary=f"Assigned project for task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": refreshed.project_id == project_id, "task": _task_payload(refreshed)}

def _tool_tasks_mark_in_progress(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, status="in_progress")
    if updated is None:
        raise RuntimeError("task status update failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task status verification failed")
    _record_audit_event(
        operation="tasks.mark_in_progress",
        summary=f"Marked task #{task_id} in progress",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": (refreshed.status or "").lower() == "in_progress", "task": _task_payload(refreshed)}

def _tool_tasks_reopen(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.update_task(task_id, status="not_started")
    if updated is None:
        raise RuntimeError("task reopen failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task reopen verification failed")
    _record_audit_event(
        operation="tasks.reopen",
        summary=f"Reopened task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "verified": (refreshed.status or "").lower() == "not_started", "task": _task_payload(refreshed)}


def _tool_tasks_create(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    project_id = arguments.get("project_id")
    due_date_raw = arguments.get("due_date")
    due_time_raw = arguments.get("due_time")
    importance_raw = arguments.get("importance")
    tags_raw = arguments.get("tags")
    recurrence_rule = arguments.get("recurrence_rule")

    created = task_service.create_task(
        name=name,
        project_id=int(project_id) if project_id is not None else None,
        due_date=_parse_date(str(due_date_raw)) if due_date_raw is not None else None,
        due_time=_parse_time(str(due_time_raw)) if due_time_raw is not None else None,
        importance=float(importance_raw) if importance_raw is not None else None,
        tags=[str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else None,
        recurrence_rule=str(recurrence_rule).strip() if isinstance(recurrence_rule, str) and recurrence_rule.strip() else None,
    )
    if created is None:
        raise RuntimeError("task creation failed")
    refreshed = task_service.get_task(created.id)
    if refreshed is None:
        raise RuntimeError("task creation verification failed")
    _record_audit_event(
        operation="tasks.create",
        summary=f"Created task #{refreshed.id}",
        details={"task": _task_payload(refreshed)},
        undo_actions=[{"type": "delete_task", "task_id": refreshed.id}],
    )
    return {
        "created": True,
        "task": _task_payload(refreshed),
    }


def _tool_tasks_complete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.complete_task(task_id)
    if updated is None:
        raise RuntimeError("task completion failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task completion verification failed")
    verified = (refreshed.status or "").lower() == "done"
    _record_audit_event(
        operation="tasks.complete",
        summary=f"Completed task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {
        "completed": True,
        "verified": verified,
        "task": _task_payload(refreshed),
    }


def _tool_tasks_skip(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    before = task_service.get_task(task_id)
    before_payload = _task_payload(before) if before else None
    updated = task_service.skip_task(task_id)
    if updated is None:
        raise RuntimeError("task skip failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task skip verification failed")
    _record_audit_event(
        operation="tasks.skip",
        summary=f"Skipped task #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {
        "skipped": True,
        "task": _task_payload(refreshed),
    }


def _tool_tasks_update_fields(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    existing = task_service.get_task(task_id)
    if existing is None:
        raise RuntimeError("task not found")
    before_payload = _task_payload(existing)

    provided_fields = [field for field in arguments.keys() if field != "task_id"]
    if not provided_fields:
        raise ValueError("at least one updatable field is required")

    updates: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        updates["name"] = name
    if "project_id" in arguments:
        project_id_raw = arguments.get("project_id")
        updates["project_id"] = int(project_id_raw) if project_id_raw is not None else None
    if "status" in arguments:
        status = str(arguments.get("status") or "").strip()
        if not status:
            raise ValueError("status cannot be empty")
        updates["status"] = status
    if "due_date" in arguments:
        due_date_raw = arguments.get("due_date")
        updates["due_date"] = _parse_date(str(due_date_raw)) if due_date_raw is not None else None
    if "due_time" in arguments:
        due_time_raw = arguments.get("due_time")
        updates["due_time"] = _parse_time(str(due_time_raw)) if due_time_raw is not None else None
    if "importance" in arguments:
        importance_raw = arguments.get("importance")
        updates["importance"] = float(importance_raw) if importance_raw is not None else None
    if "tags" in arguments:
        tags_raw = arguments.get("tags")
        updates["tags"] = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    if "recurrence_rule" in arguments:
        recurrence_rule = arguments.get("recurrence_rule")
        updates["recurrence_rule"] = str(recurrence_rule).strip() if recurrence_rule is not None else None

    updated = task_service.update_task(task_id, **updates)
    if updated is None:
        raise RuntimeError("task update failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("task update verification failed")

    verified = True
    for field in provided_fields:
        if field == "name" and refreshed.name != updates.get("name"):
            verified = False
        elif field == "project_id" and refreshed.project_id != updates.get("project_id"):
            verified = False
        elif field == "status" and refreshed.status != updates.get("status"):
            verified = False
        elif field == "due_date" and refreshed.due_date != updates.get("due_date"):
            verified = False
        elif field == "due_time" and refreshed.due_time != updates.get("due_time"):
            verified = False
        elif field == "importance" and refreshed.importance != updates.get("importance"):
            verified = False
        elif field == "tags" and list(refreshed.tags or []) != list(updates.get("tags") or []):
            verified = False
        elif field == "recurrence_rule" and refreshed.recurrence_rule != updates.get("recurrence_rule"):
            verified = False
    _record_audit_event(
        operation="tasks.update_fields",
        summary=f"Updated task #{task_id}",
        details={
            "task_id": task_id,
            "provided_fields": provided_fields,
            "before": before_payload,
            "after": _task_payload(refreshed),
        },
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}],
    )

    return {
        "updated": True,
        "verified": verified,
        "task": _task_payload(refreshed),
    }

def _tool_tasks_resolve_candidates(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    include_done = bool(arguments.get("include_done", False))
    limit = int(arguments.get("limit", 5))
    resolution = resolve_task_target(
        query,
        include_done=include_done,
        priority_index_limit=20,
        candidate_limit=max(1, min(limit, 25)),
    )
    selected = resolution.get("selected_task")
    selected_payload = _task_payload(selected) if selected else None
    return {
        "query": query,
        "resolution": resolution.get("resolution"),
        "ambiguous": bool(resolution.get("ambiguous")),
        "ambiguity_reason": resolution.get("ambiguity_reason"),
        "confidence": float(resolution.get("confidence") or 0.0),
        "selected_task_id": resolution.get("selected_task_id"),
        "selected_task": selected_payload,
        "candidates": list(resolution.get("candidates") or []),
    }


def _tool_tasks_resolve_scope(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    scope_type = str(arguments.get("scope_type") or "unknown").strip().lower()
    source_project_name = arguments.get("source_project_name")
    raw_due_date = arguments.get("source_due_date")
    source_due_date = None
    if isinstance(raw_due_date, str) and raw_due_date.strip():
        source_due_date = date.fromisoformat(raw_due_date.strip())
    raw_names = arguments.get("task_names")
    task_names: list[str] = []
    if isinstance(raw_names, list):
        task_names = [str(name).strip() for name in raw_names if str(name).strip()]

    resolution = resolve_scope(
        scope_type=scope_type,
        source_project_name=str(source_project_name).strip() if isinstance(source_project_name, str) else None,
        source_due_date=source_due_date,
        task_names=task_names,
    )
    tasks = list(resolution.get("_task_objects") or [])
    return {
        "scope_type": resolution.get("scope_type"),
        "scope_ref": resolution.get("scope_ref"),
        "matched_count": int(resolution.get("matched_count") or 0),
        "matched_task_ids": list(resolution.get("matched_task_ids") or []),
        "matched_tasks": [_task_payload(task) for task in tasks[:50]],
        "unresolved_names": list(resolution.get("unresolved_names") or []),
        "ambiguous": bool(resolution.get("ambiguous")),
        "ambiguity_reason": resolution.get("ambiguity_reason"),
        "ambiguity_details": list(resolution.get("ambiguity_details") or []),
        "candidates_by_name": dict(resolution.get("candidates_by_name") or {}),
    }


def _tool_tasks_preview_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    task = task_service.get_task(task_id)
    if task is None:
        preview_id = _store_preview(
            "delete",
            {
                "requires_approval": True,
                "approval_reason": "destructive",
                "affected_task_ids": [],
                "affected_count": 0,
                "before_tasks": [],
            },
        )
        return {
            "preview_id": preview_id,
            "operation": "delete",
            "requires_approval": True,
            "approval_reason": "destructive",
            "policy_gates": {"destructive": True, "blast_radius": False},
            "affected_task_ids": [],
            "affected_count": 0,
            "before_tasks": [],
        }

    before = [_task_payload(task)]
    preview_id = _store_preview(
        "delete",
        {
            "task_id": task.id,
            "requires_approval": True,
            "approval_reason": "destructive",
            "affected_task_ids": [task.id],
            "affected_count": 1,
            "before_tasks": before,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "delete",
        "requires_approval": True,
        "approval_reason": "destructive",
        "policy_gates": {"destructive": True, "blast_radius": False},
        "affected_task_ids": [task.id],
        "affected_count": 1,
        "before_tasks": before,
    }


def _tool_tasks_commit_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None

    cached = _idempotent_result("delete", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}

    preview = _get_preview(preview_id, "delete")
    if preview is None:
        raise ValueError("Unknown delete preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before delete commit")

    candidate_ids = list(preview.get("affected_task_ids") or [])
    deleted_ids: list[int] = []
    for task_id in candidate_ids:
        if task_service.delete_task(int(task_id)):
            deleted_ids.append(int(task_id))

    verified_deleted = [
        task_id
        for task_id in candidate_ids
        if task_service.get_task(int(task_id)) is None
    ]
    before_tasks = list(preview.get("before_tasks") or [])
    result = {
        "operation": "delete",
        "preview_id": preview_id,
        "committed": True,
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": deleted_ids,
        "affected_count": len(deleted_ids),
        "verified_affected_task_ids": verified_deleted,
        "verified_affected_count": len(verified_deleted),
    }
    _record_audit_event(
        operation="tasks.commit_delete",
        summary=f"Deleted {len(verified_deleted)} task(s)",
        details={
            "preview_id": preview_id,
            "affected_task_ids": deleted_ids,
            "verified_affected_task_ids": verified_deleted,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("delete", idempotency_key, result)
    return result


def _tool_tasks_preview_bulk_update(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    updates = dict(arguments.get("updates") or {})
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")

    normalized_updates: dict[str, Any] = {}
    if "due_date" in updates:
        due_date_raw = updates.get("due_date")
        if due_date_raw is None:
            normalized_updates["due_date"] = None
        else:
            normalized_updates["due_date"] = _parse_date(str(due_date_raw)).isoformat()
    if "due_time" in updates:
        due_time_raw = updates.get("due_time")
        if due_time_raw is None:
            normalized_updates["due_time"] = None
        else:
            normalized_updates["due_time"] = _parse_time(str(due_time_raw)).isoformat()
    if "project_id" in updates:
        project_raw = updates.get("project_id")
        normalized_updates["project_id"] = int(project_raw) if project_raw is not None else None

    if not normalized_updates:
        raise ValueError("No supported updates provided for bulk preview")

    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if (task.status or "").lower() in {"done", "canceled"}:
            continue
        existing_tasks.append(task)

    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = affected_count > MAX_BULK_AUTO_COMMIT
    approval_reason = "blast_radius" if requires_approval else None
    preview_id = _store_preview(
        "bulk_update",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "updates": normalized_updates,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_update",
        "scope_ref": scope_ref,
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {
            "destructive": False,
            "blast_radius": requires_approval,
            "bulk_auto_commit_threshold": MAX_BULK_AUTO_COMMIT,
        },
        "updates": normalized_updates,
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }


def _tool_tasks_commit_bulk_update(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None

    cached = _idempotent_result("bulk_update", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}

    preview = _get_preview(preview_id, "bulk_update")
    if preview is None:
        raise ValueError("Unknown bulk_update preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_update commit")

    updates = dict(preview.get("updates") or {})
    before_tasks = list(preview.get("before_tasks") or [])
    update_payload: dict[str, Any] = {}
    if "due_date" in updates:
        update_payload["due_date"] = _parse_date(updates.get("due_date"))
    if "due_time" in updates:
        update_payload["due_time"] = _parse_time(updates.get("due_time"))
    if "project_id" in updates and updates.get("project_id") is not None:
        update_payload["project_id"] = int(updates["project_id"])

    affected_task_ids = list(preview.get("task_ids") or [])
    updated_ids: list[int] = []
    for task_id in affected_task_ids:
        updated = task_service.update_task(int(task_id), **update_payload)
        if updated is not None:
            updated_ids.append(int(task_id))

    verified_ids: list[int] = []
    for task_id in updated_ids:
        refreshed = task_service.get_task(task_id)
        if refreshed is None:
            continue
        verified = True
        if "due_date" in update_payload:
            if update_payload["due_date"] != refreshed.due_date:
                verified = False
        if "due_time" in update_payload:
            if update_payload["due_time"] != refreshed.due_time:
                verified = False
        if "project_id" in update_payload:
            if refreshed.project_id != update_payload["project_id"]:
                verified = False
        if verified:
            verified_ids.append(task_id)

    result = {
        "operation": "bulk_update",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "updates": updates,
        "affected_task_ids": updated_ids,
        "affected_count": len(updated_ids),
        "verified_affected_task_ids": verified_ids,
        "verified_affected_count": len(verified_ids),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_update",
        summary=f"Bulk updated {len(verified_ids)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "updates": updates,
            "verified_affected_task_ids": verified_ids,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_update", idempotency_key, result)
    return result

def _tool_tasks_preview_bulk_complete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")
    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if (task.status or "").lower() in {"done", "canceled"}:
            continue
        existing_tasks.append(task)
    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = affected_count > MAX_BULK_AUTO_COMMIT
    approval_reason = "blast_radius" if requires_approval else None
    preview_id = _store_preview(
        "bulk_complete",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_complete",
        "scope_ref": scope_ref,
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {
            "destructive": False,
            "blast_radius": requires_approval,
            "bulk_auto_commit_threshold": MAX_BULK_AUTO_COMMIT,
        },
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }

def _tool_tasks_commit_bulk_complete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None
    cached = _idempotent_result("bulk_complete", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    preview = _get_preview(preview_id, "bulk_complete")
    if preview is None:
        raise ValueError("Unknown bulk_complete preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_complete commit")
    before_tasks = list(preview.get("before_tasks") or [])
    affected_task_ids = list(preview.get("task_ids") or [])
    completed_ids: list[int] = []
    for task_id in affected_task_ids:
        updated = task_service.complete_task(int(task_id))
        if updated is not None:
            completed_ids.append(int(task_id))
    verified_ids: list[int] = []
    for task_id in completed_ids:
        refreshed = task_service.get_task(task_id)
        if refreshed is not None and (refreshed.status or "").lower() == "done":
            verified_ids.append(task_id)
    result = {
        "operation": "bulk_complete",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": completed_ids,
        "affected_count": len(completed_ids),
        "verified_affected_task_ids": verified_ids,
        "verified_affected_count": len(verified_ids),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_complete",
        summary=f"Bulk completed {len(verified_ids)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "verified_affected_task_ids": verified_ids,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_complete", idempotency_key, result)
    return result

def _tool_tasks_preview_bulk_skip(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    target_due_date = _parse_date(str(arguments.get("target_due_date") or "")) or (date.today() + timedelta(days=1))
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")
    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if (task.status or "").lower() in {"done", "canceled"}:
            continue
        existing_tasks.append(task)
    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = affected_count > MAX_BULK_AUTO_COMMIT
    approval_reason = "blast_radius" if requires_approval else None
    preview_id = _store_preview(
        "bulk_skip",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "target_due_date": target_due_date.isoformat(),
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_skip",
        "scope_ref": scope_ref,
        "target_due_date": target_due_date.isoformat(),
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {
            "destructive": False,
            "blast_radius": requires_approval,
            "bulk_auto_commit_threshold": MAX_BULK_AUTO_COMMIT,
        },
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }

def _tool_tasks_commit_bulk_skip(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None
    cached = _idempotent_result("bulk_skip", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    preview = _get_preview(preview_id, "bulk_skip")
    if preview is None:
        raise ValueError("Unknown bulk_skip preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_skip commit")
    before_tasks = list(preview.get("before_tasks") or [])
    target_due_date = _parse_date(str(preview.get("target_due_date") or ""))
    if target_due_date is None:
        raise RuntimeError("bulk_skip preview missing target_due_date")
    affected_task_ids = list(preview.get("task_ids") or [])
    skipped_ids: list[int] = []
    for task_id in affected_task_ids:
        updated = task_service.update_task(int(task_id), due_date=target_due_date)
        if updated is not None:
            skipped_ids.append(int(task_id))
    verified_ids: list[int] = []
    for task_id in skipped_ids:
        refreshed = task_service.get_task(task_id)
        if refreshed is not None and refreshed.due_date == target_due_date:
            verified_ids.append(task_id)
    result = {
        "operation": "bulk_skip",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "target_due_date": target_due_date.isoformat(),
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": skipped_ids,
        "affected_count": len(skipped_ids),
        "verified_affected_task_ids": verified_ids,
        "verified_affected_count": len(verified_ids),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_skip",
        summary=f"Bulk skipped {len(verified_ids)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "target_due_date": target_due_date.isoformat(),
            "verified_affected_task_ids": verified_ids,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_skip", idempotency_key, result)
    return result

def _tool_tasks_preview_bulk_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")
    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        existing_tasks.append(task)
    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = True
    approval_reason = "destructive"
    preview_id = _store_preview(
        "bulk_delete",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_delete",
        "scope_ref": scope_ref,
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {"destructive": True, "blast_radius": affected_count > MAX_BULK_AUTO_COMMIT},
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }

def _tool_tasks_commit_bulk_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None
    cached = _idempotent_result("bulk_delete", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    preview = _get_preview(preview_id, "bulk_delete")
    if preview is None:
        raise ValueError("Unknown bulk_delete preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_delete commit")
    before_tasks = list(preview.get("before_tasks") or [])
    candidate_ids = list(preview.get("task_ids") or [])
    deleted_ids: list[int] = []
    for task_id in candidate_ids:
        if task_service.delete_task(int(task_id)):
            deleted_ids.append(int(task_id))
    verified_deleted = [task_id for task_id in candidate_ids if task_service.get_task(int(task_id)) is None]
    result = {
        "operation": "bulk_delete",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": deleted_ids,
        "affected_count": len(deleted_ids),
        "verified_affected_task_ids": verified_deleted,
        "verified_affected_count": len(verified_deleted),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_delete",
        summary=f"Bulk deleted {len(verified_deleted)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "affected_task_ids": deleted_ids,
            "verified_affected_task_ids": verified_deleted,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_delete", idempotency_key, result)
    return result

def _tool_tasks_preview_bulk_move_project(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    project_id_raw = arguments.get("project_id")
    project_id = int(project_id_raw) if project_id_raw is not None else None
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")
    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if (task.status or "").lower() in {"done", "canceled"}:
            continue
        existing_tasks.append(task)
    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = affected_count > MAX_BULK_AUTO_COMMIT
    approval_reason = "blast_radius" if requires_approval else None
    preview_id = _store_preview(
        "bulk_move_project",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "project_id": project_id,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_move_project",
        "scope_ref": scope_ref,
        "project_id": project_id,
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {
            "destructive": False,
            "blast_radius": requires_approval,
            "bulk_auto_commit_threshold": MAX_BULK_AUTO_COMMIT,
        },
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }

def _tool_tasks_commit_bulk_move_project(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None
    cached = _idempotent_result("bulk_move_project", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    preview = _get_preview(preview_id, "bulk_move_project")
    if preview is None:
        raise ValueError("Unknown bulk_move_project preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_move_project commit")
    before_tasks = list(preview.get("before_tasks") or [])
    target_project_id_raw = preview.get("project_id")
    target_project_id = int(target_project_id_raw) if target_project_id_raw is not None else None
    affected_task_ids = list(preview.get("task_ids") or [])
    moved_ids: list[int] = []
    for task_id in affected_task_ids:
        updated = task_service.update_task(int(task_id), project_id=target_project_id)
        if updated is not None:
            moved_ids.append(int(task_id))
    verified_ids: list[int] = []
    for task_id in moved_ids:
        refreshed = task_service.get_task(task_id)
        if refreshed is not None and refreshed.project_id == target_project_id:
            verified_ids.append(task_id)
    result = {
        "operation": "bulk_move_project",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "project_id": target_project_id,
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": moved_ids,
        "affected_count": len(moved_ids),
        "verified_affected_task_ids": verified_ids,
        "verified_affected_count": len(verified_ids),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_move_project",
        summary=f"Bulk moved {len(verified_ids)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "project_id": target_project_id,
            "verified_affected_task_ids": verified_ids,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_move_project", idempotency_key, result)
    return result

def _tool_tasks_preview_bulk_retag(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    raw_task_ids = list(arguments.get("task_ids") or [])
    scope_ref = str(arguments.get("scope_ref") or "task_ids")
    set_tags_value = arguments.get("set_tags")
    add_tags = _normalize_tags(list(arguments.get("add_tags") or []))
    remove_tags = _normalize_tags(list(arguments.get("remove_tags") or []))
    set_tags = _normalize_tags(list(set_tags_value or [])) if set_tags_value is not None else None
    if set_tags is None and not add_tags and not remove_tags:
        raise ValueError("one of set_tags, add_tags, or remove_tags is required")
    unique_task_ids = list(dict.fromkeys(int(task_id) for task_id in raw_task_ids))
    if not unique_task_ids:
        raise ValueError("task_ids are required for bulk preview")
    existing_tasks = []
    for task_id in unique_task_ids:
        task = task_service.get_task(task_id)
        if task is None:
            continue
        if (task.status or "").lower() in {"done", "canceled"}:
            continue
        existing_tasks.append(task)
    existing_ids = [task.id for task in existing_tasks]
    before_tasks = [_task_payload(task) for task in existing_tasks]
    affected_count = len(existing_ids)
    requires_approval = affected_count > MAX_BULK_AUTO_COMMIT
    approval_reason = "blast_radius" if requires_approval else None
    preview_id = _store_preview(
        "bulk_retag",
        {
            "scope_ref": scope_ref,
            "task_ids": existing_ids,
            "tag_updates": {
                "set_tags": set_tags,
                "add_tags": add_tags,
                "remove_tags": remove_tags,
            },
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "affected_task_ids": existing_ids,
            "affected_count": affected_count,
            "before_tasks": before_tasks,
        },
    )
    return {
        "preview_id": preview_id,
        "operation": "bulk_retag",
        "scope_ref": scope_ref,
        "tag_updates": {
            "set_tags": set_tags,
            "add_tags": add_tags,
            "remove_tags": remove_tags,
        },
        "requires_approval": requires_approval,
        "approval_reason": approval_reason,
        "policy_gates": {
            "destructive": False,
            "blast_radius": requires_approval,
            "bulk_auto_commit_threshold": MAX_BULK_AUTO_COMMIT,
        },
        "affected_task_ids": existing_ids,
        "affected_count": affected_count,
        "before_tasks": before_tasks,
    }

def _tool_tasks_commit_bulk_retag(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    preview_id = str(arguments["preview_id"])
    approved = bool(arguments.get("approved", False))
    idempotency_key = str(arguments.get("idempotency_key") or "").strip() or None
    cached = _idempotent_result("bulk_retag", idempotency_key)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    preview = _get_preview(preview_id, "bulk_retag")
    if preview is None:
        raise ValueError("Unknown bulk_retag preview_id")
    if preview.get("requires_approval") and not approved:
        raise RuntimeError("Approval required before bulk_retag commit")
    before_tasks = list(preview.get("before_tasks") or [])
    tag_updates = dict(preview.get("tag_updates") or {})
    set_tags_raw = tag_updates.get("set_tags")
    set_tags = _normalize_tags(list(set_tags_raw or [])) if set_tags_raw is not None else None
    add_tags = _normalize_tags(list(tag_updates.get("add_tags") or []))
    remove_tags = _normalize_tags(list(tag_updates.get("remove_tags") or []))
    remove_keys = {tag.lower() for tag in remove_tags}
    affected_task_ids = list(preview.get("task_ids") or [])
    retagged_ids: list[int] = []
    for task_id in affected_task_ids:
        task = task_service.get_task(int(task_id))
        if task is None:
            continue
        tags = _task_tags(task)
        if set_tags is not None:
            tags = list(set_tags)
        if add_tags:
            tags = _normalize_tags(tags + add_tags)
        if remove_keys:
            tags = [tag for tag in tags if tag.lower() not in remove_keys]
        updated = task_service.update_task(int(task_id), tags=tags)
        if updated is not None:
            retagged_ids.append(int(task_id))
    verified_ids: list[int] = []
    set_keys = {tag.lower() for tag in set_tags} if set_tags is not None else None
    add_keys = {tag.lower() for tag in add_tags}
    for task_id in retagged_ids:
        refreshed = task_service.get_task(task_id)
        if refreshed is None:
            continue
        refreshed_keys = {tag.lower() for tag in _task_tags(refreshed)}
        verified = True
        if set_keys is not None and refreshed_keys != set_keys:
            verified = False
        if add_keys and not add_keys.issubset(refreshed_keys):
            verified = False
        if remove_keys and refreshed_keys.intersection(remove_keys):
            verified = False
        if verified:
            verified_ids.append(task_id)
    result = {
        "operation": "bulk_retag",
        "preview_id": preview_id,
        "committed": True,
        "scope_ref": preview.get("scope_ref"),
        "tag_updates": {
            "set_tags": set_tags,
            "add_tags": add_tags,
            "remove_tags": remove_tags,
        },
        "idempotent_replay": False,
        "idempotency_key": idempotency_key,
        "affected_task_ids": retagged_ids,
        "affected_count": len(retagged_ids),
        "verified_affected_task_ids": verified_ids,
        "verified_affected_count": len(verified_ids),
    }
    _record_audit_event(
        operation="tasks.commit_bulk_retag",
        summary=f"Bulk retagged {len(verified_ids)} task(s)",
        details={
            "preview_id": preview_id,
            "scope_ref": preview.get("scope_ref"),
            "tag_updates": result["tag_updates"],
            "verified_affected_task_ids": verified_ids,
        },
        undo_actions=[
            {"type": "restore_task_snapshot", "snapshot": snapshot}
            for snapshot in before_tasks
            if isinstance(snapshot, dict)
        ],
    )
    _remember_commit_result("bulk_retag", idempotency_key, result)
    return result

def _tool_dependencies_add(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    depends_on_task_id = int(arguments["depends_on_task_id"])
    if task_id == depends_on_task_id:
        raise ValueError("task_id cannot depend on itself")
    task = task_service.get_task(task_id)
    dependency = task_service.get_task(depends_on_task_id)
    if task is None or dependency is None:
        raise RuntimeError("task or dependency task not found")
    before_payload = _task_payload(task)
    tags = _task_tags(task)
    dep_tag = f"depends_on:{depends_on_task_id}"
    if dep_tag.lower() not in {value.lower() for value in tags}:
        tags = _normalize_tags(tags + [dep_tag])
    updated = task_service.update_task(task_id, tags=tags)
    if updated is None:
        raise RuntimeError("dependency add failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("dependency add verification failed")
    refreshed_keys = {value.lower() for value in _task_tags(refreshed)}
    verified = dep_tag.lower() in refreshed_keys
    _record_audit_event(
        operation="dependencies.add",
        summary=f"Added dependency for task #{task_id}",
        details={"task_id": task_id, "depends_on_task_id": depends_on_task_id, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed), "depends_on_task_id": depends_on_task_id}

def _tool_dependencies_remove(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    depends_on_task_id = int(arguments["depends_on_task_id"])
    task = task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("task not found")
    before_payload = _task_payload(task)
    dep_tag = f"depends_on:{depends_on_task_id}"
    tags = [tag for tag in _task_tags(task) if tag.lower() != dep_tag.lower()]
    updated = task_service.update_task(task_id, tags=tags)
    if updated is None:
        raise RuntimeError("dependency remove failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("dependency remove verification failed")
    refreshed_keys = {value.lower() for value in _task_tags(refreshed)}
    verified = dep_tag.lower() not in refreshed_keys
    _record_audit_event(
        operation="dependencies.remove",
        summary=f"Removed dependency for task #{task_id}",
        details={"task_id": task_id, "depends_on_task_id": depends_on_task_id, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed), "depends_on_task_id": depends_on_task_id}

def _tool_dependencies_list(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    task = task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("task not found")
    dependency_ids: list[int] = []
    for tag in _task_tags(task):
        normalized = tag.strip().lower()
        if not normalized.startswith("depends_on:"):
            continue
        suffix = normalized.removeprefix("depends_on:")
        if suffix.isdigit():
            dependency_ids.append(int(suffix))
    dependency_ids = list(dict.fromkeys(dependency_ids))
    dependencies = []
    for dep_id in dependency_ids:
        dependency = task_service.get_task(dep_id)
        if dependency is not None:
            dependencies.append(_task_payload(dependency))
    blocked_by: list[int] = []
    for candidate in task_service.get_all_tasks(include_done=True):
        candidate_keys = {tag.lower() for tag in _task_tags(candidate)}
        if f"depends_on:{task_id}" in candidate_keys:
            blocked_by.append(int(candidate.id))
    return {
        "task_id": task_id,
        "dependency_ids": dependency_ids,
        "dependencies": dependencies,
        "blocked_by_task_ids": blocked_by,
        "blocked_by_count": len(blocked_by),
    }

def _tool_subtasks_create(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    parent_task_id = int(arguments["parent_task_id"])
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    parent = task_service.get_task(parent_task_id)
    if parent is None:
        raise RuntimeError("parent task not found")
    due_date_raw = arguments.get("due_date")
    due_time_raw = arguments.get("due_time")
    project_id_raw = arguments.get("project_id")
    tags = _normalize_tags(list(arguments.get("tags") or []))
    tags = _normalize_tags(tags + [f"subtask_of:{parent_task_id}"])
    created = task_service.create_task(
        name=name,
        project_id=int(project_id_raw) if project_id_raw is not None else parent.project_id,
        due_date=_parse_date(str(due_date_raw)) if due_date_raw is not None else parent.due_date,
        due_time=_parse_time(str(due_time_raw)) if due_time_raw is not None else parent.due_time,
        importance=float(arguments["importance"]) if "importance" in arguments else parent.importance,
        tags=tags,
        recurrence_rule=None,
    )
    if created is None:
        raise RuntimeError("subtask creation failed")
    refreshed = task_service.get_task(created.id)
    if refreshed is None:
        raise RuntimeError("subtask creation verification failed")
    _record_audit_event(
        operation="subtasks.create",
        summary=f"Created subtask #{refreshed.id}",
        details={"parent_task_id": parent_task_id, "subtask": _task_payload(refreshed)},
        undo_actions=[{"type": "delete_task", "task_id": refreshed.id}],
    )
    return {"created": True, "parent_task_id": parent_task_id, "subtask": _task_payload(refreshed)}

def _tool_subtasks_list(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    parent_task_id = int(arguments["parent_task_id"])
    include_done = bool(arguments.get("include_done", False))
    marker = f"subtask_of:{parent_task_id}"
    subtasks = []
    for task in task_service.get_all_tasks(include_done=True):
        if not include_done and (task.status or "").lower() in {"done", "canceled"}:
            continue
        if marker in {tag.lower() for tag in _task_tags(task)}:
            subtasks.append(task)
    payload = _list_payload(subtasks)
    payload["parent_task_id"] = parent_task_id
    return payload

def _tool_subtasks_promote(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    task_id = int(arguments["task_id"])
    task = task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("task not found")
    before_payload = _task_payload(task)
    tags = [tag for tag in _task_tags(task) if not tag.lower().startswith("subtask_of:")]
    updates: dict[str, Any] = {"tags": tags}
    if "project_id" in arguments:
        project_id_raw = arguments.get("project_id")
        updates["project_id"] = int(project_id_raw) if project_id_raw is not None else None
    updated = task_service.update_task(task_id, **updates)
    if updated is None:
        raise RuntimeError("subtask promote failed")
    refreshed = task_service.get_task(task_id)
    if refreshed is None:
        raise RuntimeError("subtask promote verification failed")
    verified = not any(tag.lower().startswith("subtask_of:") for tag in _task_tags(refreshed))
    _record_audit_event(
        operation="subtasks.promote",
        summary=f"Promoted subtask #{task_id}",
        details={"before": before_payload, "after": _task_payload(refreshed)},
        undo_actions=[{"type": "restore_task_snapshot", "snapshot": before_payload}],
    )
    return {"updated": True, "verified": verified, "task": _task_payload(refreshed)}

def _tool_audit_list_events(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    limit = int(arguments.get("limit", 50))
    if limit < 0:
        limit = 0
    operation = str(arguments.get("operation") or "").strip().lower()
    events = _list_audit_events(limit=limit, operation=operation or None)
    return {"count": len(events), "events": events}

def _tool_audit_get_event(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    event_id = str(arguments["event_id"])
    event = _get_audit_event(event_id)
    return {"event": event}

def _tool_audit_explain_last_mutation(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "").strip().lower()
    events = _list_audit_events(limit=1, operation=operation or None)
    event = events[0] if events else None
    if event is None:
        return {"has_event": False, "event": None, "explanation": "No matching mutation events found."}
    undo_count = len(list(event.get("undo_actions") or []))
    explanation = f"{event.get('summary')} (operation={event.get('operation')}, undo_actions={undo_count})"
    return {"has_event": True, "event": event, "explanation": explanation}

def _tool_undo_preview(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    event_id = arguments.get("event_id")
    event = None
    if event_id is not None:
        event = _get_audit_event(str(event_id))
    else:
        for candidate in _list_audit_events(limit=200):
            if list(candidate.get("undo_actions") or []):
                event = candidate
                break
    if event is None:
        return {
            "undo_id": None,
            "event_id": str(event_id) if event_id is not None else None,
            "can_undo": False,
            "requires_approval": True,
            "undo_action_count": 0,
            "summary": "No undoable mutation found.",
        }
    undo_actions = list(event.get("undo_actions") or [])
    if not undo_actions:
        return {
            "undo_id": None,
            "event_id": event.get("event_id"),
            "can_undo": False,
            "requires_approval": True,
            "undo_action_count": 0,
            "summary": "Event has no undo actions.",
        }
    undo_id = _store_undo_preview(str(event.get("event_id")), undo_actions)
    return {
        "undo_id": undo_id,
        "event_id": event.get("event_id"),
        "can_undo": True,
        "requires_approval": True,
        "undo_action_count": len(undo_actions),
        "summary": str(event.get("summary") or ""),
    }

def _tool_undo_commit(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    undo_id = str(arguments["undo_id"])
    approved = bool(arguments.get("approved", False))
    preview = _get_undo_preview(undo_id)
    if preview is None:
        raise ValueError("Unknown undo_id")
    if not approved:
        raise RuntimeError("Approval required before undo commit")
    undo_actions = list(preview.get("undo_actions") or [])
    applied_actions: list[dict[str, Any]] = []
    failed_actions: list[dict[str, Any]] = []
    for action in reversed(undo_actions):
        if _apply_undo_action(action):
            applied_actions.append(action)
        else:
            failed_actions.append(action)
    result = {
        "operation": "undo",
        "undo_id": undo_id,
        "event_id": preview.get("event_id"),
        "committed": True,
        "applied_count": len(applied_actions),
        "failed_count": len(failed_actions),
        "applied_actions": applied_actions,
        "failed_actions": failed_actions,
    }
    _record_audit_event(
        operation="undo.commit",
        summary=f"Undo applied {len(applied_actions)} action(s)",
        details={
            "undo_id": undo_id,
            "event_id": preview.get("event_id"),
            "applied_count": len(applied_actions),
            "failed_count": len(failed_actions),
        },
        undo_actions=[],
    )
    return result

def _tool_interop_export_seed(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    from ..seed import export_seed_data
    include_tasks = bool(arguments.get("include_tasks", True))
    include_done_tasks = bool(arguments.get("include_done_tasks", False))
    seed = export_seed_data(include_tasks=include_tasks, include_done_tasks=include_done_tasks)
    return {
        "seed": seed,
        "counts": {
            "goals": len(list(seed.get("goals") or [])),
            "projects": len(list(seed.get("projects") or [])),
            "tasks": len(list(seed.get("tasks") or [])),
            "calendar_urls": len(list(seed.get("calendar_urls") or [])),
        },
    }

def _tool_interop_import_seed(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    from ..seed import load_seed_data, validate_seed_data
    seed = arguments.get("seed")
    if not isinstance(seed, dict):
        raise ValueError("seed object is required")
    dry_run = bool(arguments.get("dry_run", False))
    validation_errors = validate_seed_data(seed)
    if validation_errors:
        return {
            "imported": False,
            "dry_run": dry_run,
            "validation_errors": validation_errors,
            "stats": None,
        }
    if dry_run:
        return {
            "imported": False,
            "dry_run": True,
            "validation_errors": [],
            "stats": {
                "goals": len(list(seed.get("goals") or [])),
                "projects": len(list(seed.get("projects") or [])),
                "tasks": len(list(seed.get("tasks") or [])),
                "calendar_urls": len(list(seed.get("calendar_urls") or [])),
            },
        }
    stats = load_seed_data(seed)
    result_stats = {
        "goals_created": stats.goals_created,
        "goals_skipped": stats.goals_skipped,
        "goals_overwritten": stats.goals_overwritten,
        "projects_created": stats.projects_created,
        "projects_skipped": stats.projects_skipped,
        "projects_overwritten": stats.projects_overwritten,
        "tasks_created": stats.tasks_created,
        "tasks_skipped": stats.tasks_skipped,
        "tasks_overwritten": stats.tasks_overwritten,
        "calendars_added": stats.calendars_added,
        "calendars_skipped": stats.calendars_skipped,
        "errors": list(stats.errors or []),
        "summary": stats.summary(),
    }
    _record_audit_event(
        operation="interop.import_seed",
        summary="Imported seed data",
        details=result_stats,
        undo_actions=[],
    )
    return {
        "imported": True,
        "dry_run": False,
        "validation_errors": [],
        "stats": result_stats,
    }


def _tool_projects_get(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project = project_service.get_project(int(arguments["project_id"]))
    return {"project": _project_payload(project) if project else None}


def _tool_projects_list(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    status = arguments.get("status")
    goal_id_raw = arguments.get("goal_id")
    projects = project_service.get_all_projects(
        status=str(status).strip() if isinstance(status, str) and status.strip() else None,
        goal_id=int(goal_id_raw) if goal_id_raw is not None else None,
    )
    return _project_list_payload(projects)


def _tool_projects_create(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    goal_id_raw = arguments.get("goal_id")
    status = str(arguments.get("status") or "in_progress").strip() or "in_progress"
    summary = arguments.get("summary")
    start_date = _parse_date(str(arguments.get("start_date"))) if arguments.get("start_date") is not None else None
    end_date = _parse_date(str(arguments.get("end_date"))) if arguments.get("end_date") is not None else None
    created = project_service.create_project(
        name=name,
        goal_id=int(goal_id_raw) if goal_id_raw is not None else None,
        summary=str(summary).strip() if isinstance(summary, str) else None,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    refreshed = project_service.get_project(created.id if created else None) if created else None
    if refreshed is None:
        raise RuntimeError("project creation failed")
    _record_audit_event(
        operation="projects.create",
        summary=f"Created project #{refreshed.id}",
        details={"project": _project_payload(refreshed)},
        undo_actions=[{"type": "delete_project", "project_id": refreshed.id}],
    )
    return {"created": True, "project": _project_payload(refreshed)}


def _tool_projects_update(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project_id = int(arguments["project_id"])
    before = project_service.get_project(project_id)
    before_payload = _snapshot_project(before) if before else None
    updates: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        updates["name"] = name
    if "goal_id" in arguments:
        goal_id_raw = arguments.get("goal_id")
        updates["goal_id"] = int(goal_id_raw) if goal_id_raw is not None else None
    if "status" in arguments:
        status = str(arguments.get("status") or "").strip()
        if not status:
            raise ValueError("status cannot be empty")
        updates["status"] = status
    if "summary" in arguments:
        summary = arguments.get("summary")
        updates["summary"] = str(summary).strip() if isinstance(summary, str) else None
    if "start_date" in arguments:
        updates["start_date"] = _parse_date(str(arguments.get("start_date"))) if arguments.get("start_date") is not None else None
    if "end_date" in arguments:
        updates["end_date"] = _parse_date(str(arguments.get("end_date"))) if arguments.get("end_date") is not None else None
    if not updates:
        raise ValueError("at least one updatable field is required")
    updated = project_service.update_project(project_id, **updates)
    if updated is None:
        raise RuntimeError("project update failed")
    refreshed = project_service.get_project(project_id)
    if refreshed is None:
        raise RuntimeError("project update verification failed")
    _record_audit_event(
        operation="projects.update",
        summary=f"Updated project #{project_id}",
        details={"before": before_payload, "after": _project_payload(refreshed)},
        undo_actions=[{"type": "restore_project_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "project": _project_payload(refreshed)}


def _tool_projects_archive(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project_id = int(arguments["project_id"])
    before = project_service.get_project(project_id)
    before_payload = _snapshot_project(before) if before else None
    updated = project_service.update_project(project_id, status="done")
    if updated is None:
        raise RuntimeError("project archive failed")
    refreshed = project_service.get_project(project_id)
    if refreshed is None:
        raise RuntimeError("project archive verification failed")
    _record_audit_event(
        operation="projects.archive",
        summary=f"Archived project #{project_id}",
        details={"before": before_payload, "after": _project_payload(refreshed)},
        undo_actions=[{"type": "restore_project_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "project": _project_payload(refreshed)}


def _tool_projects_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project_id = int(arguments["project_id"])
    before = project_service.get_project(project_id)
    before_payload = _snapshot_project(before) if before else None
    deleted = bool(project_service.delete_project(project_id))
    verified = project_service.get_project(project_id) is None
    if deleted and before_payload:
        _record_audit_event(
            operation="projects.delete",
            summary=f"Deleted project #{project_id}",
            details={"project_id": project_id, "verified": verified},
            undo_actions=[{"type": "restore_project_snapshot", "snapshot": before_payload}],
        )
    return {"deleted": deleted, "verified": verified, "project_id": project_id}


def _tool_projects_list_tasks(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    project_id = int(arguments["project_id"])
    include_done = bool(arguments.get("include_done", False))
    tasks = task_service.get_project_tasks(project_id)
    if not include_done:
        tasks = [task for task in tasks if (task.status or "").lower() not in {"done", "canceled"}]
    return _list_payload(tasks)


def _tool_goals_get(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal = goal_service.get_goal(int(arguments["goal_id"]))
    return {"goal": _goal_payload(goal) if goal else None}


def _tool_goals_list(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    include_archived = bool(arguments.get("include_archived", False))
    goals = goal_service.get_all_goals(include_archived=include_archived)
    return _goal_list_payload(goals)


def _tool_goals_create(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    goal_type = str(arguments.get("goal_type") or "bigger_goal").strip() or "bigger_goal"
    description = arguments.get("description")
    created = goal_service.create_goal(
        name=name,
        goal_type=goal_type,
        description=str(description).strip() if isinstance(description, str) else None,
    )
    refreshed = goal_service.get_goal(created.id if created else None) if created else None
    if refreshed is None:
        raise RuntimeError("goal creation failed")
    _record_audit_event(
        operation="goals.create",
        summary=f"Created goal #{refreshed.id}",
        details={"goal": _goal_payload(refreshed)},
        undo_actions=[{"type": "delete_goal", "goal_id": refreshed.id}],
    )
    return {"created": True, "goal": _goal_payload(refreshed)}


def _tool_goals_update(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal_id = int(arguments["goal_id"])
    before = goal_service.get_goal(goal_id)
    before_payload = _snapshot_goal(before) if before else None
    updates: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        updates["name"] = name
    if "goal_type" in arguments:
        goal_type = str(arguments.get("goal_type") or "").strip()
        if not goal_type:
            raise ValueError("goal_type cannot be empty")
        updates["goal_type"] = goal_type
    if "description" in arguments:
        description = arguments.get("description")
        updates["description"] = str(description).strip() if isinstance(description, str) else None
    if "archived" in arguments:
        updates["archived"] = bool(arguments.get("archived"))
    if not updates:
        raise ValueError("at least one updatable field is required")
    updated = goal_service.update_goal(goal_id, **updates)
    if updated is None:
        raise RuntimeError("goal update failed")
    refreshed = goal_service.get_goal(goal_id)
    if refreshed is None:
        raise RuntimeError("goal update verification failed")
    _record_audit_event(
        operation="goals.update",
        summary=f"Updated goal #{goal_id}",
        details={"before": before_payload, "after": _goal_payload(refreshed)},
        undo_actions=[{"type": "restore_goal_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "goal": _goal_payload(refreshed)}


def _tool_goals_archive(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal_id = int(arguments["goal_id"])
    before = goal_service.get_goal(goal_id)
    before_payload = _snapshot_goal(before) if before else None
    updated = goal_service.archive_goal(goal_id)
    if updated is None:
        raise RuntimeError("goal archive failed")
    refreshed = goal_service.get_goal(goal_id)
    if refreshed is None:
        raise RuntimeError("goal archive verification failed")
    _record_audit_event(
        operation="goals.archive",
        summary=f"Archived goal #{goal_id}",
        details={"before": before_payload, "after": _goal_payload(refreshed)},
        undo_actions=[{"type": "restore_goal_snapshot", "snapshot": before_payload}] if before_payload else [],
    )
    return {"updated": True, "goal": _goal_payload(refreshed)}


def _tool_goals_delete(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal_id = int(arguments["goal_id"])
    before = goal_service.get_goal(goal_id)
    before_payload = _snapshot_goal(before) if before else None
    deleted = bool(goal_service.delete_goal(goal_id))
    verified = goal_service.get_goal(goal_id) is None
    if deleted and before_payload:
        _record_audit_event(
            operation="goals.delete",
            summary=f"Deleted goal #{goal_id}",
            details={"goal_id": goal_id, "verified": verified},
            undo_actions=[{"type": "restore_goal_snapshot", "snapshot": before_payload}],
        )
    return {"deleted": deleted, "verified": verified, "goal_id": goal_id}


def _tool_goals_list_projects(arguments: dict[str, Any], _: MCPRequestContext) -> dict[str, Any]:
    goal_id = int(arguments["goal_id"])
    projects = project_service.get_all_projects(goal_id=goal_id)
    return _project_list_payload(projects)

def _tool_ops_ping(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return {"status": "ok", "timestamp": date.today().isoformat()}


def _tool_ops_health(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    checks: dict[str, str] = {"database": "unknown"}
    task_count = 0
    with get_db() as conn:
        conn.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
        row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
        task_count = int(row["count"]) if row else 0

    return {
        "status": "ok",
        "checks": checks,
        "task_count": task_count,
    }


def _tool_ops_version(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return {
        "app_version": __version__,
        "mcp_phase": "phase4_local_writes",
        "mcp_server_version": MCP_SERVER_VERSION,
        "mcp_schema_version": MCP_SCHEMA_VERSION,
        "tool_contract_version": MCP_TOOL_CONTRACT_VERSION,
    }


def _tool_ops_get_capabilities(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return {"capabilities": DEFAULT_MCP_CAPABILITIES}


def _tool_ops_get_schema_versions(_: dict[str, Any], __: MCPRequestContext) -> dict[str, Any]:
    return {
        "mcp_schema_version": MCP_SCHEMA_VERSION,
        "tool_contract_version": MCP_TOOL_CONTRACT_VERSION,
    }


_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
_TASK_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["count", "task_ids", "tasks"],
    "properties": {
        "count": {"type": "integer"},
        "task_ids": {"type": "array"},
        "tasks": {"type": "array"},
    },
}
_PROJECT_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["project"],
    "properties": {"project": {"type": ["object", "null"]}},
}
_PROJECT_LIST_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["count", "project_ids", "projects"],
    "properties": {
        "count": {"type": "integer"},
        "project_ids": {"type": "array"},
        "projects": {"type": "array"},
    },
}
_GOAL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["goal"],
    "properties": {"goal": {"type": ["object", "null"]}},
}
_GOAL_LIST_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["count", "goal_ids", "goals"],
    "properties": {
        "count": {"type": "integer"},
        "goal_ids": {"type": "array"},
        "goals": {"type": "array"},
    },
}


def register_read_only_tools(registry: MCPToolRegistry) -> None:
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.get",
                description="Get one task by ID.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["task"],
                    "properties": {"task": {"type": ["object", "null"]}},
                },
                read_only=True,
                tags=["tasks", "read"],
            ),
            handler=_tool_tasks_get,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list",
                description="List tasks with optional include_done and limit filters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_done": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read"],
            ),
            handler=_tool_tasks_list,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_today",
                description="List active tasks due today.",
                input_schema=_EMPTY_SCHEMA,
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "today"],
            ),
            handler=_tool_tasks_list_today,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_overdue",
                description="List active tasks with due date before today.",
                input_schema=_EMPTY_SCHEMA,
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "overdue"],
            ),
            handler=_tool_tasks_list_overdue,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_inbox",
                description="List active tasks with no due date.",
                input_schema=_EMPTY_SCHEMA,
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "inbox"],
            ),
            handler=_tool_tasks_list_inbox,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_upcoming",
                description="List tasks due between today and N days ahead.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "upcoming"],
            ),
            handler=_tool_tasks_list_upcoming,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_completed",
                description="List completed tasks.",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "completed"],
            ),
            handler=_tool_tasks_list_completed,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_recurring",
                description="List tasks that have recurrence rules.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "recurring"],
            ),
            handler=_tool_tasks_list_recurring,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_ids",
                description="List tasks by explicit IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "ids"],
            ),
            handler=_tool_tasks_list_by_ids,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.search",
                description="Search tasks by case-insensitive name substring.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "search"],
            ),
            handler=_tool_tasks_search,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_project",
                description="List tasks in one project.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "project"],
            ),
            handler=_tool_tasks_list_by_project,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_goal",
                description="List tasks by goal through linked projects.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {
                        "goal_id": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "goal"],
            ),
            handler=_tool_tasks_list_by_goal,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_status",
                description="List tasks matching one exact status.",
                input_schema={
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "status"],
            ),
            handler=_tool_tasks_list_by_status,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_priority",
                description="List tasks by minimum importance threshold.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "min_importance": {"type": "number"},
                        "limit": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "priority"],
            ),
            handler=_tool_tasks_list_by_priority,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_date_range",
                description="List tasks with due dates between start_date and end_date inclusive.",
                input_schema={
                    "type": "object",
                    "required": ["start_date", "end_date"],
                    "properties": {
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "date_range"],
            ),
            handler=_tool_tasks_list_by_date_range,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_by_tag",
                description="List tasks containing one tag.",
                input_schema={
                    "type": "object",
                    "required": ["tag"],
                    "properties": {
                        "tag": {"type": "string"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "tag"],
            ),
            handler=_tool_tasks_list_by_tag,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_blocked",
                description="List tasks tagged blocked.",
                input_schema={
                    "type": "object",
                    "properties": {"include_done": {"type": "boolean"}},
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "blocked"],
            ),
            handler=_tool_tasks_list_blocked,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.list_stale",
                description="List old undated tasks by age threshold in days.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["tasks", "read", "stale"],
            ),
            handler=_tool_tasks_list_stale,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.create",
                description="Create a task with optional scheduling and metadata fields.",
                input_schema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "project_id": {"type": ["integer", "null"]},
                        "due_date": {"type": ["string", "null"]},
                        "due_time": {"type": ["string", "null"]},
                        "importance": {"type": ["number", "null"]},
                        "tags": {"type": ["array", "null"]},
                        "recurrence_rule": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["created", "task"],
                    "properties": {
                        "created": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "create", "write"],
            ),
            handler=_tool_tasks_create,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.complete",
                description="Mark one task as completed and return verified state.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["completed", "verified", "task"],
                    "properties": {
                        "completed": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "complete", "write"],
            ),
            handler=_tool_tasks_complete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.skip",
                description="Skip/defer one task and return updated state.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["skipped", "task"],
                    "properties": {
                        "skipped": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "skip", "write"],
            ),
            handler=_tool_tasks_skip,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.update_fields",
                description="Update selected task fields and return verified updated state.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "project_id": {"type": ["integer", "null"]},
                        "status": {"type": "string"},
                        "due_date": {"type": ["string", "null"]},
                        "due_time": {"type": ["string", "null"]},
                        "importance": {"type": ["number", "null"]},
                        "tags": {"type": ["array", "null"]},
                        "recurrence_rule": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "update", "write"],
            ),
            handler=_tool_tasks_update_fields,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.rename",
                description="Rename one task.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "name"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "rename", "write"],
            ),
            handler=_tool_tasks_rename,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.set_due",
                description="Set task due date/time.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "due_date"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "due_date": {"type": "string"},
                        "due_time": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "due", "write"],
            ),
            handler=_tool_tasks_set_due,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.clear_due",
                description="Clear task due date/time.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {"task_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "due", "write"],
            ),
            handler=_tool_tasks_clear_due,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.set_priority",
                description="Set task importance/priority.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "importance"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "importance": {"type": "number"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "priority", "write"],
            ),
            handler=_tool_tasks_set_priority,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.set_tags",
                description="Replace task tags with an explicit list.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "tags"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "tags": {"type": "array"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "tags", "write"],
            ),
            handler=_tool_tasks_set_tags,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.add_tags",
                description="Add one or more tags to a task.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "tags"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "tags": {"type": "array"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "tags", "write"],
            ),
            handler=_tool_tasks_add_tags,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.remove_tags",
                description="Remove one or more tags from a task.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "tags"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "tags": {"type": "array"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "tags", "write"],
            ),
            handler=_tool_tasks_remove_tags,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.assign_project",
                description="Assign task to a project (or clear project).",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "project_id": {"type": ["integer", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "project", "write"],
            ),
            handler=_tool_tasks_assign_project,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.mark_in_progress",
                description="Set task status to in_progress.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {"task_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "status", "write"],
            ),
            handler=_tool_tasks_mark_in_progress,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.reopen",
                description="Reopen task by setting status to not_started.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {"task_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "verified", "task"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "task": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["tasks", "status", "write"],
            ),
            handler=_tool_tasks_reopen,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.resolve_candidates",
                description="Resolve a task target query into ranked candidates and selected task if unambiguous.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "include_done": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "query",
                        "resolution",
                        "ambiguous",
                        "ambiguity_reason",
                        "confidence",
                        "selected_task_id",
                        "selected_task",
                        "candidates",
                    ],
                    "properties": {
                        "query": {"type": "string"},
                        "resolution": {"type": "string"},
                        "ambiguous": {"type": "boolean"},
                        "ambiguity_reason": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "selected_task_id": {"type": ["integer", "null"]},
                        "selected_task": {"type": ["object", "null"]},
                        "candidates": {"type": "array"},
                    },
                },
                read_only=True,
                tags=["tasks", "resolve", "read"],
            ),
            handler=_tool_tasks_resolve_candidates,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.resolve_scope",
                description="Resolve bulk-edit scope selectors to deterministic task IDs and ambiguity metadata.",
                input_schema={
                    "type": "object",
                    "required": ["scope_type"],
                    "properties": {
                        "scope_type": {
                            "type": "string",
                            "enum": ["project", "all", "task_names", "due_date", "overdue", "unknown"],
                        },
                        "source_project_name": {"type": "string"},
                        "source_due_date": {"type": "string"},
                        "task_names": {"type": "array"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "scope_type",
                        "scope_ref",
                        "matched_count",
                        "matched_task_ids",
                        "matched_tasks",
                        "unresolved_names",
                        "ambiguous",
                        "ambiguity_reason",
                        "ambiguity_details",
                        "candidates_by_name",
                    ],
                    "properties": {
                        "scope_type": {"type": "string"},
                        "scope_ref": {"type": "string"},
                        "matched_count": {"type": "integer"},
                        "matched_task_ids": {"type": "array"},
                        "matched_tasks": {"type": "array"},
                        "unresolved_names": {"type": "array"},
                        "ambiguous": {"type": "boolean"},
                        "ambiguity_reason": {"type": ["string", "null"]},
                        "ambiguity_details": {"type": "array"},
                        "candidates_by_name": {"type": "object"},
                    },
                },
                read_only=True,
                tags=["tasks", "resolve", "read", "bulk"],
            ),
            handler=_tool_tasks_resolve_scope,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_delete",
                description="Create a destructive delete preview for a specific task ID.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "preview_id",
                        "operation",
                        "requires_approval",
                        "approval_reason",
                        "policy_gates",
                        "affected_task_ids",
                        "affected_count",
                        "before_tasks",
                    ],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "operation": {"type": "string"},
                        "requires_approval": {"type": "boolean"},
                        "approval_reason": {"type": ["string", "null"]},
                        "policy_gates": {"type": "object"},
                        "affected_task_ids": {"type": "array"},
                        "affected_count": {"type": "integer"},
                        "before_tasks": {"type": "array"},
                    },
                },
                read_only=True,
                tags=["tasks", "preview", "delete"],
            ),
            handler=_tool_tasks_preview_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_delete",
                description="Commit a previously previewed delete operation with optional idempotency key.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "operation",
                        "preview_id",
                        "committed",
                        "idempotent_replay",
                        "idempotency_key",
                        "affected_task_ids",
                        "affected_count",
                        "verified_affected_task_ids",
                        "verified_affected_count",
                    ],
                    "properties": {
                        "operation": {"type": "string"},
                        "preview_id": {"type": "string"},
                        "committed": {"type": "boolean"},
                        "idempotent_replay": {"type": "boolean"},
                        "idempotency_key": {"type": ["string", "null"]},
                        "affected_task_ids": {"type": "array"},
                        "affected_count": {"type": "integer"},
                        "verified_affected_task_ids": {"type": "array"},
                        "verified_affected_count": {"type": "integer"},
                    },
                },
                read_only=False,
                tags=["tasks", "commit", "delete", "write"],
            ),
            handler=_tool_tasks_commit_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_update",
                description="Create a bulk update preview for explicit task IDs and update spec.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids", "updates"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "updates": {"type": "object"},
                        "scope_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "preview_id",
                        "operation",
                        "scope_ref",
                        "requires_approval",
                        "approval_reason",
                        "policy_gates",
                        "updates",
                        "affected_task_ids",
                        "affected_count",
                        "before_tasks",
                    ],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "operation": {"type": "string"},
                        "scope_ref": {"type": "string"},
                        "requires_approval": {"type": "boolean"},
                        "approval_reason": {"type": ["string", "null"]},
                        "policy_gates": {"type": "object"},
                        "updates": {"type": "object"},
                        "affected_task_ids": {"type": "array"},
                        "affected_count": {"type": "integer"},
                        "before_tasks": {"type": "array"},
                    },
                },
                read_only=True,
                tags=["tasks", "preview", "bulk", "update"],
            ),
            handler=_tool_tasks_preview_bulk_update,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_update",
                description="Commit a previously previewed bulk update operation with optional idempotency key.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "operation",
                        "preview_id",
                        "committed",
                        "scope_ref",
                        "idempotent_replay",
                        "idempotency_key",
                        "updates",
                        "affected_task_ids",
                        "affected_count",
                        "verified_affected_task_ids",
                        "verified_affected_count",
                    ],
                    "properties": {
                        "operation": {"type": "string"},
                        "preview_id": {"type": "string"},
                        "committed": {"type": "boolean"},
                        "scope_ref": {"type": "string"},
                        "idempotent_replay": {"type": "boolean"},
                        "idempotency_key": {"type": ["string", "null"]},
                        "updates": {"type": "object"},
                        "affected_task_ids": {"type": "array"},
                        "affected_count": {"type": "integer"},
                        "verified_affected_task_ids": {"type": "array"},
                        "verified_affected_count": {"type": "integer"},
                    },
                },
                read_only=False,
                tags=["tasks", "commit", "bulk", "update", "write"],
            ),
            handler=_tool_tasks_commit_bulk_update,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_complete",
                description="Create a bulk completion preview for explicit task IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "scope_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["preview_id", "operation", "scope_ref", "requires_approval", "approval_reason", "policy_gates", "affected_task_ids", "affected_count", "before_tasks"]},
                read_only=True,
                tags=["tasks", "preview", "bulk", "complete"],
            ),
            handler=_tool_tasks_preview_bulk_complete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_complete",
                description="Commit a previously previewed bulk completion operation.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "preview_id", "committed", "scope_ref", "idempotent_replay", "idempotency_key", "affected_task_ids", "affected_count", "verified_affected_task_ids", "verified_affected_count"]},
                read_only=False,
                tags=["tasks", "commit", "bulk", "complete", "write"],
            ),
            handler=_tool_tasks_commit_bulk_complete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_skip",
                description="Create a bulk skip/defer preview for explicit task IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "scope_ref": {"type": "string"},
                        "target_due_date": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["preview_id", "operation", "scope_ref", "target_due_date", "requires_approval", "approval_reason", "policy_gates", "affected_task_ids", "affected_count", "before_tasks"]},
                read_only=True,
                tags=["tasks", "preview", "bulk", "skip"],
            ),
            handler=_tool_tasks_preview_bulk_skip,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_skip",
                description="Commit a previously previewed bulk skip/defer operation.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "preview_id", "committed", "scope_ref", "target_due_date", "idempotent_replay", "idempotency_key", "affected_task_ids", "affected_count", "verified_affected_task_ids", "verified_affected_count"]},
                read_only=False,
                tags=["tasks", "commit", "bulk", "skip", "write"],
            ),
            handler=_tool_tasks_commit_bulk_skip,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_delete",
                description="Create a destructive bulk delete preview for explicit task IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "scope_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["preview_id", "operation", "scope_ref", "requires_approval", "approval_reason", "policy_gates", "affected_task_ids", "affected_count", "before_tasks"]},
                read_only=True,
                tags=["tasks", "preview", "bulk", "delete"],
            ),
            handler=_tool_tasks_preview_bulk_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_delete",
                description="Commit a previously previewed bulk delete operation.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "preview_id", "committed", "scope_ref", "idempotent_replay", "idempotency_key", "affected_task_ids", "affected_count", "verified_affected_task_ids", "verified_affected_count"]},
                read_only=False,
                tags=["tasks", "commit", "bulk", "delete", "write"],
            ),
            handler=_tool_tasks_commit_bulk_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_move_project",
                description="Create a bulk move-to-project preview for explicit task IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "project_id": {"type": ["integer", "null"]},
                        "scope_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["preview_id", "operation", "scope_ref", "project_id", "requires_approval", "approval_reason", "policy_gates", "affected_task_ids", "affected_count", "before_tasks"]},
                read_only=True,
                tags=["tasks", "preview", "bulk", "project"],
            ),
            handler=_tool_tasks_preview_bulk_move_project,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_move_project",
                description="Commit a previously previewed bulk move-to-project operation.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "preview_id", "committed", "scope_ref", "project_id", "idempotent_replay", "idempotency_key", "affected_task_ids", "affected_count", "verified_affected_task_ids", "verified_affected_count"]},
                read_only=False,
                tags=["tasks", "commit", "bulk", "project", "write"],
            ),
            handler=_tool_tasks_commit_bulk_move_project,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.preview_bulk_retag",
                description="Create a bulk retag preview for explicit task IDs.",
                input_schema={
                    "type": "object",
                    "required": ["task_ids"],
                    "properties": {
                        "task_ids": {"type": "array"},
                        "set_tags": {"type": "array"},
                        "add_tags": {"type": "array"},
                        "remove_tags": {"type": "array"},
                        "scope_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["preview_id", "operation", "scope_ref", "tag_updates", "requires_approval", "approval_reason", "policy_gates", "affected_task_ids", "affected_count", "before_tasks"]},
                read_only=True,
                tags=["tasks", "preview", "bulk", "retag"],
            ),
            handler=_tool_tasks_preview_bulk_retag,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="tasks.commit_bulk_retag",
                description="Commit a previously previewed bulk retag operation.",
                input_schema={
                    "type": "object",
                    "required": ["preview_id"],
                    "properties": {
                        "preview_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                        "idempotency_key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "preview_id", "committed", "scope_ref", "tag_updates", "idempotent_replay", "idempotency_key", "affected_task_ids", "affected_count", "verified_affected_task_ids", "verified_affected_count"]},
                read_only=False,
                tags=["tasks", "commit", "bulk", "retag", "write"],
            ),
            handler=_tool_tasks_commit_bulk_retag,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="dependencies.add",
                description="Add a task dependency edge using metadata tags.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "depends_on_task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "depends_on_task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["updated", "verified", "task", "depends_on_task_id"]},
                read_only=False,
                tags=["dependencies", "write"],
            ),
            handler=_tool_dependencies_add,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="dependencies.remove",
                description="Remove a task dependency edge from metadata tags.",
                input_schema={
                    "type": "object",
                    "required": ["task_id", "depends_on_task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "depends_on_task_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["updated", "verified", "task", "depends_on_task_id"]},
                read_only=False,
                tags=["dependencies", "write"],
            ),
            handler=_tool_dependencies_remove,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="dependencies.list",
                description="List dependency edges for a task.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {"task_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["task_id", "dependency_ids", "dependencies", "blocked_by_task_ids", "blocked_by_count"]},
                read_only=True,
                tags=["dependencies", "read"],
            ),
            handler=_tool_dependencies_list,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="subtasks.create",
                description="Create a subtask linked to a parent task.",
                input_schema={
                    "type": "object",
                    "required": ["parent_task_id", "name"],
                    "properties": {
                        "parent_task_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "project_id": {"type": ["integer", "null"]},
                        "due_date": {"type": ["string", "null"]},
                        "due_time": {"type": ["string", "null"]},
                        "importance": {"type": "number"},
                        "tags": {"type": "array"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["created", "parent_task_id", "subtask"]},
                read_only=False,
                tags=["subtasks", "write"],
            ),
            handler=_tool_subtasks_create,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="subtasks.list",
                description="List subtasks for a parent task.",
                input_schema={
                    "type": "object",
                    "required": ["parent_task_id"],
                    "properties": {
                        "parent_task_id": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["parent_task_id", "count", "task_ids", "tasks"]},
                read_only=True,
                tags=["subtasks", "read"],
            ),
            handler=_tool_subtasks_list,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="subtasks.promote",
                description="Promote a subtask into a regular task.",
                input_schema={
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "integer"},
                        "project_id": {"type": ["integer", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["updated", "verified", "task"]},
                read_only=False,
                tags=["subtasks", "write"],
            ),
            handler=_tool_subtasks_promote,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.get",
                description="Get one project by ID.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {"project_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema=_PROJECT_OUTPUT_SCHEMA,
                read_only=True,
                tags=["projects", "read"],
            ),
            handler=_tool_projects_get,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.list",
                description="List projects with optional status/goal filters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "goal_id": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_PROJECT_LIST_OUTPUT_SCHEMA,
                read_only=True,
                tags=["projects", "read"],
            ),
            handler=_tool_projects_list,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.create",
                description="Create a project.",
                input_schema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "goal_id": {"type": "integer"},
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["created", "project"],
                    "properties": {
                        "created": {"type": "boolean"},
                        "project": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["projects", "write", "create"],
            ),
            handler=_tool_projects_create,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.update",
                description="Update project fields.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "goal_id": {"type": "integer"},
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                        "start_date": {"type": ["string", "null"]},
                        "end_date": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "project"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "project": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["projects", "write", "update"],
            ),
            handler=_tool_projects_update,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.archive",
                description="Archive/complete one project.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {"project_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "project"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "project": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["projects", "write", "archive"],
            ),
            handler=_tool_projects_archive,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.delete",
                description="Delete one project by ID.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {"project_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["deleted", "verified", "project_id"],
                    "properties": {
                        "deleted": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "project_id": {"type": "integer"},
                    },
                },
                read_only=False,
                tags=["projects", "write", "delete"],
            ),
            handler=_tool_projects_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="projects.list_tasks",
                description="List tasks for one project.",
                input_schema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {"type": "integer"},
                        "include_done": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema=_TASK_OUTPUT_SCHEMA,
                read_only=True,
                tags=["projects", "read", "tasks"],
            ),
            handler=_tool_projects_list_tasks,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.get",
                description="Get one goal by ID.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {"goal_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema=_GOAL_OUTPUT_SCHEMA,
                read_only=True,
                tags=["goals", "read"],
            ),
            handler=_tool_goals_get,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.list",
                description="List goals.",
                input_schema={
                    "type": "object",
                    "properties": {"include_archived": {"type": "boolean"}},
                    "additionalProperties": False,
                },
                output_schema=_GOAL_LIST_OUTPUT_SCHEMA,
                read_only=True,
                tags=["goals", "read"],
            ),
            handler=_tool_goals_list,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.create",
                description="Create a goal.",
                input_schema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "goal_type": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["created", "goal"],
                    "properties": {
                        "created": {"type": "boolean"},
                        "goal": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["goals", "write", "create"],
            ),
            handler=_tool_goals_create,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.update",
                description="Update goal fields.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {
                        "goal_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "goal_type": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "archived": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "goal"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "goal": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["goals", "write", "update"],
            ),
            handler=_tool_goals_update,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.archive",
                description="Archive one goal.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {"goal_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["updated", "goal"],
                    "properties": {
                        "updated": {"type": "boolean"},
                        "goal": {"type": "object"},
                    },
                },
                read_only=False,
                tags=["goals", "write", "archive"],
            ),
            handler=_tool_goals_archive,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.delete",
                description="Delete one goal by ID.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {"goal_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["deleted", "verified", "goal_id"],
                    "properties": {
                        "deleted": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "goal_id": {"type": "integer"},
                    },
                },
                read_only=False,
                tags=["goals", "write", "delete"],
            ),
            handler=_tool_goals_delete,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="goals.list_projects",
                description="List projects for one goal.",
                input_schema={
                    "type": "object",
                    "required": ["goal_id"],
                    "properties": {"goal_id": {"type": "integer"}},
                    "additionalProperties": False,
                },
                output_schema=_PROJECT_LIST_OUTPUT_SCHEMA,
                read_only=True,
                tags=["goals", "read", "projects"],
            ),
            handler=_tool_goals_list_projects,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="audit.list_events",
                description="List recent audit events with optional operation filter.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "operation": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["count", "events"]},
                read_only=True,
                tags=["audit", "read"],
            ),
            handler=_tool_audit_list_events,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="audit.get_event",
                description="Get one audit event by event_id.",
                input_schema={
                    "type": "object",
                    "required": ["event_id"],
                    "properties": {"event_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["event"]},
                read_only=True,
                tags=["audit", "read"],
            ),
            handler=_tool_audit_get_event,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="audit.explain_last_mutation",
                description="Explain the last mutation event with optional operation filter.",
                input_schema={
                    "type": "object",
                    "properties": {"operation": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["has_event", "event", "explanation"]},
                read_only=True,
                tags=["audit", "read"],
            ),
            handler=_tool_audit_explain_last_mutation,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="undo.preview",
                description="Preview undo for a specific or most recent undoable audit event.",
                input_schema={
                    "type": "object",
                    "properties": {"event_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["undo_id", "event_id", "can_undo", "requires_approval", "undo_action_count", "summary"]},
                read_only=True,
                tags=["undo", "preview"],
            ),
            handler=_tool_undo_preview,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="undo.commit",
                description="Commit a previously previewed undo operation.",
                input_schema={
                    "type": "object",
                    "required": ["undo_id"],
                    "properties": {
                        "undo_id": {"type": "string"},
                        "approved": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["operation", "undo_id", "event_id", "committed", "applied_count", "failed_count", "applied_actions", "failed_actions"]},
                read_only=False,
                tags=["undo", "commit", "write"],
            ),
            handler=_tool_undo_commit,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="interop.export_seed",
                description="Export current Noctem data as seed payload.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_tasks": {"type": "boolean"},
                        "include_done_tasks": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["seed", "counts"]},
                read_only=True,
                tags=["interop", "export", "read"],
            ),
            handler=_tool_interop_export_seed,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="interop.import_seed",
                description="Import seed payload into Noctem with optional dry-run validation.",
                input_schema={
                    "type": "object",
                    "required": ["seed"],
                    "properties": {
                        "seed": {"type": "object"},
                        "dry_run": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object", "required": ["imported", "dry_run", "validation_errors", "stats"]},
                read_only=False,
                tags=["interop", "import", "write"],
            ),
            handler=_tool_interop_import_seed,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="ops.ping",
                description="Simple liveness check for MCP server.",
                input_schema=_EMPTY_SCHEMA,
                output_schema={"type": "object", "required": ["status", "timestamp"]},
                read_only=True,
                tags=["ops"],
            ),
            handler=_tool_ops_ping,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="ops.health",
                description="Health checks for MCP dependencies.",
                input_schema=_EMPTY_SCHEMA,
                output_schema={"type": "object", "required": ["status", "checks", "task_count"]},
                read_only=True,
                tags=["ops"],
            ),
            handler=_tool_ops_health,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="ops.version",
                description="Return application and MCP phase version metadata.",
                input_schema=_EMPTY_SCHEMA,
                output_schema={"type": "object", "required": ["app_version", "mcp_phase"]},
                read_only=True,
                tags=["ops"],
            ),
            handler=_tool_ops_version,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="ops.get_capabilities",
                description="Return MCP capability contract supported by this server.",
                input_schema=_EMPTY_SCHEMA,
                output_schema={"type": "object", "required": ["capabilities"]},
                read_only=True,
                tags=["ops", "capabilities"],
            ),
            handler=_tool_ops_get_capabilities,
        )
    )
    registry.register(
        MCPTool(
            definition=MCPToolDefinition(
                name="ops.get_schema_versions",
                description="Return active schema and tool contract versions.",
                input_schema=_EMPTY_SCHEMA,
                output_schema={"type": "object", "required": ["mcp_schema_version", "tool_contract_version"]},
                read_only=True,
                tags=["ops", "schema"],
            ),
            handler=_tool_ops_get_schema_versions,
        )
    )
