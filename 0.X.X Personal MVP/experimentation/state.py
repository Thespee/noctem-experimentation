#!/usr/bin/env python3
"""
Noctem State Management
SQLite-based persistence for tasks, memory, and system state.
"""

import sqlite3
import json
import socket
from datetime import datetime, timedelta
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
    
    # Improvements queue (for parent-suggested changes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS improvements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 3,
            patch TEXT,
            status TEXT DEFAULT 'pending',
            source TEXT DEFAULT 'parent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)
    
    # Reports (training data: problem -> solution pairs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT NOT NULL,
            content TEXT,
            metrics_json TEXT,
            problems_json TEXT,
            solutions_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Incidents log (errors, issues, notable events)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            severity TEXT DEFAULT 'info',
            category TEXT,
            message TEXT,
            details TEXT,
            task_id INTEGER,
            acknowledged INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Daily reports tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE UNIQUE,
            tasks_completed INTEGER,
            tasks_failed INTEGER,
            incidents_count INTEGER,
            report_text TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Personal Task Tracking: Goals -> Projects -> User Tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES goals(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 5,
            due_date DATE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    
    # Message log for NLP training
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT,
            content TEXT,
            parsed_intent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_task ON memory(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_log_task ON skill_log(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_improvements_status ON improvements(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_status ON user_tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_project ON user_tasks(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_goal ON projects(goal_id)")
    
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
# Improvement Operations (Parent)
# =============================================================================

def create_improvement(title: str, description: str = "", priority: int = 3,
                       patch: str = "", source: str = "parent") -> int:
    """Create a new improvement suggestion."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO improvements (title, description, priority, patch, source, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    """, (title, description, priority, patch, source))
    imp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return imp_id


def get_improvement(imp_id: int) -> Optional[Dict]:
    """Get an improvement by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM improvements WHERE id = ?", (imp_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_improvements() -> List[Dict]:
    """Get all pending improvements."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM improvements 
        WHERE status = 'pending'
        ORDER BY priority ASC, created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_improvement_status(imp_id: int, status: str) -> bool:
    """Update improvement status (pending/approved/applied/rejected)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    resolved_at = datetime.now().isoformat() if status in ('applied', 'rejected') else None
    
    cursor.execute("""
        UPDATE improvements 
        SET status = ?, resolved_at = ?
        WHERE id = ?
    """, (status, resolved_at, imp_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# =============================================================================
# Report Operations (Training Data - Parent)
# =============================================================================

def create_report(report_type: str, content: str, metrics: Dict = None,
                  problems: List = None, solutions: List = None) -> int:
    """Create a report for training data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (report_type, content, metrics_json, problems_json, solutions_json)
        VALUES (?, ?, ?, ?, ?)
    """, (
        report_type,
        content,
        json.dumps(metrics) if metrics else None,
        json.dumps(problems) if problems else None,
        json.dumps(solutions) if solutions else None
    ))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_recent_reports(report_type: str = None, limit: int = 10) -> List[Dict]:
    """Get recent reports, optionally filtered by type."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if report_type:
        cursor.execute("""
            SELECT * FROM reports 
            WHERE report_type = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (report_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM reports 
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Parse JSON fields
    results = []
    for row in rows:
        r = dict(row)
        for field in ('metrics_json', 'problems_json', 'solutions_json'):
            if r.get(field):
                try:
                    r[field] = json.loads(r[field])
                except json.JSONDecodeError:
                    pass
        results.append(r)
    
    return results


def get_task_stats(since_hours: int = 24) -> Dict:
    """Get task statistics for a time period."""
    conn = get_connection()
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
    
    # Total tasks
    cursor.execute("""
        SELECT COUNT(*) FROM tasks WHERE created_at > ?
    """, (since,))
    total = cursor.fetchone()[0]
    
    # Successful tasks
    cursor.execute("""
        SELECT COUNT(*) FROM tasks WHERE created_at > ? AND status = 'done'
    """, (since,))
    successful = cursor.fetchone()[0]
    
    # Failed tasks
    cursor.execute("""
        SELECT COUNT(*) FROM tasks WHERE created_at > ? AND status = 'failed'
    """, (since,))
    failed = cursor.fetchone()[0]
    
    # Get failed task details
    cursor.execute("""
        SELECT id, input, result FROM tasks 
        WHERE created_at > ? AND status = 'failed'
        ORDER BY created_at DESC
        LIMIT 10
    """, (since,))
    failed_tasks = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "success_rate": f"{(successful/total*100):.1f}%" if total > 0 else "N/A",
        "failed_tasks": failed_tasks
    }


def get_skill_stats(since_hours: int = 24) -> Dict:
    """Get skill execution statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
    
    # Stats by skill
    cursor.execute("""
        SELECT skill_name, 
               COUNT(*) as total,
               SUM(success) as successful,
               AVG(duration_ms) as avg_duration
        FROM skill_log 
        WHERE created_at > ?
        GROUP BY skill_name
    """, (since,))
    
    by_skill = {}
    for row in cursor.fetchall():
        by_skill[row['skill_name']] = {
            'total': row['total'],
            'successful': row['successful'],
            'avg_duration_ms': round(row['avg_duration']) if row['avg_duration'] else 0
        }
    
    # Failed skill executions
    cursor.execute("""
        SELECT skill_name, input, output FROM skill_log
        WHERE created_at > ? AND success = 0
        ORDER BY created_at DESC
        LIMIT 10
    """, (since,))
    failed = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "by_skill": by_skill,
        "failed_executions": failed
    }


# =============================================================================
# Incident Operations (Email/Daily Reports)
# =============================================================================

def log_incident(message: str, severity: str = "info", category: str = None,
                 details: str = None, task_id: int = None):
    """
    Log an incident.
    
    Severity levels: info, warning, error, critical
    Categories: system, task, skill, network, email, other
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO incidents (severity, category, message, details, task_id)
        VALUES (?, ?, ?, ?, ?)
    """, (severity, category, message, details, task_id))
    conn.commit()
    conn.close()


def get_incidents_since(since: datetime) -> List[Dict]:
    """Get incidents since a given datetime."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM incidents
        WHERE created_at >= ?
        ORDER BY created_at DESC
    """, (since.isoformat(),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_unacknowledged_incidents() -> List[Dict]:
    """Get all unacknowledged incidents."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM incidents
        WHERE acknowledged = 0
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def acknowledge_incidents(incident_ids: List[int] = None):
    """Mark incidents as acknowledged. If no IDs given, acknowledge all."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if incident_ids:
        placeholders = ','.join('?' * len(incident_ids))
        cursor.execute(f"""
            UPDATE incidents SET acknowledged = 1
            WHERE id IN ({placeholders})
        """, incident_ids)
    else:
        cursor.execute("UPDATE incidents SET acknowledged = 1")
    
    conn.commit()
    conn.close()


def get_tasks_since(since: datetime, status: str = None) -> List[Dict]:
    """Get tasks created/completed since a given datetime."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("""
            SELECT * FROM tasks
            WHERE completed_at >= ? AND status = ?
            ORDER BY completed_at DESC
        """, (since.isoformat(), status))
    else:
        cursor.execute("""
            SELECT * FROM tasks
            WHERE created_at >= ?
            ORDER BY created_at DESC
        """, (since.isoformat(),))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_report_date() -> Optional[datetime]:
    """Get the date of the last daily report."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MAX(report_date) as last_date FROM daily_reports
        WHERE sent_at IS NOT NULL
    """)
    row = cursor.fetchone()
    conn.close()
    
    if row and row['last_date']:
        return datetime.fromisoformat(row['last_date'])
    return None


def save_daily_report(report_date: datetime, tasks_completed: int, tasks_failed: int,
                      incidents_count: int, report_text: str):
    """Save a daily report."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_reports (report_date, tasks_completed, tasks_failed, 
                                   incidents_count, report_text)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
            tasks_completed = excluded.tasks_completed,
            tasks_failed = excluded.tasks_failed,
            incidents_count = excluded.incidents_count,
            report_text = excluded.report_text
    """, (report_date.date().isoformat(), tasks_completed, tasks_failed,
          incidents_count, report_text))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


def mark_report_sent(report_date: datetime):
    """Mark a daily report as sent."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE daily_reports SET sent_at = CURRENT_TIMESTAMP
        WHERE report_date = ?
    """, (report_date.date().isoformat(),))
    conn.commit()
    conn.close()


# =============================================================================
# Personal Task Operations (Goals -> Projects -> Tasks)
# =============================================================================

def create_goal(name: str, description: str = "") -> int:
    """Create a new goal."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO goals (name, description) VALUES (?, ?)
    """, (name, description))
    goal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return goal_id


def get_goals(status: str = "active") -> List[Dict]:
    """Get all goals, optionally filtered by status."""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM goals WHERE status = ? ORDER BY created_at", (status,))
    else:
        cursor.execute("SELECT * FROM goals ORDER BY created_at")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_project(name: str, goal_id: int = None, description: str = "") -> int:
    """Create a new project, optionally linked to a goal."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO projects (name, goal_id, description) VALUES (?, ?, ?)
    """, (name, goal_id, description))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def get_projects(goal_id: int = None, status: str = "active") -> List[Dict]:
    """Get projects, optionally filtered by goal and status."""
    conn = get_connection()
    cursor = conn.cursor()
    if goal_id:
        cursor.execute("""
            SELECT * FROM projects WHERE goal_id = ? AND status = ? ORDER BY created_at
        """, (goal_id, status))
    else:
        cursor.execute("SELECT * FROM projects WHERE status = ? ORDER BY created_at", (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_user_task(title: str, project_id: int = None, description: str = "",
                     priority: int = 5, due_date: str = None) -> int:
    """Create a new user task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_tasks (title, project_id, description, priority, due_date)
        VALUES (?, ?, ?, ?, ?)
    """, (title, project_id, description, priority, due_date))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def get_user_tasks(project_id: int = None, status: str = "pending") -> List[Dict]:
    """Get user tasks, optionally filtered by project and status."""
    conn = get_connection()
    cursor = conn.cursor()
    if project_id:
        cursor.execute("""
            SELECT ut.*, p.name as project_name 
            FROM user_tasks ut
            LEFT JOIN projects p ON ut.project_id = p.id
            WHERE ut.project_id = ? AND ut.status = ?
            ORDER BY ut.priority ASC, ut.created_at ASC
        """, (project_id, status))
    else:
        cursor.execute("""
            SELECT ut.*, p.name as project_name 
            FROM user_tasks ut
            LEFT JOIN projects p ON ut.project_id = p.id
            WHERE ut.status = ?
            ORDER BY ut.priority ASC, ut.due_date ASC NULLS LAST, ut.created_at ASC
        """, (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def complete_user_task(task_id: int) -> bool:
    """Mark a user task as done."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (task_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_user_task(task_id: int) -> Optional[Dict]:
    """Get a user task by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ut.*, p.name as project_name, g.name as goal_name
        FROM user_tasks ut
        LEFT JOIN projects p ON ut.project_id = p.id
        LEFT JOIN goals g ON p.goal_id = g.id
        WHERE ut.id = ?
    """, (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def log_message(direction: str, content: str, parsed_intent: str = None):
    """Log a message for NLP training."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO message_log (direction, content, parsed_intent)
        VALUES (?, ?, ?)
    """, (direction, content, parsed_intent))
    conn.commit()
    conn.close()


def get_tasks_due_soon(days: int = 7) -> List[Dict]:
    """Get tasks due within the next N days."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ut.*, p.name as project_name
        FROM user_tasks ut
        LEFT JOIN projects p ON ut.project_id = p.id
        WHERE ut.status = 'pending' 
        AND ut.due_date IS NOT NULL
        AND ut.due_date <= date('now', '+' || ? || ' days')
        ORDER BY ut.due_date ASC
    """, (days,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_completed_tasks_since(since: datetime) -> List[Dict]:
    """Get user tasks completed since a given datetime."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ut.*, p.name as project_name
        FROM user_tasks ut
        LEFT JOIN projects p ON ut.project_id = p.id
        WHERE ut.status = 'done' AND ut.completed_at >= ?
        ORDER BY ut.completed_at DESC
    """, (since.isoformat(),))
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
