"""
Wiki Chunking Module (v0.9.0)

Splits documents into searchable chunks with overlap and section detection.
Target: 500-1000 tokens per chunk with 100-token overlap.
"""

import re
import uuid
from typing import List, Tuple, Optional
from dataclasses import dataclass

from noctem.db import get_db
from noctem.models import KnowledgeChunk


# Approximate tokens per character (rough estimate for English text)
CHARS_PER_TOKEN = 4

# Target chunk size in tokens
MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 1000
TARGET_CHUNK_TOKENS = 700
OVERLAP_TOKENS = 100


@dataclass
class TextChunk:
    """Intermediate representation of a text chunk before DB storage."""
    content: str
    page_or_section: Optional[str]
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // CHARS_PER_TOKEN


def tokens_to_chars(tokens: int) -> int:
    """Convert token count to approximate character count."""
    return tokens * CHARS_PER_TOKEN


def extract_page_number(text: str) -> Optional[str]:
    """Extract page marker from text if present."""
    match = re.search(r"\[PAGE (\d+)\]", text)
    if match:
        return f"p.{match.group(1)}"
    return None


def extract_markdown_section(text: str) -> Optional[str]:
    """Extract the most recent markdown heading from text."""
    # Find all headings in the text
    headings = re.findall(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE)
    if headings:
        # Return the last (most recent) heading
        level, title = headings[-1]
        return title.strip()
    return None


def find_section_context(full_text: str, position: int) -> Optional[str]:
    """
    Find the section context for a given position in the text.
    
    Looks backward from position to find the nearest heading or page marker.
    """
    text_before = full_text[:position]
    
    # Check for page marker first (PDF)
    page = extract_page_number(text_before[-500:] if len(text_before) > 500 else text_before)
    if page:
        return page
    
    # Check for markdown section
    section = extract_markdown_section(text_before)
    if section:
        return f"## {section}"
    
    return None


def split_into_sentences(text: str) -> List[Tuple[str, int]]:
    """
    Split text into sentences with their starting positions.
    
    Returns:
        List of (sentence, start_position) tuples.
    """
    # Sentence-ending patterns (simplified)
    sentence_pattern = r'(?<=[.!?])\s+'
    
    sentences = []
    current_pos = 0
    
    for match in re.finditer(sentence_pattern, text):
        end_pos = match.start()
        sentence = text[current_pos:end_pos + 1].strip()
        if sentence:
            sentences.append((sentence, current_pos))
        current_pos = match.end()
    
    # Don't forget the last sentence
    if current_pos < len(text):
        last_sentence = text[current_pos:].strip()
        if last_sentence:
            sentences.append((last_sentence, current_pos))
    
    return sentences


def split_into_paragraphs(text: str) -> List[Tuple[str, int]]:
    """
    Split text into paragraphs with their starting positions.
    
    Returns:
        List of (paragraph, start_position) tuples.
    """
    paragraphs = []
    current_pos = 0
    
    # Split on double newlines
    for match in re.finditer(r'\n\s*\n', text):
        para = text[current_pos:match.start()].strip()
        if para:
            paragraphs.append((para, current_pos))
        current_pos = match.end()
    
    # Don't forget the last paragraph
    if current_pos < len(text):
        last_para = text[current_pos:].strip()
        if last_para:
            paragraphs.append((last_para, current_pos))
    
    return paragraphs


