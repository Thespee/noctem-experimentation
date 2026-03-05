"""Tests for v0.9.3 Phase 4 MCP write-tool integration."""
from datetime import date, timedelta
from uuid import uuid4

from noctem.agent import workflow as workflow_module
from noctem.mcp import get_mcp_server
from noctem.services import task_service


def test_mcp_create_complete_skip_tools_end_to_end():
    server = get_mcp_server()
    marker = f"phase4-mcp-{uuid4().hex[:8]}"

    created = server.call_tool(
        "tasks.create",
        {"name": marker},
        context={"source": "tests", "correlation_id": "phase4-create-1"},
    )
    assert created["ok"] is True
    created_task = created["result"]["task"]
    task_id = int(created_task["id"])
    assert task_service.get_task(task_id) is not None

    updated = server.call_tool(
        "tasks.update_fields",
        {"task_id": task_id, "importance": 1.0},
        context={"source": "tests", "correlation_id": "phase4-update-1"},
    )
    assert updated["ok"] is True
    assert updated["result"]["verified"] is True
    assert updated["result"]["task"]["importance"] == 1.0

    completed = server.call_tool(
        "tasks.complete",
        {"task_id": task_id},
        context={"source": "tests", "correlation_id": "phase4-complete-1"},
    )
    assert completed["ok"] is True
    assert completed["result"]["verified"] is True
    assert completed["result"]["task"]["status"] == "done"

    created_skip = server.call_tool(
        "tasks.create",
        {"name": f"{marker}-skip"},
        context={"source": "tests", "correlation_id": "phase4-create-2"},
    )
    assert created_skip["ok"] is True
    skip_task_id = int(created_skip["result"]["task"]["id"])

    skipped = server.call_tool(
        "tasks.skip",
        {"task_id": skip_task_id},
        context={"source": "tests", "correlation_id": "phase4-skip-1"},
    )
    assert skipped["ok"] is True
    refreshed = task_service.get_task(skip_task_id)
    assert refreshed is not None
    assert refreshed.due_date == date.today() + timedelta(days=1)


class _RecorderServer:
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.calls = []

    def call_tool(self, tool_name, arguments, context=None):
        self.calls.append(tool_name)
        return self._wrapped.call_tool(tool_name, arguments, context=context)

    def __getattr__(self, item):
        return getattr(self._wrapped, item)


def test_workflow_add_complete_skip_route_through_mcp(monkeypatch):
    wrapped = get_mcp_server()
    recorder = _RecorderServer(wrapped)
    monkeypatch.setattr(workflow_module, "get_mcp_server", lambda: recorder)

    marker = f"phase4-workflow-{uuid4().hex[:8]}"
    add_result = workflow_module.submit_input(f"{marker} tomorrow", source="web")
    assert add_result["status"] == "completed"
    assert "tasks.create" in recorder.calls

    created = task_service.get_task(add_result["task"]["id"])
    assert created is not None

    complete_result = workflow_module.submit_input(f"done {marker}", source="web")
    assert complete_result["status"] == "completed"
    assert "tasks.complete" in recorder.calls

    new_for_skip = workflow_module.submit_input(f"{marker}-skip tomorrow", source="web")
    assert new_for_skip["status"] == "completed"
    skip_result = workflow_module.submit_input(f"skip {marker}-skip", source="web")
    assert skip_result["status"] == "completed"
    assert "tasks.skip" in recorder.calls


def test_wave2_task_project_goal_tool_slice_end_to_end():
    server = get_mcp_server()
    marker = uuid4().hex[:8]

    created_goal = server.call_tool(
        "goals.create",
        {"name": f"goal-{marker}", "goal_type": "bigger_goal"},
        context={"source": "tests", "correlation_id": "phase4-goal-create"},
    )
    assert created_goal["ok"] is True
    goal_id = int(created_goal["result"]["goal"]["id"])

    created_project = server.call_tool(
        "projects.create",
        {"name": f"project-{marker}", "goal_id": goal_id},
        context={"source": "tests", "correlation_id": "phase4-project-create"},
    )
    assert created_project["ok"] is True
    project_id = int(created_project["result"]["project"]["id"])

    created_task = server.call_tool(
        "tasks.create",
        {"name": f"task-{marker}", "project_id": project_id},
        context={"source": "tests", "correlation_id": "phase4-task-create"},
    )
    assert created_task["ok"] is True
    task_id = int(created_task["result"]["task"]["id"])

    renamed = server.call_tool(
        "tasks.rename",
        {"task_id": task_id, "name": f"task-renamed-{marker}"},
        context={"source": "tests", "correlation_id": "phase4-task-rename"},
    )
    assert renamed["ok"] is True
    assert renamed["result"]["verified"] is True

    by_project = server.call_tool(
        "tasks.list_by_project",
        {"project_id": project_id},
        context={"source": "tests"},
    )
    assert by_project["ok"] is True
    assert task_id in set(by_project["result"]["task_ids"])

    by_goal = server.call_tool(
        "tasks.list_by_goal",
        {"goal_id": goal_id},
        context={"source": "tests"},
    )
    assert by_goal["ok"] is True
    assert task_id in set(by_goal["result"]["task_ids"])

    search = server.call_tool(
        "tasks.search",
        {"query": f"renamed-{marker}"},
        context={"source": "tests"},
    )
    assert search["ok"] is True
    assert task_id in set(search["result"]["task_ids"])

