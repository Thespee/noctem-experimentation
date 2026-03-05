"""
Prompt management service for Noctem v0.6.0 Final Polish.

Manages LLM prompt templates with versioning:
- Get/render prompts with variable substitution
- Update prompts (creates new version)
- View version history
- Rollback to previous versions
- Seed default prompts
"""
import re
import logging
from typing import Optional
from datetime import datetime

from ..db import get_db
from ..models import PromptTemplate, PromptVersion

logger = logging.getLogger(__name__)


# ============================================================================
# Default Prompts (seeded on first use)
# ============================================================================

DEFAULT_PROMPTS = {
    "task_analyzer_system": {
        "description": "System prompt for task analysis - suggests how computer/automation can help",
        "prompt_text": """You are a helpful assistant analyzing tasks. 
Your job is to suggest practical ways a computer or automation could help with each task.
Be specific, concise, and practical. Focus on things that are actually achievable with current technology.
Keep your response to 2-3 sentences maximum.""",
        "variables": [],
    },
    "task_analyzer_user": {
        "description": "User prompt template for task analysis",
        "prompt_text": """Task: {{name}}
Project: {{project}}
Due: {{due_date}}
Tags: {{tags}}

What could a computer or automation help with for this task?
Be specific and practical. Consider: reminders, research, templates, scheduling, notifications, data gathering, etc.""",
        "variables": ["name", "project", "due_date", "tags"],
    },
    "project_analyzer_system": {
        "description": "System prompt for project analysis - suggests next actions",
        "prompt_text": """You are a helpful assistant analyzing projects and their tasks.
Your job is to suggest the most important next action the person should take.
Be specific, concrete, and actionable. Focus on one clear next step.
Keep your response to 2-3 sentences maximum.""",
        "variables": [],
    },
    "project_analyzer_user": {
        "description": "User prompt template for project analysis",
        "prompt_text": """Project: {{name}}
Summary: {{summary}}
Status: {{status}}

Current Tasks:
{{task_list}}

What should the person do next to make progress on this project?
Suggest one specific, concrete action. Consider task priorities, dependencies, and what might be blocking progress.""",
        "variables": ["name", "summary", "status", "task_list"],
    },
}


# ============================================================================
# Core Functions
# ============================================================================

