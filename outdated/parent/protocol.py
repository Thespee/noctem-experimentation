#!/usr/bin/env python3
"""
Parent-child communication protocol.
Defines message formats for remote supervision.
"""

import json
import secrets
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime


class ParentCommand(Enum):
    """Commands that parent can send to child."""
    STATUS = "status"          # Get current status
    HISTORY = "history"        # Get task history
    HEALTH = "health"          # Get health metrics
    LOGS = "logs"              # Get recent logs
    REPORT = "report"          # Generate babysitting report
    IMPROVE = "improve"        # Request improvement analysis
    APPLY = "apply"            # Apply improvement patch
    APPROVE = "approve"        # Approve an improvement
    REJECT = "reject"          # Reject an improvement


@dataclass
class ParentRequest:
    """Request from parent to child."""
    command: ParentCommand
    params: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: secrets.token_hex(4))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_signal_message(self) -> str:
        """Encode as Signal message."""
        params_json = json.dumps(self.params) if self.params else "{}"
        return f"/parent {self.command.value} {params_json}"
    
    @classmethod
    def from_signal_message(cls, message: str) -> Optional['ParentRequest']:
        """Parse from Signal message."""
        message = message.strip()
        if not message.startswith("/parent"):
            return None
        
        parts = message.split(maxsplit=2)
        if len(parts) < 2:
            return None
        
        try:
            command = ParentCommand(parts[1].lower())
            params = json.loads(parts[2]) if len(parts) > 2 else {}
            return cls(command=command, params=params)
        except (ValueError, json.JSONDecodeError):
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "command": self.command.value,
            "params": self.params,
            "request_id": self.request_id,
            "timestamp": self.timestamp
        }


@dataclass
class ParentResponse:
    """Response from child to parent."""
    request_id: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_signal_message(self) -> str:
        """Encode as Signal message (formatted for readability)."""
        if self.error:
            return f"❌ Error: {self.error}"
        
        return self._format_data()
    
    def _format_data(self) -> str:
        """Format response data for Signal."""
        data = self.data
        
        if "status" in data:
            return self._format_status(data["status"])
        elif "history" in data:
            return self._format_history(data)
        elif "health" in data:
            return self._format_health(data["health"])
        elif "report" in data:
            return data["report"]
        elif "logs" in data:
            return self._format_logs(data["logs"])
        else:
            # Generic JSON output, truncated
            return json.dumps(data, indent=2)[:1500]
    
    def _format_status(self, status: Dict) -> str:
        """Format status response."""
        return (
            f"📊 Noctem Status\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"State: {status.get('state', 'unknown')}\n"
            f"Uptime: {status.get('uptime', 'unknown')}\n"
            f"Active tasks: {status.get('active_tasks', 0)}\n"
            f"Queue: {status.get('queue_size', 0)}\n"
            f"Last activity: {status.get('last_activity', 'never')}"
        )
    
    def _format_history(self, data: Dict) -> str:
        """Format history response."""
        history = data.get("history", [])
        stats = data.get("stats", {})
        
        lines = [
            "📜 Recent History",
            "━━━━━━━━━━━━━━━━",
            f"Total: {stats.get('total', 0)} | Success: {stats.get('success_rate', 'N/A')}"
        ]
        
        for item in history[:10]:
            emoji = "✅" if item.get("success") else "❌"
            task = item.get("input", "unknown")[:35]
            lines.append(f"{emoji} {task}")
        
        if len(history) > 10:
            lines.append(f"  ...and {len(history) - 10} more")
        
        return "\n".join(lines)
    
    def _format_health(self, health: Dict) -> str:
        """Format health response."""
        return (
            f"💚 Health Check\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Ollama: {'✅' if health.get('ollama') else '❌'}\n"
            f"Signal: {'✅' if health.get('signal') else '❌'}\n"
            f"Disk: {health.get('disk_usage', '?')}%\n"
            f"Memory: {health.get('memory_usage', '?')}%\n"
            f"CPU: {health.get('cpu_usage', '?')}%"
        )
    
    def _format_logs(self, logs: list) -> str:
        """Format logs response."""
        if not logs:
            return "📋 No recent logs"
        
        lines = ["📋 Recent Logs", "━━━━━━━━━━━━━━━━"]
        for log in logs[-20:]:  # Last 20 lines
            lines.append(log[:80])  # Truncate long lines
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParentResponse':
        """Create from dictionary."""
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            data=data.get("data", {}),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
