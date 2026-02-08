#!/usr/bin/env python3
"""
Noctem Skills Package
Auto-discovers and registers all skills.
"""

from .base import (
    Skill,
    SkillResult,
    SkillContext,
    register_skill,
    get_skill,
    get_all_skills,
    get_skill_manifest
)

# Import all skill modules to trigger registration
# Add new skills here as they're created
from . import shell
from . import signal_send
from . import file_ops
from . import task_status
from . import web_fetch
from . import web_search
from . import troubleshoot
# from . import optimize   # TODO
# from . import warp_agent # TODO

__all__ = [
    "Skill",
    "SkillResult", 
    "SkillContext",
    "register_skill",
    "get_skill",
    "get_all_skills",
    "get_skill_manifest"
]