def test_wave2_bulk_families_and_tag_metadata_tools():
    server = get_mcp_server()
    marker = uuid4().hex[:8]

    created_a = server.call_tool(
        "tasks.create",
        {"name": f"bulk-a-{marker}"},
        context={"source": "tests", "correlation_id": "phase4-bulk-a"},
    )
    created_b = server.call_tool(
        "tasks.create",
        {"name": f"bulk-b-{marker}"},
        context={"source": "tests", "correlation_id": "phase4-bulk-b"},
    )
    assert created_a["ok"] is True and created_b["ok"] is True
    task_a = int(created_a["result"]["task"]["id"])
    task_b = int(created_b["result"]["task"]["id"])

    set_tags = server.call_tool(
        "tasks.set_tags",
        {"task_id": task_a, "tags": ["alpha", "beta"]},
        context={"source": "tests"},
    )
    add_tags = server.call_tool(
        "tasks.add_tags",
        {"task_id": task_a, "tags": ["gamma"]},
        context={"source": "tests"},
    )
    remove_tags = server.call_tool(
        "tasks.remove_tags",
        {"task_id": task_a, "tags": ["beta"]},
        context={"source": "tests"},
    )
    assert set_tags["ok"] is True
    assert add_tags["ok"] is True
    assert remove_tags["ok"] is True
    assert {"alpha", "gamma"}.issubset(set(remove_tags["result"]["task"]["tags"]))

    preview_complete = server.call_tool(
        "tasks.preview_bulk_complete",
        {"task_ids": [task_a, task_b], "scope_ref": "tests.bulk_complete"},
        context={"source": "tests"},
    )
    assert preview_complete["ok"] is True
    assert preview_complete["result"]["requires_approval"] is True
    commit_complete = server.call_tool(
        "tasks.commit_bulk_complete",
        {"preview_id": preview_complete["result"]["preview_id"], "approved": True},
        context={"source": "tests"},
    )
    assert commit_complete["ok"] is True
    assert commit_complete["result"]["verified_affected_count"] == 2

    created_c = server.call_tool(
        "tasks.create",
        {"name": f"bulk-c-{marker}"},
        context={"source": "tests"},
    )
    created_d = server.call_tool(
        "tasks.create",
        {"name": f"bulk-d-{marker}"},
        context={"source": "tests"},
    )
    assert created_c["ok"] is True and created_d["ok"] is True
    task_c = int(created_c["result"]["task"]["id"])
    task_d = int(created_d["result"]["task"]["id"])

    preview_skip = server.call_tool(
        "tasks.preview_bulk_skip",
        {"task_ids": [task_c], "scope_ref": "tests.bulk_skip"},
        context={"source": "tests"},
    )
    assert preview_skip["ok"] is True
    commit_skip = server.call_tool(
        "tasks.commit_bulk_skip",
        {"preview_id": preview_skip["result"]["preview_id"]},
        context={"source": "tests"},
    )
    assert commit_skip["ok"] is True
    assert commit_skip["result"]["verified_affected_count"] == 1

    project = server.call_tool(
        "projects.create",
        {"name": f"bulk-project-{marker}"},
        context={"source": "tests"},
    )
    assert project["ok"] is True
    project_id = int(project["result"]["project"]["id"])

    preview_move = server.call_tool(
        "tasks.preview_bulk_move_project",
        {"task_ids": [task_c, task_d], "project_id": project_id, "scope_ref": "tests.bulk_move"},
        context={"source": "tests"},
    )
    assert preview_move["ok"] is True
    commit_move = server.call_tool(
        "tasks.commit_bulk_move_project",
        {"preview_id": preview_move["result"]["preview_id"], "approved": True},
        context={"source": "tests"},
    )
    assert commit_move["ok"] is True
    assert commit_move["result"]["verified_affected_count"] == 2

    preview_retag = server.call_tool(
        "tasks.preview_bulk_retag",
        {"task_ids": [task_c, task_d], "add_tags": ["wave2"], "scope_ref": "tests.bulk_retag"},
        context={"source": "tests"},
    )
    assert preview_retag["ok"] is True
    commit_retag = server.call_tool(
        "tasks.commit_bulk_retag",
        {"preview_id": preview_retag["result"]["preview_id"], "approved": True},
        context={"source": "tests"},
    )
    assert commit_retag["ok"] is True
    assert commit_retag["result"]["verified_affected_count"] == 2

    preview_delete = server.call_tool(
        "tasks.preview_bulk_delete",
        {"task_ids": [task_d], "scope_ref": "tests.bulk_delete"},
        context={"source": "tests"},
    )
    assert preview_delete["ok"] is True
    assert preview_delete["result"]["requires_approval"] is True
    commit_delete = server.call_tool(
        "tasks.commit_bulk_delete",
        {"preview_id": preview_delete["result"]["preview_id"], "approved": True},
        context={"source": "tests"},
    )
    assert commit_delete["ok"] is True
    assert task_service.get_task(task_d) is None

