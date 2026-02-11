#!/usr/bin/env python3
"""
Noctem Skill Framework
Base classes and utilities for building skills.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import time


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    output: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error
        }


@dataclass
class SkillContext:
    """Context passed to skills during execution."""
    task_id: Optional[int] = None
    task_input: Optional[str] = None
    previous_output: Optional[str] = None
    previous_data: Optional[Dict] = None
    memory: List[Dict] = field(default_factory=list)
    config: Dict = field(default_factory=dict)


class Skill(ABC):
    """Base class for all Noctem skills."""
    
    # Subclasses must define these
    name: str = "base"
    description: str = "Base skill - do not use directly"
    parameters: Dict[str, str] = {}
    
    def __init__(self):
        """Initialize the skill."""
        pass
    
    @abstractmethod
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        """
        Execute the skill.
        
        Args:
            params: Parameters for this skill invocation
            context: Execution context (task info, previous outputs, etc.)
        
        Returns:
            SkillResult with success status, output, and optional data
        """
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """
        Validate parameters. Returns error message if invalid, None if valid.
        Override in subclass for custom validation.
        """
        # Check required parameters (those without "optional" in description)
        for param_name, param_desc in self.parameters.items():
            if "optional" not in param_desc.lower() and param_name not in params:
                return f"Missing required parameter: {param_name}"
        return None
    
    def get_manifest(self) -> Dict:
        """Get skill manifest for LLM planning."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        """
        Execute skill with timing and validation.
        This is the method called by the skill runner.
        """
        # Validate parameters
        error = self.validate_params(params)
        if error:
            return SkillResult(success=False, output="", error=error)
        
        # Execute with timing
        start = time.time()
        try:
            result = self.run(params, context)
        except Exception as e:
            result = SkillResult(
                success=False,
                output="",
                error=f"Skill execution failed: {str(e)}"
            )
        
        duration_ms = int((time.time() - start) * 1000)
        
        # Log execution if we have a task_id
        if context.task_id:
            try:
                from state import log_skill_execution
                log_skill_execution(
                    task_id=context.task_id,
                    skill_name=self.name,
                    input_data=str(params),
                    output=result.output[:1000] if result.output else "",
                    success=result.success,
                    duration_ms=duration_ms
                )
            except ImportError:
                pass  # state module not available
        
        return result


# Global skill registry
_registry: Dict[str, Skill] = {}


def register_skill(skill_class: type) -> type:
    """Decorator to register a skill class."""
    instance = skill_class()
    _registry[instance.name] = instance
    return skill_class


def get_skill(name: str) -> Optional[Skill]:
    """Get a skill by name."""
    return _registry.get(name)


def get_all_skills() -> Dict[str, Skill]:
    """Get all registered skills."""
    return _registry.copy()


def get_skill_manifest() -> Dict[str, Dict]:
    """Get manifest of all skills for LLM planning."""
    return {
        name: skill.get_manifest() 
        for name, skill in _registry.items()
    }
