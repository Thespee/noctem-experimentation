"""
Tests for wiki ingestion module (v0.9.0).
"""

import pytest
import tempfile
from pathlib import Path

from noctem.wiki.ingestion import (
    compute_file_hash,
    detect_file_type,
    extract_text_from_txt,
    extract_text_from_markdown,
    extract_title_from_markdown,
    create_source,
    get_source_by_id,
    get_source_by_path,
    list_sources,
    update_source_status,
    verify_source,
    discover_new_sources,
    delete_source,
)
from noctem.wiki import TRUST_PERSONAL, TRUST_CURATED, TRUST_WEB


class TestFileDetection:
    """Tests for file type detection."""
    
    def test_detect_pdf(self):
        assert detect_file_type(Path("document.pdf")) == "pdf"
        assert detect_file_type(Path("DOCUMENT.PDF")) == "pdf"
    
    def test_detect_markdown(self):
        assert detect_file_type(Path("notes.md")) == "md"
        assert detect_file_type(Path("readme.markdown")) == "md"
    
    def test_detect_txt(self):
        assert detect_file_type(Path("file.txt")) == "txt"
        assert detect_file_type(Path("file.text")) == "txt"
    
    def test_unsupported_type(self):
        assert detect_file_type(Path("document.docx")) is None
        assert detect_file_type(Path("image.png")) is None


