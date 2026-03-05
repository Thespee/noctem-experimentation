"""
Noctem Skills Infrastructure v0.8.0

Skills are the "how" — packaged knowledge, procedures, and optional code.
This module provides:
- SkillLoader: Parse and validate SKILL.yaml files
- SkillRegistry: Discover, register, and manage skills
- SkillTriggerDetector: Match user input to skills
- SkillExecutor: Execute skills with logging and approval flow
- SkillService: High-level API for skill operations
"""

from noctem.skills.loader import SkillLoader
from noctem.skills.registry import SkillRegistry
from noctem.skills.trigger import SkillTriggerDetector
from noctem.skills.executor import SkillExecutor, SkillApprovalRequired
from noctem.skills.service import SkillService, get_skill_service

__all__ = [
    "SkillLoader",
    "SkillRegistry",
    "SkillTriggerDetector",
    "SkillExecutor",
    "SkillApprovalRequired",
    "SkillService",
    "get_skill_service",
]
