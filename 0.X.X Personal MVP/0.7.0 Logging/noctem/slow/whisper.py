"""
Whisper transcription service for voice journals.
Uses faster-whisper with CTranslate2 backend for efficient local inference.
"""
import os
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Model sizes: tiny, base, small, medium, large-v2, large-v3
# tiny = ~39M params, fastest, least accurate
# For CPU-only, tiny or base recommended
DEFAULT_MODEL = "tiny"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"  # Quantized for CPU efficiency


class WhisperService:
    """Local whisper transcription service."""
    
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
    
    def _ensure_model(self):
        """Lazy-load the model on first use."""
        if self._model is None:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Whisper model loaded successfully")
        return self._model
    
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> Tuple[str, dict]:
        """
        Transcribe an audio file to text.
        
        Args:
            audio_path: Path to audio file (mp3, wav, ogg, etc.)
            language: Optional language code (e.g., 'en'). Auto-detected if None.
            
        Returns:
            Tuple of (transcription_text, metadata_dict)
        """
        model = self._ensure_model()
        
        logger.info(f"Transcribing: {audio_path}")
        
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,  # Filter out silence
        )
        
        # Collect all segments into full text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())
        
        full_text = " ".join(text_parts)
        
        metadata = {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "model": self.model_size,
        }
        
        logger.info(f"Transcription complete: {len(full_text)} chars, {info.duration:.1f}s audio")
        
        return full_text, metadata
    
    def is_ready(self) -> bool:
        """Check if the service can be initialized."""
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False
    
    def preload(self) -> bool:
        """
        Pre-download and cache the model.
        Returns True if successful.
        """
        try:
            self._ensure_model()
            return True
        except Exception as e:
            logger.error(f"Failed to preload Whisper model: {e}")
            return False


# Singleton instance for the application
_whisper_service: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    """Get or create the whisper service singleton."""
    global _whisper_service
    if _whisper_service is None:
        _whisper_service = WhisperService()
    return _whisper_service


def transcribe_audio(audio_path: str, language: Optional[str] = None) -> Tuple[str, dict]:
    """Convenience function to transcribe audio."""
    service = get_whisper_service()
    return service.transcribe(audio_path, language)
