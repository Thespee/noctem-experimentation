"""Tests for v0.9.3 MCP Phase 1 skeleton and read-only tools."""
from datetime import date, timedelta

from noctem.agent import workflow as workflow_module
from noctem.mcp import get_mcp_server
from noctem.mcp.contracts import MCP_SCHEMA_VERSION
from noctem.mcp.server import _redact_for_debug
from noctem.services import task_service


def test_mcp_tools_list_exposes_phase1_read_only_tools():
    server = get_mcp_server()

    listing = server.tools_list(context={"source": "tests", "correlation_id": "mcp-list-1"})
    assert listing["ok"] is True
    assert listing["schema_version"] == MCP_SCHEMA_VERSION
    assert listing["tool_name"] == "tools/list"
    assert listing["correlation_id"] == "mcp-list-1"

    tool_names = {tool["name"] for tool in listing["result"]["tools"]}
    assert "tasks.get" in tool_names
    assert "tasks.list_today" in tool_names
    assert "tasks.list_overdue" in tool_names
    assert "tasks.list_inbox" in tool_names
    assert "ops.health" in tool_names
    assert "ops.get_capabilities" in tool_names
    assert "tasks.preview_delete" in tool_names
    assert "tasks.commit_delete" in tool_names
    assert "tasks.create" in tool_names
    assert "tasks.complete" in tool_names
    assert "tasks.skip" in tool_names
    assert "tasks.update_fields" in tool_names
    assert "tasks.search" in tool_names
    assert "tasks.list_upcoming" in tool_names
    assert "tasks.rename" in tool_names
    assert "tasks.set_tags" in tool_names
    assert "tasks.add_tags" in tool_names
    assert "tasks.remove_tags" in tool_names
    assert "tasks.preview_bulk_complete" in tool_names
    assert "tasks.commit_bulk_complete" in tool_names
    assert "tasks.preview_bulk_skip" in tool_names
    assert "tasks.commit_bulk_skip" in tool_names
    assert "tasks.preview_bulk_delete" in tool_names
    assert "tasks.commit_bulk_delete" in tool_names
    assert "tasks.preview_bulk_move_project" in tool_names
    assert "tasks.commit_bulk_move_project" in tool_names
    assert "tasks.preview_bulk_retag" in tool_names
    assert "tasks.commit_bulk_retag" in tool_names
    assert "dependencies.add" in tool_names
    assert "dependencies.remove" in tool_names
    assert "dependencies.list" in tool_names
    assert "subtasks.create" in tool_names
    assert "subtasks.list" in tool_names
    assert "subtasks.promote" in tool_names
    assert "projects.list" in tool_names
    assert "projects.create" in tool_names
    assert "goals.list" in tool_names
    assert "goals.create" in tool_names
    assert "audit.list_events" in tool_names
    assert "audit.get_event" in tool_names
    assert "audit.explain_last_mutation" in tool_names
    assert "undo.preview" in tool_names
    assert "undo.commit" in tool_names
    assert "interop.export_seed" in tool_names
    assert "interop.import_seed" in tool_names

    by_name = {tool["name"]: tool for tool in listing["result"]["tools"]}
    assert by_name["tasks.list_today"]["read_only"] is True
    assert by_name["tasks.create"]["read_only"] is False
    assert by_name["tasks.complete"]["read_only"] is False
    assert by_name["tasks.skip"]["read_only"] is False
    assert by_name["tasks.update_fields"]["read_only"] is False
    assert by_name["tasks.commit_delete"]["read_only"] is False
    assert listing["result"]["tool_count"] == len(listing["result"]["tools"])


def test_mcp_tasks_list_today_returns_structured_envelope():
    today_task = task_service.create_task("phase1-mcp-today", due_date=date.today())
    task_service.create_task("phase1-mcp-tomorrow", due_date=date.today() + timedelta(days=1))

    server = get_mcp_server()
    result = server.call_tool(
        "tasks.list_today",
        {},
        context={"source": "tests", "correlation_id": "mcp-today-1"},
    )

    assert result["ok"] is True
    assert result["tool_name"] == "tasks.list_today"
    assert result["correlation_id"] == "mcp-today-1"
    assert result["audit"]["read_only"] is True
    assert result["result"]["count"] >= 1

    ids = set(result["result"]["task_ids"])
    assert today_task.id in ids


def test_mcp_unknown_tool_returns_error_envelope():
    server = get_mcp_server()
    result = server.call_tool("tasks.unknown", {}, context={"source": "tests"})

    assert result["ok"] is False
    assert result["tool_name"] == "tasks.unknown"
    assert result["error"]["code"] == "tool_not_found"


def test_query_path_uses_mcp_server_for_today_summary(monkeypatch):
    class _FakeMCPServer:
        def __init__(self):
            self.calls = []

        def call_tool(self, tool_name, arguments, context=None):
            self.calls.append((tool_name, arguments, context))
            if tool_name == "tasks.list_today":
                return {
                    "ok": True,
                    "tool_name": tool_name,
                    "correlation_id": "today-corr",
                    "result": {"count": 2, "task_ids": [1, 2], "tasks": []},
                }
            if tool_name == "tasks.list_overdue":
                return {
                    "ok": True,
                    "tool_name": tool_name,
                    "correlation_id": "overdue-corr",
                    "result": {"count": 1, "task_ids": [3], "tasks": []},
                }
            raise AssertionError(f"Unexpected tool: {tool_name}")

    fake_server = _FakeMCPServer()
    monkeypatch.setattr(workflow_module, "get_mcp_server", lambda: fake_server)

    result = workflow_module.submit_input("What do I have on for today?", source="web")
    assert result["status"] == "completed"
    assert result["today_count"] == 2
    assert result["overdue_count"] == 1
    assert "You have 2 task(s) due today and 1 overdue." in result["response"]
    assert [name for name, *_ in fake_server.calls] == ["tasks.list_today", "tasks.list_overdue"]

def test_mcp_debug_redaction_masks_sensitive_fields():
    payload = {
        "telegram_bot_token": "123456:secret-token",
        "nested": {
            "auth_header": "Bearer abc",
            "safe": {"value": 7},
        },
        "safe_key": "not-sensitive",
    }
    redacted = _redact_for_debug(payload)

    assert redacted["telegram_bot_token"] == "[REDACTED]"
    assert redacted["nested"]["auth_header"] == "[REDACTED]"
    assert redacted["nested"]["safe"]["value"] == 7
    assert redacted["safe_key"] == "not-sensitive"
