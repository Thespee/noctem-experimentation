"""
Tests for noctem.skills.executor - SkillExecutor

Tests execution flow, logging, and approval workflow.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from noctem.skills.executor import SkillExecutor, SkillApprovalRequired
from noctem.skills.registry import SkillRegistry
from noctem.models import Skill, SkillTrigger, SkillExecution


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
description: "A test skill"
triggers:
  - pattern: "how do I test"
    confidence_threshold: 0.8
dependencies: []
requires_approval: false
instructions_file: instructions.md
"""


@pytest.fixture
def approval_skill_yaml():
    return """
name: approval-skill
version: "1.0.0"
description: "A skill requiring approval"
triggers:
  - pattern: "do risky thing"
    confidence_threshold: 0.8
dependencies: []
requires_approval: true
instructions_file: instructions.md
"""


@pytest.fixture
def sample_instructions():
    return "# Test Skill\n\nThese are the instructions."


def create_skill_dir(base_path: Path, name: str, yaml_content: str, instructions: str):
    """Helper to create a skill directory."""
    skill_path = base_path / name
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.yaml").write_text(yaml_content, encoding="utf-8")
    (skill_path / "instructions.md").write_text(instructions, encoding="utf-8")
    return skill_path


class TestExecuteSkill:
    """Tests for execute_skill method."""
    
    def test_execute_simple_skill(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should execute a skill and return execution record."""
        bundled, user = temp_skill_dirs
        yaml = sample_skill_yaml.replace("test-skill", "simple-skill")
        create_skill_dir(bundled, "simple-skill", yaml, sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        execution = executor.execute_skill(
            "simple-skill",
            context={"input": "how do I test"},
            trigger_type="pattern_match",
            trigger_input="how do I test",
            trigger_confidence=0.95,
        )
        
        assert execution is not None
        assert execution.skill_name == "simple-skill"
        assert execution.status == "completed"
        assert execution.trigger_confidence == 0.95
    
    def test_execute_unknown_skill_raises(self, temp_skill_dirs):
        """Should raise ValueError for unknown skill."""
        bundled, user = temp_skill_dirs
        registry = SkillRegistry(bundled, user)
        executor = SkillExecutor(registry)
        
        with pytest.raises(ValueError, match="Skill 'nonexistent' not found"):
            executor.execute_skill("nonexistent", {}, "explicit", "", 1.0)
    
    def test_execute_disabled_skill_raises(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should raise ValueError for disabled skill."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "disabled-skill", sample_skill_yaml.replace("test-skill", "disabled-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        registry.disable_skill("disabled-skill")
        
        executor = SkillExecutor(registry)
        
        with pytest.raises(ValueError, match="Skill 'disabled-skill' is disabled"):
            executor.execute_skill("disabled-skill", {}, "explicit", "", 1.0)


class TestApprovalWorkflow:
    """Tests for approval workflow."""
    
    def test_approval_required_raises_exception(self, temp_skill_dirs, approval_skill_yaml, sample_instructions):
        """Should raise SkillApprovalRequired for skills needing approval."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "approval-skill", approval_skill_yaml, sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        with pytest.raises(SkillApprovalRequired) as exc_info:
            executor.execute_skill(
                "approval-skill",
                context={},
                trigger_type="pattern_match",
                trigger_input="do risky thing",
                trigger_confidence=0.9,
            )
        
        assert exc_info.value.skill_name == "approval-skill"
        assert exc_info.value.execution_id is not None
    
    def test_approval_required_creates_pending_execution(self, temp_skill_dirs, approval_skill_yaml, sample_instructions):
        """Should create pending execution record."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "approval-skill", approval_skill_yaml, sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        try:
            executor.execute_skill("approval-skill", {}, "explicit", "", 1.0)
        except SkillApprovalRequired as e:
            pending = executor.get_pending_approvals()
            
            assert len(pending) >= 1
            assert any(p.skill_name == "approval-skill" for p in pending)
    
    def test_approve_pending_execution(self, temp_skill_dirs, approval_skill_yaml, sample_instructions):
        """Should approve and complete pending execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "approval-skill", approval_skill_yaml, sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        # Trigger approval required
        execution_id = None
        try:
            executor.execute_skill("approval-skill", {}, "explicit", "", 1.0)
        except SkillApprovalRequired as e:
            execution_id = e.execution_id
        
        # Approve it
        if execution_id:
            execution = executor.approve_pending_execution(execution_id)
            
            assert execution.status == "completed"
            assert execution.approved is True
    
    def test_reject_pending_execution(self, temp_skill_dirs, approval_skill_yaml, sample_instructions):
        """Should reject pending execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "approval-skill", approval_skill_yaml, sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        # Trigger approval required
        execution_id = None
        try:
            executor.execute_skill("approval-skill", {}, "explicit", "", 1.0)
        except SkillApprovalRequired as e:
            execution_id = e.execution_id
        
        # Reject it
        if execution_id:
            execution = executor.reject_pending_execution(execution_id)
            
            assert execution.status == "rejected"
            assert execution.approved is False


class TestExecutionLogging:
    """Tests for execution logging."""
    
    def test_execution_includes_trace_id(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should include trace_id in execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "trace-skill", sample_skill_yaml.replace("test-skill", "trace-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        execution = executor.execute_skill(
            "trace-skill",
            context={"trace_id": "test-trace-123"},
            trigger_type="explicit",
            trigger_confidence=1.0,
        )
        
        assert execution.trace_id == "test-trace-123"
    
    def test_execution_records_timestamps(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should record start and end timestamps."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "time-skill", sample_skill_yaml.replace("test-skill", "time-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        execution = executor.execute_skill("time-skill", {}, "explicit", "", 1.0)
        
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert execution.completed_at >= execution.started_at


class TestSkillStats:
    """Tests for skill stats updates."""
    
    def test_successful_execution_updates_stats(self, temp_skill_dirs, sample_skill_yaml, sample_instructions):
        """Should update skill stats on successful execution."""
        bundled, user = temp_skill_dirs
        create_skill_dir(bundled, "stats-skill", sample_skill_yaml.replace("test-skill", "stats-skill"), sample_instructions)
        
        registry = SkillRegistry(bundled, user)
        registry.discover_skills()
        executor = SkillExecutor(registry)
        
        # Execute skill
        executor.execute_skill("stats-skill", {}, "explicit", "", 1.0)
        
        # Check stats
        skill = registry.get_skill("stats-skill")
        
        assert skill.use_count == 1
        assert skill.success_count == 1
        assert skill.failure_count == 0


class TestSkillApprovalRequiredException:
    """Tests for SkillApprovalRequired exception."""
    
    def test_exception_has_skill_name(self):
        """Should contain skill name."""
        exc = SkillApprovalRequired("my-skill", 123)
        
        assert exc.skill_name == "my-skill"
        assert exc.execution_id == 123
    
    def test_exception_message(self):
        """Should have descriptive message."""
        exc = SkillApprovalRequired("risky-skill", 456)
        
        assert "risky-skill" in str(exc)
        assert "approval" in str(exc).lower()
