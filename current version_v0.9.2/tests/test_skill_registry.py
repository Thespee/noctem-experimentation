"""
Tests for noctem.skills.registry - SkillRegistry

Tests skill discovery, registration, and CRUD operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from noctem.skills.registry import SkillRegistry
from noctem.models import Skill, SkillTrigger


@pytest.fixture
def temp_skill_dirs():
    """Create temporary bundled and user skill directories."""
    bundled = tempfile.mkdtemp(prefix="noctem_bundled_")
    user = tempfile.mkdtemp(prefix="noctem_user_")
    yield Path(bundled), Path(user)
    shutil.rmtree(bundled, ignore_errors=True)
    shutil.rmtree(user, ignore_errors=True)


@pytest.fixture
def sample_skill_yaml():
    return """
name: test-skill
version: "1.0.0"
description: "A test skill"
triggers:
  - pattern: "how do I test"
    confidence_threshold: 0.8
dependencies: []
requires_approval: false
instructions_file: instructions.md
"""


@pytest.fixture
def sample_instructions():
    return "# Test Skill\n\nThis is a test skill with instructions."


def create_skill_dir(base_path: Path, name: str, yaml_content: str, instructions: str):
    """Helper to create a skill directory structure."""
    skill_path = base_path / name
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.yaml").write_text(yaml_content, encoding="utf-8")
    (skill_path / "instructions.md").write_text(instructions, encoding="utf-8")
    return skill_path


class TestDiscoverSkills:
    """Tests for discover_skills method."""
    
    def test_discover_bundled_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should discover skills in bundled directory."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "bundled-skill", sample_skill_yaml.replace("test-skill", "bundled-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        discovered = registry.discover_skills()
        
        assert len(discovered) == 1
        assert discovered[0].name == "bundled-skill"
        assert discovered[0].source == "bundled"
    
    def test_discover_user_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should discover skills in user directory."""
        bundled, user = temp_skill_dirs
        create_skill_dir(user, "user-skill", sample_skill_yaml.replace("test-skill", "user-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        discovered = registry.discover_skills()
        
        assert len(discovered) == 1
        assert discovered[0].name == "user-skill"
        assert discovered[0].source == "user"
    
    def test_discover_multiple_skills(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should discover skills from both directories."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "skill-a", sample_skill_yaml.replace("test-skill", "skill-a"), sample_instructions)
        create_skill_dir(bundled, "skill-b", sample_skill_yaml.replace("test-skill", "skill-b"), sample_instructions)
        create_skill_dir(user, "skill-c", sample_skill_yaml.replace("test-skill", "skill-c"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        discovered = registry.discover_skills()
        
        assert len(discovered) == 3
        names = {s.name for s in discovered}
        assert names == {"skill-a", "skill-b", "skill-c"}
    
    def test_discover_empty_directories(self, temp_skill_dirs):
        """Should handle empty skill directories."""
        bundled, user = temp_skill_dirs
        
        registry = SkillRegistry(bundled, user)
        discovered = registry.discover_skills()
        
        assert len(discovered) == 0
    
    def test_discover_skips_invalid_skills(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should skip directories without valid SKILL.yaml."""
        bundled, user = temp_skill_dirs
        
        # Create valid skill
        create_skill_dir(bundled, "valid-skill", sample_skill_yaml.replace("test-skill", "valid-skill"), sample_instructions)
        
        # Create invalid skill (no SKILL.yaml)
        invalid_path = bundled / "invalid-skill"
        invalid_path.mkdir()
        (invalid_path / "instructions.md").write_text("No YAML", encoding="utf-8")
        
        registry = SkillRegistry(bundled, user)
        discovered = registry.discover_skills()
        
        assert len(discovered) == 1
        assert discovered[0].name == "valid-skill"


class TestGetSkill:
    """Tests for get_skill method."""
    
    def test_get_existing_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should return skill by name."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        skill = registry.get_skill("my-skill")
        
        assert skill is not None
        assert skill.name == "my-skill"
    
    def test_get_nonexistent_skill(self, temp_skill_dirs):
        """Should return None for unknown skill."""
        bundled, user = temp_skill_dirs
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        skill = registry.get_skill("nonexistent")
        
        assert skill is None


class TestGetAllSkills:
    """Tests for get_all_skills method."""
    
    def test_get_all_skills(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should return all registered skills."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "skill-1", sample_skill_yaml.replace("test-skill", "skill-1"), sample_instructions)
        create_skill_dir(user, "skill-2", sample_skill_yaml.replace("test-skill", "skill-2"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        all_skills = registry.get_all_skills(enabled_only=False)
        
        assert len(all_skills) == 2
    
    def test_get_enabled_only(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should filter to enabled skills only."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "enabled-skill", sample_skill_yaml.replace("test-skill", "enabled-skill"), sample_instructions)
        create_skill_dir(bundled, "disabled-skill", sample_skill_yaml.replace("test-skill", "disabled-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        # Disable one skill
        registry.disable_skill("disabled-skill")
        
        enabled_skills = registry.get_all_skills(enabled_only=True)
        all_skills = registry.get_all_skills(enabled_only=False)
        
        assert len(enabled_skills) == 1
        assert len(all_skills) == 2
        assert enabled_skills[0].name == "enabled-skill"


class TestEnableDisableSkill:
    """Tests for enable_skill and disable_skill methods."""
    
    def test_disable_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should disable a skill."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        result = registry.disable_skill("my-skill")
        skill = registry.get_skill("my-skill")
        
        assert result is True
        assert skill.enabled is False
    
    def test_enable_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should enable a previously disabled skill."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        registry.disable_skill("my-skill")
        
        result = registry.enable_skill("my-skill")
        skill = registry.get_skill("my-skill")
        
        assert result is True
        assert skill.enabled is True
    
    def test_disable_nonexistent_skill(self, temp_skill_dirs):
        """Should return False for nonexistent skill."""
        bundled, user = temp_skill_dirs
        registry = SkillRegistry(bundled, user)
        
        result = registry.disable_skill("nonexistent")
        
        assert result is False


class TestGetSkillInstructions:
    """Tests for get_skill_instructions method."""
    
    def test_get_instructions(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should load and return skill instructions."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        instructions = registry.get_skill_instructions("my-skill")
        
        assert instructions == sample_instructions
    
    def test_get_instructions_nonexistent_skill(self, temp_skill_dirs):
        """Should return None for nonexistent skill."""
        bundled, user = temp_skill_dirs
        registry = SkillRegistry(bundled, user)
        
        instructions = registry.get_skill_instructions("nonexistent")
        
        assert instructions is None


class TestUpdateStats:
    """Tests for update_skill_stats method."""
    
    def test_update_stats_success(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should update stats for successful execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        registry.update_skill_stats("my-skill", success=True)
        skill = registry.get_skill("my-skill")
        
        assert skill.use_count == 1
        assert skill.success_count == 1
        assert skill.failure_count == 0
        assert skill.last_used is not None
    
    def test_update_stats_failure(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should update stats for failed execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        registry.update_skill_stats("my-skill", success=False)
        skill = registry.get_skill("my-skill")
        
        assert skill.use_count == 1
        assert skill.success_count == 0
        assert skill.failure_count == 1
    
    def test_update_stats_multiple_times(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should accumulate stats correctly."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "my-skill", sample_skill_yaml.replace("test-skill", "my-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        
        registry.update_skill_stats("my-skill", success=True)
        registry.update_skill_stats("my-skill", success=True)
        registry.update_skill_stats("my-skill", success=False)
        
        skill = registry.get_skill("my-skill")
        
        assert skill.use_count == 3
        assert skill.success_count == 2
        assert skill.failure_count == 1
