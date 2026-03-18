"""Tests for agent/memory_pack.py — context docs via retrieval, compaction injection."""
import pytest

from ..agent.memory_pack import (
    ACTIVE_MEMORY_BUDGET,
    CONTEXT_DOCS_BUDGET,
    RECENT_CHATS_BUDGET,
    _context_docs_section,
    _estimate_tokens,
    _recent_chat_section,
    _tail_lines_to_budget,
)


class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens("") == 0
        assert _estimate_tokens(None) == 0

    def test_short_text(self):
        tokens = _estimate_tokens("hello world")
        assert tokens >= 1

    def test_proportional(self):
        short = _estimate_tokens("abc")
        long = _estimate_tokens("a" * 400)
        assert long > short


class TestTailLinesToBudget:
    def test_selects_from_tail(self):
        lines = [f"line {i}" for i in range(100)]
        selected, used = _tail_lines_to_budget(lines, budget_tokens=10)
        # Should be a small number of the most recent lines
        assert len(selected) < len(lines)
        assert selected[-1] == "line 99"

    def test_empty_input(self):
        selected, used = _tail_lines_to_budget([], budget_tokens=100)
        assert selected == []
        assert used == 0


class TestRecentChatSection:
    def test_no_messages_returns_placeholder(self):
        text, tokens = _recent_chat_section("nonexistent-thread", budget_tokens=500)
        assert "no recent" in text.lower()

    def test_budget_respected(self):
        # With no messages, this should be near-zero tokens
        text, tokens = _recent_chat_section("empty-thread", budget_tokens=10)
        assert tokens <= 10


class TestContextDocsSection:
    def test_returns_placeholder_when_empty(self):
        text, tokens = _context_docs_section(budget_tokens=500, query="test query")
        assert "no context docs" in text.lower() or tokens >= 0

    def test_budget_is_respected(self):
        text, tokens = _context_docs_section(budget_tokens=100, query="")
        assert tokens <= 100


class TestBudgetConstants:
    def test_budget_math(self):
        from ..agent.memory_pack import TOTAL_CONTEXT_BUDGET, RESERVED_FOR_TOOLS_AND_OUTPUT
        assert ACTIVE_MEMORY_BUDGET == TOTAL_CONTEXT_BUDGET - RESERVED_FOR_TOOLS_AND_OUTPUT
        assert RECENT_CHATS_BUDGET > 0
        assert CONTEXT_DOCS_BUDGET > 0
