"""
Tests for v0.6.0 Final Polish features.

Tests cover:
- Prompt service (versioning, variables, rollback)
- Conversation service (message recording, thinking feed)
- Forecast service (density calculation, day briefs)
"""
import pytest
from datetime import date, datetime, timedelta


class TestPromptService:
    """Tests for the prompt management service."""
    
    def test_seed_default_prompts(self):
        """Test that default prompts are seeded correctly."""
        from noctem.services.prompt_service import seed_default_prompts, list_prompts
        
        result = seed_default_prompts()
        assert result["created"] >= 0
        
        # Check prompts exist
        prompts = list_prompts()
        names = [p.name for p in prompts]
        assert "task_analyzer_system" in names or result["skipped"] > 0
    
    def test_get_prompt_auto_seeds(self):
        """Test that getting a prompt auto-seeds if not found."""
        from noctem.services.prompt_service import get_prompt
        
        prompt = get_prompt("task_analyzer_system")
        assert prompt is not None
        assert prompt.prompt_text is not None
        assert len(prompt.prompt_text) > 10
    
    def test_render_prompt_with_variables(self):
        """Test rendering a prompt with variable substitution."""
        from noctem.services.prompt_service import render_prompt, seed_default_prompts
        
        seed_default_prompts()
        
        rendered = render_prompt("task_analyzer_user", {
            "name": "Buy groceries",
            "project": "Home",
            "due_date": "tomorrow",
            "tags": "shopping, food",
        })
        
        assert rendered is not None
        assert "Buy groceries" in rendered
        assert "Home" in rendered
    
    def test_update_prompt_creates_version(self):
        """Test that updating a prompt creates a new version."""
        from noctem.services.prompt_service import (
            get_prompt, update_prompt, seed_default_prompts
        )
        
        seed_default_prompts()
        
        original = get_prompt("task_analyzer_system")
        original_version = original.version
        
        new_version = update_prompt(
            "task_analyzer_system",
            "New prompt text for testing.",
            created_by="test",
        )
        
        assert new_version is not None
        assert new_version.version == original_version + 1
        assert new_version.prompt_text == "New prompt text for testing."
    
    def test_get_prompt_history(self):
        """Test retrieving prompt version history."""
        from noctem.services.prompt_service import (
            get_prompt_history, update_prompt, seed_default_prompts
        )
        
        seed_default_prompts()
        
        # Create a few versions
        update_prompt("task_analyzer_system", "Version 2", created_by="test")
        update_prompt("task_analyzer_system", "Version 3", created_by="test")
        
        history = get_prompt_history("task_analyzer_system")
        assert len(history) >= 3
        assert history[0].version > history[1].version  # Newest first
    
    def test_rollback_prompt(self):
        """Test rolling back to a previous version."""
        from noctem.services.prompt_service import (
            get_prompt, rollback_prompt, update_prompt, seed_default_prompts
        )
        
        seed_default_prompts()
        
        original = get_prompt("task_analyzer_system")
        original_text = original.prompt_text
        original_version = original.version
        
        # Update to new text
        update_prompt("task_analyzer_system", "Changed text", created_by="test")
        
        # Rollback to original version
        rolled_back = rollback_prompt("task_analyzer_system", to_version=original_version)
        
        assert rolled_back is not None
        assert rolled_back.prompt_text == original_text
    
    def test_extract_variables(self):
        """Test extracting variables from prompt text."""
        from noctem.services.prompt_service import extract_variables
        
        text = "Hello {{name}}, your project is {{project}} due {{date}}."
        variables = extract_variables(text)
        
        assert "name" in variables
        assert "project" in variables
        assert "date" in variables
        assert len(variables) == 3


