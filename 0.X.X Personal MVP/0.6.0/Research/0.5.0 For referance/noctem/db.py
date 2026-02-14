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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    completed_at TIMESTAMP
);

-- Habits
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    goal_id INTEGER REFERENCES goals(id),
    frequency TEXT DEFAULT 'daily' 
        CHECK(frequency IN ('daily', 'weekly', 'custom')),
    target_count INTEGER DEFAULT 1,  -- times per frequency period
    custom_days TEXT,  -- JSON array for custom, e.g., ["mon","wed","fri"]
    time_preference TEXT DEFAULT 'anytime'
        CHECK(time_preference IN ('morning', 'afternoon', 'evening', 'anytime')),
    duration_minutes INTEGER,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Habit completions
CREATE TABLE IF NOT EXISTS habit_logs (
    id INTEGER PRIMARY KEY,
    habit_id INTEGER REFERENCES habits(id) NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
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
    action_type TEXT NOT NULL,  -- task_created, task_completed, habit_logged, etc.
    entity_type TEXT,  -- task, habit, project, etc.
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

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);
CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(completed_at);
CREATE INDEX IF NOT EXISTS idx_time_blocks_start ON time_blocks(start_time);
CREATE INDEX IF NOT EXISTS idx_action_log_type ON action_log(action_type);
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
    print(f"Database initialized at {DB_PATH}")


def reset_db():
    """Drop all tables and reinitialize. USE WITH CAUTION."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()


if __name__ == "__main__":
    init_db()
