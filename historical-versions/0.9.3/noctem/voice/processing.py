"""Voice journal processing pipeline for v0.9.3."""
import logging

from .journals import (
    get_pending_journals,
    mark_transcribing,
    complete_transcription,
    fail_transcription,
)
from .transcription import get_whisper_service
from ..fast.capture import process_voice_transcription

logger = logging.getLogger(__name__)


def process_pending_voice_journals(max_items: int = 1) -> int:
    """
    Process pending voice journals:
    1) transcribe audio
    2) persist transcription
    3) route transcription through thought/task capture
    """
    pending = get_pending_journals()
    if not pending:
        return 0

    whisper = get_whisper_service()
    count = 0

    for journal in pending[:max_items]:
        journal_id = journal["id"]
        audio_path = journal["audio_path"]
        mark_transcribing(journal_id)

        try:
            text, metadata = whisper.transcribe(audio_path)
            complete_transcription(
                journal_id,
                transcription=text,
                duration_seconds=metadata.get("duration"),
                language=metadata.get("language"),
            )
            if text and text.strip():
                process_voice_transcription(text, journal_id)
            count += 1
            logger.info(f"Voice journal {journal_id} transcribed and routed")
        except Exception as e:
            logger.error(f"Voice journal {journal_id} transcription failed: {e}")
            fail_transcription(journal_id, str(e))

    return count
