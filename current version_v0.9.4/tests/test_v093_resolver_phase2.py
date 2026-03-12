"""Tests for v0.9.3 Phase 2 resolver engine behavior."""
from uuid import uuid4

from noctem.mcp import get_mcp_server
from noctem.services import task_service


def _client():
    from noctem.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_mcp_resolve_candidates_selects_unique_task():
    marker = f"phase2-unique-{uuid4().hex[:10]}"
    task = task_service.create_task(f"{marker} alpha")

    server = get_mcp_server()
    result = server.call_tool(
        "tasks.resolve_candidates",
        {"query": marker, "include_done": False, "limit": 5},
        context={"source": "tests", "correlation_id": "resolve-unique-1"},
    )

    assert result["ok"] is True
    assert result["result"]["resolution"] == "selected"
    assert result["result"]["ambiguous"] is False
    assert result["result"]["selected_task_id"] == task.id


def test_mcp_resolve_candidates_flags_ambiguity_for_close_matches():
    marker = f"phase2-ambig-{uuid4().hex[:10]}"
    task_service.create_task(f"{marker} alpha")
    task_service.create_task(f"{marker} beta")

    server = get_mcp_server()
    result = server.call_tool(
        "tasks.resolve_candidates",
        {"query": marker, "include_done": False, "limit": 5},
        context={"source": "tests", "correlation_id": "resolve-ambig-1"},
    )

    assert result["ok"] is True
    assert result["result"]["ambiguous"] is True
    assert result["result"]["resolution"] == "ambiguous"
    assert result["result"]["selected_task_id"] is None
    assert len(result["result"]["candidates"]) >= 2


def test_mcp_resolve_scope_reports_unresolved_names():
    marker = f"phase2-scope-{uuid4().hex[:10]}"
    existing = f"{marker} existing"
    missing = f"completely-unmatched-{uuid4().hex[:12]}"
    matched = task_service.create_task(existing)

    server = get_mcp_server()
    result = server.call_tool(
        "tasks.resolve_scope",
        {"scope_type": "task_names", "task_names": [existing, missing]},
        context={"source": "tests", "correlation_id": "resolve-scope-1"},
    )

    assert result["ok"] is True
    assert result["result"]["scope_type"] == "task_names"
    assert result["result"]["matched_count"] == 1
    assert matched.id in result["result"]["matched_task_ids"]
    assert missing in result["result"]["unresolved_names"]
    assert result["result"]["ambiguous"] is False


def test_delete_with_ambiguous_target_requests_clarification():
    marker = f"phase2-delete-{uuid4().hex[:10]}"
    task_service.create_task(f"{marker} alpha")
    task_service.create_task(f"{marker} beta")

    client = _client()
    resp = client.post("/api/agent/submit", json={"input": f"delete {marker}"})
    assert resp.status_code == 200
    payload = resp.get_json()

    assert payload["success"] is True
    assert payload["status"] == "interrupted"
    assert payload["interrupt"]["type"] == "clarify"
    assert "multiple close task matches" in payload["response"].lower()
    assert len(payload["interrupt"]["options"]) >= 2
