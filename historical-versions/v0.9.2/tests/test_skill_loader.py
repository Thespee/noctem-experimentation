"""
Tests for Noctem v0.8.0 SkillLoader.

Tests cover:
- SKILL.yaml parsing
- Schema validation
- Instructions loading
- Resource access
"""
import pytest
import tempfile
import os
from pathlib import Path

# Set up test database before imports
TEST_DB = tempfile.mktemp(suffix='.db')
os.environ['NOCTEM_DB_PATH'] = TEST_DB

from noctem import db
from noctem.db import init_db

# Override DB path for testing
db.DB_PATH = Path(TEST_DB)


@pytest.fixture(autouse=True)
def setup_db():
    """Set up fresh database for each test."""
    db.DB_PATH = Path(TEST_DB)
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    init_db()
    yield
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


@pytest.fixture
def temp_skill_dir():
    """Create a temporary skill directory with valid structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_path = Path(tmpdir) / "test-skill"
        skill_path.mkdir()
        
        # Create SKILL.yaml
        yaml_content = """
name: test-skill
version: "1.0.0"
description: "A test skill for unit testing"
triggers:
  - pattern: "how do I test"
    confidence_threshold: 0.8
  - pattern: "test help"
    confidence_threshold: 0.7
dependencies: []
requires_approval: false
instructions_file: instructions.md
"""
        (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
        
        # Create instructions.md
        instructions = """# Test Skill Instructions

This is a test skill for unit testing.

## Steps

