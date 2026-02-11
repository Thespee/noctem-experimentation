# Phase 3: Parent Function Implementation Guide

**Objective**: Implement remote supervision and AI-assisted self-improvement from external machine.

**Prerequisites**: 
- Phase 1 complete (web skills)
- Phase 2 complete (birth with auto-start)
- Warp CLI installed on parent machine
- Signal configured on both machines

---

## Overview

The "parent" function runs on your main workstation (not the Noctem machine) and provides:
1. Remote status monitoring
2. History and log retrieval
3. Health checks
4. AI-assisted improvement suggestions via Warp
5. Babysitting reports via Signal

---

## Architecture

```
┌─────────────────────┐         Signal          ┌─────────────────────┐
│   Parent Machine    │◄──────────────────────►│   Noctem Machine    │
│  (Your Workstation) │                         │  (USB/Dedicated)    │
│                     │                         │                     │
│  ┌───────────────┐  │    Query/Response       │  ┌───────────────┐  │
│  │  parent.py    │──┼────────────────────────►│  │  daemon.py    │  │
│  └───────────────┘  │                         │  └───────────────┘  │
│         │           │                         │         │           │
│         ▼           │                         │         ▼           │
│  ┌───────────────┐  │                         │  ┌───────────────┐  │
│  │  Warp CLI     │  │                         │  │  noctem.db    │  │
│  │  (Analysis)   │  │                         │  │  (History)    │  │
│  └───────────────┘  │                         │  └───────────────┘  │
└─────────────────────┘                         └─────────────────────┘
```

---

## Step 1: Create Parent Protocol Messages

### 1.1 Define Protocol in `parent/protocol.py`

```python
"""Parent-child communication protocol."""
import json
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

class ParentCommand(Enum):
    STATUS = "status"          # Get current status
    HISTORY = "history"        # Get task history
    HEALTH = "health"          # Get health metrics
    LOGS = "logs"              # Get recent logs
    IMPROVE = "improve"        # Request improvement analysis
    APPLY_PATCH = "apply"      # Apply improvement patch
    REPORT = "report"          # Generate babysitting report

@dataclass
class ParentRequest:
    command: ParentCommand
    params: Dict[str, Any] = None
    request_id: str = None
    
    def __post_init__(self):
        if self.request_id is None:
            import secrets
            self.request_id = secrets.token_hex(4)
        if self.params is None:
            self.params = {}
    
    def to_signal_message(self) -> str:
        """Encode as Signal message."""
        return f"/parent {self.command.value} {json.dumps(self.params)}"
    
    @classmethod
    def from_signal_message(cls, message: str) -> Optional['ParentRequest']:
        """Parse from Signal message."""
        if not message.strip().startswith("/parent"):
            return None
        
        parts = message.strip().split(maxsplit=2)
        if len(parts) < 2:
            return None
        
        try:
            command = ParentCommand(parts[1].lower())
            params = json.loads(parts[2]) if len(parts) > 2 else {}
            return cls(command=command, params=params)
        except (ValueError, json.JSONDecodeError):
            return None

@dataclass
class ParentResponse:
    request_id: str
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_signal_message(self) -> str:
        """Encode as Signal message (may be truncated for long responses)."""
        if self.error:
            return f"❌ Error: {self.error}"
        
        # Format based on data type
        return self._format_data()
    
    def _format_data(self) -> str:
        """Format response data for Signal."""
        data = self.data
        
        if "status" in data:
            return self._format_status(data)
        elif "history" in data:
            return self._format_history(data)
        elif "health" in data:
            return self._format_health(data)
        elif "report" in data:
            return data["report"]
        else:
            return json.dumps(data, indent=2)[:1500]  # Truncate
    
    def _format_status(self, data: dict) -> str:
        s = data["status"]
        return (
            f"📊 Noctem Status\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"State: {s.get('state', 'unknown')}\n"
            f"Uptime: {s.get('uptime', 'unknown')}\n"
            f"Active tasks: {s.get('active_tasks', 0)}\n"
            f"Queue: {s.get('queue_size', 0)}\n"
            f"Last activity: {s.get('last_activity', 'never')}"
        )
    
    def _format_history(self, data: dict) -> str:
        history = data["history"]
        lines = ["📜 Recent History", "━━━━━━━━━━━━━━━━"]
        for item in history[:10]:
            status_emoji = "✅" if item.get("success") else "❌"
            lines.append(f"{status_emoji} {item.get('task', 'unknown')[:40]}")
        return "\n".join(lines)
    
    def _format_health(self, data: dict) -> str:
        h = data["health"]
        return (
            f"💚 Health Check\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Ollama: {'✅' if h.get('ollama') else '❌'}\n"
            f"Signal: {'✅' if h.get('signal') else '❌'}\n"
            f"Disk: {h.get('disk_usage', '?')}%\n"
            f"Memory: {h.get('memory_usage', '?')}%\n"
            f"CPU: {h.get('cpu_usage', '?')}%"
        )
```

