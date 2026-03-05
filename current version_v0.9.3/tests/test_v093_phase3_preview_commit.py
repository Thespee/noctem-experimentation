"""Tests for v0.9.3 Phase 3 preview/commit mutation flow."""
from datetime import date, timedelta
from uuid import uuid4

from noctem.mcp import get_mcp_server
from noctem.services import project_service, task_service


def _client():
    from noctem.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_mcp_delete_preview_commit_and_idempotency_replay():
    task = task_service.create_task(f"phase3-delete-{uuid4().hex[:10]}")
    server = get_mcp_server()

    preview = server.call_tool(
        "tasks.preview_delete",
        {"task_id": task.id},
        context={"source": "tests", "correlation_id": "phase3-delete-preview"},
    )
    assert preview["ok"] is True
    assert preview["result"]["requires_approval"] is True
    assert preview["result"]["affected_count"] == 1
    preview_id = preview["result"]["preview_id"]

    commit = server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview_id, "approved": True, "idempotency_key": "phase3-del-key-1"},
        context={"source": "tests", "correlation_id": "phase3-delete-commit"},
    )
    assert commit["ok"] is True
    assert commit["result"]["verified_affected_count"] == 1
    assert commit["result"]["idempotent_replay"] is False
    assert task_service.get_task(task.id) is None

    replay = server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview_id, "approved": True, "idempotency_key": "phase3-del-key-1"},
        context={"source": "tests", "correlation_id": "phase3-delete-replay"},
    )
    assert replay["ok"] is True
    assert replay["result"]["idempotent_replay"] is True
    assert replay["result"]["verified_affected_count"] == 1


def test_mcp_delete_commit_requires_approval_flag():
    task = task_service.create_task(f"phase3-delete-no-approval-{uuid4().hex[:10]}")
    server = get_mcp_server()
    preview = server.call_tool(
        "tasks.preview_delete",
        {"task_id": task.id},
        context={"source": "tests"},
    )
    assert preview["ok"] is True

    commit = server.call_tool(
        "tasks.commit_delete",
        {"preview_id": preview["result"]["preview_id"], "approved": False},
        context={"source": "tests"},
    )
    assert commit["ok"] is False
    assert commit["error"]["code"] == "tool_execution_error"
    assert "Approval required" in commit["error"]["message"]
    assert task_service.get_task(task.id) is not None


def test_mcp_preview_bulk_update_requires_approval_for_large_scope():
    tasks = [task_service.create_task(f"phase3-bulk-{idx}-{uuid4().hex[:6]}") for idx in range(4)]
    server = get_mcp_server()
    preview = server.call_tool(
        "tasks.preview_bulk_update",
        {
            "task_ids": [task.id for task in tasks],
            "updates": {"due_date": date.today().isoformat()},
            "scope_ref": "tests",
        },
        context={"source": "tests"},
    )
    assert preview["ok"] is True
    assert preview["result"]["affected_count"] == 4
    assert preview["result"]["requires_approval"] is True
    assert preview["result"]["approval_reason"] == "blast_radius"


def test_mcp_resolve_scope_overdue_matches_only_overdue_tasks():
    overdue = task_service.create_task(
        f"phase3-overdue-{uuid4().hex[:8]}",
        due_date=date.today() - timedelta(days=1),
    )
    today = task_service.create_task(f"phase3-today-{uuid4().hex[:8]}", due_date=date.today())

    server = get_mcp_server()
    result = server.call_tool(
        "tasks.resolve_scope",
        {"scope_type": "overdue"},
        context={"source": "tests"},
    )
    assert result["ok"] is True
    assert result["result"]["scope_type"] == "overdue"
    matched_ids = set(result["result"]["matched_task_ids"])
    assert overdue.id in matched_ids
    assert today.id not in matched_ids


def test_workflow_bulk_edit_large_scope_requires_approval_then_commits():
    project_name = f"phase3-project-{uuid4().hex[:8]}"
    project = project_service.create_project(project_name)
    tasks = [
        task_service.create_task(f"phase3-task-{idx}-{uuid4().hex[:6]}", project_id=project.id)
        for idx in range(4)
    ]

    client = _client()
    submit = client.post("/api/agent/submit", json={"input": f"move all tasks from {project_name} to today"})
    assert submit.status_code == 200
    first = submit.get_json()
    assert first["success"] is True
    assert first["status"] == "interrupted"
    assert first["interrupt"]["type"] == "approve"
    assert "approve this update" in first["response"].lower()

    resume = client.post(
        f"/api/agent/resume/{first['workflow_id']}",
        json={"response": "yes"},
    )
    assert resume.status_code == 200
    final = resume.get_json()
    assert final["success"] is True
    assert final["status"] == "completed"
    assert final["updated_count"] == 4

    for task in tasks:
        refreshed = task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.due_date == date.today()
