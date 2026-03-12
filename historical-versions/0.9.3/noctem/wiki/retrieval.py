"""
Wiki Retrieval Module (v0.9.0)

Semantic search over the knowledge base with trust level weighting
and citation formatting.
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass

from noctem.db import get_db
from noctem.models import Source, KnowledgeChunk
from noctem.wiki.embeddings import search_similar, DEFAULT_EMBEDDING_MODEL
from noctem.wiki.chunking import get_chunk_by_id
from noctem.wiki.ingestion import get_source_by_id


@dataclass
class SearchResult:
    """A search result with chunk, source, and relevance info."""
    chunk: KnowledgeChunk
    source: Source
    similarity_score: float
    citation_ref: str
    
    @property
    def trust_weight(self) -> float:
        """Weight factor based on trust level (higher trust = higher weight)."""
        # trust_level: 1=personal (highest trust), 2=curated, 3=web (lowest trust)
        # Invert so personal gets highest weight
        return 1.0 / self.source.trust_level if self.source else 1.0
    
    @property
    def weighted_score(self) -> float:
        """Similarity score weighted by trust level."""
        return self.similarity_score * self.trust_weight


def format_citation(chunk: KnowledgeChunk, source: Source, index: int) -> str:
    """
    Format a citation reference.
    
    Returns:
        String like "[1] productivity.md, Section: Daily Routine"
    """
    parts = [f"[{index}]"]
    
    if source and source.file_name:
        parts.append(source.file_name)
    
    if chunk.page_or_section:
        parts.append(chunk.page_or_section)
    
    return " ".join(parts)


def search(
    query: str,
    n_results: int = 5,
    trust_level: Optional[int] = None,
    source_ids: Optional[List[int]] = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> List[SearchResult]:
    """
    Search the wiki knowledge base.
    
    Args:
        query: Search query text
        n_results: Maximum number of results to return
        trust_level: Filter to sources at or above this trust level (1=personal, 2=curated, 3=web)
        source_ids: Optional list of specific source IDs to search
        model: Embedding model to use
    
    Returns:
        List of SearchResult objects, sorted by weighted score (highest first)
    """
    # Get matching chunk IDs from vector store
    raw_results = search_similar(
        query=query,
        n_results=n_results * 2,  # Fetch extra to allow for filtering
        model=model,
        source_ids=source_ids,
    )
    
    results = []
    
    for chunk_id, similarity, metadata in raw_results:
        # Get full chunk from database
        chunk = get_chunk_by_id(chunk_id)
        if not chunk:
            continue
        
        # Get source
        source = get_source_by_id(chunk.source_id)
        if not source:
            continue
        
        # Filter by trust level if specified
        if trust_level is not None and source.trust_level > trust_level:
            continue
        
        # Attach source to chunk
        chunk.source = source
        chunk.similarity_score = similarity
        
        # Create citation reference
        citation_ref = f"{source.file_name}"
        if chunk.page_or_section:
            citation_ref += f", {chunk.page_or_section}"
        
        results.append(SearchResult(
            chunk=chunk,
            source=source,
            similarity_score=similarity,
            citation_ref=citation_ref,
        ))
    
    # Sort by weighted score (trust level affects ranking)
    results.sort(key=lambda r: r.weighted_score, reverse=True)
    
    # Return top n_results
    return results[:n_results]


def get_context_for_query(
    query: str,
    n_chunks: int = 5,
    max_tokens: int = 3000,
    trust_level: Optional[int] = None,
) -> Tuple[str, List[SearchResult]]:
    """
    Get formatted context for LLM query answering.
    
    Args:
        query: User's question
        n_chunks: Maximum number of chunks to include
        max_tokens: Approximate max tokens for context
        trust_level: Optional trust level filter
    
    Returns:
        Tuple of (formatted_context, search_results)
        formatted_context is ready to insert into an LLM prompt
    """
    results = search(
        query=query,
        n_results=n_chunks,
        trust_level=trust_level,
    )
    
    if not results:
        return "", []
    
    # Build context string with citations
    context_parts = []
    total_tokens = 0
    
    for i, result in enumerate(results, start=1):
        chunk_text = result.chunk.content
        chunk_tokens = result.chunk.token_count or (len(chunk_text) // 4)
        
        if total_tokens + chunk_tokens > max_tokens:
            break
        
        # Format with citation marker
        context_parts.append(
            f"[{i}] Source: {result.citation_ref}\n"
            f"{chunk_text}\n"
        )
        total_tokens += chunk_tokens
    
    context = "\n---\n".join(context_parts)
    
    return context, results[:len(context_parts)]


def format_citations_footer(results: List[SearchResult]) -> str:
    """
    Format the citations footer for an answer.
    
    Args:
        results: List of SearchResult objects used in the answer
    
    Returns:
        Formatted citation list like:
        ---
        [1] productivity.md, ## Daily Routine
        [2] deep-work.pdf, p.47
    """
    if not results:
        return ""
    
    lines = ["---"]
    for i, result in enumerate(results, start=1):
        lines.append(format_citation(result.chunk, result.source, i))
    
    return "\n".join(lines)


def extract_quote(text: str, max_words: int = 30) -> str:
    """
    Extract a quotable snippet from text (max 30 words by default).
    
    Args:
        text: Source text
        max_words: Maximum words to include
    
    Returns:
        Quoted snippet, possibly truncated with "..."
    """
    # Clean up whitespace
    text = " ".join(text.split())
    
    words = text.split()
    if len(words) <= max_words:
        return f'"{text}"'
    
    truncated = " ".join(words[:max_words])
    return f'"{truncated}..."'


def get_all_indexed_sources() -> List[Source]:
    """Get all successfully indexed sources."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sources WHERE status = 'indexed' ORDER BY trust_level, title"
        ).fetchall()
        return [Source.from_row(row) for row in rows]


def get_wiki_stats() -> dict:
    """Get overall wiki statistics."""
    with get_db() as conn:
        # Count sources by status
        source_stats = conn.execute(
            """
            SELECT status, COUNT(*) as count 
            FROM sources 
            GROUP BY status
            """
        ).fetchall()
        
        # Count total chunks
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_chunks"
        ).fetchone()[0]
        
        # Count by trust level
        trust_stats = conn.execute(
            """
            SELECT trust_level, COUNT(*) as count 
            FROM sources 
            WHERE status = 'indexed'
            GROUP BY trust_level
            """
        ).fetchall()
    
    return {
        "sources_by_status": {row["status"]: row["count"] for row in source_stats},
        "total_chunks": chunk_count,
        "sources_by_trust": {row["trust_level"]: row["count"] for row in trust_stats},
    }
