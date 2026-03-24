"""
Tests for v0.9.1 skill-wiki bridge.
Verifies {{wiki:query}} placeholder resolution in skill instructions.
"""
import pytest
import re
from unittest.mock import patch, MagicMock
from noctem.skills.executor import SkillExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_registry():
    """Create a mock SkillRegistry."""
    registry = MagicMock()
    return registry


@pytest.fixture
def executor(mock_registry):
    """Create a SkillExecutor with mocked registry."""
    return SkillExecutor(mock_registry)


# ---------------------------------------------------------------------------
# Wiki placeholder regex tests
# ---------------------------------------------------------------------------

class TestWikiPlaceholderRegex:
    """Test that the regex correctly identifies {{wiki:query}} patterns."""

    def test_single_placeholder(self, executor):
        text = "Before {{wiki:productivity tips}} after"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 1
        assert matches[0].group(1) == "productivity tips"

    def test_multiple_placeholders(self, executor):
        text = "{{wiki:topic one}} middle {{wiki:topic two}}"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "topic one"
        assert matches[1].group(1) == "topic two"

    def test_no_placeholders(self, executor):
        text = "Regular instructions with no wiki refs"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 0

    def test_placeholder_with_special_chars(self, executor):
        text = "{{wiki:how to use the daily review process?}}"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 1
        assert "daily review" in matches[0].group(1)

    def test_nested_braces_not_matched(self, executor):
        """Regular double braces without wiki: prefix are not matched."""
        text = "Use {{variable}} but also {{wiki:real query}}"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 1
        assert matches[0].group(1) == "real query"

    def test_whitespace_trimmed(self, executor):
        text = "{{wiki:  spaced query  }}"
        matches = list(executor.WIKI_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 1
        # The regex captures with spaces, but _resolve trims
        assert "spaced query" in matches[0].group(1)


# ---------------------------------------------------------------------------
# _resolve_wiki_placeholders tests
# ---------------------------------------------------------------------------

class TestResolveWikiPlaceholders:
    """Test the placeholder resolution logic."""

    def test_no_placeholders_passthrough(self, executor):
        """Instructions without wiki refs pass through unchanged."""
        text = "Normal instructions"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        assert resolved == text
        assert ctx == []

    @patch('noctem.wiki.retrieval.get_context_for_query')
    def test_single_replacement_with_results(self, mock_query, executor):
        """A placeholder with results gets replaced with context."""
        mock_query.return_value = ("Chunk content here", [MagicMock()])
        
        text = "Before {{wiki:test query}} after"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        
        assert "{{wiki:" not in resolved
        assert "[Wiki context for 'test query']" in resolved
        assert "Chunk content here" in resolved
        assert resolved.startswith("Before ")
        assert resolved.endswith(" after")
        assert len(ctx) == 1
        assert ctx[0]["query"] == "test query"
        assert ctx[0]["results_count"] == 1

    @patch('noctem.wiki.retrieval.get_context_for_query')
    def test_single_replacement_no_results(self, mock_query, executor):
        """A placeholder with no results shows 'no results' message."""
        mock_query.return_value = ("", [])
        
        text = "Check {{wiki:nonexistent topic}}"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        
        assert "{{wiki:" not in resolved
        assert "[No wiki results for 'nonexistent topic']" in resolved
        assert ctx[0]["results_count"] == 0

    @patch('noctem.wiki.retrieval.get_context_for_query')
    def test_multiple_replacements(self, mock_query, executor):
        """Multiple placeholders are all resolved."""
        mock_query.side_effect = [
            ("First result", [MagicMock()]),
            ("Second result", [MagicMock(), MagicMock()]),
        ]
        
        text = "Start {{wiki:alpha}} middle {{wiki:beta}} end"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        
        assert "{{wiki:" not in resolved
        assert "First result" in resolved
        assert "Second result" in resolved
        assert len(ctx) == 2

    @patch('noctem.wiki.retrieval.get_context_for_query')
    def test_error_handling(self, mock_query, executor):
        """Wiki lookup errors are caught and shown gracefully."""
        mock_query.side_effect = Exception("DB connection failed")
        
        text = "Use {{wiki:broken query}} here"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        
        assert "{{wiki:" not in resolved
        assert "[Wiki lookup failed for 'broken query'" in resolved
        assert ctx[0].get("error") is not None

    @patch('noctem.wiki.retrieval.get_context_for_query')
    def test_context_preview_truncated(self, mock_query, executor):
        """Context preview is truncated to 200 chars."""
        long_text = "A" * 500
        mock_query.return_value = (long_text, [MagicMock()])
        
        text = "{{wiki:long content}}"
        resolved, ctx = executor._resolve_wiki_placeholders(text)
        
        assert len(ctx[0]["context_preview"]) == 200


# ---------------------------------------------------------------------------
# Integration with execute_skill
# ---------------------------------------------------------------------------

class TestSkillWikiBridgeIntegration:
    """Test that wiki bridge integrates into the execution flow."""

    def _setup_skill(self, registry, name="test-skill", requires_approval=False):
        """Helper: set up a mock skill in the registry."""
        skill = MagicMock()
        skill.id = 1
        skill.name = name
        skill.version = "1.0"
        skill.enabled = True
        skill.requires_approval = requires_approval
        skill.skill_path = "/tmp/test-skill.yaml"
        registry.get_skill.return_value = skill
        return skill

    @patch('noctem.wiki.retrieval.get_context_for_query')
    @patch.object(SkillExecutor, '_log_stage')
    @patch.object(SkillExecutor, '_get_execution')
    @patch.object(SkillExecutor, '_complete_execution')
    @patch.object(SkillExecutor, '_update_execution_status')
    @patch.object(SkillExecutor, '_approve_execution')
    @patch.object(SkillExecutor, '_create_execution_record', return_value=1)
    def test_wiki_context_added_to_context(
        self, mock_create, mock_approve, mock_update, mock_complete,
        mock_get_exec, mock_log, mock_wiki_query, executor, mock_registry
    ):
        """Wiki context is added to the execution context dict."""
        self._setup_skill(mock_registry)
        
        # Mock instruction loading to return text with wiki placeholder
        mock_metadata = MagicMock()
        executor.loader = MagicMock()
        executor.loader.parse_skill_yaml.return_value = mock_metadata
        executor.loader.load_instructions.return_value = "Do {{wiki:deep work}} now"
        
        mock_wiki_query.return_value = ("Focus deeply on tasks", [MagicMock()])
        mock_get_exec.return_value = MagicMock()
        
        context = {"input": "test"}
        executor.execute_skill("test-skill", context=context)
        
        # The context should now have wiki_context
        assert "wiki_context" in context
        assert context["wiki_context"][0]["query"] == "deep work"

    @patch.object(SkillExecutor, '_log_stage')
    @patch.object(SkillExecutor, '_get_execution')
    @patch.object(SkillExecutor, '_complete_execution')
    @patch.object(SkillExecutor, '_update_execution_status')
    @patch.object(SkillExecutor, '_approve_execution')
    @patch.object(SkillExecutor, '_create_execution_record', return_value=1)
    def test_no_wiki_refs_no_context(
        self, mock_create, mock_approve, mock_update, mock_complete,
        mock_get_exec, mock_log, executor, mock_registry
    ):
        """Without wiki placeholders, wiki_context is not added."""
        self._setup_skill(mock_registry)
        
        executor.loader = MagicMock()
        executor.loader.parse_skill_yaml.return_value = MagicMock()
        executor.loader.load_instructions.return_value = "Normal instructions"
        mock_get_exec.return_value = MagicMock()
        
        context = {"input": "test"}
        executor.execute_skill("test-skill", context=context)
        
        assert "wiki_context" not in context
