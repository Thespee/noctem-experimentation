"""
Tests for Noctem v0.9.2 — UI/UX Overhaul & Fixes.

Covers:
- Task CRUD API endpoints
- All-day ICS event detection
- 14-day table data (2-week dashboard)
- Whisper graceful import
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from noctem.services import task_service, project_service
from noctem.services.forecast_service import (
    get_14_day_table_data,
    get_7_day_table_data,
    _build_table_day,
    calculate_density,
    _density_to_label,
)
from noctem.services.ics_import import parse_vevent, parse_ics_content


# =============================================================================
# Task CRUD (powers inline creation & check-off in upcoming/projects views)
# =============================================================================

class TestTaskCRUD:
    """Test task create, complete, and update operations."""

    def test_create_task_basic(self):
        task = task_service.create_task("Buy groceries")
        assert task.id is not None
        assert task.name == "Buy groceries"
        assert task.status == "not_started"

    def test_create_task_with_due_date(self):
        due = date.today() + timedelta(days=3)
        task = task_service.create_task("Report", due_date=due)
        assert task.due_date == due

    def test_create_task_with_project(self):
        proj = project_service.create_project("TestProj")
        task = task_service.create_task("Sub-task", project_id=proj.id)
        assert task.project_id == proj.id

    def test_complete_task(self):
        task = task_service.create_task("Finish this")
        completed = task_service.complete_task(task.id)
        assert completed is not None
        assert completed.status == "done"

    def test_complete_nonexistent_returns_none(self):
        result = task_service.complete_task(999999)
        assert result is None

    def test_update_task_name(self):
        task = task_service.create_task("Old name")
        updated = task_service.update_task(task.id, name="New name")
        assert updated.name == "New name"

    def test_update_task_due_date(self):
        task = task_service.create_task("Undated")
        new_date = date.today() + timedelta(days=7)
        updated = task_service.update_task(task.id, due_date=new_date)
        assert updated.due_date == new_date

    def test_update_task_status(self):
        task = task_service.create_task("In progress")
        updated = task_service.update_task(task.id, status="in_progress")
        assert updated.status == "in_progress"


# =============================================================================
# All-day ICS event detection
# =============================================================================

class TestAllDayICSDetection:
    """Test that DTSTART;VALUE=DATE produces all_day=True."""

    def _make_ics(self, dtstart_line, dtend_line=None):
        """Build minimal ICS bytes with given DTSTART/DTEND."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:test-allday@noctem",
            "SUMMARY:Test Event",
            dtstart_line,
        ]
        if dtend_line:
            lines.append(dtend_line)
        lines += ["END:VEVENT", "END:VCALENDAR"]
        return "\r\n".join(lines).encode("utf-8")

    def test_all_day_event_detected(self):
        """DTSTART;VALUE=DATE should set all_day=True."""
        content = self._make_ics(
            "DTSTART;VALUE=DATE:20260301",
            "DTEND;VALUE=DATE:20260302",
        )
        events = parse_ics_content(content)
        assert len(events) == 1
        assert events[0]["all_day"] is True

    def test_timed_event_not_all_day(self):
        """Normal DTSTART with time should set all_day=False."""
        content = self._make_ics(
            "DTSTART:20260301T140000Z",
            "DTEND:20260301T150000Z",
        )
        events = parse_ics_content(content)
        assert len(events) == 1
        assert events[0]["all_day"] is False

    def test_all_day_event_title(self):
        content = self._make_ics(
            "DTSTART;VALUE=DATE:20260415",
            "DTEND;VALUE=DATE:20260416",
        )
        events = parse_ics_content(content)
        assert events[0]["title"] == "Test Event"

    def test_all_day_event_start_is_datetime(self):
        """All-day events should have start_time as datetime (midnight)."""
        content = self._make_ics(
            "DTSTART;VALUE=DATE:20260301",
            "DTEND;VALUE=DATE:20260302",
        )
        events = parse_ics_content(content)
        assert isinstance(events[0]["start_time"], datetime)


# =============================================================================
# 14-day table data (2-week dashboard)
# =============================================================================

class TestForecast14Day:
    """Test get_14_day_table_data for the 2-week dashboard."""

    def test_returns_two_weeks(self):
        data = get_14_day_table_data()
        assert "current_week" in data
        assert "next_week" in data
        assert len(data["current_week"]) == 7
        assert len(data["next_week"]) == 7

    def test_current_week_starts_monday(self):
        data = get_14_day_table_data()
        first_day = date.fromisoformat(data["current_week"][0]["date"])
        assert first_day.weekday() == 0  # Monday

    def test_next_week_starts_monday(self):
        data = get_14_day_table_data()
        first_next = date.fromisoformat(data["next_week"][0]["date"])
        assert first_next.weekday() == 0

    def test_weeks_are_contiguous(self):
        data = get_14_day_table_data()
        last_current = date.fromisoformat(data["current_week"][6]["date"])
        first_next = date.fromisoformat(data["next_week"][0]["date"])
        assert (first_next - last_current).days == 1

    def test_today_flag_set(self):
        data = get_14_day_table_data()
        all_days = data["current_week"] + data["next_week"]
        today_flags = [d for d in all_days if d["is_today"]]
        assert len(today_flags) == 1

    def test_day_has_required_fields(self):
        data = get_14_day_table_data()
        day = data["current_week"][0]
        for field in ("date", "day_name", "density", "density_label", "tasks", "events"):
            assert field in day, f"Missing field: {field}"

    def test_density_calculation(self):
        d = calculate_density(task_count=3, event_count=2, blocked_hours=3)
        assert 0.0 <= d <= 1.0

    def test_density_labels(self):
        assert _density_to_label(0.0) == "free"
        assert _density_to_label(0.3) == "light"
        assert _density_to_label(0.5) == "moderate"
        assert _density_to_label(0.7) == "busy"
        assert _density_to_label(0.9) == "packed"


