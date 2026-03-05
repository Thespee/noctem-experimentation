"""
Tests for wiki query module (v0.9.0).
"""

import pytest
from unittest.mock import patch, MagicMock

from noctem.wiki.query import (
    WikiAnswer,
    query_llm,
    check_wiki_ready,
    WIKI_QA_SYSTEM_PROMPT,
)


class TestWikiAnswer:
    """Tests for WikiAnswer dataclass."""
    
    def test_wiki_answer_creation(self):
        answer = WikiAnswer(
            answer="Test answer",
            sources_used=[],
            citations="",
            query="Test question",
            model_used="test-model",
            context_tokens=100,
        )
        
        assert answer.answer == "Test answer"
        assert answer.query == "Test question"
        assert answer.context_tokens == 100
    
    def test_has_answer_true(self):
        answer = WikiAnswer(
            answer="Here is a real answer with content.",
            sources_used=[],
            citations="",
            query="q",
            model_used="m",
            context_tokens=0,
        )
        
        assert answer.has_answer is True
    
    def test_has_answer_false_no_info(self):
        answer = WikiAnswer(
            answer="I don't have enough information to answer.",
            sources_used=[],
            citations="",
            query="q",
            model_used="m",
            context_tokens=0,
        )
        
        assert answer.has_answer is False
    
    def test_has_answer_false_empty(self):
        answer = WikiAnswer(
            answer="",
            sources_used=[],
            citations="",
            query="q",
            model_used="m",
            context_tokens=0,
        )
        
        assert answer.has_answer is False
    
    def test_formatted_with_citations(self):
        answer = WikiAnswer(
            answer="The answer is X.",
            sources_used=[],
            citations="---\n[1] source.md",
            query="q",
            model_used="m",
            context_tokens=0,
        )
        
        formatted = answer.formatted()
        
        assert "The answer is X." in formatted
        assert "---" in formatted
        assert "[1] source.md" in formatted
    
    def test_formatted_without_citations(self):
        answer = WikiAnswer(
            answer="Simple answer.",
            sources_used=[],
            citations="",
            query="q",
            model_used="m",
            context_tokens=0,
        )
        
        formatted = answer.formatted()
        assert formatted == "Simple answer."


class TestQueryLLM:
    """Tests for LLM query function."""
    
    def test_query_llm_mocked_success(self):
        """Test successful LLM query with mocked response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "This is the LLM's answer."
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch("noctem.wiki.query.requests.post", return_value=mock_response):
            result = query_llm("Test prompt")
            assert result == "This is the LLM's answer."
    
    def test_query_llm_connection_error(self):
        """Test LLM query when Ollama is unavailable."""
        import requests
        
        with patch("noctem.wiki.query.requests.post",
                   side_effect=requests.exceptions.ConnectionError()):
            result = query_llm("Test prompt")
            assert "error" in result.lower()
            assert "connect" in result.lower()
    
    def test_query_llm_timeout(self):
        """Test LLM query timeout."""
        import requests
        
        with patch("noctem.wiki.query.requests.post",
                   side_effect=requests.exceptions.Timeout()):
            result = query_llm("Test prompt")
            assert "error" in result.lower()
            assert "timed out" in result.lower()


class TestCheckWikiReady:
    """Tests for wiki readiness check."""
    
    def test_check_wiki_ready_no_ollama(self):
        """Test when Ollama is not available."""
        with patch("noctem.wiki.query.check_ollama_available", return_value=(False, "Ollama not running")):
            with patch("noctem.wiki.retrieval.get_wiki_stats", return_value={
                "sources_by_status": {"indexed": 1},
                "total_chunks": 10,
            }):
                is_ready, message = check_wiki_ready()
                assert is_ready is False
                assert "ollama" in message.lower()
    
    def test_check_wiki_ready_no_sources(self):
        """Test when no sources are indexed."""
        with patch("noctem.wiki.query.check_ollama_available", return_value=(True, "OK")):
            with patch("noctem.wiki.retrieval.get_wiki_stats", return_value={
                "sources_by_status": {},
                "total_chunks": 0,
            }):
                is_ready, message = check_wiki_ready()
                assert is_ready is False
                assert "no indexed" in message.lower() or "no knowledge" in message.lower()
    
    def test_check_wiki_ready_success(self):
        """Test successful readiness check."""
        with patch("noctem.wiki.query.check_ollama_available", return_value=(True, "OK")):
            with patch("noctem.wiki.retrieval.get_wiki_stats", return_value={
                "sources_by_status": {"indexed": 5},
                "total_chunks": 50,
            }):
                is_ready, message = check_wiki_ready()
                assert is_ready is True
                assert "ready" in message.lower()
                assert "5 sources" in message
                assert "50 chunks" in message


class TestSystemPrompt:
    """Tests for system prompt."""
    
    def test_system_prompt_content(self):
        """Verify system prompt contains key instructions."""
        assert "ONLY use information from the provided sources" in WIKI_QA_SYSTEM_PROMPT
        assert "cite" in WIKI_QA_SYSTEM_PROMPT.lower()
        assert "[1]" in WIKI_QA_SYSTEM_PROMPT or "[2]" in WIKI_QA_SYSTEM_PROMPT
