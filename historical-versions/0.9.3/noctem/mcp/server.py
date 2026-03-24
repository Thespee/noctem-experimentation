"""Noctem in-process MCP server (Phase 1 skeleton)."""
from __future__ import annotations

import copy
import logging
import time
import uuid
from typing import Any

from .contracts import (
    DEFAULT_MCP_CAPABILITIES,
    MCP_SCHEMA_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    MCPAuditEnvelope,
    MCPError,
    MCPRequestContext,
    MCPToolCallEnvelope,
    utc_now_iso,
)
from .registry import MCPToolRegistry
from .tools import register_read_only_tools
logger = logging.getLogger(__name__)

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}
_SENSITIVE_FIELD_HINTS = ("token", "secret", "password", "authorization", "auth")

def _redact_for_debug(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            lowered = str(key).strip().lower()
            if any(hint in lowered for hint in _SENSITIVE_FIELD_HINTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_for_debug(child)
        return redacted
    if isinstance(value, list):
        return [_redact_for_debug(item) for item in value]
    return value


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py_type = _TYPE_MAP.get(expected_type)
    if py_type is None:
        return True
    return isinstance(value, py_type)


def _validate_object_schema(payload: Any, schema: dict[str, Any]) -> list[str]:
    if not schema:
        return []
    if schema.get("type") != "object":
        return []
    if not isinstance(payload, dict):
        return ["arguments must be a JSON object"]

    errors: list[str] = []
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    additional_properties = schema.get("additionalProperties", True)

    for key in required:
        if key not in payload:
            errors.append(f"missing required field: {key}")

    if additional_properties is False:
        for key in payload.keys():
            if key not in properties:
                errors.append(f"unknown field: {key}")

    for key, value in payload.items():
        prop_schema = properties.get(key)
        if not prop_schema:
            continue
        expected = prop_schema.get("type")
        if expected is None:
            continue
        if isinstance(expected, list):
            if not any(_matches_type(value, option) for option in expected):
                errors.append(f"field {key} has invalid type")
        elif not _matches_type(value, expected):
            errors.append(f"field {key} has invalid type")
        if "enum" in prop_schema and value not in prop_schema["enum"]:
            errors.append(f"field {key} must be one of {prop_schema['enum']}")

    return errors


class NoctemMCPServer:
    """Single-process MCP server wrapper with strict tool contracts."""

    def __init__(self) -> None:
        self.registry = MCPToolRegistry()
        self.capabilities = copy.deepcopy(DEFAULT_MCP_CAPABILITIES)
        self.schema_version = MCP_SCHEMA_VERSION
        self.server_name = MCP_SERVER_NAME
        self.server_version = MCP_SERVER_VERSION
        register_read_only_tools(self.registry)

    def _normalize_context(self, context: dict[str, Any] | MCPRequestContext | None) -> MCPRequestContext:
        if isinstance(context, MCPRequestContext):
            normalized = context
        elif isinstance(context, dict):
            normalized = MCPRequestContext(
                source=str(context.get("source") or "unknown"),
                thread_id=context.get("thread_id"),
                workflow_id=context.get("workflow_id"),
                correlation_id=context.get("correlation_id"),
            )
        else:
            normalized = MCPRequestContext()

        if not normalized.correlation_id:
            normalized.correlation_id = f"mcp-{uuid.uuid4().hex[:12]}"
        return normalized

    def _audit(
        self,
        *,
        tool_name: str,
        context: MCPRequestContext,
        read_only: bool,
        started_at: str,
        started_perf: float,
    ) -> MCPAuditEnvelope:
        completed_at = utc_now_iso()
        elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
        return MCPAuditEnvelope(
            event="mcp.tool_call",
            tool_name=tool_name,
            source=context.source,
            read_only=read_only,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=elapsed_ms,
            thread_id=context.thread_id,
            workflow_id=context.workflow_id,
        )

    def _error_response(
        self,
        *,
        tool_name: str,
        context: MCPRequestContext,
        error: MCPError,
        read_only: bool,
        started_at: str,
        started_perf: float,
    ) -> dict[str, Any]:
        envelope = MCPToolCallEnvelope(
            tool_name=tool_name,
            correlation_id=context.correlation_id or f"mcp-{uuid.uuid4().hex[:12]}",
            ok=False,
            result=None,
            error=error,
            audit=self._audit(
                tool_name=tool_name,
                context=context,
                read_only=read_only,
                started_at=started_at,
                started_perf=started_perf,
            ),
        )
        return envelope.to_dict()

    def initialize(self, context: dict[str, Any] | MCPRequestContext | None = None) -> dict[str, Any]:
        normalized = self._normalize_context(context)
        started_at = utc_now_iso()
        started_perf = time.perf_counter()
        envelope = MCPToolCallEnvelope(
            tool_name="initialize",
            correlation_id=normalized.correlation_id,
            ok=True,
            result={
                "schema_version": self.schema_version,
                "server_name": self.server_name,
                "server_version": self.server_version,
                "capabilities": self.capabilities,
            },
            error=None,
            audit=self._audit(
                tool_name="initialize",
                context=normalized,
                read_only=True,
                started_at=started_at,
                started_perf=started_perf,
            ),
        )
        return envelope.to_dict()

    def tools_list(self, context: dict[str, Any] | MCPRequestContext | None = None) -> dict[str, Any]:
        normalized = self._normalize_context(context)
        started_at = utc_now_iso()
        started_perf = time.perf_counter()
        definitions = self.registry.list_definitions()
        envelope = MCPToolCallEnvelope(
            tool_name="tools/list",
            correlation_id=normalized.correlation_id,
            ok=True,
            result={
                "tools": [tool.to_dict() for tool in definitions],
                "tool_count": len(definitions),
                "capabilities": self.capabilities,
                "schema_version": self.schema_version,
            },
            error=None,
            audit=self._audit(
                tool_name="tools/list",
                context=normalized,
                read_only=True,
                started_at=started_at,
                started_perf=started_perf,
            ),
        )
        return envelope.to_dict()

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        *,
        context: dict[str, Any] | MCPRequestContext | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_context(context)
        started_at = utc_now_iso()
        started_perf = time.perf_counter()

        tool = self.registry.get_tool(tool_name)
        if tool is None:
            return self._error_response(
                tool_name=tool_name,
                context=normalized,
                error=MCPError(code="tool_not_found", message=f"Unknown tool: {tool_name}"),
                read_only=True,
                started_at=started_at,
                started_perf=started_perf,
            )

        payload = arguments or {}
        logger.debug(
            "[MCP_DEBUG] call start tool=%s corr=%s source=%s args=%s",
            tool_name,
            normalized.correlation_id,
            normalized.source,
            _redact_for_debug(payload),
        )
        schema_errors = _validate_object_schema(payload, tool.definition.input_schema)
        if schema_errors:
            logger.debug(
                "[MCP_DEBUG] call invalid_arguments tool=%s corr=%s errors=%s",
                tool_name,
                normalized.correlation_id,
                schema_errors,
            )
            return self._error_response(
                tool_name=tool_name,
                context=normalized,
                error=MCPError(
                    code="invalid_arguments",
                    message="Tool arguments failed schema validation",
                    details={"errors": schema_errors},
                ),
                read_only=tool.definition.read_only,
                started_at=started_at,
                started_perf=started_perf,
            )

        try:
            result = tool.handler(payload, normalized)
            if not isinstance(result, dict):
                raise TypeError("tool result must be a JSON object")
            output_errors = _validate_object_schema(result, tool.definition.output_schema)
            if output_errors:
                return self._error_response(
                    tool_name=tool_name,
                    context=normalized,
                    error=MCPError(
                        code="invalid_tool_output",
                        message="Tool returned payload that does not match output schema",
                        details={"errors": output_errors},
                    ),
                    read_only=tool.definition.read_only,
                    started_at=started_at,
                    started_perf=started_perf,
                )
            envelope = MCPToolCallEnvelope(
                tool_name=tool_name,
                correlation_id=normalized.correlation_id,
                ok=True,
                result=result,
                error=None,
                audit=self._audit(
                    tool_name=tool_name,
                    context=normalized,
                    read_only=tool.definition.read_only,
                    started_at=started_at,
                    started_perf=started_perf,
                ),
            )
            logger.debug(
                "[MCP_DEBUG] call ok tool=%s corr=%s read_only=%s result_keys=%s",
                tool_name,
                normalized.correlation_id,
                tool.definition.read_only,
                sorted(result.keys()),
            )
            return envelope.to_dict()
        except Exception as exc:
            logger.debug(
                "[MCP_DEBUG] call failed tool=%s corr=%s error=%s",
                tool_name,
                normalized.correlation_id,
                exc,
            )
            return self._error_response(
                tool_name=tool_name,
                context=normalized,
                error=MCPError(
                    code="tool_execution_error",
                    message=f"Tool execution failed: {exc}",
                ),
                read_only=tool.definition.read_only,
                started_at=started_at,
                started_perf=started_perf,
            )


_SERVER_INSTANCE: NoctemMCPServer | None = None


def get_mcp_server() -> NoctemMCPServer:
    global _SERVER_INSTANCE
    if _SERVER_INSTANCE is None:
        _SERVER_INSTANCE = NoctemMCPServer()
    return _SERVER_INSTANCE
