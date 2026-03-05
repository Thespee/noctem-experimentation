"""
Noctem Wiki Module (v0.9.0)

Personal knowledge base with semantic search and citations.

Components:
- ingestion: File parsing (PDF, MD, TXT) and source tracking
- chunking: Text splitting with overlap and section detection
- embeddings: Ollama + ChromaDB integration for vector storage
- retrieval: Semantic search with trust level weighting
- query: Query mode with LLM-generated answers and citations
"""

from pathlib import Path

from noctem.db import DATA_DIR

# Wiki data directories
# NOTE: use the same shared runtime DATA_DIR as the DB so everything is portable.
SOURCES_DIR = DATA_DIR / "sources"
CHROMA_DIR = DATA_DIR / "chroma"

# Ensure directories exist
SOURCES_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Supported file types
SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}

# Trust levels
TRUST_PERSONAL = 1  # Your own notes
TRUST_CURATED = 2   # Vetted sources you trust
TRUST_WEB = 3       # Unverified web content

__all__ = [
    "SOURCES_DIR",
    "CHROMA_DIR",
    "SUPPORTED_EXTENSIONS",
    "TRUST_PERSONAL",
    "TRUST_CURATED",
    "TRUST_WEB",
]