---

## Step 2: Implement Child-Side Handler

### 2.1 Create `parent/child_handler.py`

This runs on the Noctem machine and handles incoming parent commands.

```python
"""Handle parent commands on the Noctem (child) side."""
import json
import psutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
import sqlite3

from .protocol import ParentCommand, ParentRequest, ParentResponse

class ChildHandler:
    def __init__(self, db_path: Path, working_dir: Path):
        self.db_path = db_path
        self.working_dir = working_dir
        self.start_time = datetime.now()
    
    def handle_request(self, request: ParentRequest) -> ParentResponse:
        """Handle a parent request and return response."""
        handlers = {
            ParentCommand.STATUS: self._handle_status,
            ParentCommand.HISTORY: self._handle_history,
            ParentCommand.HEALTH: self._handle_health,
            ParentCommand.LOGS: self._handle_logs,
            ParentCommand.REPORT: self._handle_report,
        }
        
        handler = handlers.get(request.command)
        if handler is None:
            return ParentResponse(
                request_id=request.request_id,
                success=False,
                data={},
                error=f"Unknown command: {request.command.value}"
            )
        
        try:
            data = handler(request.params)
            return ParentResponse(
                request_id=request.request_id,
                success=True,
                data=data
            )
        except Exception as e:
            return ParentResponse(
                request_id=request.request_id,
                success=False,
                data={},
                error=str(e)
            )
    
    def _handle_status(self, params: Dict) -> Dict[str, Any]:
        """Get current system status."""
        # Get uptime
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        # Get task stats from database
        active_tasks = 0
        queue_size = 0
        last_activity = "never"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count active/pending tasks
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'")
            active_tasks = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
            queue_size = cursor.fetchone()[0]
            
            # Get last activity
            cursor.execute("SELECT MAX(updated_at) FROM tasks")
            result = cursor.fetchone()[0]
            if result:
                last_activity = result
            
            conn.close()
        except:
            pass
        
        return {
            "status": {
                "state": "running",
                "uptime": uptime_str,
                "active_tasks": active_tasks,
                "queue_size": queue_size,
                "last_activity": last_activity
            }
        }
    
    def _handle_history(self, params: Dict) -> Dict[str, Any]:
        """Get task history."""
        limit = params.get("limit", 20)
        since_hours = params.get("since_hours", 24)
        
        history = []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            since = datetime.now() - timedelta(hours=since_hours)
            cursor.execute("""
                SELECT task_id, task_type, status, created_at, completed_at, error
                FROM tasks
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (since.isoformat(), limit))
            
            for row in cursor.fetchall():
                history.append({
                    "task_id": row[0],
                    "task": row[1],
                    "success": row[2] == "completed",
                    "status": row[2],
                    "created": row[3],
                    "completed": row[4],
                    "error": row[5]
                })
            
            conn.close()
        except Exception as e:
            history = [{"error": str(e)}]
        
        # Calculate stats
        total = len(history)
        successful = sum(1 for h in history if h.get("success"))
        
        return {
            "history": history,
            "stats": {
                "total": total,
                "successful": successful,
                "success_rate": f"{(successful/total*100):.1f}%" if total > 0 else "N/A"
            }
        }
    
    def _handle_health(self, params: Dict) -> Dict[str, Any]:
        """Get system health metrics."""
        health = {
            "ollama": False,
            "signal": False,
            "disk_usage": 0,
            "memory_usage": 0,
            "cpu_usage": 0
        }
        
        # Check Ollama
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            health["ollama"] = resp.status_code == 200
        except:
            pass
        
        # Check Signal
        try:
            result = subprocess.run(
                ["signal-cli", "--version"],
                capture_output=True,
                timeout=5
            )
            health["signal"] = result.returncode == 0
        except:
            pass
        
        # System metrics
        health["disk_usage"] = psutil.disk_usage('/').percent
        health["memory_usage"] = psutil.virtual_memory().percent
        health["cpu_usage"] = psutil.cpu_percent(interval=1)
        
        return {"health": health}
    
    def _handle_logs(self, params: Dict) -> Dict[str, Any]:
        """Get recent logs."""
        lines = params.get("lines", 50)
        log_file = self.working_dir / "noctem.log"
        
        if not log_file.exists():
            return {"logs": [], "message": "No log file found"}
        
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:]
            return {"logs": [l.strip() for l in recent]}
        except Exception as e:
            return {"logs": [], "error": str(e)}
    
    def _handle_report(self, params: Dict) -> Dict[str, Any]:
        """Generate a babysitting report."""
        # Gather all info
        status = self._handle_status({})["status"]
        history = self._handle_history({"limit": 100, "since_hours": 24})
        health = self._handle_health({})["health"]
        
        # Calculate metrics
        total_tasks = history["stats"]["total"]
        success_rate = history["stats"]["success_rate"]
        
        # Find errors
        errors = [h for h in history["history"] if h.get("error")]
        
        # Build report
        report = f"""🍼 Noctem Babysitting Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱ Uptime: {status['uptime']}
📊 Tasks (24h): {total_tasks} ({success_rate} success)
💾 Disk: {health['disk_usage']}%
🧠 Memory: {health['memory_usage']}%
🔥 Errors (24h): {len(errors)}"""
        
        if errors:
            report += "\n\nRecent errors:"
            for e in errors[:3]:
                report += f"\n  • {e.get('task', 'unknown')}: {e.get('error', 'unknown')}"
        
        report += "\n\n🔧 Services:"
        report += f"\n  Ollama: {'✅' if health['ollama'] else '❌'}"
        report += f"\n  Signal: {'✅' if health['signal'] else '❌'}"
        
        return {"report": report}


# Singleton instance
_handler: Optional[ChildHandler] = None

def init_child_handler(db_path: Path, working_dir: Path):
    global _handler
    _handler = ChildHandler(db_path, working_dir)

def get_child_handler() -> Optional[ChildHandler]:
    return _handler
```

