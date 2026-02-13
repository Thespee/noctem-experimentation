#!/usr/bin/env python3
"""
Noctem Task Status Skill
Report on current task queue status.
"""

import sys
from pathlib import Path
from typing import Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .base import Skill, SkillResult, SkillContext, register_skill


@register_skill
class TaskStatusSkill(Skill):
    """Report current task queue status."""
    
    name = "task_status"
    description = "Get the current status of the task queue including running, pending, and recent tasks."
    parameters = {
        "include_recent": "bool (optional, default true) - include recently completed tasks",
        "recent_limit": "int (optional, default 5) - number of recent tasks to show"
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        include_recent = params.get("include_recent", True)
        recent_limit = params.get("recent_limit", 5)
        
        try:
            from state import get_running_tasks, get_pending_tasks, get_recent_tasks
            
            running = get_running_tasks()
            pending = get_pending_tasks()
            recent = get_recent_tasks(recent_limit) if include_recent else []
            
            # Build status report
            lines = []
            
            # Running tasks
            if running:
                lines.append("=== RUNNING ===")
                for task in running:
                    lines.append(f"  [{task['id']}] {task['input'][:50]}...")
            else:
                lines.append("=== RUNNING ===")
                lines.append("  (none)")
            
            # Pending tasks
            lines.append("")
            lines.append(f"=== PENDING ({len(pending)}) ===")
            if pending:
                for task in pending[:10]:  # Show max 10
                    lines.append(f"  [{task['id']}] p{task['priority']} \"{task['input'][:40]}\"")
                if len(pending) > 10:
                    lines.append(f"  ... and {len(pending) - 10} more")
            else:
                lines.append("  (none)")
            
            # Recent tasks
            if include_recent and recent:
                lines.append("")
                lines.append("=== RECENT ===")
                for task in recent:
                    status_icon = "✓" if task['status'] == 'done' else "✗"
                    result_preview = ""
                    if task.get('result'):
                        result_preview = f" → {task['result'][:30]}..."
                    lines.append(f"  [{task['id']}] {status_icon} \"{task['input'][:30]}\"{result_preview}")
            
            output = '\n'.join(lines)
            
            return SkillResult(
                success=True,
                output=output,
                data={
                    "running_count": len(running),
                    "pending_count": len(pending),
                    "recent_count": len(recent)
                }
            )
            
        except ImportError as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Could not import state module: {e}"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Failed to get task status: {str(e)}"
            )


if __name__ == "__main__":
    # Test
    skill = TaskStatusSkill()
    ctx = SkillContext()
    result = skill.execute({}, ctx)
    print(result.output)
