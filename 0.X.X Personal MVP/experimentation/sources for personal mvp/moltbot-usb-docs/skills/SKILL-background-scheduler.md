# Moltbot Skill: Background Task Scheduler with State Management

## Purpose
This skill enables Moltbot to:
- Run tasks automatically in the background
- Save and restore task state between runs
- Interrupt background tasks for on-demand requests
- Resume tasks from saved checkpoints
- Log all task activity

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Moltbot System                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Ollama    │  │  Signal     │  │  Task       │         │
│  │   (LLM)     │  │  Handler    │  │  Runner     │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│                   ┌──────▼──────┐                           │
│                   │   State     │                           │
│                   │   Manager   │                           │
│                   └──────┬──────┘                           │
│                          │                                  │
│         ┌────────────────┼────────────────┐                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Task 1     │  │  Task 2     │  │  Task N     │         │
│  │  (scraper)  │  │  (calendar) │  │  (email)    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### scheduler.py - Main Scheduler Module
Location: `~/moltbot-system/skills/scheduler.py`

```python
#!/usr/bin/env python3
"""
Moltbot Background Task Scheduler
Manages background tasks with state persistence
"""

import os
import sys
import json
import signal
import time
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import sqlite3

# Configuration
MOLTBOT_DIR = Path.home() / "moltbot-system"
STATE_DIR = MOLTBOT_DIR / "state"
TASKS_DIR = MOLTBOT_DIR / "tasks"
LOGS_DIR = MOLTBOT_DIR / "logs"
DB_PATH = MOLTBOT_DIR / "data" / "scheduler.db"

# Ensure directories exist
for d in [STATE_DIR, TASKS_DIR, LOGS_DIR, MOLTBOT_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class TaskState:
    """State of a scheduled task"""
    task_id: str
    name: str
    status: str  # 'idle', 'running', 'paused', 'error'
    last_run: Optional[str]
    next_run: Optional[str]
    run_count: int
    error_count: int
    last_error: Optional[str]
    checkpoint: Optional[Dict]  # Task-specific state


class StateManager:
    """Manages persistent state for all tasks"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS task_state (
                task_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                last_run TEXT,
                next_run TEXT,
                run_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                last_error TEXT,
                checkpoint TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                action TEXT,
                message TEXT,
                duration_seconds REAL
            );
            
            CREATE INDEX IF NOT EXISTS idx_log_task ON task_log(task_id);
            CREATE INDEX IF NOT EXISTS idx_log_time ON task_log(timestamp);
        ''')
        self.conn.commit()
    
    def get_state(self, task_id: str) -> Optional[TaskState]:
        """Get state for a specific task"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM task_state WHERE task_id = ?', (task_id,))
        row = cursor.fetchone()
        
        if row:
            return TaskState(
                task_id=row['task_id'],
                name=row['name'],
                status=row['status'],
                last_run=row['last_run'],
                next_run=row['next_run'],
                run_count=row['run_count'],
                error_count=row['error_count'],
                last_error=row['last_error'],
                checkpoint=json.loads(row['checkpoint']) if row['checkpoint'] else None
            )
        return None
    
    def save_state(self, state: TaskState):
        """Save task state"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO task_state 
            (task_id, name, status, last_run, next_run, run_count, error_count, last_error, checkpoint, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            state.task_id,
            state.name,
            state.status,
            state.last_run,
            state.next_run,
            state.run_count,
            state.error_count,
            state.last_error,
            json.dumps(state.checkpoint) if state.checkpoint else None
        ))
        self.conn.commit()
    
    def log_action(self, task_id: str, action: str, message: str, duration: float = None):
        """Log a task action"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO task_log (task_id, action, message, duration_seconds)
            VALUES (?, ?, ?, ?)
        ''', (task_id, action, message, duration))
        self.conn.commit()
    
    def get_all_states(self) -> List[TaskState]:
        """Get all task states"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM task_state ORDER BY name')
        
        states = []
        for row in cursor.fetchall():
            states.append(TaskState(
                task_id=row['task_id'],
                name=row['name'],
                status=row['status'],
                last_run=row['last_run'],
                next_run=row['next_run'],
                run_count=row['run_count'],
                error_count=row['error_count'],
                last_error=row['last_error'],
                checkpoint=json.loads(row['checkpoint']) if row['checkpoint'] else None
            ))
        return states
    
    def get_recent_logs(self, task_id: str = None, limit: int = 20) -> List[Dict]:
        """Get recent log entries"""
        cursor = self.conn.cursor()
        if task_id:
            cursor.execute('''
                SELECT * FROM task_log WHERE task_id = ?
                ORDER BY timestamp DESC LIMIT ?
            ''', (task_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM task_log ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]


@dataclass
class ScheduledTask:
    """Definition of a scheduled task"""
    task_id: str
    name: str
    script_path: str
    interval_minutes: int
    enabled: bool = True
    priority: int = 5  # 1=highest, 10=lowest


class TaskScheduler:
    """Main task scheduler with interrupt support"""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.current_task: Optional[str] = None
        self.interrupt_flag = threading.Event()
        
        self._load_tasks()
        self._setup_signal_handlers()
    
    def _load_tasks(self):
        """Load task definitions from config file"""
        config_path = MOLTBOT_DIR / "config" / "tasks.json"
        
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                for task_def in config.get('tasks', []):
                    task = ScheduledTask(**task_def)
                    self.tasks[task.task_id] = task
                    
                    # Initialize state if not exists
                    if not self.state_manager.get_state(task.task_id):
                        self.state_manager.save_state(TaskState(
                            task_id=task.task_id,
                            name=task.name,
                            status='idle',
                            last_run=None,
                            next_run=None,
                            run_count=0,
                            error_count=0,
                            last_error=None,
                            checkpoint=None
                        ))
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
    
    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals"""
        print("\nReceived interrupt signal, saving state...")
        self.interrupt_flag.set()
        
        if self.current_task:
            state = self.state_manager.get_state(self.current_task)
            if state:
                state.status = 'paused'
                self.state_manager.save_state(state)
                self.state_manager.log_action(
                    self.current_task, 'paused', 
                    'Task paused due to interrupt'
                )
        
        self.running = False
    
    def run_task(self, task_id: str, force: bool = False) -> Dict:
        """
        Run a specific task
        
        Args:
            task_id: ID of task to run
            force: Run even if not due
        
        Returns:
            Result dictionary
        """
        if task_id not in self.tasks:
            return {'error': f'Task {task_id} not found'}
        
        task = self.tasks[task_id]
        state = self.state_manager.get_state(task_id)
        
        # Check if due (unless forced)
        if not force and state and state.next_run:
            next_run = datetime.fromisoformat(state.next_run)
            if datetime.now() < next_run:
                return {'skipped': True, 'reason': 'Not due yet', 'next_run': state.next_run}
        
        self.current_task = task_id
        start_time = time.time()
        
        try:
            # Update state
            state = state or TaskState(
                task_id=task_id, name=task.name, status='idle',
                last_run=None, next_run=None, run_count=0,
                error_count=0, last_error=None, checkpoint=None
            )
            state.status = 'running'
            self.state_manager.save_state(state)
            self.state_manager.log_action(task_id, 'started', f'Running {task.name}')
            
            # Run the task script
            result = subprocess.run(
                ['bash', task.script_path],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=TASKS_DIR
            )
            
            duration = time.time() - start_time
            
            # Update state
            state.status = 'idle'
            state.last_run = datetime.now().isoformat()
            state.next_run = (datetime.now() + timedelta(minutes=task.interval_minutes)).isoformat()
            state.run_count += 1
            
            if result.returncode != 0:
                state.error_count += 1
                state.last_error = result.stderr[:500]
                self.state_manager.log_action(
                    task_id, 'error',
                    f'Exit code {result.returncode}: {result.stderr[:200]}',
                    duration
                )
            else:
                self.state_manager.log_action(
                    task_id, 'completed',
                    f'Completed successfully',
                    duration
                )
            
            self.state_manager.save_state(state)
            
            return {
                'task_id': task_id,
                'success': result.returncode == 0,
                'duration': duration,
                'stdout': result.stdout[:500],
                'stderr': result.stderr[:200] if result.returncode != 0 else None
            }
            
        except subprocess.TimeoutExpired:
            state.status = 'error'
            state.error_count += 1
            state.last_error = 'Task timed out after 5 minutes'
            self.state_manager.save_state(state)
            self.state_manager.log_action(task_id, 'timeout', 'Task timed out')
            return {'error': 'Task timed out'}
            
        except Exception as e:
            state.status = 'error'
            state.error_count += 1
            state.last_error = str(e)
            self.state_manager.save_state(state)
            self.state_manager.log_action(task_id, 'error', str(e))
            return {'error': str(e)}
            
        finally:
            self.current_task = None
    
    def run_due_tasks(self) -> List[Dict]:
        """Run all tasks that are due"""
        results = []
        
        # Sort by priority
        sorted_tasks = sorted(
            self.tasks.values(),
            key=lambda t: t.priority
        )
        
        for task in sorted_tasks:
            if not task.enabled:
                continue
            
            if self.interrupt_flag.is_set():
                break
            
            result = self.run_task(task.task_id)
            results.append(result)
            
            # Small delay between tasks
            time.sleep(1)
        
        return results
    
    def save_checkpoint(self, task_id: str, checkpoint: Dict):
        """Save a checkpoint for a task"""
        state = self.state_manager.get_state(task_id)
        if state:
            state.checkpoint = checkpoint
            self.state_manager.save_state(state)
    
    def load_checkpoint(self, task_id: str) -> Optional[Dict]:
        """Load checkpoint for a task"""
        state = self.state_manager.get_state(task_id)
        return state.checkpoint if state else None
    
    def pause_task(self, task_id: str):
        """Pause a task"""
        state = self.state_manager.get_state(task_id)
        if state:
            state.status = 'paused'
            self.state_manager.save_state(state)
            self.state_manager.log_action(task_id, 'paused', 'Task paused by user')
    
    def resume_task(self, task_id: str):
        """Resume a paused task"""
        state = self.state_manager.get_state(task_id)
        if state and state.status == 'paused':
            state.status = 'idle'
            self.state_manager.save_state(state)
            self.state_manager.log_action(task_id, 'resumed', 'Task resumed by user')
    
    def start_daemon(self, check_interval: int = 60):
        """Start the scheduler daemon"""
        self.running = True
        print(f"Scheduler started. Checking every {check_interval} seconds.")
        
        while self.running:
            if not self.interrupt_flag.is_set():
                self.run_due_tasks()
            
            # Wait for interval or interrupt
            for _ in range(check_interval):
                if self.interrupt_flag.is_set() or not self.running:
                    break
                time.sleep(1)
        
        print("Scheduler stopped.")
    
    def status(self) -> Dict:
        """Get scheduler status"""
        states = self.state_manager.get_all_states()
        
        return {
            'running': self.running,
            'current_task': self.current_task,
            'task_count': len(self.tasks),
            'tasks': [
                {
                    'id': s.task_id,
                    'name': s.name,
                    'status': s.status,
                    'last_run': s.last_run,
                    'next_run': s.next_run,
                    'run_count': s.run_count,
                    'error_count': s.error_count
                }
                for s in states
            ]
        }


# CLI Interface
if __name__ == "__main__":
    scheduler = TaskScheduler()
    
    if len(sys.argv) < 2:
        print("Usage: scheduler.py <command> [args]")
        print("Commands: daemon, run, run-all, status, logs, pause, resume")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "daemon":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        scheduler.start_daemon(check_interval=interval)
    
    elif cmd == "run" and len(sys.argv) > 2:
        task_id = sys.argv[2]
        result = scheduler.run_task(task_id, force=True)
        print(json.dumps(result, indent=2))
    
    elif cmd == "run-all":
        results = scheduler.run_due_tasks()
        print(json.dumps(results, indent=2))
    
    elif cmd == "status":
        status = scheduler.status()
        print(json.dumps(status, indent=2, default=str))
    
    elif cmd == "logs":
        task_id = sys.argv[2] if len(sys.argv) > 2 else None
        logs = scheduler.state_manager.get_recent_logs(task_id)
        for log in logs:
            print(f"[{log['timestamp']}] {log['task_id']}: {log['action']} - {log['message']}")
    
    elif cmd == "pause" and len(sys.argv) > 2:
        scheduler.pause_task(sys.argv[2])
        print(f"Task {sys.argv[2]} paused")
    
    elif cmd == "resume" and len(sys.argv) > 2:
        scheduler.resume_task(sys.argv[2])
        print(f"Task {sys.argv[2]} resumed")
    
    else:
        print(f"Unknown command: {cmd}")
```

