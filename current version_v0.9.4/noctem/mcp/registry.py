"""Tool registry for Noctem MCP server."""
from __future__ import annotations

from .contracts import MCPTool, MCPToolDefinition


class MCPToolRegistry:
    """Simple in-process MCP tool registry."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        name = (tool.definition.name or "").strip()
        if not name:
            raise ValueError("Tool name is required")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def get_tool(self, name: str) -> MCPTool | None:
        return self._tools.get((name or "").strip())

    def list_definitions(self) -> list[MCPToolDefinition]:
        return [
            self._tools[name].definition
            for name in sorted(self._tools.keys())
        ]
