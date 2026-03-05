"""
Wiki Query Module (v0.9.0)

Query mode: Ask questions and get answers grounded in your wiki with citations.
"""

import requests
from typing import Optional, Tuple, List
from dataclasses import dataclass

from noctem.wiki.retrieval import (
    search,
    get_context_for_query,
    format_citations_footer,
    SearchResult,
)
from noctem.wiki.embeddings import check_ollama_available


# Default LLM for query answering
DEFAULT_QUERY_MODEL = "qwen2.5:7b-instruct-q4_K_M"
OLLAMA_BASE_URL = "http://localhost:11434"


# System prompt for wiki Q&A
WIKI_QA_SYSTEM_PROMPT = """You are a helpful assistant answering questions based on the user's personal knowledge base.

IMPORTANT RULES:
1. ONLY use information from the provided sources to answer.
2. If the sources don't contain enough information to answer, say "I don't have enough information in my sources to answer this question."
3. ALWAYS cite your sources using [1], [2], etc. matching the source numbers provided.
4. Keep answers concise but complete.
5. If you quote directly, keep quotes under 30 words and use quotation marks.
6. Never make up information not in the sources.

The user's sources are provided below. Answer their question using ONLY these sources."""


@dataclass
class WikiAnswer:
    """A wiki query answer with citations."""
    answer: str
    sources_used: List[SearchResult]
    citations: str  # Formatted footer
    query: str
    model_used: str
    context_tokens: int
    
    @property
    def has_answer(self) -> bool:
        """Whether a meaningful answer was generated."""
        return bool(self.answer and "don't have enough information" not in self.answer.lower())
    
    def formatted(self) -> str:
        """Get the full formatted answer with citations."""
        if self.citations:
            return f"{self.answer}\n\n{self.citations}"
        return self.answer


def query_llm(
    prompt: str,
    system_prompt: str = WIKI_QA_SYSTEM_PROMPT,
    model: str = DEFAULT_QUERY_MODEL,
    temperature: float = 0.3,
) -> str:
    """
    Query the LLM via Ollama.
    
    Args:
        prompt: User prompt with context
        system_prompt: System instructions
        model: Ollama model name
        temperature: Response temperature (lower = more focused)
    
    Returns:
        Generated response text
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("response", "").strip()
    
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure it's running: `ollama serve`"
    except requests.exceptions.Timeout:
        return "Error: LLM request timed out. Try a shorter query or check Ollama."
    except Exception as e:
        return f"Error: {e}"


def ask(
    question: str,
    n_sources: int = 5,
    max_context_tokens: int = 3000,
    trust_level: Optional[int] = None,
    model: str = DEFAULT_QUERY_MODEL,
) -> WikiAnswer:
    """
    Ask a question and get an answer grounded in your wiki.
    
    Args:
        question: The user's question
        n_sources: Maximum number of source chunks to use
        max_context_tokens: Maximum tokens of context to include
        trust_level: Optional filter (1=personal only, 2=personal+curated, 3=all)
        model: LLM model for generating answer
    
    Returns:
        WikiAnswer object with answer, sources, and citations
    """
    # Get relevant context
    context, results = get_context_for_query(
        query=question,
        n_chunks=n_sources,
        max_tokens=max_context_tokens,
        trust_level=trust_level,
    )
    
    if not context:
        return WikiAnswer(
            answer="I don't have any sources in my knowledge base yet. "
                   "Add documents to `data/sources/` and run `noctem wiki ingest`.",
            sources_used=[],
            citations="",
            query=question,
            model_used=model,
            context_tokens=0,
        )
    
    # Estimate context tokens
    context_tokens = len(context) // 4
    
    # Build prompt
    prompt = f"""Based on the following sources from my knowledge base:

{context}

Question: {question}

Answer (cite sources using [1], [2], etc.):"""
    
    # Query LLM
    answer = query_llm(prompt, model=model)
    
    # Format citations
    citations = format_citations_footer(results)
    
    return WikiAnswer(
        answer=answer,
        sources_used=results,
        citations=citations,
        query=question,
        model_used=model,
        context_tokens=context_tokens,
    )


def simple_search(
    query: str,
    n_results: int = 5,
    trust_level: Optional[int] = None,
) -> List[Tuple[str, str, float]]:
    """
    Simple search without LLM - just returns matching chunks.
    
    Args:
        query: Search query
        n_results: Max results
        trust_level: Optional trust filter
    
    Returns:
        List of (content_snippet, citation_ref, similarity_score) tuples
    """
    results = search(
        query=query,
        n_results=n_results,
        trust_level=trust_level,
    )
    
    output = []
    for result in results:
        # Truncate content for display
        content = result.chunk.content
        if len(content) > 300:
            content = content[:300] + "..."
        
        output.append((
            content,
            result.citation_ref,
            result.similarity_score,
        ))
    
    return output


def check_wiki_ready() -> Tuple[bool, str]:
    """
    Check if the wiki is ready for queries.
    
    Returns:
        Tuple of (is_ready, message)
    """
    issues = []
    
    # Check Ollama
    ollama_ok, ollama_msg = check_ollama_available()
    if not ollama_ok:
        issues.append(f"Ollama: {ollama_msg}")
    
    # Check for indexed sources
    from noctem.wiki.retrieval import get_wiki_stats
    stats = get_wiki_stats()
    
    indexed_count = stats.get("sources_by_status", {}).get("indexed", 0)
    if indexed_count == 0:
        issues.append("No indexed sources. Run `noctem wiki ingest` first.")
    
    chunk_count = stats.get("total_chunks", 0)
    if chunk_count == 0:
        issues.append("No knowledge chunks. Sources may have failed to process.")
    
    if issues:
        return False, "Wiki not ready:\n- " + "\n- ".join(issues)
    
    return True, f"Wiki ready: {indexed_count} sources, {chunk_count} chunks indexed."