### 2.2 Update `signal_receiver.py` to Handle Parent Commands

```python
# Add to signal_receiver.py message handler:

def handle_message(message: str, sender: str) -> str:
    # Check for parent commands
    if message.strip().startswith("/parent"):
        from parent.protocol import ParentRequest
        from parent.child_handler import get_child_handler
        
        request = ParentRequest.from_signal_message(message)
        if request is None:
            return "Invalid parent command. Use: /parent <status|history|health|logs|report>"
        
        handler = get_child_handler()
        if handler is None:
            return "Parent handler not initialized"
        
        response = handler.handle_request(request)
        return response.to_signal_message()
    
    # ... rest of message handling
```

---

## Step 3: Implement Parent-Side CLI

### 3.1 Create `parent/cli.py`

This runs on your workstation.

```python
#!/usr/bin/env python3
"""
Parent CLI - Remote supervision for Noctem.

Usage:
    parent status              Get current Noctem status
    parent history [--hours N] Get task history
    parent health              Check system health
    parent report              Generate babysitting report
    parent improve             Analyze and suggest improvements (opens Warp)
    parent watch [--interval]  Continuous monitoring mode
"""
import argparse
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Optional
import tempfile

# Configuration - edit these for your setup
SIGNAL_CLI = "signal-cli"
MY_NUMBER = None  # Your phone number
NOCTEM_NUMBER = None  # Noctem's phone number (or group ID)

def load_config():
    """Load configuration from file."""
    global MY_NUMBER, NOCTEM_NUMBER
    
    config_path = Path.home() / ".config" / "noctem-parent" / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        MY_NUMBER = config.get("my_number")
        NOCTEM_NUMBER = config.get("noctem_number")

def save_config(my_number: str, noctem_number: str):
    """Save configuration."""
    config_dir = Path.home() / ".config" / "noctem-parent"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config = {"my_number": my_number, "noctem_number": noctem_number}
    (config_dir / "config.json").write_text(json.dumps(config, indent=2))

def send_command(command: str, params: dict = None) -> Optional[str]:
    """Send a command to Noctem and wait for response."""
    if MY_NUMBER is None or NOCTEM_NUMBER is None:
        print("Error: Not configured. Run 'parent config' first.")
        return None
    
    # Build message
    params_str = json.dumps(params) if params else "{}"
    message = f"/parent {command} {params_str}"
    
    # Send via signal-cli
    try:
        subprocess.run(
            [SIGNAL_CLI, "-u", MY_NUMBER, "send", "-m", message, NOCTEM_NUMBER],
            capture_output=True,
            check=True,
            timeout=30
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to send: {e.stderr.decode()}")
        return None
    except subprocess.TimeoutExpired:
        print("Timeout sending message")
        return None
    
    # Wait for response (poll signal-cli receive)
    print("Waiting for response...", end="", flush=True)
    
    for _ in range(30):  # Wait up to 30 seconds
        time.sleep(1)
        print(".", end="", flush=True)
        
        try:
            result = subprocess.run(
                [SIGNAL_CLI, "-u", MY_NUMBER, "receive", "--timeout", "1"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Parse response (simplified - real impl would parse JSON)
            if result.stdout and NOCTEM_NUMBER in result.stdout:
                # Extract message content
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if '"body"' in line or 'Body:' in line:
                        # Found response
                        print()  # Newline after dots
                        return result.stdout
                        
        except subprocess.TimeoutExpired:
            continue
    
    print("\nNo response received")
    return None

def cmd_status(args):
    """Get Noctem status."""
    response = send_command("status")
    if response:
        print(response)

def cmd_history(args):
    """Get task history."""
    params = {"limit": args.limit, "since_hours": args.hours}
    response = send_command("history", params)
    if response:
        print(response)

def cmd_health(args):
    """Check system health."""
    response = send_command("health")
    if response:
        print(response)

def cmd_report(args):
    """Generate babysitting report."""
    response = send_command("report")
    if response:
        print(response)

def cmd_improve(args):
    """Analyze and suggest improvements using Warp."""
    print("Gathering Noctem state for analysis...")
    
    # Collect data
    status = send_command("status")
    history = send_command("history", {"limit": 50, "since_hours": 48})
    health = send_command("health")
    logs = send_command("logs", {"lines": 100})
    
    # Create context file for Warp
    context = f"""# Noctem Analysis Context

## Current Status
{status or 'Unable to fetch'}

## Recent History (48h)
{history or 'Unable to fetch'}

## Health Check
{health or 'Unable to fetch'}

## Recent Logs
{logs or 'Unable to fetch'}

---

## Your Task

Analyze the above Noctem state and:
1. Identify any issues or inefficiencies
2. Suggest improvements to the codebase
3. Generate specific code patches for the most impactful improvements

Focus on:
- Error patterns that could be prevented
- Performance optimizations
- New skills that would be useful based on task patterns
- Configuration improvements

Generate patches in unified diff format that can be reviewed and applied.
"""
    
    # Write context to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(context)
        context_file = f.name
    
    print(f"\nContext saved to: {context_file}")
    print("\nLaunching Warp for analysis...")
    
    # Launch Warp with context
    # Note: Actual Warp CLI integration would vary
    try:
        subprocess.run([
            "warp",  # Or however Warp CLI is invoked
            "--context", context_file
        ])
    except FileNotFoundError:
        print("\nWarp CLI not found. Please open Warp manually and load:")
        print(f"  {context_file}")
        print("\nOr copy the context and paste into Warp.")

def cmd_watch(args):
    """Continuous monitoring mode."""
    interval = args.interval
    print(f"Starting watch mode (interval: {interval}s, Ctrl+C to stop)")
    print("=" * 50)
    
    try:
        while True:
            # Get report
            response = send_command("report")
            if response:
                # Clear screen and print
                print("\033[2J\033[H")  # ANSI clear screen
                print(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 50)
                print(response)
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")

def cmd_config(args):
    """Configure parent settings."""
    print("Noctem Parent Configuration")
    print("-" * 30)
    
    my_number = input("Your Signal phone number (e.g., +1234567890): ").strip()
    noctem_number = input("Noctem's Signal number or group ID: ").strip()
    
    save_config(my_number, noctem_number)
    print("\nConfiguration saved!")

def main():
    load_config()
    
    parser = argparse.ArgumentParser(
        description="Parent - Remote supervision for Noctem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Status
    subparsers.add_parser("status", help="Get current Noctem status")
    
    # History
    history_parser = subparsers.add_parser("history", help="Get task history")
    history_parser.add_argument("--hours", type=int, default=24, help="Hours of history")
    history_parser.add_argument("--limit", type=int, default=20, help="Max items")
    
    # Health
    subparsers.add_parser("health", help="Check system health")
    
    # Report
    subparsers.add_parser("report", help="Generate babysitting report")
    
    # Improve
    subparsers.add_parser("improve", help="Analyze and suggest improvements")
    
    # Watch
    watch_parser = subparsers.add_parser("watch", help="Continuous monitoring")
    watch_parser.add_argument("--interval", type=int, default=300, help="Seconds between updates")
    
    # Config
    subparsers.add_parser("config", help="Configure parent settings")
    
    args = parser.parse_args()
    
    commands = {
        "status": cmd_status,
        "history": cmd_history,
        "health": cmd_health,
        "report": cmd_report,
        "improve": cmd_improve,
        "watch": cmd_watch,
        "config": cmd_config,
    }
    
    if args.command is None:
        parser.print_help()
        return
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

---

## Step 4: Create Improvement Workflow

### 4.1 Create `parent/improve.py`

```python
"""
Improvement workflow - Generate and manage code improvements.
"""
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import subprocess

