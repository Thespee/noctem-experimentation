"""
Tests for v0.9.1 wiki CLI commands.

All wiki module functions are mocked to avoid needing Ollama/ChromaDB.
"""
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
from noctem.models import Source


# Helper to capture stdout from handle_wiki_command
def run_wiki_cmd(args: str):
    """Run handle_wiki_command and capture stdout."""
    import sys
    from noctem.cli import handle_wiki_command
    
    old_stdout = sys.stdout
    sys.stdout = captured = StringIO()
    try:
        result = handle_wiki_command(args, log=None)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue(), result


class TestWikiHelp:
    """Test wiki help output."""

    def test_wiki_help_on_unknown(self):
        output, result = run_wiki_cmd("help")
        assert "Wiki Commands" in output
        assert result is True

    def test_wiki_help_on_empty(self):
        output, result = run_wiki_cmd("")
        # Empty subcommand falls through to help
        assert "Wiki Commands" in output


class TestWikiStatus:
    """Test wiki status command."""

    @patch("noctem.wiki.query.check_wiki_ready")
    @patch("noctem.wiki.retrieval.get_wiki_stats")
    def test_status_shows_stats(self, mock_stats, mock_ready):
        mock_stats.return_value = {
            "sources_by_status": {"indexed": 3, "pending": 1},
            "total_chunks": 42,
            "sources_by_trust": {1: 2, 2: 1},
        }
        mock_ready.return_value = (True, "Wiki ready: 3 sources, 42 chunks indexed.")
        
        output, result = run_wiki_cmd("status")
        assert "Wiki Status" in output
        assert "42" in output  # total chunks
        assert result is True

    @patch("noctem.wiki.query.check_wiki_ready")
    @patch("noctem.wiki.retrieval.get_wiki_stats")
    def test_status_empty_wiki(self, mock_stats, mock_ready):
        mock_stats.return_value = {
            "sources_by_status": {},
            "total_chunks": 0,
            "sources_by_trust": {},
        }
        mock_ready.return_value = (False, "Wiki not ready:\n- No indexed sources.")
        
        output, result = run_wiki_cmd("status")
        assert "not ready" in output


class TestWikiSources:
    """Test wiki sources command."""

    @patch("noctem.wiki.ingestion.list_sources")
    def test_sources_lists_indexed(self, mock_list):
        mock_list.return_value = [
            Source(
                id=1, file_name="notes.md", title="My Notes",
                status="indexed", trust_level=1, chunk_count=10,
            ),
            Source(
                id=2, file_name="book.pdf", title="Deep Work",
                status="indexed", trust_level=2, chunk_count=25,
            ),
        ]
        
        output, result = run_wiki_cmd("sources")
        assert "My Notes" in output
        assert "Deep Work" in output
        assert "personal" in output
        assert "curated" in output

    @patch("noctem.wiki.ingestion.list_sources")
    def test_sources_empty(self, mock_list):
        mock_list.return_value = []
        
        output, result = run_wiki_cmd("sources")
        assert "No sources" in output


class TestWikiSearch:
    """Test wiki search command."""

    @patch("noctem.wiki.query.simple_search")
    def test_search_returns_results(self, mock_search):
        mock_search.return_value = [
            ("This is a chunk about productivity...", "notes.md, ## Productivity", 0.85),
            ("Another relevant chunk...", "book.pdf, p.42", 0.72),
        ]
        
        output, result = run_wiki_cmd('search "productivity tips"')
        assert "Searching" in output
        assert "productivity" in output.lower()
        assert "0.85" in output
        assert result is True

    @patch("noctem.wiki.query.simple_search")
    def test_search_no_results(self, mock_search):
        mock_search.return_value = []
        
        output, result = run_wiki_cmd('search "nonexistent topic"')
        assert "No results" in output

    def test_search_no_query(self):
        output, result = run_wiki_cmd("search")
        assert "Usage" in output


class TestWikiAsk:
    """Test wiki ask command."""

    @patch("noctem.wiki.query.ask")
    def test_ask_returns_answer(self, mock_ask):
        mock_answer = MagicMock()
        mock_answer.formatted.return_value = "The answer is 42.\n\n---\n[1] notes.md"
        mock_answer.has_answer = True
        mock_answer.sources_used = [MagicMock()]
        mock_answer.model_used = "qwen2.5:7b"
        mock_ask.return_value = mock_answer
        
        output, result = run_wiki_cmd('ask "what is the answer?"')
        assert "42" in output
        assert result is True

    def test_ask_no_question(self):
        output, result = run_wiki_cmd("ask")
        assert "Usage" in output


class TestWikiIngest:
    """Test wiki ingest command."""

    @patch("noctem.wiki.embeddings.check_ollama_available")
    def test_ingest_fails_without_ollama(self, mock_ollama):
        mock_ollama.return_value = (False, "Ollama not running")
        
        output, result = run_wiki_cmd("ingest")
        assert "Ollama" in output or "ollama" in output

    @patch("noctem.wiki.embeddings.check_ollama_available")
    @patch("noctem.wiki.ingestion.discover_new_sources")
    def test_ingest_no_new_files(self, mock_discover, mock_ollama):
        mock_ollama.return_value = (True, "OK")
        mock_discover.return_value = []
        
        output, result = run_wiki_cmd("ingest")
        assert "No new files" in output


class TestWikiVerify:
    """Test wiki verify command."""

    @patch("noctem.wiki.ingestion.list_sources")
    def test_verify_no_sources(self, mock_list):
        mock_list.return_value = []
        
        output, result = run_wiki_cmd("verify")
        assert "No indexed sources" in output

    @patch("noctem.wiki.ingestion.verify_source")
    @patch("noctem.wiki.ingestion.list_sources")
    def test_verify_all_unchanged(self, mock_list, mock_verify):
        mock_list.return_value = [
            Source(id=1, file_name="notes.md", title="Notes", status="indexed"),
        ]
        mock_verify.return_value = True
        
        output, result = run_wiki_cmd("verify")
        assert "unchanged" in output
        assert "All sources verified" in output

    @patch("noctem.wiki.ingestion.verify_source")
    @patch("noctem.wiki.ingestion.list_sources")
    def test_verify_detects_changes(self, mock_list, mock_verify):
        mock_list.return_value = [
            Source(id=1, file_name="notes.md", title="Notes", status="indexed"),
        ]
        mock_verify.return_value = False
        
        output, result = run_wiki_cmd("verify")
        assert "CHANGED" in output


class TestWikiRoutedFromShortcut:
    """Test that .w shortcut routes to wiki handler."""

    def test_dot_w_status(self):
        """'.w status' should route through parse_command to WIKI type."""
        from noctem.parser.command import parse_command, CommandType
        
        cmd = parse_command(".w status")
        assert cmd.type == CommandType.WIKI
        assert cmd.args == ["status"]
    
    def test_slash_wiki_search(self):
        """/wiki search should route to WIKI type."""
        from noctem.parser.command import parse_command, CommandType
        
        cmd = parse_command("/wiki search query")
        assert cmd.type == CommandType.WIKI
        assert cmd.args == ["search", "query"]
