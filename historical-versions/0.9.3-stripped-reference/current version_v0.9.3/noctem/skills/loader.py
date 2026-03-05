"""
Skill Loader - Parse and validate SKILL.yaml files.

Handles:
- YAML parsing with PyYAML
- Schema validation
- Loading instructions.md
- Accessing skill resources
"""

import re
from pathlib import Path
from typing import Optional, Tuple

import yaml

from noctem.models import SkillMetadata, SkillTrigger


class SkillValidationError(Exception):
    """Raised when skill validation fails."""
    pass


class SkillLoader:
    """
    Loads and validates skill definitions from SKILL.yaml files.
    
    Usage:
        loader = SkillLoader()
        metadata = loader.parse_skill_yaml(Path("/path/to/skill"))
        valid, errors = loader.validate_skill(Path("/path/to/skill"))
        instructions = loader.load_instructions(metadata, Path("/path/to/skill"))
    """
    
    # Semver regex pattern
    SEMVER_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')
    
    # Required fields in SKILL.yaml
    REQUIRED_FIELDS = ['name', 'version', 'description', 'triggers', 'requires_approval', 'instructions_file']
    
    def __init__(self):
        pass
    
    def parse_skill_yaml(self, skill_path: Path) -> SkillMetadata:
        """
        Parse SKILL.yaml file and return SkillMetadata.
        
        Args:
            skill_path: Path to the skill directory containing SKILL.yaml
            
        Returns:
            SkillMetadata object
            
        Raises:
            FileNotFoundError: If SKILL.yaml doesn't exist
            yaml.YAMLError: If YAML is malformed
            SkillValidationError: If required fields are missing
        """
        yaml_path = skill_path / "SKILL.yaml"
        
        if not yaml_path.exists():
            raise FileNotFoundError(f"SKILL.yaml not found in {skill_path}")
        
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if data is None:
            raise SkillValidationError("SKILL.yaml is empty")
        
        return SkillMetadata.from_dict(data)
    
    def validate_skill(self, skill_path: Path) -> Tuple[bool, list[str]]:
        """
        Validate a skill directory structure and SKILL.yaml content.
        
        Args:
            skill_path: Path to the skill directory
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check directory exists
        if not skill_path.exists():
            errors.append(f"Skill directory does not exist: {skill_path}")
            return False, errors
        
        if not skill_path.is_dir():
            errors.append(f"Skill path is not a directory: {skill_path}")
            return False, errors
        
        # Check SKILL.yaml exists
        yaml_path = skill_path / "SKILL.yaml"
        if not yaml_path.exists():
            errors.append("SKILL.yaml not found")
            return False, errors
        
        # Parse YAML
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {e}")
            return False, errors
        
        if data is None:
            errors.append("SKILL.yaml is empty")
            return False, errors
        
        # Validate required fields
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Validate name
        name = data.get('name', '')
        if not name:
            errors.append("name cannot be empty")
        elif not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$', name):
            errors.append("name must be lowercase, start/end with alphanumeric, use hyphens only")
        
        # Validate version (semver)
        version = data.get('version', '')
        if not self.SEMVER_PATTERN.match(str(version)):
            errors.append(f"version must be semver format (X.Y.Z), got: {version}")
        
        # Validate description length
        description = data.get('description', '')
        if len(description) > 500:
            errors.append(f"description exceeds 500 characters (got {len(description)})")
        
        # Validate triggers
        triggers = data.get('triggers', [])
        if not isinstance(triggers, list):
            errors.append("triggers must be a list")
        elif len(triggers) == 0:
            errors.append("triggers must have at least one entry")
        else:
            for i, trigger in enumerate(triggers):
                if not isinstance(trigger, dict):
                    errors.append(f"trigger[{i}] must be a dict")
                    continue
                if 'pattern' not in trigger:
                    errors.append(f"trigger[{i}] missing 'pattern'")
                elif not trigger['pattern']:
                    errors.append(f"trigger[{i}] pattern cannot be empty")
                
                threshold = trigger.get('confidence_threshold', 0.8)
                if not isinstance(threshold, (int, float)):
                    errors.append(f"trigger[{i}] confidence_threshold must be a number")
                elif not (0.5 <= threshold <= 1.0):
                    errors.append(f"trigger[{i}] confidence_threshold must be between 0.5 and 1.0")
        
        # Validate dependencies
        dependencies = data.get('dependencies', [])
        if not isinstance(dependencies, list):
            errors.append("dependencies must be a list")
        
        # Validate requires_approval
        requires_approval = data.get('requires_approval')
        if not isinstance(requires_approval, bool):
            errors.append("requires_approval must be a boolean")
        
        # Validate instructions_file exists
        instructions_file = data.get('instructions_file', 'instructions.md')
        instructions_path = skill_path / instructions_file
        if not instructions_path.exists():
            errors.append(f"instructions_file not found: {instructions_file}")
        
        return len(errors) == 0, errors
    
    def load_instructions(self, metadata: SkillMetadata, skill_path: Path) -> str:
        """
        Load the full instructions markdown for a skill.
        
        Args:
            metadata: SkillMetadata with instructions_file field
            skill_path: Path to the skill directory
            
        Returns:
            Full instructions as string
            
        Raises:
            FileNotFoundError: If instructions file doesn't exist
        """
        instructions_path = skill_path / metadata.instructions_file
        
        if not instructions_path.exists():
            raise FileNotFoundError(
                f"Instructions file not found: {instructions_path}"
            )
        
        with open(instructions_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def get_skill_resources(self, skill_path: Path, resource_name: str) -> Optional[Path]:
        """
        Get path to a resource file in the skill's resources directory.
        
        Args:
            skill_path: Path to the skill directory
            resource_name: Name of the resource file or subdirectory path
            
        Returns:
            Path to the resource, or None if not found
        """
        resources_path = skill_path / "resources" / resource_name
        
        if resources_path.exists():
            return resources_path
        
        return None
    
    def list_skill_resources(self, skill_path: Path) -> list[Path]:
        """
        List all resource files in a skill's resources directory.
        
        Args:
            skill_path: Path to the skill directory
            
        Returns:
            List of paths to resource files
        """
        resources_dir = skill_path / "resources"
        
        if not resources_dir.exists():
            return []
        
        return list(resources_dir.rglob("*"))
