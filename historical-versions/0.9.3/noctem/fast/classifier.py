"""
Fast classifier for Noctem v0.6.0 Polish.

Rule-based classifier with confidence scoring to route inputs:
- Actionable (high confidence) → Task
- Note → Thought (stored)
- Ambiguous → Butler clarification queue
"""
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum

from ..parser.task_parser import parse_task, ParsedTask


class ThoughtKind(Enum):
    """Classification kinds for thoughts."""
    ACTIONABLE = "actionable"
    NOTE = "note"
    AMBIGUOUS = "ambiguous"


class AmbiguityReason(Enum):
    """Reasons for ambiguity classification."""
    SCOPE = "scope"      # Could be project or task
    TIMING = "timing"    # When should this be done?
    INTENT = "intent"    # Reminder vs actionable


@dataclass
class ClassificationResult:
    """Result of classifying an input."""
    kind: ThoughtKind
    confidence: float  # 0.0-1.0
    ambiguity_reason: Optional[AmbiguityReason] = None
    parsed_task: Optional[ParsedTask] = None
    is_command: bool = False  # True if input is a system command, not a thought


# Confidence thresholds
HIGH_CONFIDENCE = 0.8
MEDIUM_CONFIDENCE = 0.5

# Action verbs that signal actionable items
ACTION_VERBS = {
    "buy", "get", "call", "email", "text", "send", "finish", "complete",
    "schedule", "book", "make", "write", "create", "submit", "pay",
    "fix", "repair", "clean", "organize", "prepare", "review", "check",
    "update", "cancel", "return", "pick up", "drop off", "meet",
    "remind", "follow up", "contact", "ask", "tell", "confirm"
}

# Note indicators
NOTE_PREFIXES = {"note:", "note -", "remember:", "idea:", "thought:"}
NOTE_KEYWORDS = {"learned", "realized", "interesting", "remember that", "fyi", "for later"}

# Ambiguity indicators
VAGUE_WORDS = {"thing", "stuff", "something", "that", "it", "maybe", "might", "probably"}
PROJECT_INDICATORS = {"project", "initiative", "effort", "work on", "start"}


def _has_action_verb(text: str) -> bool:
    """Check if text contains an action verb."""
    text_lower = text.lower()
    words = set(text_lower.split())
    
    # Check single-word verbs
    if words & ACTION_VERBS:
        return True
    
    # Check multi-word verbs
    for verb in ACTION_VERBS:
        if " " in verb and verb in text_lower:
            return True
    
    return False


def _has_temporal_marker(text: str) -> bool:
    """Check if text contains date/time indicators."""
    temporal_patterns = [
        r'\b(today|tomorrow|yesterday)\b',
        r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        r'\b(next|this)\s+(week|month|year)\b',
        r'\b(morning|afternoon|evening|night)\b',
        r'\b\d{1,2}(:\d{2})?\s*(am|pm)\b',
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}\b',
        r'\bby\s+(the\s+)?(end|start|beginning)\b',
        r'\b(due|deadline|before|after|until)\b',
        r'\bin\s+\d+\s+(days?|weeks?|hours?|minutes?)\b',
    ]
    
    text_lower = text.lower()
    for pattern in temporal_patterns:
        if re.search(pattern, text_lower):
            return True
    return False


def _has_importance_marker(text: str) -> bool:
    """Check for !1, !2, !3 importance markers."""
    return bool(re.search(r'![1-3](?:\b|$)', text))


def _has_project_tag(text: str) -> bool:
    """Check for /project or +project tags."""
    return bool(re.search(r'[/+]\w+', text))


def _is_note(text: str) -> Tuple[bool, float]:
    """
    Check if text is a note/memory.
    Returns (is_note, confidence).
    """
    text_lower = text.lower().strip()
    
    # Check for explicit note prefixes
    for prefix in NOTE_PREFIXES:
        if text_lower.startswith(prefix):
            return True, 0.95
    
    # Check for note keywords
    for keyword in NOTE_KEYWORDS:
        if keyword in text_lower:
            return True, 0.85
    
    return False, 0.0


def _is_command(text: str) -> bool:
    """Check if text is a system command (not a thought to capture)."""
    text_stripped = text.strip().lower()
    
    # Slash commands
    if text_stripped.startswith('/'):
        return True
    
    # Quick actions
    quick_actions = ['done', 'skip', 'delete', 'remove', 'habit done']
    for action in quick_actions:
        if text_stripped.startswith(action + ' '):
            return True
    
    # Navigation commands
    nav_commands = {'today', 'week', 'projects', 'habits', 'goals', 'status', 
                    'help', 'config', 'slow', 'suggest', 'web', 'quit', 'exit'}
    if text_stripped in nav_commands:
        return True
    
    # Correction command
    if text_stripped.startswith('*'):
        return True
    
    return False


