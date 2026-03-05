"""
Tests for wiki embeddings module (v0.9.0).

Note: Many of these tests require Ollama and ChromaDB to be available.
Tests are marked with pytest.mark.integration for those requiring external services.
"""

import pytest
from unittest.mock import patch, MagicMock

from noctem.wiki.embeddings import (
    get_ollama_embedding,
    check_ollama_available,
    EmbeddingError,
    DEFAULT_EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
)


class TestOllamaAvailability:
    """Tests for Ollama availability checking."""
    
    def test_check_ollama_available_mocked_success(self):
        """Test successful Ollama check with mocked response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "nomic-embed-text:latest"},
                {"name": "qwen2.5:7b"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch("noctem.wiki.embeddings.requests.get", return_value=mock_response):
            is_available, message = check_ollama_available()
            assert is_available is True
            assert "ready" in message.lower()
    
    def test_check_ollama_available_model_not_installed(self):
        """Test when embedding model is not installed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b"},  # Different model
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch("noctem.wiki.embeddings.requests.get", return_value=mock_response):
            is_available, message = check_ollama_available()
            assert is_available is False
            assert "not installed" in message.lower()
    
    def test_check_ollama_not_running(self):
        """Test when Ollama is not running."""
        import requests
        
        with patch("noctem.wiki.embeddings.requests.get", 
                   side_effect=requests.exceptions.ConnectionError()):
            is_available, message = check_ollama_available()
            assert is_available is False
            assert "not running" in message.lower()


class TestEmbeddingGeneration:
    """Tests for embedding generation."""
    
    def test_get_embedding_mocked(self):
        """Test embedding generation with mocked response."""
        mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5] * 100  # 500-dim fake embedding
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": mock_embedding}
        mock_response.raise_for_status = MagicMock()
        
        with patch("noctem.wiki.embeddings.requests.post", return_value=mock_response):
            result = get_ollama_embedding("test text")
            assert result == mock_embedding
            assert len(result) == 500
    
    def test_get_embedding_connection_error(self):
        """Test embedding when Ollama is unavailable."""
        import requests
        
        with patch("noctem.wiki.embeddings.requests.post",
                   side_effect=requests.exceptions.ConnectionError()):
            with pytest.raises(EmbeddingError) as exc_info:
                get_ollama_embedding("test text")
            assert "cannot connect" in str(exc_info.value).lower()
    
    def test_get_embedding_timeout(self):
        """Test embedding timeout handling."""
        import requests
        
        with patch("noctem.wiki.embeddings.requests.post",
                   side_effect=requests.exceptions.Timeout()):
            with pytest.raises(EmbeddingError) as exc_info:
                get_ollama_embedding("test text")
            assert "timed out" in str(exc_info.value).lower()


class TestChromaDBIntegration:
    """Tests for ChromaDB integration.
    
    These tests use the actual ChromaDB but with isolated collections.
    """
    
    def test_get_chroma_client(self):
        """Test that we can create a ChromaDB client."""
        from noctem.wiki.embeddings import get_chroma_client
        
        client = get_chroma_client()
        assert client is not None
    
    def test_get_wiki_collection(self):
        """Test that we can get/create the wiki collection."""
        from noctem.wiki.embeddings import get_wiki_collection
        
        collection = get_wiki_collection()
        assert collection is not None
        assert collection.name == "noctem_wiki"
    
    def test_collection_stats(self):
        """Test collection statistics."""
        from noctem.wiki.embeddings import get_collection_stats
        
        stats = get_collection_stats()
        assert "collection_name" in stats
        assert "chunk_count" in stats


class TestVectorStoreOperations:
    """Tests for vector store add/search/delete operations.
    
    These tests mock the embedding generation but use real ChromaDB.
    """
    
    def test_add_and_search_chunks_mocked(self):
        """Test adding and searching chunks with mocked embeddings."""
        from noctem.wiki.embeddings import (
            add_chunks_to_vectorstore,
            search_similar,
            delete_source_embeddings,
            clear_all_embeddings,
        )
        from noctem.models import KnowledgeChunk
        
        # Create test chunks
        test_chunks = [
            KnowledgeChunk(
                id=1,
                source_id=999,  # Test source ID
                chunk_id="test-chunk-001",
                content="Machine learning is a type of artificial intelligence.",
                page_or_section="p.1",
                chunk_index=0,
                token_count=10,
            ),
            KnowledgeChunk(
                id=2,
                source_id=999,
                chunk_id="test-chunk-002",
                content="Deep learning uses neural networks with many layers.",
                page_or_section="p.2",
                chunk_index=1,
                token_count=10,
            ),
        ]
        
        # Mock the embedding function
        fake_embeddings = [
            [0.1] * 768,  # Fake 768-dim embedding
            [0.2] * 768,
        ]
        embedding_index = [0]
        
        def mock_embedding(text, model=None):
            result = fake_embeddings[embedding_index[0] % len(fake_embeddings)]
            embedding_index[0] += 1
            return result
        
        with patch("noctem.wiki.embeddings.get_ollama_embedding", side_effect=mock_embedding):
            # Clear any existing test data
            delete_source_embeddings(999)
            
            # Add chunks
            count = add_chunks_to_vectorstore(test_chunks)
            assert count == 2
            
            # Search (also uses mocked embedding)
            results = search_similar("machine learning", n_results=2)
            
            # Should find our test chunks
            chunk_ids = [r[0] for r in results]
            assert "test-chunk-001" in chunk_ids or "test-chunk-002" in chunk_ids
            
            # Cleanup
            deleted = delete_source_embeddings(999)
            assert deleted == 2


class TestEmbeddingError:
    """Tests for EmbeddingError exception."""
    
    def test_embedding_error_message(self):
        error = EmbeddingError("Test error message")
        assert str(error) == "Test error message"
    
    def test_embedding_error_is_exception(self):
        assert issubclass(EmbeddingError, Exception)
