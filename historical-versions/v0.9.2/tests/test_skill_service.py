"""
Tests for noctem.skills.service - SkillService

Tests the high-level API for skill operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from noctem.skills.service import SkillService, get_skill_service
from noctem.models import Skill


@pytest.fixture
def temp_skill_dirs():
    """Create temporary skill directories."""
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
description: "A test skill for testing"
triggers:
  - pattern: "how do I test"
    confidence_threshold: 0.8
dependencies: []
requires_approval: false
instructions_file: instructions.md
"""


@pytest.fixture
def sample_instructions():
    return "# Test Skill\n\nThis is a test skill with helpful instructions."


def create_skill_dir(base_path: Path, name: str, yaml_content: str, instructions: str):
    """Helper to create a skill directory."""
    skill_path = base_path / name
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.yaml").write_text(yaml_content, encoding="utf-8")
    (skill_path / "instructions.md").write_text(instructions, encoding="utf-8")
    return skill_path


class TestInitialize:
    """Tests for initialize method."""
    
    def test_initialize_discovers_skills(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should discover skills on initialization."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "init-skill", sample_skill_yaml.replace("test-skill", "init-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        discovered = service.initialize()
        
        assert len(discovered) == 1
        assert discovered[0].name == "init-skill"
    
    def test_initialize_sets_initialized_flag(self, temp_skill_dirs):
        """Should set _initialized flag."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        assert service._initialized is False
        
        service.initialize()
        assert service._initialized is True


class TestHandleInput:
    """Tests for handle_input method."""
    
    def test_handle_input_triggers_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should trigger skill on matching input."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "handle-skill", sample_skill_yaml.replace("test-skill", "handle-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        triggered, skill_name, response = service.handle_input("how do I test")
        
        assert triggered is True
        assert skill_name == "handle-skill"
        assert response is not None
    
    def test_handle_input_no_match(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should return no trigger for non-matching input."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "specific-skill", sample_skill_yaml.replace("test-skill", "specific-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        triggered, skill_name, response = service.handle_input("completely unrelated query")
        
        assert triggered is False
        assert skill_name is None
    
    def test_handle_input_auto_initializes(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should auto-initialize if not already initialized."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "auto-skill", sample_skill_yaml.replace("test-skill", "auto-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        assert service._initialized is False
        
        triggered, _, _ = service.handle_input("how do I test")
        
        assert service._initialized is True


class TestRunSkill:
    """Tests for run_skill method."""
    
    def test_run_skill_explicit(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should run skill by name."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "run-skill", sample_skill_yaml.replace("test-skill", "run-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        success, message = service.run_skill("run-skill")
        
        assert success is True
        assert message == sample_instructions
    
    def test_run_skill_not_found(self, temp_skill_dirs):
        """Should return failure for unknown skill."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        success, message = service.run_skill("nonexistent")
        
        assert success is False
        assert "not found" in message.lower()


class TestListSkills:
    """Tests for list_skills method."""
    
    def test_list_skills_returns_all(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should return all skills."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "skill-a", sample_skill_yaml.replace("test-skill", "skill-a"), sample_instructions)
        create_skill_dir(bundled, "skill-b", sample_skill_yaml.replace("test-skill", "skill-b"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        skills = service.list_skills(enabled_only=False)
        
        assert len(skills) == 2
    
    def test_list_skills_enabled_only(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should filter to enabled skills."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "enabled-skill", sample_skill_yaml.replace("test-skill", "enabled-skill"), sample_instructions)
        create_skill_dir(bundled, "disabled-skill", sample_skill_yaml.replace("test-skill", "disabled-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        service.disable_skill("disabled-skill")
        
        enabled_skills = service.list_skills(enabled_only=True)
        all_skills = service.list_skills(enabled_only=False)
        
        assert len(enabled_skills) == 1
        assert len(all_skills) == 2


class TestGetSkillInfo:
    """Tests for get_skill_info method."""
    
    def test_get_skill_info(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should return detailed skill info."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "info-skill", sample_skill_yaml.replace("test-skill", "info-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        info = service.get_skill_info("info-skill")
        
        assert info is not None
        assert info["name"] == "info-skill"
        assert info["version"] == "1.0.0"
        assert "triggers" in info
        assert "stats" in info
    
    def test_get_skill_info_not_found(self, temp_skill_dirs):
        """Should return None for unknown skill."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        info = service.get_skill_info("nonexistent")
        
        assert info is None


class TestEnableDisableSkill:
    """Tests for enable_skill and disable_skill methods."""
    
    def test_disable_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should disable a skill."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "toggle-skill", sample_skill_yaml.replace("test-skill", "toggle-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        
        result = service.disable_skill("toggle-skill")
        info = service.get_skill_info("toggle-skill")
        
        assert result is True
        assert info["enabled"] is False
    
    def test_enable_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should enable a disabled skill."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "toggle-skill", sample_skill_yaml.replace("test-skill", "toggle-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        service.initialize()
        service.disable_skill("toggle-skill")
        
        result = service.enable_skill("toggle-skill")
        info = service.get_skill_info("toggle-skill")
        
        assert result is True
        assert info["enabled"] is True


class TestCreateSkill:
    """Tests for create_skill method."""
    
    def test_create_skill(self, temp_skill_dirs):
        """Should create a new user skill."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        skill = service.create_skill(
            name="new-skill",
            description="A new skill",
            instructions="Instructions for new skill",
        )
        
        assert skill is not None
        assert skill.name == "new-skill"
        assert skill.source == "user"
    
    def test_create_skill_with_triggers(self, temp_skill_dirs):
        """Should create skill with custom triggers."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        skill = service.create_skill(
            name="custom-trigger",
            description="Skill with custom trigger",
            instructions="Custom instructions",
            triggers=[{"pattern": "custom trigger phrase", "confidence_threshold": 0.9}],
        )
        
        assert skill is not None
        assert len(skill.triggers) == 1
        assert skill.triggers[0].pattern == "custom trigger phrase"
    
    def test_create_skill_invalid_name_raises(self, temp_skill_dirs):
        """Should raise error for invalid name."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        with pytest.raises(ValueError, match="Name must be lowercase"):
            service.create_skill(
                name="Invalid Name",
                description="Invalid",
                instructions="Instructions",
            )
    
    def test_create_skill_files_exist(self, temp_skill_dirs):
        """Should create SKILL.yaml and instructions.md files."""
        bundled, user = temp_skill_dirs
        
        service = SkillService(bundled, user)
        service.initialize()
        
        service.create_skill(
            name="files-skill",
            description="Check files exist",
            instructions="Test instructions content",
        )
        
        skill_path = user / "files-skill"
        
        assert (skill_path / "SKILL.yaml").exists()
        assert (skill_path / "instructions.md").exists()


class TestValidateSkill:
    """Tests for validate_skill method."""
    
    def test_validate_valid_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should validate a correct skill."""
        bundled, user = temp_skill_dirs
        skill_path = create_skill_dir(bundled, "valid-skill", sample_skill_yaml.replace("test-skill", "valid-skill"), sample_instructions)
        
        service = SkillService(bundled, user)
        
        is_valid, errors = service.validate_skill(skill_path)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_invalid_skill(self, temp_skill_dirs):
        """Should return errors for invalid skill."""
        bundled, user = temp_skill_dirs
        
        # Create skill without SKILL.yaml
        invalid_path = bundled / "invalid-skill"
        invalid_path.mkdir(parents=True)
        
        service = SkillService(bundled, user)
        
        is_valid, errors = service.validate_skill(invalid_path)
        
        assert is_valid is False
        assert len(errors) > 0


class TestSingleton:
    """Tests for get_skill_service singleton."""
    
    def test_get_skill_service_returns_same_instance(self):
        """Should return same instance each time."""
        # Reset singleton for test
        import noctem.skills.service as service_module
        service_module._service_instance = None
        
        instance1 = get_skill_service()
        instance2 = get_skill_service()
        
        assert instance1 is instance2