def _calculate_actionable_confidence(text: str, parsed: ParsedTask) -> float:
    """
    Calculate confidence that text is actionable.
    Higher confidence = more signals present.
    """
    confidence = 0.3  # Base confidence
    
    # Strong signals (each adds significant confidence)
    if parsed.due_date:
        confidence += 0.25
    if parsed.due_time:
        confidence += 0.1
    if _has_importance_marker(text):
        confidence += 0.15
    if _has_project_tag(text):
        confidence += 0.1
    
    # Medium signals
    if _has_action_verb(text):
        confidence += 0.15
    if _has_temporal_marker(text) and not parsed.due_date:
        # Temporal marker but parser didn't extract date
        confidence += 0.1
    
    # Task name quality
    if parsed.name and len(parsed.name) > 3:
        confidence += 0.1
    
    # Penalize vague text
    text_lower = text.lower()
    vague_count = sum(1 for word in VAGUE_WORDS if word in text_lower.split())
    confidence -= vague_count * 0.1
    
    return min(1.0, max(0.0, confidence))


def _detect_ambiguity_reason(text: str, parsed: ParsedTask) -> Optional[AmbiguityReason]:
    """Determine why an input is ambiguous."""
    text_lower = text.lower()
    
    # Could be a project
    for indicator in PROJECT_INDICATORS:
        if indicator in text_lower:
            return AmbiguityReason.SCOPE
    
    # Very long text might be a project description
    if len(text.split()) > 15 and not parsed.due_date:
        return AmbiguityReason.SCOPE
    
    # No timing info at all
    if not parsed.due_date and not _has_temporal_marker(text):
        if _has_action_verb(text):
            return AmbiguityReason.TIMING
    
    # Vague intent
    vague_count = sum(1 for word in VAGUE_WORDS if word in text_lower.split())
    if vague_count >= 2:
        return AmbiguityReason.INTENT
    
    # Very short and vague
    if len(text.split()) <= 3 and not parsed.due_date and not _has_importance_marker(text):
        return AmbiguityReason.INTENT
    
    return None


def classify_input(text: str, source: str = "cli") -> ClassificationResult:
    """
    Classify an input and return routing decision with confidence.
    
    Args:
        text: The raw input text
        source: Where the input came from ('cli', 'telegram', 'web', 'voice')
    
    Returns:
        ClassificationResult with kind, confidence, and optional parsed task
    """
    text = text.strip()
    
    # Check if this is a command (not a thought)
    if _is_command(text):
        return ClassificationResult(
            kind=ThoughtKind.ACTIONABLE,
            confidence=1.0,
            is_command=True,
        )
    
    # Check if it's a note
    is_note, note_confidence = _is_note(text)
    if is_note:
        return ClassificationResult(
            kind=ThoughtKind.NOTE,
            confidence=note_confidence,
        )
    
    # Try to parse as a task
    parsed = parse_task(text)
    
    # Calculate actionable confidence
    confidence = _calculate_actionable_confidence(text, parsed)
    
    # High confidence = actionable
    if confidence >= HIGH_CONFIDENCE:
        return ClassificationResult(
            kind=ThoughtKind.ACTIONABLE,
            confidence=confidence,
            parsed_task=parsed,
        )
    
    # Medium confidence = actionable but flagged
    if confidence >= MEDIUM_CONFIDENCE:
        return ClassificationResult(
            kind=ThoughtKind.ACTIONABLE,
            confidence=confidence,
            parsed_task=parsed,
        )
    
    # Low confidence = ambiguous
    ambiguity_reason = _detect_ambiguity_reason(text, parsed)
    return ClassificationResult(
        kind=ThoughtKind.AMBIGUOUS,
        confidence=confidence,
        ambiguity_reason=ambiguity_reason,
        parsed_task=parsed,  # Keep parsed data in case clarification makes it a task
    )


def get_confidence_level(confidence: float) -> str:
    """Get human-readable confidence level."""
    if confidence >= HIGH_CONFIDENCE:
        return "high"
    elif confidence >= MEDIUM_CONFIDENCE:
        return "medium"
    else:
        return "low"