1. Step one
2. Step two
3. Step three
"""
        (skill_path / "instructions.md").write_text(instructions, encoding='utf-8')
        
        # Create resources directory
        (skill_path / "resources").mkdir()
        (skill_path / "resources" / "template.txt").write_text("Template content", encoding='utf-8')
        
        yield skill_path


@pytest.fixture
def invalid_skill_dir():
    """Create a temporary skill directory with invalid SKILL.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_path = Path(tmpdir) / "invalid-skill"
        skill_path.mkdir()
        
        # Create invalid SKILL.yaml (missing required fields)
        yaml_content = """
name: InvalidName  # Invalid: uppercase
version: "not-semver"  # Invalid: not semver
"""
        (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
        
        yield skill_path


# =============================================================================
# PARSE SKILL YAML TESTS
# =============================================================================

class TestParseSkillYaml:
    """Test SKILL.yaml parsing."""
    
    def test_parse_valid_skill(self, temp_skill_dir):
        """Should parse a valid SKILL.yaml file."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        metadata = loader.parse_skill_yaml(temp_skill_dir)
        
        assert metadata.name == "test-skill"
        assert metadata.version == "1.0.0"
        assert metadata.description == "A test skill for unit testing"
        assert len(metadata.triggers) == 2
        assert metadata.triggers[0].pattern == "how do I test"
        assert metadata.triggers[0].confidence_threshold == 0.8
        assert metadata.requires_approval is False
        assert metadata.instructions_file == "instructions.md"
    
    def test_parse_missing_yaml_raises(self):
        """Should raise FileNotFoundError when SKILL.yaml is missing."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "no-yaml-skill"
            skill_path.mkdir()
            
            with pytest.raises(FileNotFoundError):
                loader.parse_skill_yaml(skill_path)
    
    def test_parse_empty_yaml_raises(self):
        """Should raise SkillValidationError when SKILL.yaml is empty."""
        from noctem.skills.loader import SkillLoader, SkillValidationError
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "empty-yaml-skill"
            skill_path.mkdir()
            (skill_path / "SKILL.yaml").write_text("", encoding='utf-8')
            
            with pytest.raises(SkillValidationError):
                loader.parse_skill_yaml(skill_path)
    
    def test_parse_triggers_list(self, temp_skill_dir):
        """Should parse multiple triggers correctly."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        metadata = loader.parse_skill_yaml(temp_skill_dir)
        
        assert len(metadata.triggers) == 2
        assert metadata.triggers[0].pattern == "how do I test"
        assert metadata.triggers[1].pattern == "test help"
        assert metadata.triggers[1].confidence_threshold == 0.7


# =============================================================================
# VALIDATE SKILL TESTS
# =============================================================================

class TestValidateSkill:
    """Test skill validation."""
    
    def test_validate_valid_skill(self, temp_skill_dir):
        """Should validate a correct skill structure."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        is_valid, errors = loader.validate_skill(temp_skill_dir)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_missing_directory(self):
        """Should fail when skill directory doesn't exist."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        is_valid, errors = loader.validate_skill(Path("/nonexistent/path"))
        
        assert is_valid is False
        assert any("does not exist" in e for e in errors)
    
    def test_validate_missing_yaml(self):
        """Should fail when SKILL.yaml is missing."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "no-yaml"
            skill_path.mkdir()
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("SKILL.yaml not found" in e for e in errors)
    
    def test_validate_invalid_name_uppercase(self):
        """Should fail when name contains uppercase."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "invalid-name"
            skill_path.mkdir()
            
            yaml_content = """
name: InvalidName
version: "1.0.0"
description: "Test"
triggers:
  - pattern: "test"
    confidence_threshold: 0.8
requires_approval: false
instructions_file: instructions.md
"""
            (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
            (skill_path / "instructions.md").write_text("# Test", encoding='utf-8')
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("lowercase" in e for e in errors)
    
    def test_validate_invalid_version_not_semver(self):
        """Should fail when version is not semver."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "invalid-version"
            skill_path.mkdir()
            
            yaml_content = """
name: test-skill
version: "not-semver"
description: "Test"
triggers:
  - pattern: "test"
    confidence_threshold: 0.8
requires_approval: false
instructions_file: instructions.md
"""
            (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
            (skill_path / "instructions.md").write_text("# Test", encoding='utf-8')
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("semver" in e for e in errors)
    
    def test_validate_empty_triggers(self):
        """Should fail when triggers list is empty."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "no-triggers"
            skill_path.mkdir()
            
            yaml_content = """
name: test-skill
version: "1.0.0"
description: "Test"
triggers: []
requires_approval: false
instructions_file: instructions.md
"""
            (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
            (skill_path / "instructions.md").write_text("# Test", encoding='utf-8')
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("at least one" in e for e in errors)
    
    def test_validate_confidence_out_of_range(self):
        """Should fail when confidence_threshold is out of range."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "bad-confidence"
            skill_path.mkdir()
            
            yaml_content = """
name: test-skill
version: "1.0.0"
description: "Test"
triggers:
  - pattern: "test"
    confidence_threshold: 0.3
requires_approval: false
instructions_file: instructions.md
"""
            (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
            (skill_path / "instructions.md").write_text("# Test", encoding='utf-8')
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("between 0.5 and 1.0" in e for e in errors)
    
    def test_validate_missing_instructions_file(self):
        """Should fail when instructions file doesn't exist."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "no-instructions"
            skill_path.mkdir()
            
            yaml_content = """
name: test-skill
version: "1.0.0"
description: "Test"
triggers:
  - pattern: "test"
    confidence_threshold: 0.8
requires_approval: false
instructions_file: instructions.md
"""
            (skill_path / "SKILL.yaml").write_text(yaml_content, encoding='utf-8')
            # Note: Not creating instructions.md
            
            is_valid, errors = loader.validate_skill(skill_path)
            
            assert is_valid is False
            assert any("instructions_file not found" in e for e in errors)


# =============================================================================
# LOAD INSTRUCTIONS TESTS
# =============================================================================

class TestLoadInstructions:
    """Test loading instructions.md."""
    
    def test_load_instructions_success(self, temp_skill_dir):
        """Should load instructions.md content."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        metadata = loader.parse_skill_yaml(temp_skill_dir)
        instructions = loader.load_instructions(metadata, temp_skill_dir)
        
        assert "# Test Skill Instructions" in instructions
        assert "Step one" in instructions
    
    def test_load_instructions_missing_raises(self, temp_skill_dir):
        """Should raise FileNotFoundError when instructions file is missing."""
        from noctem.skills.loader import SkillLoader
        from noctem.models import SkillMetadata
        
        loader = SkillLoader()
        
        # Create metadata pointing to nonexistent file
        metadata = SkillMetadata(
            name="test",
            instructions_file="nonexistent.md"
        )
        
        with pytest.raises(FileNotFoundError):
            loader.load_instructions(metadata, temp_skill_dir)


# =============================================================================
# RESOURCE ACCESS TESTS
# =============================================================================

class TestResourceAccess:
    """Test skill resource access."""
    
    def test_get_existing_resource(self, temp_skill_dir):
        """Should return path to existing resource."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        resource_path = loader.get_skill_resources(temp_skill_dir, "template.txt")
        
        assert resource_path is not None
        assert resource_path.exists()
        assert resource_path.read_text() == "Template content"
    
    def test_get_nonexistent_resource(self, temp_skill_dir):
        """Should return None for nonexistent resource."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        resource_path = loader.get_skill_resources(temp_skill_dir, "nonexistent.txt")
        
        assert resource_path is None
    
    def test_list_skill_resources(self, temp_skill_dir):
        """Should list all resources in skill directory."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        resources = loader.list_skill_resources(temp_skill_dir)
        
        assert len(resources) >= 1
        assert any("template.txt" in str(r) for r in resources)
    
    def test_list_resources_empty_when_no_directory(self):
        """Should return empty list when no resources directory."""
        from noctem.skills.loader import SkillLoader
        
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_path = Path(tmpdir) / "no-resources"
            skill_path.mkdir()
            
            resources = loader.list_skill_resources(skill_path)
            
            assert resources == []


# =============================================================================
# MODEL TESTS
# =============================================================================

class TestSkillModels:
    """Test Skill and SkillMetadata models."""
    
    def test_skill_trigger_to_dict(self):
        """SkillTrigger should serialize to dict correctly."""
        from noctem.models import SkillTrigger
        
        trigger = SkillTrigger(pattern="test pattern", confidence_threshold=0.85)
        d = trigger.to_dict()
        
        assert d["pattern"] == "test pattern"
        assert d["confidence_threshold"] == 0.85
    
    def test_skill_trigger_from_dict(self):
        """SkillTrigger should deserialize from dict correctly."""
        from noctem.models import SkillTrigger
        
        d = {"pattern": "test pattern", "confidence_threshold": 0.85}
        trigger = SkillTrigger.from_dict(d)
        
        assert trigger.pattern == "test pattern"
        assert trigger.confidence_threshold == 0.85
    
    def test_skill_metadata_to_dict(self):
        """SkillMetadata should serialize to dict correctly."""
        from noctem.models import SkillMetadata, SkillTrigger
        
        metadata = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            description="Test description",
            triggers=[SkillTrigger(pattern="test", confidence_threshold=0.8)],
            requires_approval=True,
        )
        d = metadata.to_dict()
        
        assert d["name"] == "test-skill"
        assert d["version"] == "1.0.0"
        assert len(d["triggers"]) == 1
        assert d["triggers"][0]["pattern"] == "test"
    
    def test_skill_success_rate(self):
        """Skill should calculate success rate correctly."""
        from noctem.models import Skill
        
        skill = Skill(
            name="test",
            use_count=10,
            success_count=8,
            failure_count=2,
        )
        
        assert skill.success_rate == 80.0
    
    def test_skill_success_rate_no_uses(self):
        """Skill with no uses should return None for success rate."""
        from noctem.models import Skill
        
        skill = Skill(name="test", use_count=0)
        
        assert skill.success_rate is None
    
    def test_skill_triggers_json(self):
        """Skill should serialize triggers to JSON for DB storage."""
        from noctem.models import Skill, SkillTrigger
        
        skill = Skill(
            name="test",
            triggers=[
                SkillTrigger(pattern="pattern1", confidence_threshold=0.8),
                SkillTrigger(pattern="pattern2", confidence_threshold=0.7),
            ]
        )
        
        json_str = skill.triggers_json()
        
        assert "pattern1" in json_str
        assert "pattern2" in json_str
        assert "0.8" in json_str
