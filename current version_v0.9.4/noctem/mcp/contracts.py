"""Contracts and shared types for Noctem MCP Phase 4."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

MCP_SCHEMA_VERSION = "2026-03-04"
MCP_TOOL_CONTRACT_VERSION = "1.1.0"
MCP_SERVER_NAME = "noctem-task-mcp"
MCP_SERVER_VERSION = "0.9.3-phase4"

DEFAULT_MCP_CAPABILITIES: dict[str, Any] = {
    "tools": {
        "listChanged": True,
        "strictSchemas": True,
    },
    "safety": {
        "readOnlyPhase": False,
        "previewCommitRequiredForWrites": True,
    },
    "audit": {
        "correlationIds": True,
        "envelopeVersion": "1.0",
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


JsonObject = dict[str, Any]
MCPToolHandler = Callable[[JsonObject, "MCPRequestContext"], JsonObject]


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    input_schema: JsonObject
    output_schema: JsonObject
    read_only: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "read_only": self.read_only,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class MCPTool:
    definition: MCPToolDefinition
    handler: MCPToolHandler


@dataclass
class MCPRequestContext:
    source: str = "unknown"
    thread_id: str | None = None
    workflow_id: int | None = None
    correlation_id: str | None = None

    def to_dict(self) -> JsonObject:
        data: JsonObject = {"source": self.source}
        if self.thread_id:
            data["thread_id"] = self.thread_id
        if self.workflow_id is not None:
            data["workflow_id"] = self.workflow_id
        if self.correlation_id:
            data["correlation_id"] = self.correlation_id
        return data


@dataclass
class MCPError:
    code: str
    message: str
    details: JsonObject | None = None

    def to_dict(self) -> JsonObject:
        payload: JsonObject = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class MCPAuditEnvelope:
    event: str
    tool_name: str
    source: str
    read_only: bool
    started_at: str
    completed_at: str
    duration_ms: int
    thread_id: str | None = None
    workflow_id: int | None = None

    def to_dict(self) -> JsonObject:
        out: JsonObject = {
            "event": self.event,
            "tool_name": self.tool_name,
            "source": self.source,
            "read_only": self.read_only,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }
        if self.thread_id:
            out["thread_id"] = self.thread_id
        if self.workflow_id is not None:
            out["workflow_id"] = self.workflow_id
        return out


@dataclass
class MCPToolCallEnvelope:
    tool_name: str
    correlation_id: str
    ok: bool
    result: JsonObject | None
    error: MCPError | None
    audit: MCPAuditEnvelope
    schema_version: str = MCP_SCHEMA_VERSION
    server: str = MCP_SERVER_NAME
    server_version: str = MCP_SERVER_VERSION

    def to_dict(self) -> JsonObject:
        payload: JsonObject = {
            "schema_version": self.schema_version,
            "server": self.server,
            "server_version": self.server_version,
            "tool_name": self.tool_name,
            "correlation_id": self.correlation_id,
            "ok": self.ok,
            "result": self.result,
            "audit": self.audit.to_dict(),
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload
