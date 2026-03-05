"""
Tests for v0.9.1 command shortcuts (dot-prefix and slash fallback).
"""
import pytest
from noctem.parser.command import parse_command, CommandType


class TestDotPrefixShortcuts:
    """Test dot-prefix shorthand commands."""

    def test_dot_t_creates_task(self):
        """'.t buy milk' should parse as NEW_TASK."""
        cmd = parse_command(".t buy milk tomorrow")
        assert cmd.type == CommandType.NEW_TASK
        assert cmd.args == ["buy", "milk", "tomorrow"]

    def test_dot_p_creates_project(self):
        """'.p My Project' should parse as PROJECT."""
        cmd = parse_command(".p My Project")
        assert cmd.type == CommandType.PROJECT
        assert cmd.args == ["My", "Project"]

    def test_dot_g_creates_goal(self):
        """'.g Learn Spanish' should parse as GOAL."""
        cmd = parse_command(".g Learn Spanish")
        assert cmd.type == CommandType.GOAL
        assert cmd.args == ["Learn", "Spanish"]

    def test_dot_d_marks_done_by_number(self):
        """'.d 3' should parse as DONE with target_id=3."""
        cmd = parse_command(".d 3")
        assert cmd.type == CommandType.DONE
        assert cmd.target_id == 3

    def test_dot_d_marks_done_by_name(self):
        """'.d buy milk' should parse as DONE with target_name."""
        cmd = parse_command(".d buy milk")
        assert cmd.type == CommandType.DONE
        assert cmd.target_name == "buy milk"

    def test_dot_s_skips_task(self):
        """'.s 2' should parse as SKIP with target_id=2."""
        cmd = parse_command(".s 2")
        assert cmd.type == CommandType.SKIP
        assert cmd.target_id == 2

    def test_dot_s_skips_by_name(self):
        """'.s some task' should parse as SKIP with target_name."""
        cmd = parse_command(".s some task")
        assert cmd.type == CommandType.SKIP
        assert cmd.target_name == "some task"

    def test_dot_w_wiki_command(self):
        """'.w search query' should parse as WIKI."""
        cmd = parse_command(".w search my query")
        assert cmd.type == CommandType.WIKI
        assert cmd.args == ["search", "my", "query"]

    def test_dot_session(self):
        """'.session' should parse as SESSION."""
        cmd = parse_command(".session")
        assert cmd.type == CommandType.SESSION

    def test_dot_with_no_args(self):
        """Bare '.' should be treated as new task."""
        cmd = parse_command(".")
        assert cmd.type == CommandType.NEW_TASK


class TestSlashFallback:
    """Test that / still works as a command prefix."""

    def test_slash_today(self):
        cmd = parse_command("/today")
        assert cmd.type == CommandType.TODAY

    def test_slash_project(self):
        cmd = parse_command("/project My Proj")
        assert cmd.type == CommandType.PROJECT
        assert cmd.args == ["My", "Proj"]

    def test_slash_goal(self):
        cmd = parse_command("/goal Be Healthy")
        assert cmd.type == CommandType.GOAL
        assert cmd.args == ["Be", "Healthy"]

    def test_slash_prioritize(self):
        cmd = parse_command("/prioritize 5")
        assert cmd.type == CommandType.PRIORITIZE
        assert "5" in cmd.args

    def test_slash_update(self):
        cmd = parse_command("/update 3")
        assert cmd.type == CommandType.UPDATE
        assert "3" in cmd.args

    def test_slash_session(self):
        cmd = parse_command("/session")
        assert cmd.type == CommandType.SESSION

    def test_slash_wiki(self):
        cmd = parse_command("/wiki status")
        assert cmd.type == CommandType.WIKI
        assert cmd.args == ["status"]

    def test_slash_summon(self):
        cmd = parse_command("/summon help me")
        assert cmd.type == CommandType.SUMMON
        assert cmd.args == ["help", "me"]

    def test_slash_done(self):
        cmd = parse_command("/done 1")
        assert cmd.type == CommandType.DONE
        assert cmd.target_id == 1

    def test_slash_skip_by_name(self):
        cmd = parse_command("/skip buy groceries")
        assert cmd.type == CommandType.SKIP
        assert cmd.target_name == "buy groceries"

    def test_slash_delete(self):
        cmd = parse_command("/delete old task")
        assert cmd.type == CommandType.DELETE
        assert cmd.target_name == "old task"

    def test_unknown_slash_command(self):
        """Unknown /command should be treated as new task."""
        cmd = parse_command("/xyzunknown")
        assert cmd.type == CommandType.NEW_TASK


class TestBareWordCommandsStillWork:
    """Bare word commands (no prefix) should still work."""

    def test_bare_today(self):
        cmd = parse_command("today")
        assert cmd.type == CommandType.TODAY

    def test_bare_week(self):
        cmd = parse_command("week")
        assert cmd.type == CommandType.WEEK

    def test_bare_projects(self):
        cmd = parse_command("projects")
        assert cmd.type == CommandType.PROJECTS

    def test_bare_goals(self):
        cmd = parse_command("goals")
        assert cmd.type == CommandType.GOALS

    def test_bare_done_number(self):
        cmd = parse_command("done 2")
        assert cmd.type == CommandType.DONE
        assert cmd.target_id == 2

    def test_bare_skip_name(self):
        cmd = parse_command("skip buy milk")
        assert cmd.type == CommandType.SKIP
        assert cmd.target_name == "buy milk"

    def test_bare_delete(self):
        cmd = parse_command("delete old task")
        assert cmd.type == CommandType.DELETE
        assert cmd.target_name == "old task"

    def test_correction_star(self):
        """* prefix should still work for corrections."""
        cmd = parse_command("* tomorrow !1")
        assert cmd.type == CommandType.CORRECT
        assert "tomorrow !1" in cmd.args[0]

    def test_natural_text_is_new_task(self):
        """Natural text should be a new task."""
        cmd = parse_command("buy groceries tomorrow")
        assert cmd.type == CommandType.NEW_TASK


class TestDotSlashParity:
    """Dot and slash should produce the same result for the same command."""

    @pytest.mark.parametrize("dot,slash", [
        (".t buy milk", "/t buy milk"),
        (".p My Project", "/p My Project"),
        (".g Fitness", "/g Fitness"),
        (".d 1", "/d 1"),
        (".s 2", "/s 2"),
        (".w status", "/w status"),
        (".session", "/session"),
    ])
    def test_dot_slash_parity(self, dot, slash):
        """Same shortcut with . or / should produce the same CommandType."""
        dot_cmd = parse_command(dot)
        slash_cmd = parse_command(slash)
        assert dot_cmd.type == slash_cmd.type
