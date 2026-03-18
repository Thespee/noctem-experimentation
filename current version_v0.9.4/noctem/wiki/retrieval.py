"""
Wiki retrieval module (v0.9.4).

Provides:
- trust-weighted semantic retrieval over wiki chunks
- context-doc-first retrieval ordering
- provenance-rich citation formatting
"""

from dataclasses import dataclass
import re
from typing import List, Optional, Tuple

from noctem.db import get_db
from noctem.models import KnowledgeChunk, Source
from noctem.wiki.chunking import get_chunk_by_id
from noctem.wiki.embeddings import DEFAULT_EMBEDDING_MODEL, search_similar
from noctem.wiki.ingestion import get_source_by_id


@dataclass
class SearchResult:
    """A wiki chunk retrieval result with trust-weighted scoring."""

    chunk: KnowledgeChunk
    source: Source
    similarity_score: float
    citation_ref: str

    @property
    def trust_weight(self) -> float:
        # trust_level: 1=personal, 2=curated, 3=web (higher trust => higher weight)
        return 1.0 / self.source.trust_level if self.source else 1.0

    @property
    def weighted_score(self) -> float:
        return self.similarity_score * self.trust_weight


@dataclass
class ContextDocResult:
    """Context-doc retrieval result surfaced ahead of raw chunk retrieval."""

    object_id: str
    object_type: str
    typed_id: Optional[int]
    summary: str
    markdown: str
    source_event_id: Optional[str]
    generated_at: Optional[str]
    similarity_score: float

    @property
    def trust_weight(self) -> float:
        return 1.0

    @property
    def weighted_score(self) -> float:
        return self.similarity_score * self.trust_weight

    @property
    def citation_ref(self) -> str:
        return f"context:{self.object_id}"

    @property
    def content(self) -> str:
        text = (self.markdown or "").strip()
        if text:
            return text
        return (self.summary or "").strip()


def format_citation(chunk: KnowledgeChunk, source: Source, index: int) -> str:
    """Format a citation reference for a wiki chunk."""

    parts = [f"[{index}]"]
    if source and source.file_name:
        parts.append(source.file_name)
    if chunk.page_or_section:
        parts.append(chunk.page_or_section)
    if source and source.trust_level:
        parts.append(f"(trust:{source.trust_label})")
    return " ".join(parts)


def _tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", (query or "").lower())
    return [token for token in tokens if len(token) >= 3]


def search(
    query: str,
    n_results: int = 5,
    trust_level: Optional[int] = None,
    source_ids: Optional[List[int]] = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> List[SearchResult]:
    """Search wiki chunks using semantic embeddings + trust weighting."""

    raw_results = search_similar(
        query=query,
        n_results=n_results * 2,
        model=model,
        source_ids=source_ids,
    )

    results: list[SearchResult] = []
    for chunk_id, similarity, _metadata in raw_results:
        chunk = get_chunk_by_id(chunk_id)
        if not chunk:
            continue
        source = get_source_by_id(chunk.source_id)
        if not source:
            continue
        if trust_level is not None and source.trust_level > trust_level:
            continue

        chunk.source = source
        chunk.similarity_score = similarity
        citation_ref = f"{source.file_name}"
        if chunk.page_or_section:
            citation_ref += f", {chunk.page_or_section}"

        results.append(
            SearchResult(
                chunk=chunk,
                source=source,
                similarity_score=similarity,
                citation_ref=citation_ref,
            )
        )

    results.sort(key=lambda item: item.weighted_score, reverse=True)
    return results[:n_results]


def search_context_docs(
    query: str,
    n_results: int = 5,
    object_type: Optional[str] = None,
) -> List[ContextDocResult]:
    """Search object_context_docs with lexical scoring.

    TODO(v0.9.5): Add optional embedding-based similarity via the same
    ChromaDB pipeline used by wiki search.  For v0.9.4.1 lexical + recency
    is sufficient since context docs are already curated summaries.
    """

    tokens = _tokenize_query(query)
    clauses: list[str] = []
    params: list = []
    if object_type:
        clauses.append("object_type = ?")
        params.append(str(object_type).strip().lower())
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT object_id, object_type, typed_id, summary, markdown, source_event_id, generated_at
            FROM object_context_docs
            {where_clause}
            ORDER BY datetime(generated_at) DESC
            LIMIT 250
            """,
            params,
        ).fetchall()

    scored: list[ContextDocResult] = []
    for idx, row in enumerate(rows):
        summary = str(row["summary"] or "").strip()
        markdown = str(row["markdown"] or "").strip()
        haystack = f"{summary}\n{markdown}".lower()
        if not haystack:
            continue

        if tokens:
            hits = sum(1 for token in tokens if token in haystack)
            if hits == 0:
                continue
            score = hits / max(len(tokens), 1)
        else:
            score = 0.1

        recency_bonus = max(0.0, 0.2 - (idx * 0.01))
        scored.append(
            ContextDocResult(
                object_id=row["object_id"],
                object_type=row["object_type"],
                typed_id=row["typed_id"],
                summary=summary,
                markdown=markdown,
                source_event_id=row["source_event_id"],
                generated_at=row["generated_at"],
                similarity_score=score + recency_bonus,
            )
        )

    scored.sort(key=lambda item: item.weighted_score, reverse=True)
    return scored[: max(0, n_results)]


def get_context_for_query(
    query: str,
    n_chunks: int = 5,
    max_tokens: int = 3000,
    trust_level: Optional[int] = None,
) -> Tuple[str, List]:
    """Build context string with context docs first, then wiki chunks."""

    context_doc_results = search_context_docs(query=query, n_results=max(n_chunks, 3))
    wiki_results = search(query=query, n_results=n_chunks, trust_level=trust_level)
    ordered_results: list = [*context_doc_results, *wiki_results]

    if not ordered_results:
        return "", []

    context_parts: list[str] = []
    total_tokens = 0
    included_results: list = []

    for i, result in enumerate(ordered_results, start=1):
        if isinstance(result, ContextDocResult):
            chunk_text = result.content
            chunk_tokens = max(1, len(chunk_text) // 4)
            source_ref = result.citation_ref
            if result.source_event_id:
                source_ref = f"{source_ref}, event:{result.source_event_id}"
        else:
            chunk_text = result.chunk.content
            chunk_tokens = result.chunk.token_count or (len(chunk_text) // 4)
            source_ref = result.citation_ref

        if total_tokens + chunk_tokens > max_tokens:
            break

        context_parts.append(f"[{i}] Source: {source_ref}\n{chunk_text}\n")
        total_tokens += chunk_tokens
        included_results.append(result)

    context = "\n---\n".join(context_parts)
    return context, included_results


def format_citations_footer(results: List) -> str:
    """Format citations for mixed context-doc and wiki-chunk retrieval results."""

    if not results:
        return ""

    lines = ["---"]
    for i, result in enumerate(results, start=1):
        if isinstance(result, ContextDocResult):
            line = f"[{i}] {result.citation_ref}"
            if result.summary:
                line += f" — {result.summary}"
            if result.source_event_id:
                line += f" (event:{result.source_event_id})"
            lines.append(line)
        else:
            lines.append(format_citation(result.chunk, result.source, i))
    return "\n".join(lines)


def extract_quote(text: str, max_words: int = 30) -> str:
    """Extract a short quote for answer grounding."""

    text = " ".join(text.split())
    words = text.split()
    if len(words) <= max_words:
        return f"\"{text}\""
    truncated = " ".join(words[:max_words])
    return f"\"{truncated}...\""


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
        source_stats = conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM sources
            GROUP BY status
            """
        ).fetchall()
        chunk_count = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
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
