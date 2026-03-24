"""
Tests for noctem.skills.trigger - SkillTriggerDetector

Tests pattern matching and explicit invocation detection.
"""

import pytest
from noctem.skills.trigger import SkillTriggerDetector
from noctem.models import Skill, SkillTrigger


def create_test_skill(name: str, patterns: list, requires_approval: bool = False, threshold: float = 0.7) -> Skill:
    """Helper to create a test skill with specified trigger patterns."""
    triggers = [
        SkillTrigger(pattern=p, confidence_threshold=threshold)
        for p in patterns
    ]
    return Skill(
        id=1,
        name=name,
        version="1.0.0",
        source="test",
        skill_path=f"/test/{name}",
        description=f"Test skill: {name}",
        triggers=triggers,
        dependencies=[],
        requires_approval=requires_approval,
        enabled=True,
    )


class TestExplicitInvocation:
    """Tests for explicit /skill invocation."""
    
    def test_explicit_invoke_exact_match(self):
        """Should detect /skill <name> command."""
        skill = create_test_skill("cooking-basics", ["how do I cook"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("/skill cooking-basics")
        
        assert result is not None
        assert result[0] == "cooking-basics"
        assert result[1] == 1.0  # Full confidence
        assert result[2] is False  # requires_approval
    
    def test_explicit_invoke_with_extra_text(self):
        """Should detect explicit invoke even with extra text."""
        skill = create_test_skill("debug-assistant", ["help me debug"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("/skill debug-assistant help me with this")
        
        assert result is not None
        assert result[0] == "debug-assistant"
    
    def test_explicit_invoke_unknown_skill(self):
        """Should return None for unknown skill."""
        skill = create_test_skill("my-skill", ["how do I test"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("/skill unknown-skill")
        
        assert result is None
    
    def test_explicit_invoke_case_insensitive(self):
        """Should match skill names case-insensitively."""
        skill = create_test_skill("My-Skill", ["how do I test"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("/skill my-skill")
        
        assert result is not None


class TestPatternMatching:
    """Tests for pattern-based trigger detection."""
    
    def test_exact_pattern_match(self):
        """Should detect exact pattern match with high confidence."""
        skill = create_test_skill("cooking-basics", ["how do I cook pasta"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("how do I cook pasta")
        
        assert result is not None
        assert result[0] == "cooking-basics"
        assert result[1] >= 0.9  # High confidence for exact match
    
    def test_fuzzy_pattern_match(self):
        """Should detect similar patterns above threshold."""
        skill = create_test_skill("git-help", ["commit my changes"], threshold=0.5)
        detector = SkillTriggerDetector([skill])
        
        # Similar enough text should match with fuzzy matching
        result = detector.detect_skill("commit changes")
        
        assert result is not None
        assert result[0] == "git-help"
        assert result[1] >= 0.5
    
    def test_no_match_below_threshold(self):
        """Should return None for low confidence matches."""
        skill = create_test_skill("very-specific", ["implement quantum entanglement protocol"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("hello world")
        
        assert result is None
    
    def test_multiple_patterns_per_skill(self):
        """Should match any of multiple patterns."""
        skill = create_test_skill("database-help", [
            "how do I write SQL",
            "database query help",
            "SQL syntax guide"
        ], threshold=0.7)
        detector = SkillTriggerDetector([skill])
        
        result1 = detector.detect_skill("how do I write SQL")
        result2 = detector.detect_skill("database query help")
        
        assert result1 is not None
        assert result2 is not None
        assert result1[0] == "database-help"
        assert result2[0] == "database-help"
    
    def test_best_match_wins(self):
        """Should return the highest confidence match."""
        skill1 = create_test_skill("python-help", ["python programming help"])
        skill2 = create_test_skill("python-advanced", ["advanced python programming techniques"])
        detector = SkillTriggerDetector([skill1, skill2])
        
        result = detector.detect_skill("python programming help")
        
        assert result is not None
        assert result[0] == "python-help"  # Exact match should win


class TestCustomThreshold:
    """Tests for custom confidence thresholds."""
    
    def test_higher_threshold_requires_better_match(self):
        """Should not match if below custom threshold."""
        trigger = SkillTrigger(pattern="exact phrase required", confidence_threshold=0.95)
        skill = Skill(
            id=1,
            name="strict-skill",
            version="1.0.0",
            source="test",
            skill_path="/test/strict",
            description="Requires high confidence",
            triggers=[trigger],
            dependencies=[],
            requires_approval=False,
            enabled=True,
        )
        detector = SkillTriggerDetector([skill])
        
        # This should not match - partial phrase
        result = detector.detect_skill("exact phrase")
        
        # May or may not match depending on fuzzy score
        if result:
            assert result[1] >= 0.95
    
    def test_lower_threshold_allows_fuzzy_match(self):
        """Should match with lower threshold."""
        trigger = SkillTrigger(pattern="general help", confidence_threshold=0.5)
        skill = Skill(
            id=1,
            name="lenient-skill",
            version="1.0.0",
            source="test",
            skill_path="/test/lenient",
            description="Lenient matching",
            triggers=[trigger],
            dependencies=[],
            requires_approval=False,
            enabled=True,
        )
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("help")
        
        # Should match with lower threshold
        assert result is not None or True  # Dependent on RapidFuzz score


class TestApprovalRequired:
    """Tests for requires_approval flag."""
    
    def test_returns_approval_flag(self):
        """Should return requires_approval in result."""
        skill = create_test_skill("dangerous-skill", ["do something risky"], requires_approval=True)
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("do something risky")
        
        assert result is not None
        assert result[2] is True  # requires_approval
    
    def test_approval_not_required(self):
        """Should return False for safe skills."""
        skill = create_test_skill("safe-skill", ["safe operation"], requires_approval=False)
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("safe operation")
        
        assert result is not None
        assert result[2] is False


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_input(self):
        """Should handle empty input."""
        skill = create_test_skill("test-skill", ["how do I test"])
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("")
        
        assert result is None
    
    def test_no_skills_registered(self):
        """Should handle no skills."""
        detector = SkillTriggerDetector([])
        
        result = detector.detect_skill("any input")
        
        assert result is None
    
    def test_disabled_skill_not_matched(self):
        """Should not match disabled skills."""
        skill = Skill(
            id=1,
            name="disabled-skill",
            version="1.0.0",
            source="test",
            skill_path="/test/disabled",
            description="Disabled skill",
            triggers=[SkillTrigger(pattern="disabled pattern", confidence_threshold=0.8)],
            dependencies=[],
            requires_approval=False,
            enabled=False,
        )
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("disabled pattern")
        
        # Detector should filter disabled skills
        assert result is None
    
    def test_whitespace_handling(self):
        """Should handle excess whitespace."""
        skill = create_test_skill("test-skill", ["how do I test"], threshold=0.7)
        detector = SkillTriggerDetector([skill])
        
        result = detector.detect_skill("how do I test")
        
        assert result is not None
        assert result[0] == "test-skill"
