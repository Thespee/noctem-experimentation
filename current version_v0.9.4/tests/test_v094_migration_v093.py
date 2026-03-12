"""v0.9.4 migration test coverage for v0.9.3 -> v0.9.4 utility."""

import json
import sqlite3
from pathlib import Path

from noctem.migration.v093_to_v094 import run_v093_to_v094_migration


def _create_source_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE goals (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT,
            description TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            goal_id INTEGER,
            status TEXT,
            summary TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            project_id INTEGER,
            status TEXT,
            due_date DATE,
            due_time TIME,
            importance REAL,
            tags TEXT,
            recurrence_rule TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE time_blocks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            source TEXT,
            external_event_id TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            source TEXT,
            role TEXT,
            content TEXT,
            metadata TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE voice_journals (
            id INTEGER PRIMARY KEY,
            audio_path TEXT,
            original_filename TEXT,
            source TEXT,
            status TEXT,
            transcription TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            file_type TEXT,
            file_name TEXT,
            title TEXT,
            trust_level INTEGER,
            status TEXT,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE knowledge_chunks (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            chunk_id TEXT,
            content TEXT,
            page_or_section TEXT,
            chunk_index INTEGER,
            token_count INTEGER,
            created_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO goals (id, name, type, description, created_at)
        VALUES (1, 'Goal Migration', 'bigger_goal', 'Goal description', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO projects (id, name, goal_id, status, summary, created_at)
        VALUES (1, 'Project Migration', 1, 'in_progress', 'Summary', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO tasks (id, name, project_id, status, due_date, due_time, importance, tags, recurrence_rule, created_at)
        VALUES (1, 'Task Migration', 1, 'not_started', '2026-03-20', '10:00:00', 0.8, '["tag1"]', NULL, '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO time_blocks (id, title, start_time, end_time, source, external_event_id, created_at)
        VALUES (1, 'Event Migration', '2026-03-20T10:00:00', '2026-03-20T11:00:00', 'ics', 'event-1', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO conversations (id, session_id, source, role, content, metadata, created_at)
        VALUES (1, 'thread-1', 'web', 'user', 'hello migration', '{}', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO voice_journals (id, audio_path, original_filename, source, status, transcription, created_at)
        VALUES (1, 'voice/file.ogg', 'file.ogg', 'web', 'completed', 'voice text', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO sources (id, file_path, file_type, file_name, title, trust_level, status, created_at)
        VALUES (1, 'sources/doc.md', 'md', 'doc.md', 'Doc', 1, 'indexed', '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO knowledge_chunks (id, source_id, chunk_id, content, page_or_section, chunk_index, token_count, created_at)
        VALUES (1, 1, 'chunk-1', 'project migration content', 'intro', 0, 5, '2026-03-12T00:00:00Z')
        """
    )
    conn.execute(
        "INSERT INTO config (key, value) VALUES ('ics_urls', ?)",
        (json.dumps([{"url": "https://example.com/a.ics", "name": "A"}]),),
    )
    conn.commit()
    conn.close()


def test_run_v093_to_v094_migration_populates_object_core_and_verifies(tmp_path):
    source_data_dir = tmp_path / "source_data"
    target_data_dir = tmp_path / "target_data"
    source_data_dir.mkdir(parents=True)
    target_data_dir.mkdir(parents=True)
    source_db = source_data_dir / "noctem.db"
    target_db = target_data_dir / "noctem.db"
    _create_source_db(source_db)

    (source_data_dir / "sources").mkdir(parents=True)
    (source_data_dir / "sources" / "doc.md").write_text("source content", encoding="utf-8")
    (source_data_dir / "chroma").mkdir(parents=True)
    (source_data_dir / "chroma" / "index.bin").write_bytes(b"abc")

    export_dir = tmp_path / "exports"
    report = run_v093_to_v094_migration(
        source_db=source_db,
        target_db=target_db,
        export_dir=export_dir,
        copy_wiki_artifacts=True,
    )

    assert report["verification"]["ok"] is True
    assert Path(report["seed_snapshot_file"]).exists()
    assert Path(report["export_dir"]).exists()
    assert report["object_import"]["object_total"] == 8
    assert report["copied_ics_urls"]["copied"] is True

    conn = sqlite3.connect(target_db)
    object_count = conn.execute("SELECT COUNT(1) FROM objects").fetchone()[0]
    version_count = conn.execute("SELECT COUNT(1) FROM object_versions").fetchone()[0]
    ref_count = conn.execute("SELECT COUNT(1) FROM object_refs").fetchone()[0]
    task_objects = conn.execute("SELECT COUNT(1) FROM objects WHERE object_id = 'task:1'").fetchone()[0]
    conn.close()

    assert object_count == 8
    assert version_count == 8
    assert ref_count == 8
    assert task_objects == 1

    assert (target_data_dir / "sources" / "doc.md").exists()
    assert (target_data_dir / "chroma" / "index.bin").exists()
