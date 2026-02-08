#!/usr/bin/env python3
"""
Noctem State Management
SQLite-based persistence for tasks, memory, and system state.
"""

import sqlite3
import json
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Database path relative to this file
DB_PATH = Path(__file__).parent / "data" / "noctem.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # System state key-value store
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Task queue
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            input TEXT,
            priority INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            plan TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    
    # Conversation memory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            task_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Skill execution log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            skill_name TEXT,
            input TEXT,
            output TEXT,
            success INTEGER,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_task ON memory(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_log_task ON skill_log(task_id)")
    
    conn.commit()
    conn.close()


# =============================================================================
# State Operations
# =============================================================================

def get_state(key: str, default: Any = None) -> Any:
    """Get a state value by key."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM state WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return default
    
    # Try to parse as JSON
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def set_state(key: str, value: Any):
    """Set a state value."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Serialize to JSON if not a string
    if not isinstance(value, str):
        value = json.dumps(value)
    
    cursor.execute("""
        INSERT INTO state (key, value, updated_at) 
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET 
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (key, value))
    
    conn.commit()
    conn.close()


def record_boot():
    """Record boot state for persistence across reboots."""
    hostname = socket.gethostname()
    now = datetime.now().isoformat()
    
    # Get previous boot info
    last_boot = get_state("last_boot")
    last_machine = get_state("last_machine")
    
    # Record new boot
    set_state("last_boot", now)
    set_state("last_machine", hostname)
    set_state("boot_count", get_state("boot_count", 0) + 1)
    
    return {
        "current_boot": now,
        "current_machine": hostname,
        "previous_boot": last_boot,
        "previous_machine": last_machine
    }


# =============================================================================
# Task Operations
# =============================================================================

def create_task(input_text: str, source: str = "cli", priority: int = 5) -> int:
    """Create a new task and return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO tasks (input, source, priority, status)
        VALUES (?, ?, ?, 'pending')
    """, (input_text, source, priority))
    
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return task_id


def get_task(task_id: int) -> Optional[Dict]:
    """Get a task by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_next_task() -> Optional[Dict]:
    """Get the next pending task (highest priority, oldest first)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tasks 
        WHERE status = 'pending'
        ORDER BY priority ASC, created_at ASC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def update_task(task_id: int, **kwargs):
    """Update task fields."""
    if not kwargs:
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build SET clause dynamically
    set_parts = [f"{k} = ?" for k in kwargs.keys()]
    values = list(kwargs.values()) + [task_id]
    
    cursor.execute(f"""
        UPDATE tasks SET {', '.join(set_parts)}
        WHERE id = ?
    """, values)
    
    conn.commit()
    conn.close()


def start_task(task_id: int):
    """Mark a task as running."""
    update_task(task_id, status="running", started_at=datetime.now().isoformat())


def complete_task(task_id: int, result: str, success: bool = True):
    """Mark a task as completed."""
    status = "done" if success else "failed"
    update_task(task_id, status=status, result=result, completed_at=datetime.now().isoformat())


def get_running_tasks() -> List[Dict]:
    """Get all currently running tasks."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'running'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_tasks() -> List[Dict]:
    """Get all pending tasks ordered by priority."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tasks 
        WHERE status = 'pending'
        ORDER BY priority ASC, created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_recent_tasks(limit: int = 10) -> List[Dict]:
    """Get recently completed tasks."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tasks 
        WHERE status IN ('done', 'failed')
        ORDER BY completed_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def cancel_task(task_id: int) -> bool:
    """Cancel a pending task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET status = 'cancelled'
        WHERE id = ? AND status = 'pending'
    """, (task_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def set_task_priority(task_id: int, priority: int) -> bool:
    """Change a task's priority."""
    if not 1 <= priority <= 10:
        return False
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET priority = ?
        WHERE id = ? AND status = 'pending'
    """, (priority, task_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# =============================================================================
# Memory Operations
# =============================================================================

def add_memory(role: str, content: str, task_id: Optional[int] = None):
    """Add a conversation memory entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO memory (role, content, task_id)
        VALUES (?, ?, ?)
    """, (role, content, task_id))
    conn.commit()
    conn.close()


def get_recent_memory(limit: int = 20) -> List[Dict]:
    """Get recent conversation memory."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM memory
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in reversed(rows)]  # Chronological order


def get_task_memory(task_id: int) -> List[Dict]:
    """Get memory entries for a specific task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM memory
        WHERE task_id = ?
        ORDER BY created_at ASC
    """, (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# Skill Log Operations
# =============================================================================

def log_skill_execution(task_id: int, skill_name: str, input_data: str, 
                        output: str, success: bool, duration_ms: int):
    """Log a skill execution."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO skill_log (task_id, skill_name, input, output, success, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (task_id, skill_name, input_data, output, 1 if success else 0, duration_ms))
    conn.commit()
    conn.close()


def get_task_skill_log(task_id: int) -> List[Dict]:
    """Get skill execution log for a task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM skill_log
        WHERE task_id = ?
        ORDER BY created_at ASC
    """, (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# Initialization
# =============================================================================

# Auto-initialize on import
init_db()


if __name__ == "__main__":
    # Quick test
    print(f"Database: {DB_PATH}")
    print(f"Exists: {DB_PATH.exists()}")
    
    boot_info = record_boot()
    print(f"Boot info: {boot_info}")
    
    # Test task creation
    task_id = create_task("Test task", source="cli", priority=5)
    print(f"Created task: {task_id}")
    
    task = get_task(task_id)
    print(f"Task: {task}")
