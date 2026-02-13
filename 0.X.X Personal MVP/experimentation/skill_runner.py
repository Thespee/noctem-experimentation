#!/usr/bin/env python3
"""
Noctem Skill Runner
Executes skills with proper context and chaining.
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path

# Ensure we can import from the noctem package
import sys
sys.path.insert(0, str(Path(__file__).parent))

from skills import get_skill, get_all_skills, get_skill_manifest, SkillContext, SkillResult
import state


def load_config() -> Dict:
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "data" / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def run_skill(skill_name: str, params: Dict[str, Any], 
              task_id: Optional[int] = None,
              previous_output: Optional[str] = None,
              previous_data: Optional[Dict] = None) -> SkillResult:
    """
    Run a single skill with context.
    
    Args:
        skill_name: Name of the skill to run
        params: Parameters for the skill
        task_id: Optional task ID for logging
        previous_output: Output from previous skill in chain
        previous_data: Data from previous skill in chain
    
    Returns:
        SkillResult from the skill execution
    """
    skill = get_skill(skill_name)
    
    if skill is None:
        return SkillResult(
            success=False,
            output="",
            error=f"Unknown skill: {skill_name}"
        )
    
    # Build context
    config = load_config()
    memory = state.get_recent_memory(10) if task_id else []
    
    task_input = None
    if task_id:
        task = state.get_task(task_id)
        if task:
            task_input = task.get("input")
    
    context = SkillContext(
        task_id=task_id,
        task_input=task_input,
        previous_output=previous_output,
        previous_data=previous_data,
        memory=memory,
        config=config
    )
    
    # Execute skill
    return skill.execute(params, context)


def run_skill_chain(plan: List[Dict], task_id: Optional[int] = None) -> SkillResult:
    """
    Run a chain of skills, passing outputs between them.
    
    Args:
        plan: List of {"name": "skill_name", "params": {...}} dicts
        task_id: Optional task ID for logging
    
    Returns:
        Final SkillResult from the chain
    """
    if not plan:
        return SkillResult(
            success=False,
            output="",
            error="Empty skill chain"
        )
    
    previous_output = None
    previous_data = None
    last_result = None
    
    for i, step in enumerate(plan):
        skill_name = step.get("name")
        params = step.get("params", {})
        
        if not skill_name:
            return SkillResult(
                success=False,
                output="",
                error=f"Step {i} missing skill name"
            )
        
        # Run the skill
        result = run_skill(
            skill_name=skill_name,
            params=params,
            task_id=task_id,
            previous_output=previous_output,
            previous_data=previous_data
        )
        
        last_result = result
        
        # Stop chain on failure
        if not result.success:
            return result
        
        # Pass output to next skill
        previous_output = result.output
        previous_data = result.data
    
    return last_result


def list_skills() -> Dict[str, Dict]:
    """Get manifest of all available skills."""
    return get_skill_manifest()


if __name__ == "__main__":
    # Test skill runner
    print("Available skills:")
    for name, manifest in list_skills().items():
        print(f"  {name}: {manifest['description'][:50]}...")
    
    print("\nTesting shell skill:")
    result = run_skill("shell", {"command": "echo 'Hello from skill runner!'"})
    print(f"  Result: {result.output}")
    
    print("\nTesting skill chain:")
    chain = [
        {"name": "shell", "params": {"command": "date"}},
        {"name": "shell", "params": {"command": "hostname"}},
    ]
    result = run_skill_chain(chain)
    print(f"  Final output: {result.output}")
