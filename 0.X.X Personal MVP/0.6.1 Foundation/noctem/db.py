"""
Database connection and schema initialization for Noctem.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Database path - relative to this file's directory
DB_PATH = Path(__file__).parent / "data" / "noctem.db"

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
    -- v0.6.0: Slow mode suggestions
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
    importance REAL DEFAULT 0.5,  -- 0-1 scale: 1=important, 0.5=medium, 0=not important
    tags TEXT,  -- JSON array
    recurrence_rule TEXT,  -- e.g., "FREQ=DAILY", "FREQ=WEEKLY;BYDAY=MO"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    -- v0.6.0: Slow mode suggestions
    computer_help_suggestion TEXT,
    suggestion_generated_at TIMESTAMP
);

-- Calendar time blocks
CREATE TABLE IF NOT EXISTS time_blocks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'manual' CHECK(source IN ('manual', 'gcal', 'ics')),
    gcal_event_id TEXT,
    block_type TEXT DEFAULT 'other'
        CHECK(block_type IN ('meeting', 'focus', 'personal', 'other')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System config (key-value)
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT  -- JSON
);

-- Action log (for extensive local records)
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY,
    action_type TEXT NOT NULL,  -- task_created, task_completed, etc.
    entity_type TEXT,  -- task, project, goal, etc.
    entity_id INTEGER,
    details TEXT,  -- JSON with action-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Message log (verbose logging of all interactions)
CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY,
    raw_message TEXT NOT NULL,
    parsed_command TEXT,  -- CommandType
    parsed_data TEXT,  -- JSON of parsed fields
    action_taken TEXT,
    result TEXT,  -- success/error
    result_details TEXT,  -- JSON with details
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.6.0: Butler contact tracking (for 5 contacts/week limit)
CREATE TABLE IF NOT EXISTS butler_contacts (
    id INTEGER PRIMARY KEY,
    contact_type TEXT,           -- 'update', 'clarification'
    message_content TEXT,
    week_number INTEGER,         -- ISO week number
    year INTEGER,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.6.0: Slow work queue (for background LLM processing)
CREATE TABLE IF NOT EXISTS slow_work_queue (
    id INTEGER PRIMARY KEY,
    work_type TEXT,              -- 'task_computer_help', 'project_next_action'
    target_id INTEGER,           -- task_id or project_id
    depends_on_id INTEGER,       -- Another queue item that must complete first
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    result TEXT,                 -- The generated suggestion
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- v0.6.0: Voice journals (audio memos with transcription)
CREATE TABLE IF NOT EXISTS voice_journals (
    id INTEGER PRIMARY KEY,
    audio_path TEXT NOT NULL,        -- Path to stored audio file
    original_filename TEXT,          -- Original name if uploaded
    source TEXT DEFAULT 'web'        -- 'telegram', 'web'
        CHECK(source IN ('telegram', 'web')),
    status TEXT DEFAULT 'pending'    -- pending, transcribing, completed, failed
        CHECK(status IN ('pending', 'transcribing', 'completed', 'failed')),
    transcription TEXT,              -- The transcribed text
    duration_seconds REAL,           -- Audio duration
    language TEXT,                   -- Detected language code
    metadata TEXT,                   -- JSON with extra info (telegram message_id, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transcribed_at TIMESTAMP,
    error_message TEXT,
    -- v0.6.0 Final: Editable transcriptions
    transcription_edited INTEGER DEFAULT 0,
    transcription_edited_at TIMESTAMP
);

-- v0.6.0 Final: Unified conversation log (web/CLI/Telegram)
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,                  -- Groups related messages
    source TEXT,                      -- 'web', 'cli', 'telegram'
    role TEXT,                        -- 'user', 'assistant', 'system'
    content TEXT,
    thinking_summary TEXT,            -- Brief summary of system reasoning
    thinking_level TEXT,              -- 'decision', 'activity', 'debug'
    metadata TEXT,                    -- JSON: tokens, prompt_id, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- v0.6.0 Final: LLM prompt templates with versioning
CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,        -- 'task_computer_help', 'project_next_action'
    description TEXT,
    current_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY,
    template_id INTEGER REFERENCES prompt_templates(id) NOT NULL,
    version INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    variables TEXT,                   -- JSON array: ['task_name', 'project_context']
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system'  -- 'system', 'user'
);

-- v0.6.0 Polish: Universal thought capture (royal scribe pattern)
CREATE TABLE IF NOT EXISTS thoughts (
    id INTEGER PRIMARY KEY,
    source TEXT,                     -- 'telegram', 'cli', 'web', 'voice'
    raw_text TEXT NOT NULL,
    kind TEXT,                       -- 'actionable', 'note', 'ambiguous'
    ambiguity_reason TEXT,           -- 'scope', 'timing', 'intent', null
    confidence REAL,                 -- 0.0-1.0 classifier confidence
    linked_task_id INTEGER,          -- Created task if actionable
    linked_project_id INTEGER,       -- Created project if scope clarified
    voice_journal_id INTEGER,        -- Source voice journal if from voice
    status TEXT DEFAULT 'pending'    -- 'pending', 'processed', 'clarified'
        CHECK(status IN ('pending', 'processed', 'clarified')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    FOREIGN KEY (linked_task_id) REFERENCES tasks(id),
    FOREIGN KEY (linked_project_id) REFERENCES projects(id),
    FOREIGN KEY (voice_journal_id) REFERENCES voice_journals(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_time_blocks_start ON time_blocks(start_time);
CREATE INDEX IF NOT EXISTS idx_action_log_type ON action_log(action_type);
CREATE INDEX IF NOT EXISTS idx_butler_contacts_week ON butler_contacts(year, week_number);
CREATE INDEX IF NOT EXISTS idx_slow_work_status ON slow_work_queue(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_voice_journals_status ON voice_journals(status, created_at);
CREATE INDEX IF NOT EXISTS idx_thoughts_status ON thoughts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_thoughts_kind ON thoughts(kind, status);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_source ON conversations(source, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_level ON conversations(thinking_level, created_at);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_template ON prompt_versions(template_id, version);

-- v0.6.1: Execution logging (full pipeline traces)
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY,
    trace_id TEXT NOT NULL,           -- UUID grouping related logs
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stage TEXT,                       -- 'input', 'classify', 'route', 'execute', 'complete'
    component TEXT,                   -- 'fast', 'slow', 'butler', 'summon'
    input_data TEXT,                  -- JSON: raw input, source, etc.
    output_data TEXT,                 -- JSON: classification, task_id, etc.
    confidence REAL,
    duration_ms INTEGER,
    model_used TEXT,
    thought_id INTEGER,               -- Link to thought if applicable
    task_id INTEGER,                  -- Link to task if applicable
    error TEXT,
    metadata TEXT                     -- JSON: extra context
);

-- v0.6.1: Model registry (track available local models)
CREATE TABLE IF NOT EXISTS model_registry (
    name TEXT PRIMARY KEY,
    backend TEXT,                     -- 'ollama', 'vllm', 'llamacpp'
    family TEXT,                      -- 'qwen2.5', 'llama3', 'mistral'
    parameter_size TEXT,              -- '7b', '14b', '70b'
    quantization TEXT,                -- 'q4_K_M', 'q8_0', 'fp16'
    context_length INTEGER,
    supports_function_calling BOOLEAN DEFAULT 0,
    supports_json_schema BOOLEAN DEFAULT 0,
    tokens_per_sec REAL,              -- Measured on this machine
    memory_gb REAL,                   -- VRAM/RAM usage
    quality_score REAL,               -- 0-1, from capability tests
    health TEXT DEFAULT 'unknown',    -- 'ok', 'slow', 'error', 'unknown'
    last_benchmarked TIMESTAMP,
    last_used_for TEXT,               -- Track what tasks this model was used for
    notes TEXT
);

-- v0.6.1: Maintenance insights (system self-improvement)
CREATE TABLE IF NOT EXISTS maintenance_insights (
    id INTEGER PRIMARY KEY,
    insight_type TEXT,                -- 'pattern', 'blocker', 'recommendation', 'model_upgrade'
    source TEXT,                      -- 'model_scan', 'queue_health', 'project_agents'
    title TEXT,
    details TEXT,                     -- JSON with supporting data
    priority INTEGER DEFAULT 3,       -- 1-5, higher = more important
    status TEXT DEFAULT 'pending',    -- 'pending', 'reported', 'actioned', 'dismissed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reported_at TIMESTAMP,
    resolved_at TIMESTAMP
);

-- v0.6.1 indexes
CREATE INDEX IF NOT EXISTS idx_execution_logs_trace ON execution_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_execution_logs_timestamp ON execution_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_execution_logs_component ON execution_logs(component, stage);
CREATE INDEX IF NOT EXISTS idx_maintenance_insights_status ON maintenance_insights(status, priority);
"""


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
    
    print(f"Database initialized at {DB_PATH}")


def _migrate_db():
    """Add missing columns to existing tables (for upgrades)."""
    migrations = [
        # v0.6.0: Add suggestion columns to tasks
        ("tasks", "computer_help_suggestion", "TEXT"),
        ("tasks", "suggestion_generated_at", "TIMESTAMP"),
        # v0.6.0: Add suggestion columns to projects
        ("projects", "next_action_suggestion", "TEXT"),
        ("projects", "suggestion_generated_at", "TIMESTAMP"),
        # v0.6.0: Add source to message_log
        ("message_log", "source", "TEXT DEFAULT 'cli'"),
        # v0.6.0 Polish: Add duration to tasks for context-aware suggestions
        ("tasks", "duration_minutes", "INTEGER"),
        # v0.6.1: Add summon_mode to thoughts for tracking /summon requests
        ("thoughts", "summon_mode", "INTEGER DEFAULT 0"),
    ]
    
    with get_db() as conn:
        for table, column, col_type in migrations:
            # Check if column exists
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            
            if column not in columns:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    print(f"  Added column {table}.{column}")
                except Exception as e:
                    # Column might already exist in some edge cases
                    pass


def reset_db():
    """Drop all tables and reinitialize. USE WITH CAUTION."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()


if __name__ == "__main__":
    init_db()