def chunk_text(
    text: str,
    file_type: str = "txt",
    min_tokens: int = MIN_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> List[TextChunk]:
    """
    Split text into overlapping chunks suitable for embedding.
    
    Strategy:
    1. Try to split on paragraph boundaries
    2. If paragraphs are too large, split on sentences
    3. Preserve section/page context for each chunk
    4. Add overlap between consecutive chunks
    
    Args:
        text: The full text to chunk
        file_type: 'pdf', 'md', or 'txt' (affects section detection)
        min_tokens: Minimum chunk size in tokens
        max_tokens: Maximum chunk size in tokens  
        overlap_tokens: Number of tokens to overlap between chunks
    
    Returns:
        List of TextChunk objects
    """
    if not text.strip():
        return []
    
    min_chars = tokens_to_chars(min_tokens)
    max_chars = tokens_to_chars(max_tokens)
    overlap_chars = tokens_to_chars(overlap_tokens)
    
    chunks = []
    chunk_index = 0
    
    # First pass: split into paragraphs
    paragraphs = split_into_paragraphs(text)
    
    if not paragraphs:
        # Fallback: treat entire text as one paragraph
        paragraphs = [(text.strip(), 0)]
    
    current_chunk_text = ""
    current_chunk_start = 0
    
    for para_text, para_start in paragraphs:
        para_tokens = estimate_tokens(para_text)
        current_tokens = estimate_tokens(current_chunk_text)
        
        # If adding this paragraph would exceed max, finalize current chunk
        if current_chunk_text and (current_tokens + para_tokens) > max_tokens:
            # Finalize current chunk
            section = find_section_context(text, current_chunk_start)
            chunks.append(TextChunk(
                content=current_chunk_text.strip(),
                page_or_section=section,
                chunk_index=chunk_index,
                start_char=current_chunk_start,
                end_char=current_chunk_start + len(current_chunk_text),
                token_count=estimate_tokens(current_chunk_text),
            ))
            chunk_index += 1
            
            # Start new chunk with overlap from previous
            if overlap_chars > 0 and len(current_chunk_text) > overlap_chars:
                overlap_text = current_chunk_text[-overlap_chars:]
                current_chunk_text = overlap_text + "\n\n" + para_text
                current_chunk_start = para_start - len(overlap_text)
            else:
                current_chunk_text = para_text
                current_chunk_start = para_start
        else:
            # Add paragraph to current chunk
            if current_chunk_text:
                current_chunk_text += "\n\n" + para_text
            else:
                current_chunk_text = para_text
                current_chunk_start = para_start
    
    # Don't forget the last chunk
    if current_chunk_text.strip():
        section = find_section_context(text, current_chunk_start)
        chunks.append(TextChunk(
            content=current_chunk_text.strip(),
            page_or_section=section,
            chunk_index=chunk_index,
            start_char=current_chunk_start,
            end_char=current_chunk_start + len(current_chunk_text),
            token_count=estimate_tokens(current_chunk_text),
        ))
    
    # Handle chunks that are too small by merging
    chunks = _merge_small_chunks(chunks, min_tokens)
    
    # Handle chunks that are too large by splitting on sentences
    chunks = _split_large_chunks(chunks, max_tokens)
    
    # Re-index after merging/splitting
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    
    return chunks


def _merge_small_chunks(chunks: List[TextChunk], min_tokens: int) -> List[TextChunk]:
    """Merge chunks that are too small with their neighbors."""
    if len(chunks) <= 1:
        return chunks
    
    merged = []
    i = 0
    
    while i < len(chunks):
        current = chunks[i]
        
        # If current chunk is too small and there's a next chunk, merge
        while current.token_count < min_tokens and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            current = TextChunk(
                content=current.content + "\n\n" + next_chunk.content,
                page_or_section=current.page_or_section,  # Keep first section
                chunk_index=current.chunk_index,
                start_char=current.start_char,
                end_char=next_chunk.end_char,
                token_count=current.token_count + next_chunk.token_count,
            )
            i += 1
        
        merged.append(current)
        i += 1
    
    return merged


def _split_large_chunks(chunks: List[TextChunk], max_tokens: int) -> List[TextChunk]:
    """Split chunks that are too large on sentence boundaries."""
    result = []
    
    for chunk in chunks:
        if chunk.token_count <= max_tokens:
            result.append(chunk)
            continue
        
        # Split on sentences
        sentences = split_into_sentences(chunk.content)
        
        current_text = ""
        current_start = chunk.start_char
        
        for sentence, rel_pos in sentences:
            sentence_tokens = estimate_tokens(sentence)
            current_tokens = estimate_tokens(current_text)
            
            if current_text and (current_tokens + sentence_tokens) > max_tokens:
                # Finalize current sub-chunk
                result.append(TextChunk(
                    content=current_text.strip(),
                    page_or_section=chunk.page_or_section,
                    chunk_index=chunk.chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(current_text),
                    token_count=estimate_tokens(current_text),
                ))
                current_text = sentence
                current_start = chunk.start_char + rel_pos
            else:
                current_text += " " + sentence if current_text else sentence
        
        # Last sub-chunk
        if current_text.strip():
            result.append(TextChunk(
                content=current_text.strip(),
                page_or_section=chunk.page_or_section,
                chunk_index=chunk.chunk_index,
                start_char=current_start,
                end_char=current_start + len(current_text),
                token_count=estimate_tokens(current_text),
            ))
    
    return result


def save_chunks(source_id: int, chunks: List[TextChunk]) -> List[KnowledgeChunk]:
    """
    Save text chunks to the database.
    
    Returns:
        List of saved KnowledgeChunk objects with IDs.
    """
    saved_chunks = []
    
    with get_db() as conn:
        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            
            cursor = conn.execute(
                """
                INSERT INTO knowledge_chunks (
                    source_id, chunk_id, content, page_or_section,
                    chunk_index, token_count, start_char, end_char, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (source_id, chunk_id, chunk.content, chunk.page_or_section,
                 chunk.chunk_index, chunk.token_count, chunk.start_char, chunk.end_char)
            )
            
            saved_chunks.append(KnowledgeChunk(
                id=cursor.lastrowid,
                source_id=source_id,
                chunk_id=chunk_id,
                content=chunk.content,
                page_or_section=chunk.page_or_section,
                chunk_index=chunk.chunk_index,
                token_count=chunk.token_count,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
            ))
    
    return saved_chunks


def get_chunks_for_source(source_id: int) -> List[KnowledgeChunk]:
    """Get all chunks for a source, ordered by chunk_index."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_chunks 
            WHERE source_id = ? 
            ORDER BY chunk_index
            """,
            (source_id,)
        ).fetchall()
        return [KnowledgeChunk.from_row(row) for row in rows]


def get_chunk_by_id(chunk_id: str) -> Optional[KnowledgeChunk]:
    """Get a chunk by its UUID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE chunk_id = ?",
            (chunk_id,)
        ).fetchone()
        return KnowledgeChunk.from_row(row) if row else None


def delete_chunks_for_source(source_id: int) -> int:
    """Delete all chunks for a source. Returns count deleted."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM knowledge_chunks WHERE source_id = ?",
            (source_id,)
        )
        return cursor.rowcount
