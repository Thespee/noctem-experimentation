"""
Skill Registry - Discover, register, and manage skills.

Handles:
- Skill discovery from bundled/ and data/skills/ directories
- Database CRUD operations for skills
- Skill metadata caching for progressive disclosure
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from noctem.db import get_db
from noctem.models import Skill, SkillTrigger
from noctem.skills.loader import SkillLoader


class SkillRegistry:
    """
    Manages skill registration and discovery.
    
    Usage:
        registry = SkillRegistry()
        registry.discover_skills()  # Scan and register skills
        skill = registry.get_skill("my-skill")
        skills = registry.get_all_skills()
    """
    
    def __init__(self, bundled_path: Optional[Path] = None, user_path: Optional[Path] = None):
        """
        Initialize the skill registry.
        
        Args:
            bundled_path: Path to bundled skills directory (default: noctem/skills/bundled/)
            user_path: Path to user skills directory (default: noctem/data/skills/)
        """
        self.loader = SkillLoader()
        
        # Set default paths
        if bundled_path is None:
            bundled_path = Path(__file__).parent / "bundled"
        if user_path is None:
            from noctem.db import DB_PATH
            user_path = DB_PATH.parent / "skills"
        
        self.bundled_path = bundled_path
        self.user_path = user_path
    
    def discover_skills(self) -> list[Skill]:
        """
        Scan bundled and user skill directories, validate, and register in DB.
        
        Returns:
            List of discovered and registered skills
        """
        discovered = []
        
        # Ensure directories exist
        self.bundled_path.mkdir(parents=True, exist_ok=True)
        self.user_path.mkdir(parents=True, exist_ok=True)
        
        # Discover bundled skills
        for skill_dir in self._list_skill_dirs(self.bundled_path):
            skill = self._register_skill(skill_dir, source="bundled")
            if skill:
                discovered.append(skill)
        
        # Discover user skills
        for skill_dir in self._list_skill_dirs(self.user_path):
            skill = self._register_skill(skill_dir, source="user")
            if skill:
                discovered.append(skill)
        
        return discovered
    
    def _list_skill_dirs(self, parent_path: Path) -> list[Path]:
        """List all valid skill directories in a parent directory."""
        if not parent_path.exists():
            return []
        
        skill_dirs = []
        for item in parent_path.iterdir():
            if item.is_dir() and (item / "SKILL.yaml").exists():
                skill_dirs.append(item)
        
        return skill_dirs
    
    def _register_skill(self, skill_path: Path, source: str) -> Optional[Skill]:
        """
        Validate and register a single skill in the database.
        
        Args:
            skill_path: Path to skill directory
            source: 'bundled' or 'user'
            
        Returns:
            Registered Skill or None if validation failed
        """
        # Validate skill
        is_valid, errors = self.loader.validate_skill(skill_path)
        if not is_valid:
            return None
        
        # Parse metadata
        try:
            metadata = self.loader.parse_skill_yaml(skill_path)
        except Exception:
            return None
        
        # Check if skill already exists
        existing = self.get_skill(metadata.name)
        
        with get_db() as conn:
            if existing:
                # Update existing skill
                conn.execute("""
                    UPDATE skills SET
                        version = ?,
                        source = ?,
                        skill_path = ?,
                        description = ?,
                        triggers = ?,
                        dependencies = ?,
                        requires_approval = ?,
                        updated_at = ?
                    WHERE name = ?
                """, (
                    metadata.version,
                    source,
                    str(skill_path),
                    metadata.description,
                    self._triggers_to_json(metadata.triggers),
                    self._deps_to_json(metadata.dependencies),
                    1 if metadata.requires_approval else 0,
                    datetime.now().isoformat(),
                    metadata.name,
                ))
                return self.get_skill(metadata.name)
            else:
                # Insert new skill
                conn.execute("""
                    INSERT INTO skills (
                        name, version, source, skill_path, description,
                        triggers, dependencies, requires_approval, enabled,
                        use_count, success_count, failure_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, 0, 0, ?)
                """, (
                    metadata.name,
                    metadata.version,
                    source,
                    str(skill_path),
                    metadata.description,
                    self._triggers_to_json(metadata.triggers),
                    self._deps_to_json(metadata.dependencies),
                    1 if metadata.requires_approval else 0,
                    datetime.now().isoformat(),
                ))
        # Commit happens when exiting the with block
        return self.get_skill(metadata.name)
    
    def _triggers_to_json(self, triggers: list[SkillTrigger]) -> str:
        """Convert triggers list to JSON string."""
        import json
        return json.dumps([t.to_dict() for t in triggers])
    
    def _deps_to_json(self, dependencies: list[str]) -> str:
        """Convert dependencies list to JSON string."""
        import json
        return json.dumps(dependencies)
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name from the database.
        
        Args:
            name: Skill name
            
        Returns:
            Skill or None if not found
        """
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?",
                (name,)
            ).fetchone()
            
            if row:
                return Skill.from_row(row)
            return None
    
    def get_all_skills(self, enabled_only: bool = True) -> list[Skill]:
        """
        Get all skills from the database.
        
        Args:
            enabled_only: If True, only return enabled skills
            
        Returns:
            List of skills
        """
        with get_db() as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM skills WHERE enabled = 1 ORDER BY name"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM skills ORDER BY name"
                ).fetchall()
            
            return [Skill.from_row(row) for row in rows]
    
    def enable_skill(self, name: str) -> bool:
        """
        Enable a skill.
        
        Returns:
            True if skill was enabled, False if not found
        """
        with get_db() as conn:
            result = conn.execute(
                "UPDATE skills SET enabled = 1, updated_at = ? WHERE name = ?",
                (datetime.now().isoformat(), name)
            )
            return result.rowcount > 0
    
    def disable_skill(self, name: str) -> bool:
        """
        Disable a skill.
        
        Returns:
            True if skill was disabled, False if not found
        """
        with get_db() as conn:
            result = conn.execute(
                "UPDATE skills SET enabled = 0, updated_at = ? WHERE name = ?",
                (datetime.now().isoformat(), name)
            )
            return result.rowcount > 0
    
    def get_skill_metadata(self, name: str) -> Optional[dict]:
        """
        Get just the metadata for a skill (progressive disclosure).
        
        Returns:
            Dict with name, version, description, triggers or None
        """
        skill = self.get_skill(name)
        if not skill:
            return None
        
        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "triggers": [t.to_dict() for t in skill.triggers],
            "requires_approval": skill.requires_approval,
            "success_rate": skill.success_rate,
        }
    
    def get_skill_instructions(self, name: str) -> Optional[str]:
        """
        Load full instructions for a skill (on-demand).
        
        Returns:
            Instructions markdown string or None
        """
        skill = self.get_skill(name)
        if not skill:
            return None
        
        try:
            skill_path = Path(skill.skill_path)
            metadata = self.loader.parse_skill_yaml(skill_path)
            return self.loader.load_instructions(metadata, skill_path)
        except Exception:
            return None
    
    def update_skill_stats(self, name: str, success: bool) -> bool:
        """
        Update usage statistics for a skill.
        
        Args:
            name: Skill name
            success: True if execution was successful
            
        Returns:
            True if updated, False if skill not found
        """
        with get_db() as conn:
            if success:
                result = conn.execute("""
                    UPDATE skills SET
                        use_count = use_count + 1,
                        success_count = success_count + 1,
                        last_used = ?,
                        updated_at = ?
                    WHERE name = ?
                """, (datetime.now().isoformat(), datetime.now().isoformat(), name))
            else:
                result = conn.execute("""
                    UPDATE skills SET
                        use_count = use_count + 1,
                        failure_count = failure_count + 1,
                        last_used = ?,
                        updated_at = ?
                    WHERE name = ?
                """, (datetime.now().isoformat(), datetime.now().isoformat(), name))
            
            return result.rowcount > 0
    
    def delete_skill(self, name: str) -> bool:
        """
        Delete a skill from the registry.
        
        Note: This only removes from DB, not the files.
        
        Returns:
            True if deleted, False if not found
        """
        with get_db() as conn:
            result = conn.execute(
                "DELETE FROM skills WHERE name = ?",
                (name,)
            )
            return result.rowcount > 0