def get_prompt(name: str, version: Optional[int] = None) -> Optional[PromptVersion]:
    """
    Get a prompt template by name.
    
    Args:
        name: The prompt template name
        version: Specific version to get (default: current version)
    
    Returns:
        PromptVersion or None if not found
    """
    with get_db() as conn:
        # Get the template
        template_row = conn.execute(
            "SELECT * FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        
        if not template_row:
            # Try to seed defaults if this is a known prompt
            if name in DEFAULT_PROMPTS:
                seed_default_prompts()
                template_row = conn.execute(
                    "SELECT * FROM prompt_templates WHERE name = ?",
                    (name,)
                ).fetchone()
            
            if not template_row:
                return None
        
        template = PromptTemplate.from_row(template_row)
        
        # Get the requested version
        target_version = version if version is not None else template.current_version
        
        version_row = conn.execute(
            """SELECT * FROM prompt_versions 
               WHERE template_id = ? AND version = ?""",
            (template.id, target_version)
        ).fetchone()
        
        if version_row:
            return PromptVersion.from_row(version_row)
        
        return None


def render_prompt(name: str, variables: dict = None, version: Optional[int] = None) -> Optional[str]:
    """
    Get a prompt and render it with variable substitution.
    
    Variables use {{variable_name}} syntax.
    
    Args:
        name: The prompt template name
        variables: Dict of variable values to substitute
        version: Specific version to use (default: current)
    
    Returns:
        Rendered prompt string or None if not found
    """
    prompt_version = get_prompt(name, version)
    if not prompt_version:
        return None
    
    text = prompt_version.prompt_text
    
    if variables:
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            text = text.replace(placeholder, str(value) if value is not None else "")
    
    return text


def update_prompt(
    name: str,
    new_text: str,
    created_by: str = "user",
    description: Optional[str] = None,
) -> Optional[PromptVersion]:
    """
    Update a prompt template (creates a new version).
    
    Args:
        name: The prompt template name
        new_text: The new prompt text
        created_by: Who made this change ('user' or 'system')
        description: Optional new description for the template
    
    Returns:
        The new PromptVersion or None if template not found
    """
    with get_db() as conn:
        # Get existing template
        template_row = conn.execute(
            "SELECT * FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        
        if not template_row:
            logger.warning(f"Prompt template not found: {name}")
            return None
        
        template = PromptTemplate.from_row(template_row)
        new_version = template.current_version + 1
        
        # Extract variables from new text
        variables = extract_variables(new_text)
        
        # Create new version
        import json
        conn.execute(
            """INSERT INTO prompt_versions 
               (template_id, version, prompt_text, variables, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (template.id, new_version, new_text, json.dumps(variables), created_by)
        )
        
        # Update template's current version
        if description:
            conn.execute(
                """UPDATE prompt_templates 
                   SET current_version = ?, description = ?
                   WHERE id = ?""",
                (new_version, description, template.id)
            )
        else:
            conn.execute(
                """UPDATE prompt_templates 
                   SET current_version = ?
                   WHERE id = ?""",
                (new_version, template.id)
            )
        
        logger.info(f"Updated prompt '{name}' to version {new_version}")
    
    # Return the new version (after transaction committed)
    return get_prompt(name, new_version)


def get_prompt_history(name: str) -> list[PromptVersion]:
    """
    Get all versions of a prompt template.
    
    Args:
        name: The prompt template name
    
    Returns:
        List of PromptVersion objects, newest first
    """
    with get_db() as conn:
        template_row = conn.execute(
            "SELECT id FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        
        if not template_row:
            return []
        
        version_rows = conn.execute(
            """SELECT * FROM prompt_versions 
               WHERE template_id = ?
               ORDER BY version DESC""",
            (template_row["id"],)
        ).fetchall()
        
        return [PromptVersion.from_row(row) for row in version_rows]


def rollback_prompt(name: str, to_version: int) -> Optional[PromptVersion]:
    """
    Rollback a prompt to a previous version.
    
    This creates a NEW version with the old text (doesn't delete versions).
    
    Args:
        name: The prompt template name
        to_version: The version to rollback to
    
    Returns:
        The new PromptVersion (copy of old version) or None if failed
    """
    old_version = get_prompt(name, to_version)
    if not old_version:
        logger.warning(f"Version {to_version} not found for prompt '{name}'")
        return None
    
    # Create new version with old text
    return update_prompt(
        name,
        old_version.prompt_text,
        created_by=f"rollback_from_v{to_version}",
    )


def extract_variables(prompt_text: str) -> list[str]:
    """
    Extract variable names from a prompt template.
    
    Variables use {{variable_name}} syntax.
    
    Args:
        prompt_text: The prompt text to scan
    
    Returns:
        List of variable names found
    """
    pattern = r'\{\{(\w+)\}\}'
    matches = re.findall(pattern, prompt_text)
    # Return unique variables in order of first appearance
    seen = set()
    result = []
    for var in matches:
        if var not in seen:
            seen.add(var)
            result.append(var)
    return result


# ============================================================================
# Template Management
# ============================================================================

def list_prompts() -> list[PromptTemplate]:
    """
    List all prompt templates.
    
    Returns:
        List of PromptTemplate objects
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM prompt_templates ORDER BY name"
        ).fetchall()
        return [PromptTemplate.from_row(row) for row in rows]


def get_prompt_template(name: str) -> Optional[PromptTemplate]:
    """
    Get a prompt template metadata (without version content).
    
    Args:
        name: The template name
    
    Returns:
        PromptTemplate or None
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        return PromptTemplate.from_row(row) if row else None


def create_prompt_template(
    name: str,
    prompt_text: str,
    description: Optional[str] = None,
    variables: Optional[list[str]] = None,
) -> Optional[PromptTemplate]:
    """
    Create a new prompt template.
    
    Args:
        name: Unique name for the template
        prompt_text: Initial prompt text
        description: Optional description
        variables: Optional list of variables (auto-extracted if not provided)
    
    Returns:
        The created PromptTemplate or None if name exists
    """
    if variables is None:
        variables = extract_variables(prompt_text)
    
    with get_db() as conn:
        # Check if exists
        existing = conn.execute(
            "SELECT id FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        
        if existing:
            logger.warning(f"Prompt template already exists: {name}")
            return None
        
        # Create template
        conn.execute(
            """INSERT INTO prompt_templates (name, description, current_version)
               VALUES (?, ?, 1)""",
            (name, description)
        )
        template_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # Create initial version
        import json
        conn.execute(
            """INSERT INTO prompt_versions 
               (template_id, version, prompt_text, variables, created_by)
               VALUES (?, 1, ?, ?, 'system')""",
            (template_id, prompt_text, json.dumps(variables))
        )
        
        logger.info(f"Created prompt template: {name}")
        return get_prompt_template(name)


def delete_prompt_template(name: str) -> bool:
    """
    Delete a prompt template and all its versions.
    
    Args:
        name: The template name
    
    Returns:
        True if deleted, False if not found
    """
    with get_db() as conn:
        template_row = conn.execute(
            "SELECT id FROM prompt_templates WHERE name = ?",
            (name,)
        ).fetchone()
        
        if not template_row:
            return False
        
        template_id = template_row["id"]
        
        # Delete versions first
        conn.execute(
            "DELETE FROM prompt_versions WHERE template_id = ?",
            (template_id,)
        )
        
        # Delete template
        conn.execute(
            "DELETE FROM prompt_templates WHERE id = ?",
            (template_id,)
        )
        
        logger.info(f"Deleted prompt template: {name}")
        return True


# ============================================================================
# Seeding
# ============================================================================

def seed_default_prompts() -> dict:
    """
    Seed the default prompts if they don't exist.
    
    Returns:
        Dict with counts of created/skipped prompts
    """
    result = {"created": 0, "skipped": 0}
    
    for name, config in DEFAULT_PROMPTS.items():
        template = get_prompt_template(name)
        if template:
            result["skipped"] += 1
        else:
            create_prompt_template(
                name=name,
                prompt_text=config["prompt_text"],
                description=config["description"],
                variables=config["variables"],
            )
            result["created"] += 1
    
    if result["created"] > 0:
        logger.info(f"Seeded {result['created']} default prompts")
    
    return result


def get_prompt_with_context(name: str) -> Optional[dict]:
    """
    Get a prompt with full context for display/editing.
    
    Returns dict with:
    - template: PromptTemplate
    - current_version: PromptVersion
    - history_count: int
    - variables: list[str]
    """
    template = get_prompt_template(name)
    if not template:
        return None
    
    current = get_prompt(name)
    history = get_prompt_history(name)
    
    return {
        "template": template,
        "current_version": current,
        "history_count": len(history),
        "variables": current.variables if current else [],
    }