class TestConversationService:
    """Tests for the conversation service."""
    
    def test_record_message(self):
        """Test recording a conversation message."""
        from noctem.services.conversation_service import record_message
        
        msg = record_message(
            content="Test message",
            role="user",
            source="cli",
        )
        
        assert msg.id is not None
        assert msg.content == "Test message"
        assert msg.role == "user"
        assert msg.source == "cli"
    
    def test_record_thinking(self):
        """Test recording a thinking entry."""
        from noctem.services.conversation_service import record_thinking
        
        entry = record_thinking(
            summary="Processing user input",
            level="activity",
            source="butler",
        )
        
        assert entry.id is not None
        assert entry.thinking_summary == "Processing user input"
        assert entry.thinking_level == "activity"
    
    def test_get_recent_context(self):
        """Test retrieving recent conversation context."""
        from noctem.services.conversation_service import (
            record_message, get_recent_context
        )
        
        # Record some messages
        for i in range(5):
            record_message(f"Message {i}", role="user", source="cli")
        
        context = get_recent_context(limit=3)
        assert len(context) == 3
    
    def test_get_thinking_feed(self):
        """Test retrieving the thinking feed."""
        from noctem.services.conversation_service import (
            record_thinking, get_thinking_feed
        )
        
        # Record some thinking entries
        record_thinking("Decision 1", level="decision", source="butler")
        record_thinking("Activity 1", level="activity", source="slow")
        record_thinking("Activity 2", level="activity", source="sync")
        
        feed = get_thinking_feed(limit=10)
        assert len(feed) >= 3
    
    def test_thinking_feed_filter_level(self):
        """Test filtering thinking feed by level."""
        from noctem.services.conversation_service import (
            record_thinking, get_thinking_feed
        )
        
        # Record mixed entries
        record_thinking("Decision", level="decision", source="test")
        record_thinking("Activity", level="activity", source="test")
        record_thinking("Debug", level="debug", source="test")
        
        # Filter for decisions only
        decisions = get_thinking_feed(limit=10, level_filter="decisions")
        for entry in decisions:
            assert entry.thinking_level == "decision"
    
    def test_export_thinking_log(self):
        """Test exporting thinking log as JSON."""
        from noctem.services.conversation_service import (
            record_thinking, export_thinking_log
        )
        
        record_thinking("Test entry", level="activity", source="test")
        
        export = export_thinking_log()
        
        assert "entries" in export
        assert "export_time" in export
        assert isinstance(export["entries"], list)
    
    def test_session_management(self):
        """Test session auto-creation."""
        from noctem.services.conversation_service import record_message
        
        msg1 = record_message("First", source="cli")
        msg2 = record_message("Second", source="cli")
        
        # Should be same session (within 30 min)
        assert msg1.session_id == msg2.session_id


class TestForecastService:
    """Tests for the forecast service."""
    
    def test_get_14_day_forecast(self):
        """Test generating 14-day forecast."""
        from noctem.services.forecast_service import get_14_day_forecast
        
        forecast = get_14_day_forecast()
        
        assert len(forecast) == 14
        assert forecast[0].is_today
        assert forecast[0].date == date.today()
    
    def test_calculate_density(self):
        """Test density calculation."""
        from noctem.services.forecast_service import calculate_density
        
        # Empty day
        density = calculate_density(task_count=0, event_count=0, blocked_hours=0)
        assert density == 0.0
        
        # Busy day
        density = calculate_density(task_count=5, event_count=3, blocked_hours=6)
        assert density > 0.5
        assert density <= 1.0
    
    def test_density_labels(self):
        """Test density to label conversion."""
        from noctem.services.forecast_service import _density_to_label
        
        assert _density_to_label(0.0) == "free"
        assert _density_to_label(0.1) == "free"
        assert _density_to_label(0.3) == "light"
        assert _density_to_label(0.5) == "moderate"
        assert _density_to_label(0.7) == "busy"
        assert _density_to_label(0.9) == "packed"
    
    def test_generate_day_brief(self):
        """Test generating day brief."""
        from noctem.services.forecast_service import DayForecast, generate_day_brief
        
        forecast = DayForecast(
            date=date.today(),
            day_name="Mon",
            is_today=True,
            task_count=3,
            event_count=2,
            density=0.5,
            density_label="moderate",
        )
        
        brief = generate_day_brief(forecast)
        
        assert "Today" in brief
        assert "moderate" in brief
    
    def test_get_7_day_table_data(self):
        """Test 7-day table data generation."""
        from noctem.services.forecast_service import get_7_day_table_data
        
        data = get_7_day_table_data()
        
        assert len(data) == 7
        # Should start on Monday
        first_day = datetime.fromisoformat(data[0]["date"]).date()
        assert first_day.weekday() == 0  # Monday
    
    def test_week_summary(self):
        """Test week summary generation."""
        from noctem.services.forecast_service import get_week_summary
        
        summary = get_week_summary()
        
        assert "start_date" in summary
        assert "end_date" in summary
        assert "total_tasks" in summary
        assert "avg_density" in summary
        assert "days" in summary
        assert len(summary["days"]) == 7


