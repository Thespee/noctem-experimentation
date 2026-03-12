"""
Skill Trigger Detector - Match user input to skills using fuzzy matching.

Uses RapidFuzz for efficient pattern matching with confidence thresholds.
Industry standard: 0.7-0.8 confidence threshold for routing (per Oracle, AWS Lex, Dialogflow).
"""

from typing import Optional, Tuple

from noctem.models import Skill, SkillTrigger

# Try to import rapidfuzz, fall back to basic matching if not available
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


class SkillTriggerDetector:
    """
    Detects skill triggers from user input using fuzzy matching.
    
    Uses a hybrid approach:
    - Explicit invocation: `/skill <name>` always routes directly (confidence=1.0)
    - Pattern matching: Fuzzy match against trigger patterns
    - Fallback: Return None if no confident match
    
    Usage:
        detector = SkillTriggerDetector(skills)
        result = detector.detect_skill("how do I cook pasta")
        if result:
            skill_name, confidence = result
    """
    
    # Default confidence threshold (0.8 = 80%)
    DEFAULT_THRESHOLD = 0.8
    
    def __init__(self, skills: list[Skill]):
        """
        Initialize detector with a list of enabled skills.
        
        Args:
            skills: List of Skill objects with triggers
        """
        self.skills = skills
        self._build_trigger_index()
    
    def _build_trigger_index(self):
        """Build an index mapping trigger patterns to skills and thresholds."""
        self.trigger_index = {}  # pattern -> (skill_name, threshold)
        self.all_patterns = []  # List of all patterns for matching
        
        for skill in self.skills:
            if not skill.enabled:
                continue
            
            for trigger in skill.triggers:
                pattern = trigger.pattern.lower()
                self.trigger_index[pattern] = (
                    skill.name,
                    trigger.confidence_threshold,
                    skill.requires_approval,
                )
                self.all_patterns.append(pattern)
    
    def detect_skill(self, input_text: str) -> Optional[Tuple[str, float, bool]]:
        """
        Detect if user input triggers a skill.
        
        Args:
            input_text: User's input text
            
        Returns:
            Tuple of (skill_name, confidence, requires_approval) or None if no match
        """
        if not input_text or not self.all_patterns:
            return None
        
        input_lower = input_text.lower().strip()
        
        # Check for explicit invocation first
        explicit_result = self._check_explicit_invocation(input_lower)
        if explicit_result:
            return explicit_result
        
        # Use fuzzy matching
        return self._fuzzy_match(input_lower)
    
    def _check_explicit_invocation(self, input_lower: str) -> Optional[Tuple[str, float, bool]]:
        """
        Check for explicit skill invocation like '/skill skill-name'.
        
        Returns:
            (skill_name, 1.0, requires_approval) if explicit match, None otherwise
        """
        # Pattern: /skill <name> or skill: <name>
        prefixes = ["/skill ", "skill: ", "skill:"]
        
        for prefix in prefixes:
            if input_lower.startswith(prefix):
                # Get just the skill name (ignore any extra text)
                remaining = input_lower[len(prefix):].strip()
                skill_name = remaining.split()[0] if remaining else ""
                
                # Look up the skill (must be enabled)
                for skill in self.skills:
                    if skill.name.lower() == skill_name.lower() and skill.enabled:
                        return (skill.name, 1.0, skill.requires_approval)
        
        return None
    
    def _fuzzy_match(self, input_lower: str) -> Optional[Tuple[str, float, bool]]:
        """
        Use fuzzy matching to find the best skill match.
        
        Returns:
            (skill_name, confidence, requires_approval) if match found, None otherwise
        """
        if not RAPIDFUZZ_AVAILABLE:
            return self._basic_match(input_lower)
        
        # Use RapidFuzz with WRatio scorer for best overall matching
        # WRatio combines multiple matching strategies
        matches = process.extract(
            input_lower,
            self.all_patterns,
            scorer=fuzz.WRatio,
            limit=3
        )
        
        if not matches:
            return None
        
        # Check the best match
        best_pattern, best_score, _ = matches[0]
        
        # Convert score from 0-100 to 0.0-1.0
        confidence = best_score / 100.0
        
        # Look up the skill info for this pattern
        if best_pattern in self.trigger_index:
            skill_name, threshold, requires_approval = self.trigger_index[best_pattern]
            
            # Only return if confidence meets threshold
            if confidence >= threshold:
                return (skill_name, confidence, requires_approval)
        
        return None
    
    def _basic_match(self, input_lower: str) -> Optional[Tuple[str, float, bool]]:
        """
        Basic matching without RapidFuzz (fallback).
        
        Uses simple substring matching with lower confidence.
        """
        best_match = None
        best_score = 0.0
        
        for pattern, (skill_name, threshold, requires_approval) in self.trigger_index.items():
            # Simple substring matching
            if pattern in input_lower or input_lower in pattern:
                # Calculate basic similarity
                shorter = min(len(pattern), len(input_lower))
                longer = max(len(pattern), len(input_lower))
                score = shorter / longer if longer > 0 else 0.0
                
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = (skill_name, score, requires_approval)
        
        return best_match
    
    def get_all_trigger_patterns(self) -> list[dict]:
        """
        Get all trigger patterns for debugging/display.
        
        Returns:
            List of dicts with pattern, skill_name, threshold
        """
        results = []
        for pattern, (skill_name, threshold, requires_approval) in self.trigger_index.items():
            results.append({
                "pattern": pattern,
                "skill_name": skill_name,
                "confidence_threshold": threshold,
                "requires_approval": requires_approval,
            })
        return results
    
    def add_skill(self, skill: Skill):
        """Add a skill to the detector at runtime."""
        self.skills.append(skill)
        
        for trigger in skill.triggers:
            pattern = trigger.pattern.lower()
            self.trigger_index[pattern] = (
                skill.name,
                trigger.confidence_threshold,
                skill.requires_approval,
            )
            self.all_patterns.append(pattern)
    
    def remove_skill(self, skill_name: str):
        """Remove a skill from the detector at runtime."""
        self.skills = [s for s in self.skills if s.name != skill_name]
        
        # Rebuild index
        patterns_to_remove = [
            p for p, (name, _, _) in self.trigger_index.items()
            if name == skill_name
        ]
        
        for pattern in patterns_to_remove:
            del self.trigger_index[pattern]
            self.all_patterns.remove(pattern)
