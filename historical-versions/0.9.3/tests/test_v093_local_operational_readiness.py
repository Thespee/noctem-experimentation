"""Local operational readiness tests for v0.9.3 MCP-first routing."""
from uuid import uuid4

from noctem.mcp import get_mcp_server
from noctem.services import project_service, task_service
from noctem.session import UpdateItem, get_session
from noctem.web import app as web_app_module
from noctem.handlers import interactive as interactive_module
from noctem.fast import capture as capture_module


class _RecorderServer:
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.calls = []

    def call_tool(self, tool_name, arguments, context=None):
        self.calls.append(tool_name)
        return self._wrapped.call_tool(tool_name, arguments, context=context)

    def __getattr__(self, item):
        return getattr(self._wrapped, item)


def _client():
    from noctem.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_web_task_mutation_endpoints_route_through_mcp(monkeypatch):
    recorder = _RecorderServer(get_mcp_server())
    monkeypatch.setattr(web_app_module, "get_mcp_server", lambda: recorder)

    client = _client()
    marker = f"web-local-{uuid4().hex[:8]}"
    create_resp = client.post("/api/tasks", json={"name": f"{marker} tomorrow 9am"})
    assert create_resp.status_code == 200
    create_data = create_resp.get_json()
    assert create_data["success"] is True
    task_id = int(create_data["task"]["id"])

    update_resp = client.post(f"/api/tasks/{task_id}/update", json={"importance": 1.0})
    assert update_resp.status_code == 200
    assert update_resp.get_json()["success"] is True

    complete_resp = client.post(f"/api/tasks/{task_id}/complete")
    assert complete_resp.status_code == 200
    assert complete_resp.get_json()["success"] is True

    assert "tasks.create" in recorder.calls
    assert "tasks.update_fields" in recorder.calls
    assert "tasks.complete" in recorder.calls


def test_interactive_modes_route_mutations_through_mcp(monkeypatch):
    recorder = _RecorderServer(get_mcp_server())
    monkeypatch.setattr(interactive_module, "get_mcp_server", lambda: recorder)

    session = get_session()
    session.reset()

    task = task_service.create_task(f"interactive-local-{uuid4().hex[:6]}")
    interactive_module.start_prioritize_mode(5)
    response, exited = interactive_module.handle_prioritize_input("1")
    assert exited is False
    assert "Bumped" in response

    project = project_service.create_project(f"interactive-proj-{uuid4().hex[:6]}")
    item = UpdateItem(
        index=1,
        entity_type="project",
        entity_id=project.id,
        name=project.name,
        missing=["tasks"],
    )
    session.update_items = [item]
    project_response, _ = interactive_module.handle_project_update(item, f"task-{uuid4().hex[:4]} tomorrow")
    assert "Updated" in project_response

    assert "tasks.update_fields" in recorder.calls
    assert "tasks.create" in recorder.calls
    assert task_service.get_task(task.id) is not None


def test_fast_capture_actionable_creation_routes_through_mcp(monkeypatch):
    recorder = _RecorderServer(get_mcp_server())
    monkeypatch.setattr(capture_module, "get_mcp_server", lambda: recorder)

    marker = f"capture-local-{uuid4().hex[:8]}"
    result = capture_module.process_input(f"{marker} tomorrow", source="cli")
    assert result.task is not None
    assert marker.split("-")[0] in result.response.lower()
    assert "tasks.create" in recorder.calls
