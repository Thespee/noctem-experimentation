"""
Skill Service - High-level API for skill operations.

Provides a unified interface for:
- Skill discovery and initialization
- Input handling with trigger detection
- Skill execution
- User skill creation
"""

from pathlib import Path
from typing import Optional, Tuple

from noctem.models import Skill, SkillExecution, SkillMetadata, SkillTrigger
from noctem.skills.loader import SkillLoader
from noctem.skills.registry import SkillRegistry
from noctem.skills.trigger import SkillTriggerDetector
from noctem.skills.executor import SkillExecutor, SkillApprovalRequired


class SkillService:
    """
    High-level service for all skill operations.
    
    Usage:
        service = SkillService()
        service.initialize()  # Discover skills at boot
        
        # Handle user input
        triggered, skill_name, response = service.handle_input("how do I cook pasta", "cli")
        
        # List skills
        skills = service.list_skills()
        
        # Get skill info
        info = service.get_skill_info("cooking-basics")
    """
    
    def __init__(
        self,
        bundled_path: Optional[Path] = None,
        user_path: Optional[Path] = None,
    ):
        """
        Initialize the skill service.
        
        Args:
            bundled_path: Path to bundled skills directory
            user_path: Path to user skills directory
        """
        self.registry = SkillRegistry(bundled_path, user_path)
        self.loader = SkillLoader()
        self.executor = SkillExecutor(self.registry)
        self.detector: Optional[SkillTriggerDetector] = None
        self._initialized = False
    
    def initialize(self) -> list[Skill]:
        """
        Initialize the skill service by discovering all skills.
        
        This should be called at application boot.
        
        Returns:
            List of discovered skills
        """
        # Discover and register skills
        discovered = self.registry.discover_skills()
        
        # Build trigger detector
        self._rebuild_detector()
        
        self._initialized = True
        return discovered
    
    def _rebuild_detector(self):
        """Rebuild the trigger detector with current skills."""
        skills = self.registry.get_all_skills(enabled_only=True)
        self.detector = SkillTriggerDetector(skills)
    
    def handle_input(
        self,
        text: str,
        source: str = "cli",
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Handle user input, checking for skill triggers.
        
        Args:
            text: User input text
            source: Input source ('cli', 'telegram', 'web')
            
        Returns:
            Tuple of (triggered, skill_name, response)
            - triggered: True if a skill was triggered
            - skill_name: Name of triggered skill or None
            - response: Response message or None
        """
        if not self._initialized:
            self.initialize()
        
        if not self.detector:
            return (False, None, None)
        
        # Check for skill trigger
        result = self.detector.detect_skill(text)
        
        if not result:
            return (False, None, None)
        
        skill_name, confidence, requires_approval = result
        
        # Execute the skill
        try:
            execution = self.executor.execute_skill(
                skill_name,
                context={"input": text, "source": source},
                trigger_type="pattern_match" if confidence < 1.0 else "explicit",
                trigger_input=text,
                trigger_confidence=confidence,
            )
            
            # Get instructions for response
            instructions = self.registry.get_skill_instructions(skill_name)
            response = f"🔧 **Skill: {skill_name}** (v{execution.skill_version})\n\n{instructions[:500]}..."
            
            return (True, skill_name, response)
            
        except SkillApprovalRequired as e:
            response = (
                f"⚠️ **Skill '{skill_name}' requires approval**\n\n"
                f"This skill needs your permission before running.\n"
                f"Reply 'approve {e.execution_id}' to proceed or 'reject {e.execution_id}' to cancel."
            )
            return (True, skill_name, response)
        
        except Exception as e:
            return (True, skill_name, f"❌ Skill execution failed: {e}")
    
    def run_skill(
        self,
        name: str,
        context: dict = None,
    ) -> Tuple[bool, str]:
        """
        Explicitly run a skill by name.
        
        Args:
            name: Skill name
            context: Optional context dict
            
        Returns:
            Tuple of (success, message)
        """
        if not self._initialized:
            self.initialize()
        
        try:
            execution = self.executor.execute_skill(
                name,
                context=context or {},
                trigger_type="explicit",
                trigger_confidence=1.0,
            )
            
            instructions = self.registry.get_skill_instructions(name)
            return (True, instructions)
            
        except SkillApprovalRequired as e:
            return (False, f"Skill requires approval. Execution ID: {e.execution_id}")
        
        except Exception as e:
            return (False, str(e))
    
    def list_skills(self, enabled_only: bool = True) -> list[Skill]:
        """
        List all registered skills.
        
        Args:
            enabled_only: If True, only return enabled skills
            
        Returns:
            List of Skill objects
        """
        return self.registry.get_all_skills(enabled_only=enabled_only)
    
    def get_skill_info(self, name: str) -> Optional[dict]:
        """
        Get detailed info about a skill.
        
        Returns:
            Dict with skill metadata and stats, or None if not found
        """
        skill = self.registry.get_skill(name)
        if not skill:
            return None
        
        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "source": skill.source,
            "enabled": skill.enabled,
            "requires_approval": skill.requires_approval,
            "triggers": [t.to_dict() for t in skill.triggers],
            "dependencies": skill.dependencies,
            "stats": {
                "use_count": skill.use_count,
                "success_count": skill.success_count,
                "failure_count": skill.failure_count,
                "success_rate": skill.success_rate,
                "last_used": skill.last_used.isoformat() if skill.last_used else None,
            }
        }
    
    def enable_skill(self, name: str) -> bool:
        """Enable a skill."""
        result = self.registry.enable_skill(name)
        if result:
            self._rebuild_detector()
        return result
    
    def disable_skill(self, name: str) -> bool:
        """Disable a skill."""
        result = self.registry.disable_skill(name)
        if result:
            self._rebuild_detector()
        return result
    
    def create_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        triggers: list[dict] = None,
        requires_approval: bool = False,
    ) -> Optional[Skill]:
        """
        Create a new user skill.
        
        Args:
            name: Skill name (lowercase, hyphens only)
            description: Short description
            instructions: Full instructions markdown
            triggers: List of trigger pattern dicts [{"pattern": "...", "confidence_threshold": 0.8}]
            requires_approval: Whether skill requires approval
            
        Returns:
            Created Skill or None if failed
        """
        # Validate name
        import re
        if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$', name):
            raise ValueError("Name must be lowercase, start/end with alphanumeric, use hyphens only")
        
        # Create skill directory
        skill_path = self.registry.user_path / name
        skill_path.mkdir(parents=True, exist_ok=True)
        
        # Default trigger if none provided
        if not triggers:
            triggers = [{"pattern": f"how do I {name}", "confidence_threshold": 0.8}]
        
        # Create SKILL.yaml
        import yaml
        
        yaml_content = {
            "name": name,
            "version": "1.0.0",
            "description": description,
            "triggers": triggers,
            "dependencies": [],
            "requires_approval": requires_approval,
            "instructions_file": "instructions.md",
        }
        
        with open(skill_path / "SKILL.yaml", "w", encoding="utf-8") as f:
            yaml.dump(yaml_content, f, default_flow_style=False)
        
        # Create instructions.md
        with open(skill_path / "instructions.md", "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{instructions}")
        
        # Register the skill
        skill = self.registry._register_skill(skill_path, source="user")
        
        if skill:
            self._rebuild_detector()
        
        return skill
    
    def validate_skill(self, path: Path) -> Tuple[bool, list[str]]:
        """
        Validate a skill directory.
        
        Args:
            path: Path to skill directory
            
        Returns:
            Tuple of (is_valid, errors)
        """
        return self.loader.validate_skill(path)
    
    def approve_execution(self, execution_id: int) -> SkillExecution:
        """Approve a pending skill execution."""
        return self.executor.approve_pending_execution(execution_id)
    
    def reject_execution(self, execution_id: int) -> SkillExecution:
        """Reject a pending skill execution."""
        return self.executor.reject_pending_execution(execution_id)
    
    def get_pending_approvals(self) -> list[SkillExecution]:
        """Get all executions pending approval."""
        return self.executor.get_pending_approvals()


# Singleton instance for easy access
_service_instance: Optional[SkillService] = None


def get_skill_service() -> SkillService:
    """Get the global SkillService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SkillService()
    return _service_instance
