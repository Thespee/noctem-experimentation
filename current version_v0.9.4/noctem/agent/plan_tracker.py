"""Plan object tracker for multi-step task decomposition.

Plans are collections of ordered steps derived from a workflow.
Each step can be individually approved, executed, completed, or failed.
If any step fails, remaining steps are skipped.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from ..db import get_db


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


def create_plan_object(
    *,
    workflow_id: int,
    steps: list[str],
) -> dict[str, Any]:
    """Create a plan with ordered steps. Returns the plan summary dict."""
    plan_id = f"plan-{uuid.uuid4().hex[:12]}"
    with get_db() as conn:
        for idx, description in enumerate(steps):
            conn.execute(
                """
                INSERT INTO plan_steps (plan_id, workflow_id, step_index, description, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (plan_id, int(workflow_id), idx, str(description or "").strip()),
            )
    return get_plan_status(plan_id)


def get_plan_status(plan_id: str) -> dict[str, Any]:
    """Get full plan status including all steps."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, plan_id, workflow_id, step_index, description, status, result_json, created_at, updated_at
            FROM plan_steps
            WHERE plan_id = ?
            ORDER BY step_index ASC
            """,
            (str(plan_id),),
        ).fetchall()
    if not rows:
        return {"plan_id": plan_id, "steps": [], "status": "not_found"}

    steps = []
    for row in rows:
        steps.append({
            "id": int(row["id"]),
            "plan_id": row["plan_id"],
            "workflow_id": row["workflow_id"],
            "step_index": int(row["step_index"]),
            "description": row["description"],
            "status": row["status"],
            "result": _json_loads(row["result_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    statuses = [s["status"] for s in steps]
    if all(s == "completed" for s in statuses):
        overall = "completed"
    elif any(s == "failed" for s in statuses):
        overall = "failed"
    elif any(s == "executing" for s in statuses):
        overall = "executing"
    elif any(s == "approved" for s in statuses):
        overall = "approved"
    else:
        overall = "pending"

    return {
        "plan_id": plan_id,
        "workflow_id": steps[0]["workflow_id"] if steps else None,
        "status": overall,
        "total_steps": len(steps),
        "completed_steps": sum(1 for s in statuses if s == "completed"),
        "failed_steps": sum(1 for s in statuses if s == "failed"),
        "steps": steps,
    }


def approve_plan_step(step_id: int) -> dict[str, Any] | None:
    """Mark a plan step as approved (ready for execution)."""
    return _update_step_status(step_id, "approved")


def complete_plan_step(step_id: int, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Mark a plan step as completed with optional result."""
    return _update_step_status(step_id, "completed", result=result)


def fail_plan_step(step_id: int, error: str | None = None) -> dict[str, Any] | None:
    """Mark a plan step as failed and skip remaining steps in the plan."""
    updated = _update_step_status(step_id, "failed", result={"error": error} if error else None)
    if updated:
        _skip_remaining_steps(updated["plan_id"], after_index=updated["step_index"])
    return updated


def _update_step_status(
    step_id: int,
    status: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    with get_db() as conn:
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = [status]
        if result is not None:
            updates.append("result_json = ?")
            params.append(_json_dumps(result))
        params.append(int(step_id))
        conn.execute(
            f"UPDATE plan_steps SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        row = conn.execute(
            "SELECT * FROM plan_steps WHERE id = ?",
            (int(step_id),),
        ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "plan_id": row["plan_id"],
        "workflow_id": row["workflow_id"],
        "step_index": int(row["step_index"]),
        "description": row["description"],
        "status": row["status"],
        "result": _json_loads(row["result_json"]),
    }


def _skip_remaining_steps(plan_id: str, after_index: int) -> None:
    """Skip all pending steps after the given index."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE plan_steps
            SET status = 'skipped', updated_at = CURRENT_TIMESTAMP
            WHERE plan_id = ? AND step_index > ? AND status = 'pending'
            """,
            (str(plan_id), int(after_index)),
        )
