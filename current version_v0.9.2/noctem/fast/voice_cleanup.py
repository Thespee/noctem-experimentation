"""
Voice cleanup utility for Noctem v0.6.0 Polish.

Light normalization of voice transcripts to improve classification accuracy.
Removes filler words and normalizes hesitation patterns while preserving semantic content.
"""
import re
from typing import List


# Filler words to remove (common in speech but not in typed text)
FILLER_WORDS = {
    "um", "uh", "umm", "uhh", "er", "err", "ah", "ahh",
    "like", "you know", "i mean", "sort of", "kind of",
    "basically", "actually", "literally", "honestly",
    "so yeah", "yeah so", "and yeah",
}

# Patterns for filler phrases (regex patterns)
FILLER_PATTERNS = [
    r'\b(um+|uh+|er+|ah+)\b',
    r'\b(you know)\b',
    r'\b(i mean)\b',
    r'\b(sort of|kind of)\b',
    r'\b(basically|actually|literally|honestly)\s*,?\s*',
    r'\b(so yeah|yeah so|and yeah)\b',
]

# Hesitation patterns to normalize
HESITATION_PATTERNS = [
    # "I... I need to" → "I need to"
    (r'\b(\w+)\s*\.{2,}\s*\1\b', r'\1'),
    # "I I need to" → "I need to"
    (r'\b(\w+)\s+\1\b', r'\1'),
    # Multiple spaces → single space
    (r'\s{2,}', ' '),
    # Remove leading/trailing commas from cleanup
    (r'^,\s*', ''),
    (r'\s*,$', ''),
    # Clean up punctuation after filler removal
    (r'\s+([,\.!?])', r'\1'),
    (r'([,\.!?])\s*([,\.!?])+', r'\1'),
]

# Words that should be capitalized at sentence start
SENTENCE_STARTERS = {'i', "i'm", "i've", "i'll", "i'd"}


def remove_fillers(text: str) -> str:
    """
    Remove filler words and phrases from text.
    
    Args:
        text: Raw voice transcript
    
    Returns:
        Text with filler words removed
    """
    result = text
    
    # Apply regex patterns for fillers
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    return result


def normalize_hesitations(text: str) -> str:
    """
    Normalize hesitation patterns in text.
    
    Args:
        text: Text possibly containing hesitations
    
    Returns:
        Text with hesitations normalized
    """
    result = text
    
    for pattern, replacement in HESITATION_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def fix_capitalization(text: str) -> str:
    """
    Fix capitalization issues common in voice transcripts.
    
    Args:
        text: Text to fix
    
    Returns:
        Text with improved capitalization
    """
    if not text:
        return text
    
    # Capitalize first letter
    result = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
    
    # Fix "i" → "I" as standalone word
    result = re.sub(r'\bi\b', 'I', result)
    result = re.sub(r"\bi'm\b", "I'm", result, flags=re.IGNORECASE)
    result = re.sub(r"\bi've\b", "I've", result, flags=re.IGNORECASE)
    result = re.sub(r"\bi'll\b", "I'll", result, flags=re.IGNORECASE)
    result = re.sub(r"\bi'd\b", "I'd", result, flags=re.IGNORECASE)
    
    # Capitalize after sentence-ending punctuation
    result = re.sub(r'([.!?])\s+([a-z])', lambda m: m.group(1) + ' ' + m.group(2).upper(), result)
    
    return result


def clean_voice_transcript(text: str) -> str:
    """
    Full cleanup pipeline for voice transcripts.
    
    Args:
        text: Raw voice transcript from Whisper
    
    Returns:
        Cleaned text suitable for classification
    """
    if not text:
        return text
    
    result = text.strip()
    
    # Step 1: Remove filler words
    result = remove_fillers(result)
    
    # Step 2: Normalize hesitations
    result = normalize_hesitations(result)
    
    # Step 3: Fix whitespace
    result = ' '.join(result.split())
    
    # Step 4: Fix capitalization
    result = fix_capitalization(result)
    
    return result.strip()


def get_cleanup_diff(original: str, cleaned: str) -> List[str]:
    """
    Get a list of changes made during cleanup.
    Useful for debugging/logging.
    
    Args:
        original: Original text
        cleaned: Cleaned text
    
    Returns:
        List of change descriptions
    """
    changes = []
    
    if original.lower() != cleaned.lower():
        # Check for filler removal
        for pattern in FILLER_PATTERNS:
            if re.search(pattern, original, flags=re.IGNORECASE):
                changes.append("removed filler words")
                break
        
        # Check for hesitation normalization
        for pattern, _ in HESITATION_PATTERNS[:2]:  # Only check the repetition patterns
            if re.search(pattern, original, flags=re.IGNORECASE):
                changes.append("normalized hesitations")
                break
    
    if len(original) != len(cleaned):
        diff = len(original) - len(cleaned)
        if diff > 0:
            changes.append(f"reduced by {diff} chars")
    
    return changes if changes else ["no changes"]
