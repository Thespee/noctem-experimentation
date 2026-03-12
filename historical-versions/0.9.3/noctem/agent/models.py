"""Data models for v0.9.3 agentic workflow tables."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
import json


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


@dataclass
class AgentWorkflow:
    id: int
    workflow_type: str
    thread_id: str
    status: str
    current_node: Optional[str]
    source: Optional[str]
    input_text: Optional[str]
    output_text: Optional[str]
    error_message: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]

    @classmethod
    def from_row(cls, row) -> "AgentWorkflow":
        return cls(
            id=row["id"],
            workflow_type=row["workflow_type"],
            thread_id=row["thread_id"],
            status=row["status"],
            current_node=row["current_node"],
            source=row["source"] if "source" in row.keys() else None,
            input_text=row["input_text"] if "input_text" in row.keys() else None,
            output_text=row["output_text"] if "output_text" in row.keys() else None,
            error_message=row["error_message"] if "error_message" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"] if "updated_at" in row.keys() else None,
            completed_at=row["completed_at"] if "completed_at" in row.keys() else None,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_type": self.workflow_type,
            "thread_id": self.thread_id,
            "status": self.status,
            "current_node": self.current_node,
            "source": self.source,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


@dataclass
class AgentInterrupt:
    id: int
    workflow_id: int
    interrupt_type: str
    question: str
    options: Any
    context: Any
    created_at: Optional[datetime]
    resolved_at: Optional[datetime]
    resolution: Optional[str]

    @classmethod
    def from_row(cls, row) -> "AgentInterrupt":
        return cls(
            id=row["id"],
            workflow_id=row["workflow_id"],
            interrupt_type=row["interrupt_type"],
            question=row["question"],
            options=_parse_json(row["options"]),
            context=_parse_json(row["context"]),
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            resolution=row["resolution"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "interrupt_type": self.interrupt_type,
            "question": self.question,
            "options": self.options,
            "context": self.context,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
        }


@dataclass
class AgentAction:
    id: int
    workflow_id: int
    action_type: str
    input_data: Any
    output_data: Any
    decision_reasoning: Optional[str]
    created_at: Optional[datetime]

    @classmethod
    def from_row(cls, row) -> "AgentAction":
        return cls(
            id=row["id"],
            workflow_id=row["workflow_id"],
            action_type=row["action_type"],
            input_data=_parse_json(row["input_data"]),
            output_data=_parse_json(row["output_data"]),
            decision_reasoning=row["decision_reasoning"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "action_type": self.action_type,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "decision_reasoning": self.decision_reasoning,
            "created_at": self.created_at,
        }