def test_wave2_audit_undo_dependencies_subtasks_and_interop():
    server = get_mcp_server()
    marker = uuid4().hex[:8]

    parent = server.call_tool(
        "tasks.create",
        {"name": f"parent-{marker}"},
        context={"source": "tests"},
    )
    other = server.call_tool(
        "tasks.create",
        {"name": f"other-{marker}"},
        context={"source": "tests"},
    )
    assert parent["ok"] is True and other["ok"] is True
    parent_id = int(parent["result"]["task"]["id"])
    other_id = int(other["result"]["task"]["id"])

    subtask = server.call_tool(
        "subtasks.create",
        {"parent_task_id": parent_id, "name": f"child-{marker}"},
        context={"source": "tests"},
    )
    assert subtask["ok"] is True
    subtask_id = int(subtask["result"]["subtask"]["id"])

    listed_subtasks = server.call_tool(
        "subtasks.list",
        {"parent_task_id": parent_id},
        context={"source": "tests"},
    )
    assert listed_subtasks["ok"] is True
    assert subtask_id in set(listed_subtasks["result"]["task_ids"])

    add_dep = server.call_tool(
        "dependencies.add",
        {"task_id": subtask_id, "depends_on_task_id": other_id},
        context={"source": "tests"},
    )
    assert add_dep["ok"] is True
    deps = server.call_tool(
        "dependencies.list",
        {"task_id": subtask_id},
        context={"source": "tests"},
    )
    assert deps["ok"] is True
    assert other_id in set(deps["result"]["dependency_ids"])

    remove_dep = server.call_tool(
        "dependencies.remove",
        {"task_id": subtask_id, "depends_on_task_id": other_id},
        context={"source": "tests"},
    )
    assert remove_dep["ok"] is True

    audit_events = server.call_tool(
        "audit.list_events",
        {"limit": 25},
        context={"source": "tests"},
    )
    assert audit_events["ok"] is True
    assert audit_events["result"]["count"] >= 1

    explain = server.call_tool(
        "audit.explain_last_mutation",
        {},
        context={"source": "tests"},
    )
    assert explain["ok"] is True
    assert explain["result"]["has_event"] is True

    undo_target = server.call_tool(
        "tasks.create",
        {"name": f"undo-target-{marker}"},
        context={"source": "tests"},
    )
    assert undo_target["ok"] is True
    undo_task_id = int(undo_target["result"]["task"]["id"])

    create_events = server.call_tool(
        "audit.list_events",
        {"limit": 1, "operation": "tasks.create"},
        context={"source": "tests"},
    )
    assert create_events["ok"] is True
    event_id = create_events["result"]["events"][0]["event_id"]

    undo_preview = server.call_tool(
        "undo.preview",
        {"event_id": event_id},
        context={"source": "tests"},
    )
    assert undo_preview["ok"] is True
    assert undo_preview["result"]["can_undo"] is True

    undo_commit = server.call_tool(
        "undo.commit",
        {"undo_id": undo_preview["result"]["undo_id"], "approved": True},
        context={"source": "tests"},
    )
    assert undo_commit["ok"] is True
    assert task_service.get_task(undo_task_id) is None

    exported = server.call_tool(
        "interop.export_seed",
        {"include_tasks": True, "include_done_tasks": False},
        context={"source": "tests"},
    )
    assert exported["ok"] is True
    assert isinstance(exported["result"]["seed"], dict)

    imported_dry_run = server.call_tool(
        "interop.import_seed",
        {"seed": exported["result"]["seed"], "dry_run": True},
        context={"source": "tests"},
    )
    assert imported_dry_run["ok"] is True
    assert imported_dry_run["result"]["dry_run"] is True
    assert imported_dry_run["result"]["validation_errors"] == []
