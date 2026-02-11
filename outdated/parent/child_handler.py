#!/usr/bin/env python3
"""
Handle parent commands on the Noctem (child) side.
This runs on the Noctem machine and responds to /parent commands.
"""

import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

from .protocol import ParentCommand, ParentRequest, ParentResponse

logger = logging.getLogger("noctem.parent.child")


class ChildHandler:
    """Handles parent requests on the child (Noctem) side."""
    
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
            ParentCommand.APPROVE: self._handle_approve,
            ParentCommand.REJECT: self._handle_reject,
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
            logger.exception(f"Error handling {request.command.value}")
            return ParentResponse(
                request_id=request.request_id,
                success=False,
                data={},
                error=str(e)
            )
    
    def _handle_status(self, params: Dict) -> Dict[str, Any]:
        """Get current system status."""
        import state
        
        # Calculate uptime
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        # Get task counts
        running = state.get_running_tasks()
        pending = state.get_pending_tasks()
        
        # Get last activity
        recent = state.get_recent_tasks(limit=1)
        last_activity = recent[0]['completed_at'] if recent else "never"
        
        return {
            "status": {
                "state": "running",
                "uptime": uptime_str,
                "active_tasks": len(running),
                "queue_size": len(pending),
                "last_activity": last_activity
            }
        }
    
    def _handle_history(self, params: Dict) -> Dict[str, Any]:
        """Get task history."""
        import state
        
        limit = params.get("limit", 20)
        since_hours = params.get("since_hours", 24)
        
        # Get stats
        stats = state.get_task_stats(since_hours)
        
        # Get recent tasks
        conn = state.get_connection()
        cursor = conn.cursor()
        since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        
        cursor.execute("""
            SELECT id, input, status, source, created_at, completed_at, result
            FROM tasks
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (since, limit))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "id": row['id'],
                "input": row['input'],
                "status": row['status'],
                "source": row['source'],
                "success": row['status'] == 'done',
                "created": row['created_at'],
                "completed": row['completed_at'],
                "result": row['result'][:200] if row['result'] else None
            })
        
        conn.close()
        
        return {
            "history": history,
            "stats": stats
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
        except Exception:
            pass
        
        # Check Signal daemon
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', 7583))
            health["signal"] = result == 0
            sock.close()
        except Exception:
            pass
        
        # System metrics via psutil
        try:
            import psutil
            health["disk_usage"] = round(psutil.disk_usage('/').percent, 1)
            health["memory_usage"] = round(psutil.virtual_memory().percent, 1)
            health["cpu_usage"] = round(psutil.cpu_percent(interval=0.5), 1)
        except ImportError:
            # psutil not installed, try shell commands
            try:
                result = subprocess.run(
                    ["df", "-h", "/"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Parse df output
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        parts = lines[1].split()
                        if len(parts) >= 5:
                            health["disk_usage"] = float(parts[4].rstrip('%'))
            except Exception:
                pass
        except Exception:
            pass
        
        return {"health": health}
    
    def _handle_logs(self, params: Dict) -> Dict[str, Any]:
        """Get recent logs."""
        lines = params.get("lines", 50)
        log_file = self.working_dir / "logs" / "noctem.log"
        
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
        import state
        
        # Gather all info
        status = self._handle_status({})["status"]
        task_stats = state.get_task_stats(24)
        skill_stats = state.get_skill_stats(24)
        health = self._handle_health({})["health"]
        
        # Calculate metrics
        total_tasks = task_stats["total"]
        success_rate = task_stats["success_rate"]
        failed_tasks = task_stats["failed_tasks"]
        
        # Find skill issues
        skill_failures = skill_stats.get("failed_executions", [])
        
        # Build report
        report = f"""🍼 Noctem Babysitting Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱ Uptime: {status['uptime']}
📊 Tasks (24h): {total_tasks} ({success_rate} success)
💾 Disk: {health['disk_usage']}%
🧠 Memory: {health['memory_usage']}%
🔥 Errors (24h): {len(failed_tasks)}"""
        
        if failed_tasks:
            report += "\n\n❌ Recent failures:"
            for t in failed_tasks[:3]:
                task_input = t.get('input', 'unknown')[:40]
                report += f"\n  • {task_input}"
        
        if skill_failures:
            report += f"\n\n⚠️ Skill errors: {len(skill_failures)}"
            for s in skill_failures[:3]:
                report += f"\n  • {s.get('skill_name', 'unknown')}"
        
        report += "\n\n🔧 Services:"
        report += f"\n  Ollama: {'✅' if health['ollama'] else '❌'}"
        report += f"\n  Signal: {'✅' if health['signal'] else '❌'}"
        
        # Build training data (problem -> solution pairs)
        problems = []
        solutions = []
        
        for task in failed_tasks:
            problems.append({
                "type": "task_failure",
                "input": task.get("input"),
                "result": task.get("result")
            })
        
        for skill in skill_failures:
            problems.append({
                "type": "skill_failure", 
                "skill": skill.get("skill_name"),
                "input": skill.get("input"),
                "output": skill.get("output")
            })
        
        # Store as training data
        metrics = {
            "uptime": status['uptime'],
            "total_tasks": total_tasks,
            "success_rate": success_rate,
            "disk_usage": health['disk_usage'],
            "memory_usage": health['memory_usage'],
            "errors_24h": len(failed_tasks) + len(skill_failures)
        }
        
        report_id = state.create_report(
            report_type="babysitting",
            content=report,
            metrics=metrics,
            problems=problems,
            solutions=solutions
        )
        
        return {
            "report": report,
            "report_id": report_id,
            "metrics": metrics,
            "problems": problems
        }
    
    def _handle_approve(self, params: Dict) -> Dict[str, Any]:
        """Approve an improvement."""
        import state
        
        imp_id = params.get("id")
        if not imp_id:
            raise ValueError("Missing improvement ID")
        
        if state.update_improvement_status(int(imp_id), "approved"):
            return {"approved": True, "id": imp_id}
        else:
            raise ValueError(f"Improvement {imp_id} not found or already processed")
    
    def _handle_reject(self, params: Dict) -> Dict[str, Any]:
        """Reject an improvement."""
        import state
        
        imp_id = params.get("id")
        if not imp_id:
            raise ValueError("Missing improvement ID")
        
        if state.update_improvement_status(int(imp_id), "rejected"):
            return {"rejected": True, "id": imp_id}
        else:
            raise ValueError(f"Improvement {imp_id} not found or already processed")


# Singleton instance
_handler: Optional[ChildHandler] = None


def init_child_handler(db_path: Path, working_dir: Path):
    """Initialize the child handler singleton."""
    global _handler
    _handler = ChildHandler(db_path, working_dir)
    return _handler


def get_child_handler() -> Optional[ChildHandler]:
    """Get the child handler singleton."""
    return _handler


def handle_parent_message(message: str) -> Optional[str]:
    """
    Handle a /parent message and return response.
    Returns None if not a parent command.
    """
    request = ParentRequest.from_signal_message(message)
    if request is None:
        return None
    
    handler = get_child_handler()
    if handler is None:
        return "❌ Parent handler not initialized"
    
    response = handler.handle_request(request)
    return response.to_signal_message()