class TestFileHash:
    """Tests for file hashing."""
    
    def test_hash_consistency(self):
        """Same content should produce same hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, world!")
            f.flush()
            path = Path(f.name)
        
        hash1 = compute_file_hash(path)
        hash2 = compute_file_hash(path)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        
        path.unlink()
    
    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Content A")
            f.flush()
            path1 = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Content B")
            f.flush()
            path2 = Path(f.name)
        
        hash1 = compute_file_hash(path1)
        hash2 = compute_file_hash(path2)
        
        assert hash1 != hash2
        
        path1.unlink()
        path2.unlink()


class TestTextExtraction:
    """Tests for text extraction."""
    
    def test_extract_txt(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, this is a test file.\nWith multiple lines.")
            f.flush()
            path = Path(f.name)
        
        text = extract_text_from_txt(path)
        
        assert "Hello" in text
        assert "multiple lines" in text
        
        path.unlink()
    
    def test_extract_markdown(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# My Document\n\nThis is **bold** text.")
            f.flush()
            path = Path(f.name)
        
        text = extract_text_from_markdown(path)
        
        assert "# My Document" in text  # Preserves markdown
        assert "**bold**" in text
        
        path.unlink()
    
    def test_extract_title_from_markdown(self):
        content = "# My Great Title\n\nSome content here."
        assert extract_title_from_markdown(content) == "My Great Title"
    
    def test_extract_title_from_markdown_no_title(self):
        content = "Just some text without a heading."
        assert extract_title_from_markdown(content) is None
    
    def test_extract_title_from_markdown_h2_not_title(self):
        content = "## This is H2\n\nNot a title."
        # Should not extract H2 as title
        assert extract_title_from_markdown(content) is None


class TestSourceCRUD:
    """Tests for source database operations."""
    
    def test_create_source_txt(self):
        """Create a source from a text file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content for source creation.")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path, trust_level=TRUST_PERSONAL)
        
        assert source.id is not None
        assert source.file_type == "txt"
        assert source.file_name == path.name
        assert source.trust_level == TRUST_PERSONAL
        assert source.status == "pending"
        assert source.file_hash is not None
        
        # Cleanup
        delete_source(source.id)
        path.unlink()
    
    def test_create_source_markdown_extracts_title(self):
        """Markdown title should be extracted automatically."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# My Document Title\n\nContent goes here.")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        
        assert source.title == "My Document Title"
        
        delete_source(source.id)
        path.unlink()
    
    def test_create_source_with_custom_title(self):
        """Custom title should override extraction."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Auto Title\n\nContent.")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path, title="Custom Title")
        
        assert source.title == "Custom Title"
        
        delete_source(source.id)
        path.unlink()
    
    def test_get_source_by_id(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        retrieved = get_source_by_id(source.id)
        
        assert retrieved.id == source.id
        assert retrieved.file_path == source.file_path
        
        delete_source(source.id)
        path.unlink()
    
    def test_get_source_by_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        retrieved = get_source_by_path(str(path.resolve()))
        
        assert retrieved.id == source.id
        
        delete_source(source.id)
        path.unlink()
    
    def test_list_sources_all(self):
        # Create some sources
        paths = []
        sources = []
        
        for i in range(3):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(f"Content {i}")
                f.flush()
                path = Path(f.name)
                paths.append(path)
            
            source = create_source(path)
            sources.append(source)
        
        all_sources = list_sources()
        source_ids = {s.id for s in sources}
        
        # Our sources should be in the list
        found = [s for s in all_sources if s.id in source_ids]
        assert len(found) == 3
        
        # Cleanup
        for source in sources:
            delete_source(source.id)
        for path in paths:
            path.unlink()
    
    def test_list_sources_by_trust_level(self):
        paths = []
        sources = []
        
        # Create sources with different trust levels
        for trust in [TRUST_PERSONAL, TRUST_CURATED, TRUST_WEB]:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(f"Trust level {trust}")
                f.flush()
                path = Path(f.name)
                paths.append(path)
            
            source = create_source(path, trust_level=trust)
            sources.append(source)
        
        # Filter by trust level
        personal_only = list_sources(trust_level=TRUST_PERSONAL)
        personal_ids = {s.id for s in sources if s.trust_level == TRUST_PERSONAL}
        
        found = [s for s in personal_only if s.id in personal_ids]
        assert len(found) == 1
        
        # Cleanup
        for source in sources:
            delete_source(source.id)
        for path in paths:
            path.unlink()


class TestSourceStatus:
    """Tests for source status updates."""
    
    def test_update_status_to_indexed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        assert source.status == "pending"
        
        update_source_status(source.id, "indexed", chunk_count=5)
        
        updated = get_source_by_id(source.id)
        assert updated.status == "indexed"
        assert updated.chunk_count == 5
        assert updated.ingested_at is not None
        
        delete_source(source.id)
        path.unlink()
    
    def test_update_status_to_failed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        
        update_source_status(source.id, "failed", error_message="Parse error")
        
        updated = get_source_by_id(source.id)
        assert updated.status == "failed"
        assert updated.error_message == "Parse error"
        
        delete_source(source.id)
        path.unlink()


class TestSourceVerification:
    """Tests for source verification (detecting changes)."""
    
    def test_verify_unchanged_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Original content")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        
        # File unchanged
        assert verify_source(source) is True
        
        # Status should still be pending (not changed)
        updated = get_source_by_id(source.id)
        assert updated.status == "pending"
        assert updated.last_verified is not None
        
        delete_source(source.id)
        path.unlink()
    
    def test_verify_changed_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Original content")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        
        # Modify the file
        with open(path, "w") as f:
            f.write("Modified content")
        
        # File changed
        assert verify_source(source) is False
        
        # Status should be 'changed'
        updated = get_source_by_id(source.id)
        assert updated.status == "changed"
        
        delete_source(source.id)
        path.unlink()
    
    def test_verify_missing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Content")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        
        # Delete the file
        path.unlink()
        
        # File missing
        assert verify_source(source) is False
        
        # Status should be 'failed'
        updated = get_source_by_id(source.id)
        assert updated.status == "failed"
        assert "not found" in updated.error_message.lower()
        
        delete_source(source.id)


class TestSourceDiscovery:
    """Tests for discovering new source files."""
    
    def test_discover_new_files(self):
        # Create a temp directory with files
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create some files
            (tmppath / "doc1.txt").write_text("Content 1")
            (tmppath / "doc2.md").write_text("# Content 2")
            (tmppath / "ignored.docx").write_text("Ignored")  # Unsupported
            
            # Discover
            new_files = discover_new_sources(tmppath)
            
            # Should find txt and md, not docx
            extensions = {f.suffix for f in new_files}
            assert ".txt" in extensions
            assert ".md" in extensions
            assert ".docx" not in extensions


class TestSourceDelete:
    """Tests for source deletion."""
    
    def test_delete_source(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test")
            f.flush()
            path = Path(f.name)
        
        source = create_source(path)
        source_id = source.id
        
        # Delete
        result = delete_source(source_id)
        assert result is True
        
        # Should be gone
        assert get_source_by_id(source_id) is None
        
        path.unlink()
    
    def test_delete_nonexistent_source(self):
        result = delete_source(999999)
        assert result is False
