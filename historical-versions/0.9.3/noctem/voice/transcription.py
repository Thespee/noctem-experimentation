"""
Voice transcription service for v0.9.3.
Uses faster-whisper locally when available.
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "tiny"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"

try:
    from faster_whisper import WhisperModel as _WhisperModel
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    _FASTER_WHISPER_AVAILABLE = False
    _WhisperModel = None
    logger.warning(
        "faster-whisper not installed. Voice transcription will be unavailable. "
        "Install with: pip install faster-whisper"
    )


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
        if not _FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is not installed. Install with: pip install faster-whisper"
            )
        if self._model is None:
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self._model = _WhisperModel(
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
        model = self._ensure_model()
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        text_parts = [segment.text.strip() for segment in segments]
        full_text = " ".join([p for p in text_parts if p])
        metadata = {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "model": self.model_size,
        }
        return full_text, metadata

    def is_ready(self) -> bool:
        return _FASTER_WHISPER_AVAILABLE

    def preload(self) -> bool:
        try:
            self._ensure_model()
            return True
        except Exception as e:
            logger.error(f"Failed to preload Whisper model: {e}")
            return False


_whisper_service: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    global _whisper_service
    if _whisper_service is None:
        _whisper_service = WhisperService()
    return _whisper_service


def transcribe_audio(audio_path: str, language: Optional[str] = None) -> Tuple[str, dict]:
    service = get_whisper_service()
    return service.transcribe(audio_path, language)
