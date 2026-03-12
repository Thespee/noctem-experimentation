"""Object graph, internal versioning surfaces, and markdown export helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..db import DATA_DIR, get_db
from .object_context_docs import build_object_context_doc, get_object_context_doc


def _json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _clamp_limit(value: int | None, *, default: int, minimum: int, maximum: int) -> int:
    raw = default if value is None else int(value)
    return max(minimum, min(raw, maximum))


def _slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "object"
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "object"


def _object_label(snapshot: dict[str, Any], fallback: str) -> str:
    label = (
        snapshot.get("name")
        or snapshot.get("title")
        or snapshot.get("summary")
        or snapshot.get("id")
        or fallback
    )
    return str(label)


def _fetch_object_rows(
    *,
    limit: int,
    object_type: str | None = None,
    object_id: str | None = None,
) -> list:
    clauses: list[str] = []
    params: list[Any] = []
    if object_type:
        clauses.append("lower(o.object_type) = ?")
        params.append(str(object_type).strip().lower())
    if object_id:
        clauses.append("o.object_id = ?")
        params.append(str(object_id).strip())
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with get_db() as conn:
        return conn.execute(
            f"""
            SELECT
                o.object_id,
                o.object_type,
                o.typed_id,
                o.review_state,
                o.metadata_json,
                o.created_at,
                o.updated_at,
                r.head_version_id,
                hv.version_num AS head_version_num,
                hv.event_id AS head_event_id,
                hv.snapshot_json AS head_snapshot_json,
                hv.created_at AS head_version_created_at,
                cd.summary AS context_summary,
                cd.generated_at AS context_generated_at,
                (
                    SELECT COUNT(1)
                    FROM object_versions ov
                    WHERE ov.object_id = o.object_id
                ) AS version_count
            FROM objects o
            LEFT JOIN object_refs r ON r.object_id = o.object_id
            LEFT JOIN object_versions hv ON hv.version_id = r.head_version_id
            LEFT JOIN object_context_docs cd ON cd.object_id = o.object_id
            {where_sql}
            ORDER BY datetime(COALESCE(o.updated_at, o.created_at)) DESC, o.object_id
            LIMIT ?
            """,
            params,
        ).fetchall()


def list_object_nodes(
    *,
    limit: int = 300,
    object_type: str | None = None,
    object_id: str | None = None,
) -> list[dict[str, Any]]:
    bounded_limit = _clamp_limit(limit, default=300, minimum=1, maximum=5000)
    rows = _fetch_object_rows(limit=bounded_limit, object_type=object_type, object_id=object_id)
    nodes: list[dict[str, Any]] = []
    for row in rows:
        head_snapshot = _json_loads(row["head_snapshot_json"], {})
        if not isinstance(head_snapshot, dict):
            head_snapshot = {}
        metadata = _json_loads(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        object_id_value = str(row["object_id"])
        nodes.append(
            {
                "id": object_id_value,
                "object_id": object_id_value,
                "type": row["object_type"],
                "typed_id": row["typed_id"],
                "label": _object_label(head_snapshot, object_id_value),
                "review_state": row["review_state"],
                "metadata": metadata,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "head_version_id": row["head_version_id"],
                "head_version_num": row["head_version_num"],
                "head_event_id": row["head_event_id"],
                "head_version_created_at": row["head_version_created_at"],
                "head_snapshot": head_snapshot,
                "version_count": int(row["version_count"] or 0),
                "context_summary": row["context_summary"],
                "context_generated_at": row["context_generated_at"],
            }
        )
    return nodes


def _add_edge(
    *,
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    source: str,
    target: str,
    relation: str,
    target_exists: bool,
) -> None:
    key = (source, target, relation)
    if key in seen:
        return
    seen.add(key)
    edges.append(
        {
            "id": f"{relation}:{source}->{target}",
            "source": source,
            "target": target,
            "relation": relation,
            "target_exists": target_exists,
        }
    )


def build_relationship_edges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    known_ids = {str(node["id"]) for node in nodes}
    for node in nodes:
        source_id = str(node["id"])
        object_type = str(node.get("type") or "").strip().lower()
        snapshot = node.get("head_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        if object_type == "task":
            project_id = _as_int(snapshot.get("project_id"))
            if project_id is not None:
                target = f"project:{project_id}"
                _add_edge(
                    edges=edges,
                    seen=seen,
                    source=source_id,
                    target=target,
                    relation="task_project",
                    target_exists=target in known_ids,
                )
            tags_raw = snapshot.get("tags")
            tags = tags_raw if isinstance(tags_raw, list) else [tags_raw] if tags_raw else []
            for tag in tags:
                tag_text = str(tag or "").strip().lower()
                if not tag_text.startswith("subtask_of:"):
                    continue
                parent_id = _as_int(tag_text.split(":", 1)[1])
                if parent_id is None:
                    continue
                target = f"task:{parent_id}"
                _add_edge(
                    edges=edges,
                    seen=seen,
                    source=source_id,
                    target=target,
                    relation="subtask_of",
                    target_exists=target in known_ids,
                )
        if object_type == "project":
            goal_id = _as_int(snapshot.get("goal_id"))
            if goal_id is not None:
                target = f"goal:{goal_id}"
                _add_edge(
                    edges=edges,
                    seen=seen,
                    source=source_id,
                    target=target,
                    relation="project_goal",
                    target_exists=target in known_ids,
                )
    return edges


def _version_rows(*, limit: int, object_id: str | None = None) -> list:
    params: list[Any] = []
    where_sql = ""
    if object_id:
        where_sql = "WHERE v.object_id = ?"
        params.append(str(object_id).strip())
    params.append(limit)
    with get_db() as conn:
        return conn.execute(
            f"""
            SELECT
                v.version_id,
                v.object_id,
                v.version_num,
                v.parent_version_id,
                v.event_id,
                v.created_by,
                v.created_at,
                o.object_type,
                o.typed_id,
                r.head_version_id
            FROM object_versions v
            JOIN objects o ON o.object_id = v.object_id
            LEFT JOIN object_refs r ON r.object_id = v.object_id
            {where_sql}
            ORDER BY datetime(v.created_at) DESC, v.version_num DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def _event_map(event_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT event_id, operation, summary, created_at
            FROM object_events
            WHERE event_id IN ({placeholders})
            """,
            event_ids,
        ).fetchall()
    event_lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row["event_id"])
        event_lookup[event_id] = {
            "id": f"event:{event_id}",
            "event_id": event_id,
            "type": "event",
            "label": row["summary"] or row["operation"] or event_id,
            "operation": row["operation"],
            "created_at": row["created_at"],
        }
    return event_lookup


def list_object_versions(*, object_id: str, limit: int = 25) -> list[dict[str, Any]]:
    bounded = _clamp_limit(limit, default=25, minimum=1, maximum=500)
    rows = _version_rows(limit=bounded, object_id=object_id)
    event_ids = [str(row["event_id"]) for row in rows if row["event_id"]]
    events = _event_map(event_ids)
    versions: list[dict[str, Any]] = []
    for row in rows:
        event_id = row["event_id"]
        versions.append(
            {
                "id": row["version_id"],
                "version_id": row["version_id"],
                "type": "version",
                "object_id": row["object_id"],
                "object_type": row["object_type"],
                "typed_id": row["typed_id"],
                "version_num": row["version_num"],
                "parent_version_id": row["parent_version_id"],
                "event_id": event_id,
                "event_summary": events.get(event_id, {}).get("label") if event_id else None,
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "is_head": row["head_version_id"] == row["version_id"],
            }
        )
    return versions


def list_version_graph(*, limit: int = 400, object_id: str | None = None) -> dict[str, Any]:
    bounded = _clamp_limit(limit, default=400, minimum=1, maximum=5000)
    rows = _version_rows(limit=bounded, object_id=object_id)
    event_ids = [str(row["event_id"]) for row in rows if row["event_id"]]
    event_lookup = _event_map(event_ids)
    version_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    known_versions: set[str] = set()
    for row in rows:
        version_id = str(row["version_id"])
        known_versions.add(version_id)
        event_id = row["event_id"]
        version_nodes.append(
            {
                "id": version_id,
                "version_id": version_id,
                "type": "version",
                "object_id": row["object_id"],
                "object_type": row["object_type"],
                "typed_id": row["typed_id"],
                "version_num": row["version_num"],
                "parent_version_id": row["parent_version_id"],
                "event_id": event_id,
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "is_head": row["head_version_id"] == row["version_id"],
            }
        )
    for node in version_nodes:
        parent_id = node.get("parent_version_id")
        if parent_id:
            edges.append(
                {
                    "id": f"parent:{parent_id}->{node['id']}",
                    "source": parent_id,
                    "target": node["id"],
                    "relation": "parent_of",
                    "source_exists": str(parent_id) in known_versions,
                }
            )
        event_id = node.get("event_id")
        if event_id and event_id in event_lookup:
            event_node_id = event_lookup[event_id]["id"]
            edges.append(
                {
                    "id": f"event:{node['id']}->{event_node_id}",
                    "source": node["id"],
                    "target": event_node_id,
                    "relation": "created_by_event",
                    "source_exists": True,
                }
            )
    event_nodes = list(event_lookup.values())
    return {
        "count": len(version_nodes),
        "version_nodes": version_nodes,
        "event_nodes": event_nodes,
        "nodes": [*version_nodes, *event_nodes],
        "edges": edges,
    }


def build_object_graph(
    *,
    limit: int = 300,
    object_type: str | None = None,
    include_versions: bool = False,
) -> dict[str, Any]:
    nodes = list_object_nodes(limit=limit, object_type=object_type)
    edges = build_relationship_edges(nodes)
    stats = {
        "object_count": len(nodes),
        "edge_count": len(edges),
        "types": {},
        "manual_review_count": 0,
    }
    for node in nodes:
        node_type = str(node.get("type") or "unknown")
        stats["types"][node_type] = int(stats["types"].get(node_type, 0)) + 1
        if str(node.get("review_state") or "").lower() == "manual_review":
            stats["manual_review_count"] += 1
    payload: dict[str, Any] = {
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    if include_versions:
        payload["versions"] = list_version_graph(limit=min(max(limit * 3, 100), 1000))
    return payload


def get_object_version_surface(object_id: str, *, version_limit: int = 40) -> dict[str, Any] | None:
    object_id_value = str(object_id or "").strip()
    if not object_id_value:
        return None
    nodes = list_object_nodes(limit=1, object_id=object_id_value)
    if not nodes:
        return None
    object_node = nodes[0]
    versions_graph = list_version_graph(limit=version_limit, object_id=object_id_value)
    neighborhood_nodes = list_object_nodes(limit=5000)
    neighborhood_edges = build_relationship_edges(neighborhood_nodes)
    relations = [
        edge
        for edge in neighborhood_edges
        if edge.get("source") == object_id_value or edge.get("target") == object_id_value
    ]
    neighbor_ids: set[str] = set()
    for edge in relations:
        if edge.get("source") != object_id_value:
            neighbor_ids.add(str(edge.get("source")))
        if edge.get("target") != object_id_value:
            neighbor_ids.add(str(edge.get("target")))
    by_id = {str(node["id"]): node for node in neighborhood_nodes}
    neighbors = [by_id[node_id] for node_id in sorted(neighbor_ids) if node_id in by_id]
    context_doc = get_object_context_doc(object_id_value) or build_object_context_doc(object_id_value)
    return {
        "object": object_node,
        "versions": versions_graph.get("version_nodes", []),
        "version_edges": versions_graph.get("edges", []),
        "events": versions_graph.get("event_nodes", []),
        "relations": relations,
        "neighbors": neighbors,
        "context_doc": context_doc,
    }


def _next_snapshot_dir(base_dir: Path, prefix: str) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    candidate = base_dir / f"{prefix}_{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = base_dir / f"{prefix}_{timestamp}_{suffix:02d}"
        suffix += 1
    return candidate


def _object_markdown(
    *,
    node: dict[str, Any],
    relations: list[dict[str, Any]],
    versions: list[dict[str, Any]],
    context_doc: dict[str, Any] | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# {node.get('label')}")
    lines.append("")
    lines.append("## Object")
    lines.append(f"- id: {node.get('id')}")
    lines.append(f"- type: {node.get('type')}")
    lines.append(f"- typed_id: {node.get('typed_id')}")
    lines.append(f"- review_state: {node.get('review_state')}")
    lines.append(f"- version_count: {node.get('version_count')}")
    lines.append(f"- head_version_id: {node.get('head_version_id')}")
    lines.append(f"- head_event_id: {node.get('head_event_id')}")
    lines.append("")
    lines.append("## Head Snapshot")
    snapshot = node.get("head_snapshot") if isinstance(node.get("head_snapshot"), dict) else {}
    if snapshot:
        for key in sorted(snapshot.keys()):
            lines.append(f"- {key}: {snapshot.get(key)}")
    else:
        lines.append("- (no head snapshot)")
    lines.append("")
    lines.append("## Relations")
    if relations:
        for edge in relations:
            if edge.get("source") == node.get("id"):
                lines.append(f"- out/{edge.get('relation')}: {edge.get('target')}")
            else:
                lines.append(f"- in/{edge.get('relation')}: {edge.get('source')}")
    else:
        lines.append("- (no linked relations)")
    lines.append("")
    lines.append("## Recent Versions")
    if versions:
        for version in versions:
            lines.append(
                "- v{version_num} ({version_id}) event={event_id} created_at={created_at}".format(
                    version_num=version.get("version_num"),
                    version_id=version.get("version_id"),
                    event_id=version.get("event_id"),
                    created_at=version.get("created_at"),
                )
            )
    else:
        lines.append("- (no versions)")
    lines.append("")
    lines.append("## Context")
    if context_doc and context_doc.get("markdown"):
        lines.append(context_doc["markdown"])
    else:
        lines.append("- (no context document)")
    return "\n".join(lines).strip() + "\n"


def export_graph_markdown_snapshot(
    *,
    output_dir: str | None = None,
    limit: int = 500,
    include_context_docs: bool = True,
) -> dict[str, Any]:
    bounded_limit = _clamp_limit(limit, default=500, minimum=1, maximum=10000)
    graph_payload = build_object_graph(limit=bounded_limit, include_versions=False)
    nodes = list(graph_payload.get("nodes") or [])
    edges = list(graph_payload.get("edges") or [])
    base_dir = Path(output_dir).expanduser() if output_dir else (DATA_DIR / "exports")
    base_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = _next_snapshot_dir(base_dir.resolve(), "graph_snapshot")
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    objects_dir = snapshot_dir / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    object_paths: dict[str, Path] = {}
    files_written: list[str] = []
    for node in nodes:
        object_type = _slugify(str(node.get("type") or "object"))
        type_dir = objects_dir / object_type
        type_dir.mkdir(parents=True, exist_ok=True)
        id_part = str(node.get("typed_id")) if node.get("typed_id") is not None else str(node.get("id"))
        base_name = f"{_slugify(id_part)}-{_slugify(str(node.get('label') or 'object'))}"
        file_name = f"{base_name[:90]}.md"
        target = type_dir / file_name
        suffix = 1
        while target.exists():
            target = type_dir / f"{base_name[:80]}-{suffix:02d}.md"
            suffix += 1
        node_id = str(node.get("id"))
        relations = [
            edge
            for edge in edges
            if str(edge.get("source")) == node_id or str(edge.get("target")) == node_id
        ]
        versions = list_object_versions(object_id=node_id, limit=10)
        context_doc = None
        if include_context_docs:
            context_doc = get_object_context_doc(node_id) or build_object_context_doc(node_id)
        target.write_text(
            _object_markdown(node=node, relations=relations, versions=versions, context_doc=context_doc),
            encoding="utf-8",
        )
        object_paths[node_id] = target
        files_written.append(str(target))

    graph_json_path = snapshot_dir / "graph.json"
    graph_json_path.write_text(json.dumps(graph_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    files_written.append(str(graph_json_path))

    index_lines: list[str] = []
    index_lines.append("# Noctem Graph Snapshot")
    index_lines.append("")
    index_lines.append(f"- generated_at: {datetime.utcnow().isoformat()}Z")
    index_lines.append(f"- object_count: {len(nodes)}")
    index_lines.append(f"- edge_count: {len(edges)}")
    index_lines.append("")
    index_lines.append("## Objects")
    for node in nodes:
        node_id = str(node.get("id"))
        path = object_paths.get(node_id)
        if path is None:
            continue
        relative_path = path.relative_to(snapshot_dir).as_posix()
        index_lines.append(
            f"- [{node_id} — {node.get('label')}]({relative_path}) "
            f"(type={node.get('type')}, versions={node.get('version_count')})"
        )
    index_lines.append("")
    index_lines.append("## Graph JSON")
    index_lines.append(f"- [graph.json]({graph_json_path.relative_to(snapshot_dir).as_posix()})")
    index_lines.append("")
    index_path = snapshot_dir / "index.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")
    files_written.append(str(index_path))

    return {
        "snapshot_dir": str(snapshot_dir),
        "index_file": str(index_path),
        "graph_json_file": str(graph_json_path),
        "object_count": len(nodes),
        "edge_count": len(edges),
        "file_count": len(files_written),
        "files": files_written,
    }
