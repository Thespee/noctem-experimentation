"""
Tests for Noctem v0.9.3 Phase 1 quick fixes.

Covers:
- tmrw alias parsing
- Unassigned tasks endpoint
- NLP task reprocessing (differential updates)
- Projects page NLP-only creation UI
- Legacy route redirects
- Recurring ICS import (RRULE expansion)
"""
import pytest
from datetime import date, datetime, timedelta

from noctem.db import get_db
from noctem.parser.command import CommandType, parse_command
from noctem.parser.natural_date import parse_date
from noctem.parser.task_parser import parse_task
from noctem.services import project_service, task_service
from noctem.services.ics_import import import_ics_bytes, clear_ics_events


@pytest.fixture
def client():
    from noctem.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestDateAlias:
    def test_parse_tmrw_alias(self):
        parsed = parse_task("pay rent tmrw")
        assert parsed.due_date == date.today() + timedelta(days=1)

    def test_parse_standalone_ordinal_day(self):
        parsed = parse_task("pay bill 18th")
        assert parsed.due_date is not None
        assert parsed.due_date >= date.today()
        assert parsed.name.lower() == "pay bill"

    def test_parse_weekday_ordinal_month_phrase(self):
        parsed_date, remaining = parse_date("wednesday the 11th of march")
        assert parsed_date is not None
        assert parsed_date.month == 3
        assert parsed_date.day == 11
        assert remaining == ""


class TestFastCommandRecognition:
    @pytest.mark.parametrize(
        ("text", "expected_type"),
        [
            (". access", CommandType.ACCESS),
            ("access", CommandType.ACCESS),
            (". status", CommandType.STATUS),
            ("status", CommandType.STATUS),
            ("start", CommandType.START),
            ("help", CommandType.HELP),
            ("settings", CommandType.SETTINGS),
        ],
    )
    def test_parse_fast_command_variants(self, text, expected_type):
        parsed = parse_command(text)
        assert parsed.type == expected_type


class TestUnassignedTasks:
    def test_no_due_date_endpoint_excludes_completed(self, client):
        t1 = task_service.create_task("Unassigned 1")
        t2 = task_service.create_task("Unassigned 2")
        done_task = task_service.create_task("Done task")
        dated_task = task_service.create_task("Dated task", due_date=date.today() + timedelta(days=1))
        task_service.complete_task(done_task.id)

        # Ensure deterministic ordering by created_at (newest first)
        with get_db() as conn:
            conn.execute("UPDATE tasks SET created_at = ? WHERE id = ?", ("2026-03-01 10:00:00", t1.id))
            conn.execute("UPDATE tasks SET created_at = ? WHERE id = ?", ("2026-03-01 11:00:00", t2.id))

        resp = client.get("/api/tasks/no-due-date")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = [t["id"] for t in data["tasks"]]

        assert t2.id in ids
        assert t1.id in ids
        assert done_task.id not in ids
        assert dated_task.id not in ids
        assert ids.index(t2.id) < ids.index(t1.id)  # newest first


class TestTaskReprocess:
    def test_reprocess_updates_only_explicit_fields(self, client):
        project = project_service.create_project("Home")
        original_due = date.today() + timedelta(days=1)
        task = task_service.create_task(
            "Take out trash",
            project_id=project.id,
            due_date=original_due,
            importance=1.0,
            tags=["chore"],
        )

        # Only explicit field in this text should be due_date ("Sunday")
        resp = client.post(
            f"/api/tasks/{task.id}/reprocess",
            json={"text": "take out trash Sunday"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        updated = task_service.get_task(task.id)
        assert updated is not None
        assert updated.due_date != original_due  # due date changed
        assert updated.importance == 1.0  # preserved
        assert updated.tags == ["chore"]  # preserved
        assert updated.project_id == project.id  # preserved

    def test_reprocess_updates_tags_when_explicit(self, client):
        task = task_service.create_task("Clean room", tags=["oldtag"])
        resp = client.post(
            f"/api/tasks/{task.id}/reprocess",
            json={"text": "clean room #newtag"},
        )
        assert resp.status_code == 200
        updated = task_service.get_task(task.id)
        assert updated.tags == ["newtag"]


class TestProjectsPageNLPInput:
    def test_projects_page_has_no_date_input(self, client):
        resp = client.get("/tasks/projects")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'type="date"' not in html
        assert "use natural language for dates" in html
    
    def test_task_create_api_parses_nlp_date(self, client):
        resp = client.post("/api/tasks", json={"name": "Submit report tmrw"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["task"]["name"] == "Submit report"
        assert data["task"]["due_date"] == (date.today() + timedelta(days=1)).isoformat()


class TestDashboardCleanup:
    def test_dashboard_has_no_system_thinking_panel_or_polling(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "System Thinking" not in html
        assert "/api/system/thinking" not in html


class TestLegacyRoutes:
    def test_task_settings_redirects_to_settings(self, client):
        resp = client.get("/tasks/settings", follow_redirects=False)
        assert resp.status_code in (301, 302, 308)
        assert "/settings" in resp.headers.get("Location", "")


class TestRecurringICSImport:
    def test_every_other_tuesday_rrule_imports_multiple_occurrences(self):
        clear_ics_events()

        today = date.today()
        days_since_tuesday = (today.weekday() - 1) % 7
        # Start 2 weeks before most recent Tuesday
        start_date = today - timedelta(days=days_since_tuesday + 14)
        start_ymd = start_date.strftime("%Y%m%d")

        ics_content = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:therapy-session\r\n"
            "SUMMARY:Therapy Session\r\n"
            f"DTSTART:{start_ymd}T150000\r\n"
            f"DTEND:{start_ymd}T160000\r\n"
            "RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=TU\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ).encode("utf-8")

        stats = import_ics_bytes(ics_content, days_ahead=42)
        assert stats["created"] >= 2

        with get_db() as conn:
            rows = conn.execute(
                "SELECT external_event_id FROM time_blocks WHERE source = 'ics' AND external_event_id LIKE 'therapy-session::%'"
            ).fetchall()

        assert len(rows) >= 2
