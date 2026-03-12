"""
Wiki Embeddings Module (v0.9.0)

Handles embedding generation via Ollama and vector storage via ChromaDB.
"""

import requests
from typing import List, Optional, Tuple
from pathlib import Path

from noctem.wiki import CHROMA_DIR
from noctem.models import KnowledgeChunk


# Default embedding model (via Ollama)
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_BASE_URL = "http://localhost:11434"

# ChromaDB collection name
WIKI_COLLECTION_NAME = "noctem_wiki"


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


def get_ollama_embedding(text: str, model: str = DEFAULT_EMBEDDING_MODEL) -> List[float]:
    """
    Get embedding vector from Ollama.
    
    Args:
        text: Text to embed
        model: Ollama model name (default: nomic-embed-text)
    
    Returns:
        List of floats representing the embedding vector
    
    Raises:
        EmbeddingError: If Ollama is unavailable or request fails
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60,
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("embedding", [])
    
    except requests.exceptions.ConnectionError:
        raise EmbeddingError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except requests.exceptions.Timeout:
        raise EmbeddingError(f"Ollama embedding request timed out for model {model}")
    except requests.exceptions.HTTPError as e:
        raise EmbeddingError(f"Ollama API error: {e}")
    except Exception as e:
        raise EmbeddingError(f"Embedding failed: {e}")


def get_embeddings_batch(texts: List[str], model: str = DEFAULT_EMBEDDING_MODEL) -> List[List[float]]:
    """
    Get embeddings for multiple texts.
    
    Note: Ollama doesn't support true batch embedding, so this calls sequentially.
    Future optimization: use threading for parallel requests.
    
    Args:
        texts: List of texts to embed
        model: Ollama model name
    
    Returns:
        List of embedding vectors
    """
    embeddings = []
    for text in texts:
        embedding = get_ollama_embedding(text, model)
        embeddings.append(embedding)
    return embeddings


def check_ollama_available(model: str = DEFAULT_EMBEDDING_MODEL) -> Tuple[bool, str]:
    """
    Check if Ollama is available and the embedding model is installed.
    
    Returns:
        Tuple of (is_available, message)
    """
    try:
        # Check if Ollama is running
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        
        # Check if the model is installed
        data = response.json()
        installed_models = [m.get("name", "") for m in data.get("models", [])]
        
        # Model names might have :latest suffix
        model_installed = any(
            model in m or m.startswith(f"{model}:")
            for m in installed_models
        )
        
        if not model_installed:
            return False, (
                f"Embedding model '{model}' not installed. "
                f"Install with: `ollama pull {model}`"
            )
        
        return True, f"Ollama ready with model {model}"
    
    except requests.exceptions.ConnectionError:
        return False, f"Ollama not running. Start with: `ollama serve`"
    except Exception as e:
        return False, f"Ollama check failed: {e}"


def get_chroma_client():
    """
    Get or create ChromaDB client with persistent storage.
    
    Returns:
        chromadb.PersistentClient instance
    """
    try:
        import chromadb
    except ImportError:
        raise ImportError(
            "ChromaDB is required for wiki embeddings. "
            "Install with: pip install chromadb"
        )
    
    # Ensure directory exists
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_wiki_collection():
    """
    Get or create the wiki collection in ChromaDB.
    
    Returns:
        chromadb.Collection instance
    """
    client = get_chroma_client()
    
    # Get or create collection
    collection = client.get_or_create_collection(
        name=WIKI_COLLECTION_NAME,
        metadata={"description": "Noctem wiki knowledge chunks"}
    )
    
    return collection


def add_chunks_to_vectorstore(
    chunks: List[KnowledgeChunk],
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> int:
    """
    Add knowledge chunks to the vector store.
    
    Args:
        chunks: List of KnowledgeChunk objects (must have chunk_id set)
        model: Embedding model to use
    
    Returns:
        Number of chunks added
    """
    if not chunks:
        return 0
    
    collection = get_wiki_collection()
    
    # Prepare data for ChromaDB
    ids = []
    documents = []
    metadatas = []
    embeddings = []
    
    for chunk in chunks:
        if not chunk.chunk_id:
            raise ValueError(f"Chunk missing chunk_id: {chunk}")
        
        # Generate embedding
        embedding = get_ollama_embedding(chunk.content, model)
        
        ids.append(chunk.chunk_id)
        documents.append(chunk.content)
        metadatas.append({
            "source_id": chunk.source_id,
            "page_or_section": chunk.page_or_section or "",
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count or 0,
        })
        embeddings.append(embedding)
    
    # Add to collection
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    
    return len(chunks)


def search_similar(
    query: str,
    n_results: int = 5,
    model: str = DEFAULT_EMBEDDING_MODEL,
    source_ids: Optional[List[int]] = None,
    min_trust_level: Optional[int] = None,
) -> List[Tuple[str, float, dict]]:
    """
    Search for chunks similar to the query.
    
    Args:
        query: Search query text
        n_results: Maximum number of results
        model: Embedding model for query
        source_ids: Optional list of source IDs to filter by
        min_trust_level: Optional minimum trust level (filter in post-processing)
    
    Returns:
        List of (chunk_id, similarity_score, metadata) tuples
    """
    collection = get_wiki_collection()
    
    # Generate query embedding
    query_embedding = get_ollama_embedding(query, model)
    
    # Build where filter if source_ids provided
    where_filter = None
    if source_ids:
        where_filter = {"source_id": {"$in": source_ids}}
    
    # Search
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )
    
    # Process results
    output = []
    if results and results.get("ids") and results["ids"][0]:
        ids = results["ids"][0]
        distances = results["distances"][0] if results.get("distances") else [0] * len(ids)
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        
        for chunk_id, distance, metadata in zip(ids, distances, metadatas):
            # Convert distance to similarity (ChromaDB uses L2 distance)
            # Lower distance = more similar, so we invert
            similarity = 1.0 / (1.0 + distance)
            output.append((chunk_id, similarity, metadata))
    
    return output


def delete_source_embeddings(source_id: int) -> int:
    """
    Delete all embeddings for a source from the vector store.
    
    Args:
        source_id: ID of the source to delete embeddings for
    
    Returns:
        Number of embeddings deleted (approximate)
    """
    collection = get_wiki_collection()
    
    # Get all chunk IDs for this source
    results = collection.get(
        where={"source_id": source_id},
        include=["metadatas"],
    )
    
    if not results or not results.get("ids"):
        return 0
    
    chunk_ids = results["ids"]
    
    # Delete by IDs
    collection.delete(ids=chunk_ids)
    
    return len(chunk_ids)


def get_collection_stats() -> dict:
    """
    Get statistics about the wiki collection.
    
    Returns:
        Dict with count, etc.
    """
    try:
        collection = get_wiki_collection()
        count = collection.count()
        return {
            "collection_name": WIKI_COLLECTION_NAME,
            "chunk_count": count,
            "storage_path": str(CHROMA_DIR),
        }
    except Exception as e:
        return {
            "collection_name": WIKI_COLLECTION_NAME,
            "chunk_count": 0,
            "error": str(e),
        }


def clear_all_embeddings() -> int:
    """
    Clear all embeddings from the wiki collection.
    
    USE WITH CAUTION.
    
    Returns:
        Number of embeddings deleted
    """
    client = get_chroma_client()
    
    try:
        collection = client.get_collection(WIKI_COLLECTION_NAME)
        count = collection.count()
        client.delete_collection(WIKI_COLLECTION_NAME)
        return count
    except Exception:
        return 0