# =============================================================================
# Whisper graceful import
# =============================================================================

class TestVoiceTranscriptionGracefulImport:
    """Test that voice transcription module loads gracefully if faster-whisper is missing."""

    def test_transcription_module_imports(self):
        """Importing transcription module should never raise."""
        from noctem.voice import transcription
        assert hasattr(transcription, "WhisperService")
        assert hasattr(transcription, "_FASTER_WHISPER_AVAILABLE")

    def test_whisper_service_instantiates(self):
        """WhisperService() should work even without faster-whisper."""
        from noctem.voice.transcription import WhisperService
        svc = WhisperService()
        assert svc is not None

    def test_is_ready_reflects_availability(self):
        from noctem.voice.transcription import WhisperService, _FASTER_WHISPER_AVAILABLE
        svc = WhisperService()
        assert svc.is_ready() == _FASTER_WHISPER_AVAILABLE

    def test_graceful_unavailable(self):
        """If faster-whisper is not installed, _ensure_model should raise ImportError."""
        from noctem.voice.transcription import WhisperService, _FASTER_WHISPER_AVAILABLE
        if not _FASTER_WHISPER_AVAILABLE:
            svc = WhisperService()
            with pytest.raises(ImportError):
                svc._ensure_model()


# =============================================================================
# Flask API integration (task endpoints)
# =============================================================================

class TestTaskAPIEndpoints:
    """Test the Flask task API routes."""

    @pytest.fixture
    def client(self):
        from noctem.web.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_create_task_api(self, client):
        resp = client.post("/api/tasks", json={"name": "API task"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["task"]["name"] == "API task"

    def test_create_task_requires_name(self, client):
        resp = client.post("/api/tasks", json={"name": ""})
        assert resp.status_code == 400

    def test_complete_task_api(self, client):
        # Create first
        resp = client.post("/api/tasks", json={"name": "Complete me"})
        task_id = resp.get_json()["task"]["id"]
        # Complete
        resp2 = client.post(f"/api/tasks/{task_id}/complete")
        assert resp2.status_code == 200
        assert resp2.get_json()["success"] is True

    def test_complete_nonexistent_task(self, client):
        resp = client.post("/api/tasks/999999/complete")
        assert resp.status_code == 404

    def test_update_task_api(self, client):
        resp = client.post("/api/tasks", json={"name": "Original"})
        task_id = resp.get_json()["task"]["id"]
        resp2 = client.post(
            f"/api/tasks/{task_id}/update",
            json={"name": "Renamed"},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["task"]["name"] == "Renamed"

    def test_update_nonexistent_task(self, client):
        resp = client.post("/api/tasks/999999/update", json={"name": "x"})
        assert resp.status_code == 404

    def test_upcoming_api(self, client):
        resp = client.get("/api/tasks/upcoming")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "days" in data
        assert "overdue" in data

    def test_projects_api(self, client):
        resp = client.get("/api/tasks/projects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "columns" in data
        assert "inbox" in data

    def test_delete_task_api(self, client):
        marker = f"delete-api-{uuid4().hex[:8]}"
        create_resp = client.post("/api/tasks", json={"name": marker})
        task_id = create_resp.get_json()["task"]["id"]

        delete_resp = client.post(f"/api/tasks/{task_id}/delete")
        assert delete_resp.status_code == 200
        payload = delete_resp.get_json()
        assert payload["success"] is True
        assert payload["deleted"] is True
        assert task_service.get_task(task_id) is None

    def test_delete_nonexistent_task(self, client):
        resp = client.post("/api/tasks/999999/delete")
        assert resp.status_code == 404

    def test_delete_recurring_task_fully_removes_it(self, client):
        marker = f"delete-recurring-{uuid4().hex[:8]}"
        create_resp = client.post(
            "/api/tasks",
            json={
                "name": marker,
                "due_date": date.today().isoformat(),
                "recurrence_rule": "FREQ=DAILY",
            },
        )
        task_id = create_resp.get_json()["task"]["id"]
        assert task_service.get_task(task_id) is not None

        delete_resp = client.post(f"/api/tasks/{task_id}/delete")
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["success"] is True
        assert task_service.get_task(task_id) is None

        remaining = [t for t in task_service.get_all_tasks(include_done=True) if t.name == marker]
        assert remaining == []
