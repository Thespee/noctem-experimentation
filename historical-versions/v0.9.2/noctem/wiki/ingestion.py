"""
Wiki Ingestion Pipeline (v0.9.0)

Handles file detection, text extraction, and source tracking.
Supports: PDF, Markdown, TXT files.
"""

import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List
import re

from noctem.db import get_db
from noctem.models import Source
from noctem.wiki import SOURCES_DIR, SUPPORTED_EXTENSIONS, TRUST_PERSONAL


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def detect_file_type(file_path: Path) -> Optional[str]:
    """Detect file type from extension."""
    ext = file_path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".md": "md",
        ".markdown": "md",
        ".txt": "txt",
        ".text": "txt",
    }
    return type_map.get(ext)


def extract_text_from_txt(file_path: Path) -> str:
    """Extract text from a plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_text_from_markdown(file_path: Path) -> str:
    """Extract text from a Markdown file (preserves structure for section detection)."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_text_from_pdf(file_path: Path) -> Tuple[str, dict]:
    """
    Extract text from a PDF file using PyMuPDF.
    
    Returns:
        Tuple of (full_text, metadata_dict)
        metadata_dict contains: title, author, page_count
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF extraction. Install with: pip install PyMuPDF")
    
    doc = fitz.open(file_path)
    
    # Extract metadata
    metadata = {
        "title": doc.metadata.get("title", ""),
        "author": doc.metadata.get("author", ""),
        "page_count": len(doc),
    }
    
    # Extract text with page markers
    text_parts = []
    for page_num, page in enumerate(doc, start=1):
        page_text = page.get_text()
        if page_text.strip():
            # Add page marker for citation tracking
            text_parts.append(f"[PAGE {page_num}]\n{page_text}")
    
    doc.close()
    return "\n\n".join(text_parts), metadata


def extract_text(file_path: Path) -> Tuple[str, dict]:
    """
    Extract text from a file based on its type.
    
    Returns:
        Tuple of (text_content, metadata_dict)
    """
    file_type = detect_file_type(file_path)
    
    if file_type == "txt":
        return extract_text_from_txt(file_path), {}
    elif file_type == "md":
        return extract_text_from_markdown(file_path), {}
    elif file_type == "pdf":
        return extract_text_from_pdf(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")


def extract_title_from_markdown(content: str) -> Optional[str]:
    """Extract title from first H1 heading in markdown."""
    match = re.match(r"^#\s+(.+)$", content.strip(), re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def get_source_by_path(file_path: str) -> Optional[Source]:
    """Get a source by its file path."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE file_path = ?",
            (file_path,)
        ).fetchone()
        return Source.from_row(row) if row else None


def get_source_by_id(source_id: int) -> Optional[Source]:
    """Get a source by its ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ?",
            (source_id,)
        ).fetchone()
        return Source.from_row(row) if row else None


def list_sources(status: Optional[str] = None, trust_level: Optional[int] = None) -> List[Source]:
    """List all sources, optionally filtered by status or trust level."""
    with get_db() as conn:
        query = "SELECT * FROM sources WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if trust_level is not None:
            query += " AND trust_level = ?"
            params.append(trust_level)
        
        query += " ORDER BY created_at DESC"
        
        rows = conn.execute(query, params).fetchall()
        return [Source.from_row(row) for row in rows]


def create_source(
    file_path: Path,
    trust_level: int = TRUST_PERSONAL,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> Source:
    """
    Create a new source record for a file.
    
    Args:
        file_path: Path to the source file
        trust_level: 1=personal, 2=curated, 3=web
        title: Optional title (extracted from file if not provided)
        author: Optional author
    
    Returns:
        Created Source object
    """
    file_path = Path(file_path).resolve()
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_type = detect_file_type(file_path)
    if file_type is None:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")
    
    file_hash = compute_file_hash(file_path)
    file_size = file_path.stat().st_size
    file_name = file_path.name
    
    # Try to extract title if not provided
    if not title:
        if file_type == "md":
            content = extract_text_from_markdown(file_path)
            title = extract_title_from_markdown(content)
        elif file_type == "pdf":
            _, metadata = extract_text_from_pdf(file_path)
            title = metadata.get("title") or None
            if not author:
                author = metadata.get("author") or None
    
    # Use filename as fallback title
    if not title:
        title = file_path.stem
    
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sources (
                file_path, file_type, file_name, title, author,
                file_hash, file_size_bytes, trust_level, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
            """,
            (str(file_path), file_type, file_name, title, author,
             file_hash, file_size, trust_level)
        )
        source_id = cursor.lastrowid
    
    return get_source_by_id(source_id)


def update_source_status(
    source_id: int,
    status: str,
    chunk_count: int = None,
    error_message: str = None,
) -> None:
    """Update source status after processing."""
    with get_db() as conn:
        if status == "indexed":
            conn.execute(
                """
                UPDATE sources 
                SET status = ?, chunk_count = ?, ingested_at = CURRENT_TIMESTAMP, error_message = NULL
                WHERE id = ?
                """,
                (status, chunk_count or 0, source_id)
            )
        elif status == "failed":
            conn.execute(
                """
                UPDATE sources 
                SET status = ?, error_message = ?
                WHERE id = ?
                """,
                (status, error_message, source_id)
            )
        else:
            conn.execute(
                "UPDATE sources SET status = ? WHERE id = ?",
                (status, source_id)
            )


def verify_source(source: Source) -> bool:
    """
    Verify if a source file has changed since ingestion.
    
    Returns:
        True if file is unchanged, False if changed or missing.
    """
    file_path = Path(source.file_path)
    
    if not file_path.exists():
        with get_db() as conn:
            conn.execute(
                "UPDATE sources SET status = 'failed', error_message = 'File not found' WHERE id = ?",
                (source.id,)
            )
        return False
    
    current_hash = compute_file_hash(file_path)
    
    with get_db() as conn:
        conn.execute(
            "UPDATE sources SET last_verified = CURRENT_TIMESTAMP WHERE id = ?",
            (source.id,)
        )
        
        if current_hash != source.file_hash:
            conn.execute(
                "UPDATE sources SET status = 'changed' WHERE id = ?",
                (source.id,)
            )
            return False
    
    return True


def discover_new_sources(directory: Path = None) -> List[Path]:
    """
    Discover new files in the sources directory that haven't been indexed.
    
    Returns:
        List of paths to new files.
    """
    directory = directory or SOURCES_DIR
    
    # Get all supported files in directory
    all_files = []
    for ext in SUPPORTED_EXTENSIONS:
        all_files.extend(directory.glob(f"*{ext}"))
        all_files.extend(directory.glob(f"**/*{ext}"))  # Recursive
    
    # Get already-tracked paths
    with get_db() as conn:
        rows = conn.execute("SELECT file_path FROM sources").fetchall()
        tracked_paths = {row["file_path"] for row in rows}
    
    # Find new files
    new_files = []
    for file_path in all_files:
        if str(file_path.resolve()) not in tracked_paths:
            new_files.append(file_path)
    
    return new_files


def delete_source(source_id: int) -> bool:
    """
    Delete a source and its chunks from the database.
    
    Note: Does NOT delete the actual file or ChromaDB embeddings.
    Call embeddings.delete_source_embeddings() separately for full cleanup.
    
    Returns:
        True if deleted, False if not found.
    """
    with get_db() as conn:
        # Delete chunks first (foreign key)
        conn.execute("DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,))
        
        # Delete source
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return cursor.rowcount > 0
