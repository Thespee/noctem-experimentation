"""
Tests for natural language seed data parser (v0.6.0).
"""
import pytest
from datetime import date


class TestIsNaturalSeedFormat:
    """Test detection of natural seed format."""
    
    def test_detect_goals_section(self):
        """Detect text with Goals: section."""
        from noctem.seed.text_parser import is_natural_seed_format
        
        text = "Goals:\n-Goal 1\n-Goal 2"
        assert is_natural_seed_format(text) == True
    
    def test_detect_projects_by_goal(self):
        """Detect text with Projects by goal: section."""
        from noctem.seed.text_parser import is_natural_seed_format
        
        text = "Projects by goal:\n-Goal\n---- Project"
        assert is_natural_seed_format(text) == True
    
    def test_detect_tasks_by_project(self):
        """Detect text with Tasks by Project: section."""
        from noctem.seed.text_parser import is_natural_seed_format
        
        text = "Tasks by Project:\n- Project\n---- Task"
        assert is_natural_seed_format(text) == True
    
    def test_regular_task_not_detected(self):
        """Regular task text should not be detected."""
        from noctem.seed.text_parser import is_natural_seed_format
        
        text = "buy groceries tomorrow"
        assert is_natural_seed_format(text) == False


class TestParseDateHint:
    """Test date parsing from hints."""
    
    def test_parse_asap(self):
        """asap should return today."""
        from noctem.seed.text_parser import parse_date_hint
        
        result = parse_date_hint("asap")
        assert result == date.today().isoformat()
    
    def test_parse_today(self):
        """today should return today."""
        from noctem.seed.text_parser import parse_date_hint
        
        result = parse_date_hint("today")
        assert result == date.today().isoformat()
    
    def test_parse_month_day_year(self):
        """Parse 'jan 20th 2026' format."""
        from noctem.seed.text_parser import parse_date_hint
        
        result = parse_date_hint("jan 20th 2026")
        assert result == "2026-01-20"
    
    def test_parse_month_day(self):
        """Parse 'feb 11th' format (assumes current or next year)."""
        from noctem.seed.text_parser import parse_date_hint
        
        result = parse_date_hint("feb 11th")
        assert result is not None
        assert "-02-11" in result


class TestParseNaturalSeedText:
    """Test parsing natural language seed data."""
    
    def test_parse_goals(self):
        """Parse simple goals list."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Goals:
-Goal 1
-Goal 2
-Goal 3"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["goals"]) == 3
        assert result["goals"][0]["name"] == "Goal 1"
        assert result["goals"][1]["name"] == "Goal 2"
        assert result["goals"][2]["name"] == "Goal 3"
    
    def test_parse_projects_with_goals(self):
        """Parse projects nested under goals."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Projects by goal:
-Goal A
---- Project 1
---- Project 2
-Goal B
---- Project 3"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["projects"]) == 3
        assert result["projects"][0]["name"] == "Project 1"
        assert result["projects"][0]["goal"] == "Goal A"
        assert result["projects"][2]["name"] == "Project 3"
        assert result["projects"][2]["goal"] == "Goal B"
    
    def test_parse_tasks_with_projects(self):
        """Parse tasks nested under projects."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Tasks by Project:
- Project A
---- Task 1
---- Task 2
- Project B
---- Task 3"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["tasks"]) == 3
        assert result["tasks"][0]["name"] == "Task 1"
        assert result["tasks"][0]["project"] == "Project A"
        assert result["tasks"][2]["name"] == "Task 3"
        assert result["tasks"][2]["project"] == "Project B"
    
    def test_parse_tasks_with_dates(self):
        """Parse tasks with date hints after semicolon."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Tasks by Project:
- Project
---- Task 1; jan 20th 2026
---- Task 2; asap"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["name"] == "Task 1"
        assert result["tasks"][0]["due_date"] == "2026-01-20"
        assert "due_date" in result["tasks"][1]
    
    def test_parse_calendar_urls(self):
        """Parse calendar URLs with names."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Links to calendars:
gcal:
https://calendar.google.com/calendar/ical/test/basic.ics

work:
https://example.com/work.ics"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["calendar_urls"]) == 2
        assert result["calendar_urls"][0]["name"] == "gcal"
        assert "google.com" in result["calendar_urls"][0]["url"]
        assert result["calendar_urls"][1]["name"] == "work"
    
    def test_parse_full_example(self):
        """Parse a complete seed data example."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Goals:
-Health
-Career

Projects by goal:
-Health
---- Exercise
-Career
---- Learn Python

Tasks by Project:
- Exercise
---- Buy gym shoes
---- Sign up for class

- Learn Python
---- Complete tutorial; asap

Links to calendars:
personal:
https://example.com/cal.ics"""
        
        result = parse_natural_seed_text(text)
        
        assert len(result["goals"]) == 2
        assert len(result["projects"]) == 2
        assert len(result["tasks"]) == 3
        assert len(result["calendar_urls"]) == 1


class TestUserProvidedData:
    """Test with user's actual seed data format."""
    
    def test_parse_user_format(self):
        """Parse the user's actual seed data format."""
        from noctem.seed.text_parser import parse_natural_seed_text
        
        text = """Goals:
-Feel Anger
-Feel Passion
-Financial Acumen
-Learn / Practice Skills
-Physical Wealth

Projects by goal:
-Feel Anger
---- Housing
-Feel Passion
---- Summer mustic festivals
---- Cor Unum
-Financial Acumen
---- Life admin / unimportant tasks
---- Employed work
-Learn / Practice Skills
---- finish school
---- Lights with Jacob
---- Noctem
-Physical Wealth
---- Calistenics

Tasks by Project:
- Housing

- Summer mustic festivals
---- find line up of local BC festivals to work at

- Cor Unum
---- prep for march relaunch

- Life admin / unimportant tasks
---- Taxes 2025/26
---- Personal finance tracking

- finish school
---- Lab 1; jan 20th 2026
---- Assignment 1; jan 23rd
---- Lab 2 & 3; jan 28th

Links to calendars:
gcal:
https://calendar.google.com/calendar/ical/grinius.alex%40gmail.com/private-b64555d23f95c2cac4d6b505721b026b/basic.ics

work:
https://api-elb.pushoperations.com/calendars/8807d731-7fed-46ff-8ee2-e0900eddcdf4.ics"""
        
        result = parse_natural_seed_text(text)
        
        # Check goals
        assert len(result["goals"]) == 5
        goal_names = [g["name"] for g in result["goals"]]
        assert "Feel Anger" in goal_names
        assert "Physical Wealth" in goal_names
        
        # Check projects
        assert len(result["projects"]) >= 9  # 9 projects listed
        project_names = [p["name"] for p in result["projects"]]
        assert "Housing" in project_names
        assert "Noctem" in project_names
        assert "Calistenics" in project_names
        
        # Check tasks
        assert len(result["tasks"]) >= 5
        task_names = [t["name"] for t in result["tasks"]]
        assert "Taxes 2025/26" in task_names
        
        # Check task with date
        lab1 = next((t for t in result["tasks"] if "Lab 1" in t["name"]), None)
        assert lab1 is not None
        assert lab1.get("due_date") == "2026-01-20"
        
        # Check calendars
        assert len(result["calendar_urls"]) == 2
        assert result["calendar_urls"][0]["name"] == "gcal"