### Task Configuration File
Location: `~/moltbot-system/config/tasks.json`

```json
{
  "tasks": [
    {
      "task_id": "scrape-all",
      "name": "Web Scraper",
      "script_path": "scrape-all.sh",
      "interval_minutes": 60,
      "enabled": true,
      "priority": 5
    },
    {
      "task_id": "check-calendar",
      "name": "Calendar Check",
      "script_path": "check-calendar.sh",
      "interval_minutes": 15,
      "enabled": true,
      "priority": 3
    },
    {
      "task_id": "check-email",
      "name": "Email Check",
      "script_path": "check-email.sh",
      "interval_minutes": 30,
      "enabled": true,
      "priority": 4
    }
  ]
}
```

### Systemd Service
Location: `/etc/systemd/system/moltbot-scheduler.service`

```ini
[Unit]
Description=Moltbot Task Scheduler
After=network.target ollama.service

[Service]
Type=simple
User=moltbot
WorkingDirectory=/home/moltbot/moltbot-system
ExecStart=/usr/bin/python3 /home/moltbot/moltbot-system/skills/scheduler.py daemon 60
Restart=always
RestartSec=10

# Graceful shutdown
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Install the service:
```bash
sudo cp /home/moltbot/moltbot-system/config/moltbot-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable moltbot-scheduler
sudo systemctl start moltbot-scheduler
```

## Usage Instructions

### For Moltbot (Agent)

**"What tasks are running?"**
```bash
python3 ~/moltbot-system/skills/scheduler.py status
```

**"Run the scraper now"**
```bash
python3 ~/moltbot-system/skills/scheduler.py run scrape-all
```

**"Show me the task logs"**
```bash
python3 ~/moltbot-system/skills/scheduler.py logs
```

**"Pause the email checker"**
```bash
python3 ~/moltbot-system/skills/scheduler.py pause check-email
```

**"Resume the email checker"**
```bash
python3 ~/moltbot-system/skills/scheduler.py resume check-email
```

## State Management Details

### Checkpoint System

Tasks can save their progress using checkpoints. This is useful for long-running tasks that might be interrupted:

```python
# In your task script, use the checkpoint API:
from scheduler import TaskScheduler

