"""
Tests for natural language parsing.
"""
import pytest
from datetime import date, time, timedelta

from ..parser.natural_date import parse_date, parse_time, parse_recurrence, parse_datetime
from ..parser.task_parser import parse_task, parse_importance, parse_tags, parse_project
from ..parser.command import parse_command, CommandType


class TestDateParsing:
    def test_today(self):
        parsed, remaining = parse_date("buy milk today")
        assert parsed == date.today()
        assert "today" not in remaining.lower()
    
    def test_tomorrow(self):
        parsed, remaining = parse_date("call mom tomorrow")
        assert parsed == date.today() + timedelta(days=1)
    
    def test_in_n_days(self):
        parsed, remaining = parse_date("meeting in 3 days")
        assert parsed == date.today() + timedelta(days=3)
    
    def test_weekday(self):
        parsed, remaining = parse_date("report friday")
        assert parsed is not None
        assert parsed.weekday() == 4  # Friday
    
    def test_next_weekday(self):
        parsed, remaining = parse_date("meeting next monday")
        assert parsed is not None
        assert parsed.weekday() == 0  # Monday
        assert parsed > date.today()
    
    def test_month_day(self):
        parsed, remaining = parse_date("deadline feb 20")
        assert parsed is not None
        assert parsed.month == 2
        assert parsed.day == 20
    
    def test_iso_format(self):
        parsed, remaining = parse_date("event 2026-03-15")
        assert parsed == date(2026, 3, 15)
    
    def test_no_date(self):
        parsed, remaining = parse_date("buy groceries")
        assert parsed is None
        assert remaining == "buy groceries"


class TestTimeParsing:
    def test_12hour_pm(self):
        parsed, remaining = parse_time("meeting 3pm")
        assert parsed == time(15, 0)
    
    def test_12hour_am(self):
        parsed, remaining = parse_time("wake up 7am")
        assert parsed == time(7, 0)
    
    def test_24hour(self):
        parsed, remaining = parse_time("call at 15:30")
        assert parsed == time(15, 30)
    
    def test_noon(self):
        parsed, remaining = parse_time("lunch at noon")
        assert parsed == time(12, 0)
    
    def test_no_time(self):
        parsed, remaining = parse_time("buy groceries")
        assert parsed is None


class TestRecurrenceParsing:
    def test_daily(self):
        parsed, remaining = parse_recurrence("exercise daily")
        assert parsed == "FREQ=DAILY"
    
    def test_weekly(self):
        parsed, remaining = parse_recurrence("review weekly")
        assert parsed == "FREQ=WEEKLY"
    
    def test_every_day(self):
        parsed, remaining = parse_recurrence("meditate every day")
        assert parsed == "FREQ=DAILY"
    
    def test_every_monday(self):
        parsed, remaining = parse_recurrence("standup every monday")
        assert "FREQ=WEEKLY" in parsed
        assert "BYDAY=MO" in parsed
    
    def test_every_1st(self):
        parsed, remaining = parse_recurrence("pay rent every 1st")
        assert "FREQ=MONTHLY" in parsed
        assert "BYMONTHDAY=1" in parsed


class TestImportanceParsing:
    def test_exclamation_importance_high(self):
        importance, remaining = parse_importance("important task !1")
        assert importance == 1.0  # High importance
    
    def test_exclamation_importance_medium(self):
        importance, remaining = parse_importance("task !2")
        assert importance == 0.5  # Medium importance
    
    def test_exclamation_importance_low(self):
        importance, remaining = parse_importance("task !3")
        assert importance == 0.0  # Low importance
    
    def test_no_importance(self):
        importance, remaining = parse_importance("normal task")
        assert importance is None


class TestTagParsing:
    def test_single_tag(self):
        tags, remaining = parse_tags("email john #work")
        assert tags == ["work"]
    
    def test_multiple_tags(self):
        tags, remaining = parse_tags("task #work #urgent")
        assert "work" in tags
        assert "urgent" in tags
    
    def test_no_tags(self):
        tags, remaining = parse_tags("buy groceries")
        assert tags == []


class TestProjectParsing:
    def test_slash_project(self):
        project, remaining = parse_project("task /myproject")
        assert project == "myproject"
    
    def test_plus_project(self):
        project, remaining = parse_project("task +backend")
        assert project == "backend"
    
    def test_no_project(self):
        project, remaining = parse_project("buy groceries")
        assert project is None


class TestFullTaskParsing:
    def test_simple_task(self):
        parsed = parse_task("buy groceries tomorrow")
        assert "groceries" in parsed.name.lower()
        assert parsed.due_date == date.today() + timedelta(days=1)
    
    def test_complex_task(self):
        parsed = parse_task("finish report by feb 20 3pm !1 #work /project")
        assert "report" in parsed.name.lower()
        assert parsed.due_date.month == 2
        assert parsed.due_date.day == 20
        assert parsed.due_time == time(15, 0)
        assert parsed.importance == 1.0  # High importance
        assert "work" in parsed.tags
        assert parsed.project_name == "project"
    
    def test_recurring_task(self):
        parsed = parse_task("exercise daily")
        assert "exercise" in parsed.name.lower()
        assert parsed.recurrence_rule == "FREQ=DAILY"


class TestCommandParsing:
    def test_slash_command(self):
        cmd = parse_command("/today")
        assert cmd.type == CommandType.TODAY
    
    def test_done_by_number(self):
        cmd = parse_command("done 1")
        assert cmd.type == CommandType.DONE
        assert cmd.target_id == 1
    
    def test_done_by_name(self):
        cmd = parse_command("done buy milk")
        assert cmd.type == CommandType.DONE
        assert cmd.target_name == "buy milk"
    
    def test_skip(self):
        cmd = parse_command("skip 2")
        assert cmd.type == CommandType.SKIP
        assert cmd.target_id == 2
    
    def test_habit_done(self):
        cmd = parse_command("habit done exercise")
        assert cmd.type == CommandType.HABIT_DONE
        assert cmd.target_name == "exercise"
    
    def test_new_task(self):
        cmd = parse_command("buy groceries tomorrow")
        assert cmd.type == CommandType.NEW_TASK