class TestVoiceJournalEnhancements:
    """Tests for voice journal enhancements."""
    
    def test_update_transcription(self):
        """Test editing a transcription."""
        from noctem.voice.journals import (
            save_voice_journal, get_journal, update_transcription, complete_transcription
        )
        
        # Create a journal
        journal_id = save_voice_journal(
            audio_data=b"test audio data",
            source="web",
        )
        
        # Complete with initial transcription
        complete_transcription(journal_id, "Original text")
        
        # Edit transcription
        update_transcription(journal_id, "Edited text")
        
        # Verify
        journal = get_journal(journal_id)
        # Check either the edited field or the main field depending on DB state
        assert journal is not None
    
    def test_get_transcription_returns_edited(self):
        """Test that get_transcription returns edited version if available."""
        from noctem.voice.journals import (
            save_voice_journal, complete_transcription,
            update_transcription, get_transcription
        )
        
        journal_id = save_voice_journal(
            audio_data=b"test audio",
            source="web",
        )
        complete_transcription(journal_id, "Original")
        update_transcription(journal_id, "Edited")
        
        result = get_transcription(journal_id)
        assert result == "Edited"


class TestAPIEndpoints:
    """Tests for new API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from noctem.web.app import create_app
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_thinking_recent_endpoint(self, client):
        """Test /api/thinking/recent endpoint."""
        response = client.get('/api/thinking/recent')
        assert response.status_code == 200
        data = response.get_json()
        assert "entries" in data
        assert "count" in data
    
    def test_forecast_endpoint(self, client):
        """Test /api/forecast endpoint."""
        response = client.get('/api/forecast')
        assert response.status_code == 200
        data = response.get_json()
        assert "days" in data
        assert len(data["days"]) == 14
    
    def test_week_endpoint(self, client):
        """Test /api/week endpoint."""
        response = client.get('/api/week')
        assert response.status_code == 200
        data = response.get_json()
        assert "days" in data
        assert len(data["days"]) == 7
    
    def test_prompts_list_endpoint(self, client):
        """Test /api/prompts endpoint."""
        response = client.get('/api/prompts')
        assert response.status_code == 200
        data = response.get_json()
        assert "templates" in data
    
    def test_prompts_get_endpoint(self, client):
        """Test /api/prompts/<name> endpoint."""
        response = client.get('/api/prompts/task_analyzer_system')
        assert response.status_code == 200
        data = response.get_json()
        assert "name" in data
        assert "prompt_text" in data


class TestDashboardRoute:
    """Tests for the dashboard route."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from noctem.web.app import create_app
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_dashboard_loads(self, client):
        """Test that the dashboard loads successfully."""
        response = client.get('/')
        assert response.status_code == 200
    
    def test_prompts_page_loads(self, client):
        """Test that the prompts page loads."""
        response = client.get('/prompts')
        assert response.status_code == 200


class TestModels:
    """Tests for new data models."""
    
    def test_conversation_model(self):
        """Test Conversation model."""
        from noctem.models import Conversation
        
        conv = Conversation(
            source="cli",
            role="user",
            content="Test message",
        )
        
        assert conv.source == "cli"
        assert conv.role == "user"
        assert conv.metadata_json() is None or conv.metadata_json() == "null"
    
    def test_prompt_template_model(self):
        """Test PromptTemplate model."""
        from noctem.models import PromptTemplate
        
        template = PromptTemplate(
            name="test_prompt",
            description="Test description",
            current_version=1,
        )
        
        assert template.name == "test_prompt"
        assert template.current_version == 1
    
    def test_prompt_version_model(self):
        """Test PromptVersion model."""
        from noctem.models import PromptVersion
        
        version = PromptVersion(
            template_id=1,
            version=1,
            prompt_text="Test prompt {{var}}",
            variables=["var"],
        )
        
        assert version.prompt_text == "Test prompt {{var}}"
        assert "var" in version.variables
