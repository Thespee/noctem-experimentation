"""v0.9.4 graph/interface and internal versioning surface tests."""

from pathlib import Path
from uuid import uuid4

import pytest

from noctem.mcp import get_mcp_server
from noctem.services.object_context_docs import synthesize_object_context_doc


@pytest.fixture
def app():
    from noctem.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _call_tool(name: str, arguments: dict) -> dict:
    result = get_mcp_server().call_tool(
        name,
        arguments,
        context={"source": "test.v094.graph"},
    )
    assert result.get("ok") is True
    payload = result.get("result")
    assert isinstance(payload, dict)
    return payload


def _seed_graph_entities(marker: str) -> tuple[int, int, int]:
    goal = _call_tool(
        "goals.create",
        {"name": f"Goal {marker}", "goal_type": "bigger_goal"},
    )["goal"]
    goal_id = int(goal["id"])

    project = _call_tool(
        "projects.create",
        {"name": f"Project {marker}", "goal_id": goal_id},
    )["project"]
    project_id = int(project["id"])

    task = _call_tool(
        "tasks.create",
        {"name": f"Task {marker}", "project_id": project_id},
    )["task"]
    task_id = int(task["id"])

    _call_tool(
        "tasks.update_fields",
        {"task_id": task_id, "status": "in_progress"},
    )
    return goal_id, project_id, task_id


def test_graph_page_renders(client):
    response = client.get("/graph")
    assert response.status_code == 200
    assert b"Object Graph" in response.data


def test_api_graph_returns_nodes_and_typed_relationship_edges(client):
    marker = f"graph-api-{uuid4().hex[:8]}"
    goal_id, project_id, task_id = _seed_graph_entities(marker)

    response = client.get("/api/graph?limit=5000")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    graph = data["graph"]
    nodes = list(graph["nodes"])
    edges = list(graph["edges"])

    node_ids = {str(node["id"]) for node in nodes}
    task_object_id = f"task:{task_id}"
    project_object_id = f"project:{project_id}"
    goal_object_id = f"goal:{goal_id}"
    assert task_object_id in node_ids
    assert project_object_id in node_ids
    assert goal_object_id in node_ids

    edge_keys = {(edge["source"], edge["target"], edge["relation"]) for edge in edges}
    assert (task_object_id, project_object_id, "task_project") in edge_keys
    assert (project_object_id, goal_object_id, "project_goal") in edge_keys


def test_api_graph_object_surface_includes_versions_and_relations(client):
    marker = f"graph-object-{uuid4().hex[:8]}"
    _, project_id, task_id = _seed_graph_entities(marker)
    task_object_id = f"task:{task_id}"

    response = client.get(f"/api/graph/object/{task_object_id}?version_limit=50")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    surface = data["surface"]
    assert surface["object"]["id"] == task_object_id
    assert len(surface["versions"]) >= 2
    assert any(edge["target"] == f"project:{project_id}" for edge in surface["relations"])


def test_api_graph_versions_returns_parent_edges(client):
    marker = f"graph-versions-{uuid4().hex[:8]}"
    _, _, task_id = _seed_graph_entities(marker)
    task_object_id = f"task:{task_id}"

    response = client.get(f"/api/graph/versions?object_id={task_object_id}&limit=100")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    version_payload = data["versions"]
    assert version_payload["count"] >= 2
    assert any(node["object_id"] == task_object_id for node in version_payload["version_nodes"])
    assert any(edge["relation"] == "parent_of" for edge in version_payload["edges"])


def test_api_graph_export_markdown_writes_snapshot(client, tmp_path):
    marker = f"graph-export-{uuid4().hex[:8]}"
    _, _, task_id = _seed_graph_entities(marker)
    synthesize_object_context_doc(f"task:{task_id}")

    response = client.post(
        "/api/graph/export/markdown",
        json={
            "output_dir": str(tmp_path),
            "limit": 5000,
            "include_context_docs": True,
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    manifest = data["manifest"]
    snapshot_dir = Path(manifest["snapshot_dir"])
    index_file = Path(manifest["index_file"])
    graph_json = Path(manifest["graph_json_file"])

    assert snapshot_dir.exists()
    assert index_file.exists()
    assert graph_json.exists()
    assert manifest["file_count"] >= 3

    index_text = index_file.read_text(encoding="utf-8")
    assert marker in index_text