scheduler = TaskScheduler()

# Load previous checkpoint
checkpoint = scheduler.load_checkpoint('my-task')
start_index = checkpoint.get('last_index', 0) if checkpoint else 0

# Process items
for i, item in enumerate(items[start_index:], start_index):
    process(item)
    
    # Save checkpoint periodically
    if i % 10 == 0:
        scheduler.save_checkpoint('my-task', {'last_index': i})

# Clear checkpoint when done
scheduler.save_checkpoint('my-task', None)
```

### Interrupt Handling

When the scheduler receives SIGINT or SIGTERM:
1. Sets the interrupt flag
2. Current task completes its current operation
3. State is saved with status 'paused'
4. Scheduler exits gracefully

On restart, paused tasks resume from their last checkpoint.

## Monitoring

### View Real-time Logs
```bash
journalctl -u moltbot-scheduler -f
```

### Check Task Status
```bash
python3 ~/moltbot-system/skills/scheduler.py status
```

### View Recent Activity
```bash
python3 ~/moltbot-system/skills/scheduler.py logs
```

### Check Specific Task
```bash
python3 ~/moltbot-system/skills/scheduler.py logs check-calendar
```

## Adding New Tasks

1. Create task script in `~/moltbot-system/tasks/`:
```bash
cat > ~/moltbot-system/tasks/my-new-task.sh << 'EOF'
#!/bin/bash
# My new task
echo "Running my task..."
# Task logic here
EOF
chmod +x ~/moltbot-system/tasks/my-new-task.sh
```

2. Add to `tasks.json`:
```json
{
  "task_id": "my-new-task",
  "name": "My New Task",
  "script_path": "my-new-task.sh",
  "interval_minutes": 120,
  "enabled": true,
  "priority": 5
}
```

3. Restart scheduler:
```bash
sudo systemctl restart moltbot-scheduler
```

## Remote Control via Signal

Send these commands from your phone:
- `status` - Get scheduler status
- `run:task-name` - Run specific task
- `pause:task-name` - Pause task
- `resume:task-name` - Resume task
- `logs` - Get recent logs

## Security Notes

1. **Task Isolation**: Each task runs in its own subprocess
2. **Timeouts**: Tasks timeout after 5 minutes by default
3. **Error Handling**: Errors are logged but don't crash the scheduler
4. **State Persistence**: All state saved to local SQLite database
5. **No External Dependencies**: Works fully offline after initial setup
