#!/usr/bin/env python3
"""
Improvement workflow - Generate and manage code improvements.
Tracks suggested improvements and their approval/rejection status.
"""

import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime


@dataclass
class Improvement:
    """A suggested improvement to the Noctem codebase."""
    id: int
    title: str
    description: str
    priority: int  # 1-5, 1 is highest
    patch: str  # Unified diff format
    status: str = "pending"  # pending, approved, applied, rejected
    source: str = "parent"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "patch": self.patch,
            "status": self.status,
            "source": self.source,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Improvement':
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            priority=data.get("priority", 3),
            patch=data.get("patch", ""),
            status=data.get("status", "pending"),
            source=data.get("source", "parent"),
            created_at=data.get("created_at", datetime.now().isoformat())
        )
    
    def format_for_signal(self) -> str:
        """Format improvement for Signal message."""
        priority_stars = "⭐" * self.priority
        return f"""🔧 Improvement #{self.id}
Priority: {priority_stars}
Title: {self.title}

{self.description[:500]}

Reply:
  /parent approve {{"id": {self.id}}} - Approve this change
  /parent reject {{"id": {self.id}}} - Reject this change"""


class ImprovementManager:
    """Manages improvements via the state database."""
    
    def __init__(self):
        pass  # Uses state module for persistence
    
    def create(self, title: str, description: str, priority: int = 3,
               patch: str = "", source: str = "parent") -> int:
        """Create a new improvement suggestion."""
        import state
        return state.create_improvement(
            title=title,
            description=description,
            priority=priority,
            patch=patch,
            source=source
        )
    
    def get(self, imp_id: int) -> Optional[Improvement]:
        """Get an improvement by ID."""
        import state
        data = state.get_improvement(imp_id)
        if data:
            return Improvement.from_dict(data)
        return None
    
    def get_pending(self) -> List[Improvement]:
        """Get all pending improvements."""
        import state
        data = state.get_pending_improvements()
        return [Improvement.from_dict(d) for d in data]
    
    def approve(self, imp_id: int) -> bool:
        """Approve an improvement."""
        import state
        return state.update_improvement_status(imp_id, "approved")
    
    def reject(self, imp_id: int) -> bool:
        """Reject an improvement."""
        import state
        return state.update_improvement_status(imp_id, "rejected")
    
    def apply(self, imp_id: int, working_dir: Path) -> Tuple[bool, str]:
        """Apply an approved improvement patch."""
        imp = self.get(imp_id)
        if imp is None:
            return False, "Improvement not found"
        if imp.status != "approved":
            return False, f"Improvement not approved (status: {imp.status})"
        if not imp.patch:
            return False, "No patch content"
        
        # Write patch to temp file
        patch_file = Path(f"/tmp/noctem_patch_{imp_id}.diff")
        patch_file.write_text(imp.patch)
        
        try:
            # Dry run first
            result = subprocess.run(
                ["patch", "--dry-run", "-p1", "-d", str(working_dir), "-i", str(patch_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"Patch would fail:\n{result.stderr}"
            
            # Apply for real
            result = subprocess.run(
                ["patch", "-p1", "-d", str(working_dir), "-i", str(patch_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                import state
                state.update_improvement_status(imp_id, "applied")
                return True, f"Patch applied successfully:\n{result.stdout}"
            else:
                return False, f"Patch failed:\n{result.stderr}"
                
        finally:
            patch_file.unlink(missing_ok=True)


def analyze_problems(problems: List[Dict]) -> List[Dict]:
    """
    Analyze a list of problems and suggest improvements.
    This is a simple pattern-matching approach; the real analysis
    should be done by an LLM (via the parent improve command).
    """
    suggestions = []
    
    # Group problems by type
    task_failures = [p for p in problems if p.get("type") == "task_failure"]
    skill_failures = [p for p in problems if p.get("type") == "skill_failure"]
    
    # Look for patterns in task failures
    if len(task_failures) >= 3:
        # Check for common patterns
        inputs = [f.get("input", "") for f in task_failures]
        
        # Check for timeout patterns
        timeout_count = sum(1 for f in task_failures if "timeout" in str(f.get("result", "")).lower())
        if timeout_count >= 2:
            suggestions.append({
                "type": "timeout_pattern",
                "title": "Multiple timeout errors detected",
                "description": f"Found {timeout_count} timeout-related failures. Consider increasing timeouts or optimizing slow operations.",
                "priority": 2
            })
        
        # Check for connection errors
        conn_count = sum(1 for f in task_failures if "connect" in str(f.get("result", "")).lower())
        if conn_count >= 2:
            suggestions.append({
                "type": "connection_pattern",
                "title": "Multiple connection errors",
                "description": f"Found {conn_count} connection-related failures. Check network connectivity and retry logic.",
                "priority": 2
            })
    
    # Look for skill-specific issues
    skill_counts = {}
    for f in skill_failures:
        skill = f.get("skill", "unknown")
        skill_counts[skill] = skill_counts.get(skill, 0) + 1
    
    for skill, count in skill_counts.items():
        if count >= 2:
            suggestions.append({
                "type": "skill_failure_pattern",
                "title": f"Repeated failures in {skill} skill",
                "description": f"The {skill} skill has failed {count} times. Review implementation.",
                "priority": 2
            })
    
    return suggestions


def generate_training_pair(problem: Dict, solution: Dict) -> Dict:
    """
    Generate a problem->solution training pair.
    These are stored for future fine-tuning.
    """
    return {
        "problem": {
            "type": problem.get("type"),
            "context": problem.get("input") or problem.get("context"),
            "error": problem.get("result") or problem.get("output")
        },
        "solution": {
            "type": solution.get("type"),
            "description": solution.get("description"),
            "action": solution.get("action") or solution.get("patch")
        },
        "timestamp": datetime.now().isoformat()
    }
