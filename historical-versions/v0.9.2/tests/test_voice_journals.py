"""
Tests for voice journal system (v0.6.0).
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestVoiceJournalStorage:
    """Tests for voice journal storage module."""
    
    def test_save_voice_journal_bytes(self, tmp_path, monkeypatch):
        """Test saving voice journal from raw bytes."""
        # Patch the AUDIO_DIR
        from noctem.voice import journals
        monkeypatch.setattr(journals, 'AUDIO_DIR', tmp_path)
        
        # Test data
        audio_data = b"fake audio data for testing"
        
        # Save
        journal_id = journals.save_voice_journal(
            audio_data=audio_data,
            source="web",
            original_filename="test.mp3",
            metadata={"test": True}
        )
        
        assert journal_id > 0
        
        # Verify file was saved
        saved_files = list(tmp_path.glob("*.mp3"))
        assert len(saved_files) == 1
        assert saved_files[0].read_bytes() == audio_data
    
    def test_save_voice_journal_telegram_source(self, tmp_path, monkeypatch):
        """Test saving voice journal from Telegram uses .ogg extension."""
        from noctem.voice import journals
        monkeypatch.setattr(journals, 'AUDIO_DIR', tmp_path)
        
        audio_data = b"telegram voice data"
        
        journal_id = journals.save_voice_journal(
            audio_data=audio_data,
            source="telegram",
        )
        
        # Should use .ogg for telegram without filename
        saved_files = list(tmp_path.glob("*.ogg"))
        assert len(saved_files) == 1
    
    def test_get_pending_journals_empty(self):
        """Test getting pending journals when none exist."""
        from noctem.voice.journals import get_pending_journals
        
        pending = get_pending_journals()
        # Should return list (possibly empty depending on DB state)
        assert isinstance(pending, list)
    
    def test_transcription_stats(self):
        """Test getting transcription stats."""
        from noctem.voice.journals import get_transcription_stats
        
        stats = get_transcription_stats()
        
        assert "pending" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "transcribing" in stats


class TestWhisperService:
    """Tests for Whisper transcription service."""
    
    def test_whisper_service_config(self):
        """Test WhisperService default configuration."""
        from noctem.slow.whisper import WhisperService, DEFAULT_MODEL, DEFAULT_DEVICE
        
        service = WhisperService()
        
        assert service.model_size == DEFAULT_MODEL
        assert service.device == DEFAULT_DEVICE
        assert service._model is None  # Lazy loaded
    
    def test_whisper_service_is_ready(self):
        """Test is_ready check returns bool based on faster-whisper availability."""
        from noctem.slow.whisper import WhisperService
        
        service = WhisperService()
        # is_ready() returns True if faster-whisper installed, False otherwise
        result = service.is_ready()
        assert isinstance(result, bool)
    
    def test_whisper_singleton(self):
        """Test get_whisper_service returns singleton."""
        from noctem.slow.whisper import get_whisper_service
        
        svc1 = get_whisper_service()
        svc2 = get_whisper_service()
        
        assert svc1 is svc2


class TestVoiceJournalImports:
    """Test that voice journal module imports work."""
    
    def test_import_journals_module(self):
        """Test importing journals module."""
        from noctem.voice import journals
        
        assert hasattr(journals, 'save_voice_journal')
        assert hasattr(journals, 'get_pending_journals')
        assert hasattr(journals, 'mark_transcribing')
        assert hasattr(journals, 'complete_transcription')
        assert hasattr(journals, 'fail_transcription')
    
    def test_import_whisper_module(self):
        """Test importing whisper module."""
        from noctem.slow import whisper
        
        assert hasattr(whisper, 'WhisperService')
        assert hasattr(whisper, 'get_whisper_service')
        assert hasattr(whisper, 'transcribe_audio')
    
    def test_import_voice_package(self):
        """Test importing voice package."""
        from noctem import voice
        
        assert hasattr(voice, 'save_voice_journal')
        assert hasattr(voice, 'get_all_journals')


class TestVoiceWebEndpoints:
    """Tests for voice journal web endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from noctem.web.app import create_app
        app = create_app()
        app.config['TESTING'] = True
        return app.test_client()
    
    def test_voice_page_loads(self, client):
        """Test voice journals page loads."""
        response = client.get('/voice')
        assert response.status_code == 200
        assert b'Voice Journals' in response.data
    
    def test_voice_list_api(self, client):
        """Test voice list API endpoint."""
        response = client.get('/api/voice/list')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'journals' in data
        assert 'stats' in data
    
    def test_voice_upload_no_file(self, client):
        """Test voice upload without file returns error."""
        response = client.post('/api/voice/upload')
        assert response.status_code == 400
        
        data = response.get_json()
        assert data['success'] == False


class TestTelegramVoiceHandler:
    """Tests for Telegram voice message handler."""
    
    def test_handle_voice_import(self):
        """Test that handle_voice is importable."""
        from noctem.telegram.handlers import handle_voice
        assert handle_voice is not None
    
    def test_voice_handler_registered(self):
        """Test that voice handler is registered in bot."""
        # Mock the token so bot can be created
        with patch('noctem.config.Config.telegram_token', return_value='test:token'):
            from noctem.telegram.bot import create_bot
            from telegram.ext import MessageHandler
            
            app = create_bot()
            
            # Check handlers include a voice handler
            voice_handlers = [
                h for h in app.handlers.get(0, [])
                if isinstance(h, MessageHandler)
            ]
            assert len(voice_handlers) >= 2  # text + voice


class TestSlowModeVoiceTranscription:
    """Tests for voice transcription in slow mode loop."""
    
    def test_loop_has_voice_processing(self):
        """Test SlowModeLoop has voice transcription method."""
        from noctem.slow.loop import SlowModeLoop
        
        loop = SlowModeLoop()
        assert hasattr(loop, '_process_voice_transcriptions')
    
    def test_loop_imports_voice_journals(self):
        """Test slow loop imports voice journal functions."""
        from noctem.slow import loop
        
        # These should be imported
        assert hasattr(loop, 'get_pending_journals')
        assert hasattr(loop, 'mark_transcribing')
        assert hasattr(loop, 'complete_transcription')