@dataclass
class Improvement:
    id: str
    title: str
    description: str
    priority: int  # 1-5, 1 is highest
    patch: str  # Unified diff format
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"  # pending, approved, applied, rejected
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "patch": self.patch,
            "created_at": self.created_at,
            "status": self.status
        }

class ImprovementQueue:
    def __init__(self, queue_file: Path):
        self.queue_file = queue_file
        self.improvements: List[Improvement] = []
        self._load()
    
    def _load(self):
        if self.queue_file.exists():
            data = json.loads(self.queue_file.read_text())
            self.improvements = [Improvement(**item) for item in data]
    
    def _save(self):
        data = [imp.to_dict() for imp in self.improvements]
        self.queue_file.write_text(json.dumps(data, indent=2))
    
    def add(self, improvement: Improvement):
        self.improvements.append(improvement)
        self._save()
    
    def get_pending(self) -> List[Improvement]:
        return [imp for imp in self.improvements if imp.status == "pending"]
    
    def approve(self, imp_id: str) -> bool:
        for imp in self.improvements:
            if imp.id == imp_id:
                imp.status = "approved"
                self._save()
                return True
        return False
    
    def reject(self, imp_id: str) -> bool:
        for imp in self.improvements:
            if imp.id == imp_id:
                imp.status = "rejected"
                self._save()
                return True
        return False
    
    def apply(self, imp_id: str, working_dir: Path) -> tuple[bool, str]:
        """Apply an approved improvement patch."""
        imp = next((i for i in self.improvements if i.id == imp_id), None)
        if imp is None:
            return False, "Improvement not found"
        if imp.status != "approved":
            return False, "Improvement not approved"
        
        # Write patch to temp file
        patch_file = Path(f"/tmp/noctem_patch_{imp_id}.diff")
        patch_file.write_text(imp.patch)
        
        try:
            # Apply patch (dry run first)
            result = subprocess.run(
                ["patch", "--dry-run", "-p1", "-d", str(working_dir), "-i", str(patch_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"Patch would fail: {result.stderr}"
            
            # Apply for real
            result = subprocess.run(
                ["patch", "-p1", "-d", str(working_dir), "-i", str(patch_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                imp.status = "applied"
                self._save()
                return True, "Patch applied successfully"
            else:
                return False, f"Patch failed: {result.stderr}"
                
        finally:
            patch_file.unlink(missing_ok=True)

def format_improvement_for_signal(imp: Improvement) -> str:
    """Format an improvement for Signal message."""
    return f"""🔧 Improvement #{imp.id}
Priority: {'⭐' * imp.priority}
Title: {imp.title}

{imp.description}

Reply:
  /parent approve {imp.id} - Approve this change
  /parent reject {imp.id} - Reject this change
  /parent diff {imp.id} - View the full diff"""
```

---

## Step 5: Automated Babysitting Reports

### 5.1 Create `parent/scheduler.py`

This can run as a cron job or systemd timer on the Noctem machine.

```python
#!/usr/bin/env python3
"""
Scheduled babysitting report generator.

Add to crontab:
  0 */6 * * * /path/to/noctem/parent/scheduler.py --report

Or create a systemd timer.
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parent.child_handler import ChildHandler

def send_signal_report(report: str, signal_number: str, recipient: str):
    """Send report via Signal."""
    try:
        subprocess.run(
            ["signal-cli", "-u", signal_number, "send", "-m", report, recipient],
            capture_output=True,
            check=True,
            timeout=30
        )
        return True
    except:
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="Generate and send report")
    parser.add_argument("--signal-number", required=True, help="Noctem's Signal number")
    parser.add_argument("--recipient", required=True, help="Parent's Signal number")
    
    args = parser.parse_args()
    
    if args.report:
        # Initialize handler
        working_dir = Path(__file__).parent.parent
        db_path = working_dir / "noctem.db"
        
        handler = ChildHandler(db_path, working_dir)
        
        # Generate report
        from parent.protocol import ParentRequest, ParentCommand
        request = ParentRequest(command=ParentCommand.REPORT)
        response = handler.handle_request(request)
        
        report = response.to_signal_message()
        
        # Send via Signal
        if send_signal_report(report, args.signal_number, args.recipient):
            print("Report sent successfully")
        else:
            print("Failed to send report")
            sys.exit(1)

if __name__ == "__main__":
    main()
```

### 5.2 Create systemd Timer for Reports

Create `/etc/systemd/system/noctem-report.timer`:

```ini
[Unit]
Description=Noctem Babysitting Report Timer

[Timer]
OnCalendar=*-*-* 06,12,18,00:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Create `/etc/systemd/system/noctem-report.service`:

```ini
[Unit]
Description=Noctem Babysitting Report

[Service]
Type=oneshot
ExecStart=/path/to/noctem/parent/scheduler.py --report --signal-number +NOCTEM_NUMBER --recipient +PARENT_NUMBER
```

Enable: `sudo systemctl enable noctem-report.timer`

---

## Step 6: Installation on Parent Machine

### 6.1 Create `parent/install.sh`

```bash
#!/bin/bash
# Install parent CLI on your workstation

set -e

INSTALL_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/noctem-parent"

echo "Installing Noctem Parent CLI..."

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# Copy CLI script
cp cli.py "$INSTALL_DIR/parent"
chmod +x "$INSTALL_DIR/parent"

# Check if in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo ""
    echo "Add to your shell profile:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Run 'parent config' to set up your Signal numbers"
echo "  2. Run 'parent status' to test the connection"
echo "  3. Run 'parent watch' for continuous monitoring"
```

---

## Completion Checklist

- [ ] `parent/__init__.py` created
- [ ] `parent/protocol.py` created
- [ ] `parent/child_handler.py` created on Noctem
- [ ] `parent/cli.py` created for workstation
- [ ] `parent/improve.py` created
- [ ] `parent/scheduler.py` created
- [ ] `signal_receiver.py` handles /parent commands
- [ ] Scheduled reports working
- [ ] Parent CLI installed on workstation
- [ ] `parent status` returns data
- [ ] `parent report` generates report
- [ ] `parent improve` opens Warp with context

---

## Usage Examples

```bash
# On parent machine:

# Initial setup
parent config

# Check status
parent status

# Get detailed history
parent history --hours 48 --limit 50

# Health check
parent health

# Generate report
parent report

# Start continuous monitoring
parent watch --interval 300

# Analyze and improve (opens Warp)
parent improve
```

---

## Troubleshooting

### Signal messages not received
- Verify signal-cli is configured on both machines
- Check phone numbers are correct
- Test with direct signal-cli commands

### Parent command returns error
- Check that child_handler is initialized in daemon.py
- Verify database path is correct
- Check Noctem logs for errors

### Warp not launching
- Verify Warp CLI is installed
- Check PATH includes Warp
- Manually open context file in Warp
