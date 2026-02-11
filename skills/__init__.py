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

# Import skills - optional imports for those with external dependencies
# Core skills (standard library only)
from . import shell
from . import file_ops
from . import task_status
from . import task_manager

# Skills with optional dependencies - won't break if missing
def _try_import(module_name):
    try:
        __import__(f'skills.{module_name}', fromlist=[module_name])
    except ImportError as e:
        pass  # Skill unavailable due to missing dependency

_try_import('signal_send')
_try_import('web_fetch')      # requires bs4
_try_import('web_search')     # requires requests
_try_import('troubleshoot')
_try_import('email_send')
_try_import('email_fetch')
_try_import('daily_report')

__all__ = [
    "Skill",
    "SkillResult", 
    "SkillContext",
    "register_skill",
    "get_skill",
    "get_all_skills",
    "get_skill_manifest"
]
