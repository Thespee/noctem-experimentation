"""v0.9.4 retrieval integration tests for context-doc-first behavior."""

from uuid import uuid4

from noctem.mcp import get_mcp_server
from noctem.models import KnowledgeChunk, Source
from noctem.services.object_context_docs import synthesize_object_context_doc
from noctem.wiki import retrieval


def _create_task_via_mcp(name: str) -> int:
    result = get_mcp_server().call_tool(
        "tasks.create",
        {"name": name},
        context={"source": "test.retrieval"},
    )
    assert result.get("ok") is True
    return int(result["result"]["task"]["id"])


def test_search_context_docs_returns_matching_object_doc():
    marker = f"retrieval-doc-{uuid4().hex[:8]}"
    task_id = _create_task_via_mcp(marker)
    object_id = f"task:{task_id}"
    synthesize_object_context_doc(object_id)

    docs = retrieval.search_context_docs(marker, n_results=10)
    assert docs
    assert any(doc.object_id == object_id for doc in docs)


def test_get_context_for_query_prioritizes_context_docs(monkeypatch):
    marker = f"context-priority-{uuid4().hex[:8]}"
    task_id = _create_task_via_mcp(marker)
    object_id = f"task:{task_id}"
    synthesize_object_context_doc(object_id)

    monkeypatch.setattr(retrieval, "search", lambda **kwargs: [])
    context, results = retrieval.get_context_for_query(
        query=marker,
        n_chunks=3,
        max_tokens=2000,
    )
    assert context
    assert results
    assert isinstance(results[0], retrieval.ContextDocResult)
    assert f"context:{object_id}" in context


def test_format_citations_footer_includes_context_and_trust_tier():
    context_result = retrieval.ContextDocResult(
        object_id="task:101",
        object_type="task",
        typed_id=101,
        summary="Task context summary",
        markdown="Task markdown",
        source_event_id="audit-xyz",
        generated_at="2026-03-12T00:00:00Z",
        similarity_score=0.9,
    )
    wiki_source = Source(id=1, file_name="guide.md", trust_level=1)
    wiki_chunk = KnowledgeChunk(id=1, source_id=1, chunk_id="chunk-1", content="chunk", page_or_section="## Intro")
    wiki_result = retrieval.SearchResult(
        chunk=wiki_chunk,
        source=wiki_source,
        similarity_score=0.5,
        citation_ref="guide.md, ## Intro",
    )

    footer = retrieval.format_citations_footer([context_result, wiki_result])
    assert "context:task:101" in footer
    assert "event:audit-xyz" in footer
    assert "guide.md" in footer
    assert "trust:personal" in footer
