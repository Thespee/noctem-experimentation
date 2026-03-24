"""Tests for the feedback capture surface (singleton doc + .f command)."""
import pytest

from ..parser.command import parse_command, CommandType
from ..services.feedback_service import (
    export_feedback,
    get_feedback_text,
    prepend_feedback,
)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestFeedbackParser:
    def test_dot_f_recognised(self):
        cmd = parse_command(".f this is feedback")
        assert cmd.type == CommandType.FEEDBACK

    def test_slash_f_recognised(self):
        cmd = parse_command("/f more feedback here")
        assert cmd.type == CommandType.FEEDBACK

    def test_f_args_populated(self):
        cmd = parse_command(".f hello world")
        assert cmd.args  # should have at least one arg

    def test_bare_f_without_text_still_feedback(self):
        cmd = parse_command(".f")
        # ".f" alone: rest is empty, parts[0]='f', matches shorthand -> FEEDBACK
        # but no args
        assert cmd.type == CommandType.FEEDBACK

    def test_unrelated_does_not_match(self):
        cmd = parse_command("fix the build")
        assert cmd.type == CommandType.NEW_TASK


# ---------------------------------------------------------------------------
# Singleton service tests
# ---------------------------------------------------------------------------

class TestFeedbackSingleton:
    def test_lazy_creation(self):
        """First access creates the singleton with empty body."""
        body = get_feedback_text()
        assert body == ""

    def test_prepend_single_entry(self):
        result = prepend_feedback("first entry")
        assert result["ok"] is True
        body = get_feedback_text()
        assert "first entry" in body

    def test_prepend_ordering_newest_on_top(self):
        prepend_feedback("older entry")
        prepend_feedback("newer entry")
        body = get_feedback_text()
        # newer should appear before older
        assert body.index("newer entry") < body.index("older entry")

    def test_delimiter_present_between_entries(self):
        prepend_feedback("A")
        prepend_feedback("B")
        body = get_feedback_text()
        assert "&&&" in body

    def test_single_entry_surrounded_by_delimiters(self):
        prepend_feedback("solo")
        body = get_feedback_text()
        # First entry should also be surrounded: &&& above and below
        assert body.startswith("&&&")
        assert body.endswith("&&&")

    def test_second_entry_no_double_delimiter(self):
        prepend_feedback("first")
        prepend_feedback("second")
        body = get_feedback_text()
        # Should not have &&& immediately followed by another &&& (no doubling)
        import re
        assert not re.search(r'&&&\s*&&&', body)

    def test_empty_text_rejected(self):
        result = prepend_feedback("")
        assert result["ok"] is False

    def test_whitespace_only_rejected(self):
        result = prepend_feedback("   ")
        assert result["ok"] is False

    def test_three_entries_ordering(self):
        prepend_feedback("first")
        prepend_feedback("second")
        prepend_feedback("third")
        body = get_feedback_text()
        assert body.index("third") < body.index("second") < body.index("first")


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestFeedbackExport:
    def test_export_empty(self):
        data = export_feedback()
        assert data["object_id"] == "feedback_doc:1"
        assert data["body"] == ""
        assert data["version_num"] == 1  # genesis

    def test_export_after_writes(self):
        prepend_feedback("hello")
        prepend_feedback("world")
        data = export_feedback()
        assert "world" in data["body"]
        assert "hello" in data["body"]
        assert data["version_num"] >= 3  # genesis + 2 writes

    def test_version_increments(self):
        prepend_feedback("a")
        d1 = export_feedback()
        prepend_feedback("b")
        d2 = export_feedback()
        assert d2["version_num"] > d1["version_num"]


# ---------------------------------------------------------------------------
# CLI handler tests
# ---------------------------------------------------------------------------

class TestFeedbackCLI:
    def test_handle_input_feedback(self, capsys):
        from ..cli import handle_input
        result = handle_input(".f the UI is broken")
        assert result is True
        captured = capsys.readouterr()
        assert "Feedback captured" in captured.out

    def test_handle_input_feedback_empty(self, capsys):
        from ..cli import handle_input
        result = handle_input(".f")
        assert result is True
        captured = capsys.readouterr()
        assert "❌" in captured.out

    def test_feedback_text_persisted_via_cli(self):
        from ..cli import handle_input
        handle_input(".f cli feedback test")
        body = get_feedback_text()
        assert "cli feedback test" in body
