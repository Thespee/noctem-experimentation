"""
Tests for wiki retrieval module (v0.9.0).
"""

import pytest
from unittest.mock import patch, MagicMock

from noctem.wiki.retrieval import (
    SearchResult,
    format_citation,
    extract_quote,
    get_wiki_stats,
)
from noctem.models import Source, KnowledgeChunk


class TestSearchResult:
    """Tests for SearchResult dataclass."""
    
    def test_search_result_creation(self):
        source = Source(
            id=1,
            file_path="/path/to/file.md",
            file_name="file.md",
            trust_level=1,
        )
        chunk = KnowledgeChunk(
            id=1,
            source_id=1,
            chunk_id="chunk-001",
            content="Test content",
            page_or_section="## Section",
        )
        
        result = SearchResult(
            chunk=chunk,
            source=source,
            similarity_score=0.85,
            citation_ref="file.md, ## Section",
        )
        
        assert result.similarity_score == 0.85
        assert result.citation_ref == "file.md, ## Section"
    
    def test_trust_weight_personal(self):
        """Personal sources (trust=1) should have highest weight."""
        source = Source(id=1, trust_level=1)
        chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="c1", content="x")
        
        result = SearchResult(chunk=chunk, source=source, similarity_score=0.5, citation_ref="")
        assert result.trust_weight == 1.0
    
    def test_trust_weight_web(self):
        """Web sources (trust=3) should have lowest weight."""
        source = Source(id=1, trust_level=3)
        chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="c1", content="x")
        
        result = SearchResult(chunk=chunk, source=source, similarity_score=0.5, citation_ref="")
        assert result.trust_weight == pytest.approx(1/3)
    
    def test_weighted_score(self):
        """Weighted score should combine similarity and trust."""
        source = Source(id=1, trust_level=2)  # Curated
        chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="c1", content="x")
        
        result = SearchResult(chunk=chunk, source=source, similarity_score=0.8, citation_ref="")
        
        # 0.8 * (1/2) = 0.4
        assert result.weighted_score == pytest.approx(0.4)


class TestCitationFormatting:
    """Tests for citation formatting."""
    
    def test_format_citation_with_section(self):
        source = Source(id=1, file_name="document.pdf")
        chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="c1", content="x", 
                              page_or_section="p.42")
        
        citation = format_citation(chunk, source, index=1)
        
        assert "[1]" in citation
        assert "document.pdf" in citation
        assert "p.42" in citation
    
    def test_format_citation_no_section(self):
        source = Source(id=1, file_name="notes.md")
        chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="c1", content="x",
                              page_or_section=None)
        
        citation = format_citation(chunk, source, index=3)
        
        assert "[3]" in citation
        assert "notes.md" in citation


class TestQuoteExtraction:
    """Tests for quote extraction."""
    
    def test_extract_short_quote(self):
        text = "This is a short text."
        quote = extract_quote(text)
        
        assert '"This is a short text."' == quote
    
    def test_extract_long_quote_truncated(self):
        text = " ".join(["word"] * 50)  # 50 words
        quote = extract_quote(text, max_words=30)
        
        assert quote.startswith('"')
        assert quote.endswith('..."')
        assert len(quote.split()) <= 35  # 30 words + "..." + quotes
    
    def test_extract_quote_exact_limit(self):
        text = " ".join(["word"] * 30)
        quote = extract_quote(text, max_words=30)
        
        # Exactly 30 words should not be truncated
        assert "..." not in quote


class TestWikiStats:
    """Tests for wiki statistics."""
    
    def test_get_wiki_stats_empty(self):
        """Stats should work even with empty database."""
        stats = get_wiki_stats()
        
        assert "sources_by_status" in stats
        assert "total_chunks" in stats
        assert "sources_by_trust" in stats
        
        assert isinstance(stats["total_chunks"], int)
