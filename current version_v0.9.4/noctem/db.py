"""
Database connection and schema initialization for Noctem.

Data directory layout:
- Default: <package>/data/
- Override with env var: NOCTEM_DATA_DIR

This lets you keep runtime/personal data outside of git (e.g. in /personal-data/).
"""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager


def _resolve_data_dir() -> Path:
    raw = os.environ.get("NOCTEM_DATA_DIR")
    if not raw:
        return Path(__file__).parent / "data"

    p = Path(raw).expanduser()
    # If a relative path is provided, interpret relative to current working directory
    if not p.is_absolute():
        p = (Path.cwd() / p)
    return p


# Runtime data directory
DATA_DIR = _resolve_data_dir().resolve()

# Database path
DB_PATH = DATA_DIR / "noctem.db"

SCHEMA = """
-- Goals
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT CHECK(type IN ('bigger_goal', 'daily_goal')),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived INTEGER DEFAULT 0
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    goal_id INTEGER REFERENCES goals(id),
    status TEXT DEFAULT 'in_progress'
        CHECK(status IN ('backburner', 'in_progress', 'done', 'canceled')),
    summary TEXT,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_action_suggestion TEXT,
    suggestion_generated_at TIMESTAMP
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    status TEXT DEFAULT 'not_started'
        CHECK(status IN ('not_started', 'in_progress', 'done', 'canceled')),
    due_date DATE,
    due_time TIME,
    importance REAL DEFAULT 0.5,
    tags TEXT,
    recurrence_rule TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    computer_help_suggestion TEXT,
    suggestion_generated_at TIMESTAMP,
    duration_minutes INTEGER
);

-- Calendar time blocks
CREATE TABLE IF NOT EXISTS time_blocks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'manual' CHECK(source IN ('manual', 'ics')),
    external_event_id TEXT,
    block_type TEXT DEFAULT 'other'
        CHECK(block_type IN ('meeting', 'focus', 'personal', 'other')),
    all_day INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System config (key-value)
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Voice journals
CREATE TABLE IF NOT EXISTS voice_journals (
    id INTEGER PRIMARY KEY,
    audio_path TEXT NOT NULL,
    original_filename TEXT,
    source TEXT DEFAULT 'web'
        CHECK(source IN ('telegram', 'web')),
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'transcribing', 'completed', 'failed')),
    transcription TEXT,
    duration_seconds REAL,
    language TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transcribed_at TIMESTAMP,
    error_message TEXT,
    transcription_edited TEXT,
    transcription_edited_at TIMESTAMP
);

-- Unified conversations
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    source TEXT,
    role TEXT,
    content TEXT,
    thinking_summary TEXT,
    thinking_level TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wiki source documents
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_type TEXT,
    file_name TEXT,
    title TEXT,
    author TEXT,
    file_hash TEXT,
    file_size_bytes INTEGER,
    trust_level INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'processing', 'indexed', 'failed', 'changed')),
    chunk_count INTEGER DEFAULT 0,
    ingested_at TIMESTAMP,
    last_verified TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) NOT NULL,
    chunk_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    page_or_section TEXT,
    chunk_index INTEGER,
    token_count INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agentic workflow runtime tables
CREATE TABLE IF NOT EXISTS agent_workflows (
    id INTEGER PRIMARY KEY,
    workflow_type TEXT NOT NULL,
    thread_id TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'active'
        CHECK(status IN ('active', 'interrupted', 'completed', 'failed')),
    current_node TEXT,
    source TEXT DEFAULT 'web',
    input_text TEXT,
    output_text TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_interrupts (
    id INTEGER PRIMARY KEY,
    workflow_id INTEGER REFERENCES agent_workflows(id),
    interrupt_type TEXT NOT NULL,
    question TEXT NOT NULL,
    options TEXT,
    context TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution TEXT
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id INTEGER PRIMARY KEY,
    workflow_id INTEGER REFERENCES agent_workflows(id),
    action_type TEXT NOT NULL,
    input_data TEXT,
    output_data TEXT,
    decision_reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.9.4: Universal object core
CREATE TABLE IF NOT EXISTS objects (
    object_id TEXT PRIMARY KEY,
    object_type TEXT NOT NULL,
    typed_id INTEGER,
    review_state TEXT DEFAULT 'active'
        CHECK(review_state IN ('active', 'manual_review', 'resolved', 'archived')),
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS object_versions (
    version_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES objects(object_id),
    version_num INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    parent_version_id TEXT,
    event_id TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(object_id, version_num)
);

CREATE TABLE IF NOT EXISTS object_refs (
    object_id TEXT PRIMARY KEY REFERENCES objects(object_id),
    head_version_id TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS object_events (
    event_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    summary TEXT,
    details_json TEXT,
    undo_actions_json TEXT,
    correlation_id TEXT,
    idempotency_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mutation_previews (
    preview_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mutation_commit_results (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS undo_previews (
    undo_id TEXT PRIMARY KEY,
    event_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_id TEXT PRIMARY KEY,
    object_id TEXT,
    event_id TEXT,
    reason_code TEXT NOT NULL,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'rejected', 'resolved')),
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);
CREATE TABLE IF NOT EXISTS execution_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    source TEXT,
    thread_id TEXT,
    payload_json TEXT NOT NULL,
    status TEXT DEFAULT 'queued'
        CHECK(status IN ('queued', 'processing', 'completed', 'failed', 'review_blocked', 'cancelled')),
    attempt_count INTEGER DEFAULT 0,
    idempotency_key TEXT,
    priority_rank INTEGER DEFAULT 100,
    available_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    review_created_at TIMESTAMP,
    last_error TEXT,
    stale_context_json TEXT,
    result_json TEXT,
    locked_by TEXT,
    locked_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_seconds REAL,
    ok INTEGER NOT NULL DEFAULT 1,
    summary_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS delivery_publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_item_id INTEGER,
    thread_id TEXT,
    channel TEXT NOT NULL
        CHECK(channel IN ('web', 'telegram')),
    status TEXT NOT NULL
        CHECK(status IN ('delivered', 'failed', 'skipped')),
    payload_json TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS object_context_docs (
    object_id TEXT PRIMARY KEY REFERENCES objects(object_id),
    object_type TEXT NOT NULL,
    typed_id INTEGER,
    summary TEXT,
    context_json TEXT NOT NULL,
    markdown TEXT,
    source_version_id TEXT,
    source_event_id TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.9.4.1: Plan steps for multi-step plan objects
CREATE TABLE IF NOT EXISTS plan_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL,
    workflow_id INTEGER REFERENCES agent_workflows(id),
    step_index INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'executing', 'completed', 'failed', 'skipped')),
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.9.4.1: Conversation compaction records
CREATE TABLE IF NOT EXISTS conversation_compactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    dropped_line_count INTEGER NOT NULL DEFAULT 0,
    facts_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_time_blocks_start ON time_blocks(start_time);
CREATE INDEX IF NOT EXISTS idx_time_blocks_external_event ON time_blocks(external_event_id);
CREATE INDEX IF NOT EXISTS idx_voice_journals_status ON voice_journals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_source ON conversations(source, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_level ON conversations(thinking_level, created_at);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_trust ON sources(trust_level);
CREATE INDEX IF NOT EXISTS idx_sources_file_path ON sources(file_path);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON knowledge_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON knowledge_chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_agent_workflows_status ON agent_workflows(status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_workflows_thread ON agent_workflows(thread_id);
CREATE INDEX IF NOT EXISTS idx_agent_interrupts_pending ON agent_interrupts(workflow_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_agent_actions_workflow ON agent_actions(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS idx_objects_type_typed_id ON objects(object_type, typed_id);
CREATE INDEX IF NOT EXISTS idx_object_versions_object ON object_versions(object_id, version_num);
CREATE INDEX IF NOT EXISTS idx_object_events_operation ON object_events(operation, created_at);
CREATE INDEX IF NOT EXISTS idx_mutation_previews_operation ON mutation_previews(operation, created_at);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_queue_status_order ON execution_queue(status, priority_rank, available_at, id);
CREATE INDEX IF NOT EXISTS idx_execution_queue_thread ON execution_queue(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_queue_idempotency ON execution_queue(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job ON scheduler_runs(job_name, started_at);
CREATE INDEX IF NOT EXISTS idx_delivery_publications_queue_channel ON delivery_publications(queue_item_id, channel, created_at);
CREATE INDEX IF NOT EXISTS idx_object_context_docs_generated ON object_context_docs(object_type, generated_at);
CREATE INDEX IF NOT EXISTS idx_conversation_compactions_thread ON conversation_compactions(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_plan_steps_plan ON plan_steps(plan_id, step_index);
CREATE INDEX IF NOT EXISTS idx_plan_steps_workflow ON plan_steps(workflow_id, status);
"""
LEGACY_RUNTIME_TABLES = (
    "butler_contacts",
    "slow_work_queue",
    # child -> parent order for FK-linked legacy tables
    "prompt_versions",
    "prompt_templates",
    "feedback_questions",
    "feedback_sessions",
    "skill_executions",
    "skills",
    "execution_logs",
    "model_registry",
    "maintenance_insights",
    "learned_rules",
    "detected_patterns",
    "feedback_events",
    "experiment_results",
    "experiments",
)


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database schema."""
    with get_db() as conn:
        conn.executescript(SCHEMA)
    
    # Run migrations for existing databases
    _migrate_db()
    _drop_legacy_runtime_tables()
    
    print(f"Database initialized at {DB_PATH}")


def _migrate_db():
    """Add missing columns to existing tables (for upgrades)."""
    migrations = [
        ("tasks", "computer_help_suggestion", "TEXT"),
        ("tasks", "suggestion_generated_at", "TIMESTAMP"),
        ("projects", "next_action_suggestion", "TEXT"),
        ("projects", "suggestion_generated_at", "TIMESTAMP"),
        ("tasks", "duration_minutes", "INTEGER"),
        ("time_blocks", "external_event_id", "TEXT"),
        ("time_blocks", "all_day", "INTEGER DEFAULT 0"),
        ("voice_journals", "transcription_edited", "TEXT"),
        ("voice_journals", "transcription_edited_at", "TIMESTAMP"),
    ]

    def _table_exists(table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _column_names(table_name: str) -> list[str]:
        cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
        return [row[1] for row in cursor.fetchall()]
    with get_db() as conn:
        for table, column, col_type in migrations:
            if not _table_exists(table):
                continue
            columns = _column_names(table)
            if column not in columns:
                try:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {col_type}')
                    print(f"  Added column {table}.{column}")
                except Exception:
                    pass

        if _table_exists("time_blocks"):
            columns = _column_names("time_blocks")
            if "gcal_event_id" in columns:
                conn.execute(
                    """
                    UPDATE time_blocks
                    SET external_event_id = COALESCE(external_event_id, gcal_event_id)
                    WHERE gcal_event_id IS NOT NULL
                    """
                )
                try:
                    conn.execute("ALTER TABLE time_blocks DROP COLUMN gcal_event_id")
                except Exception:
                    pass
            conn.execute("UPDATE time_blocks SET source = 'ics' WHERE source = 'gcal'")

        for table_name in ("action_log", "message_log", "thoughts"):
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')


def _drop_legacy_runtime_tables():
    """
    Remove tables for runtime surfaces stripped in v0.9.3.

    This runs on every init to ensure upgraded databases converge
    to the active agentic schema.
    """
    # Use a direct connection so we can safely toggle FK checks for
    # destructive schema cleanup on upgraded databases.
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in LEGACY_RUNTIME_TABLES:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def reset_db():
    """Drop all tables and reinitialize. USE WITH CAUTION."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()


if __name__ == "__main__":
    init_db()
