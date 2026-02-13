#!/usr/bin/env python3
"""
Skill: daily_report
Generates and sends daily status reports.

The report includes:
1. Tasks completed since last report
2. Incidents/errors since last report  
3. Suggested actions for today

Parameters:
  - send (bool, optional): Send report via email (default: true)
  - period_hours (int, optional): Hours to look back (default: 24)
  - recipient (str, optional): Override recipient email

Returns:
  - success: {"report": "...", "sent": bool, "stats": {...}}
  - error: {"error": "..."}
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import socket

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.base import Skill, SkillResult, SkillContext, register_skill
from skills.email_send import send_email_smtp
from utils.vault import get_credential
import state


def get_hostname() -> str:
    """Get machine hostname for identification."""
    return socket.gethostname()


def format_task_summary(task: Dict) -> str:
    """Format a single task for the report."""
    status_emoji = "✅" if task["status"] == "done" else "❌"
    input_text = task["input"][:60] + "..." if len(task["input"]) > 60 else task["input"]
    return f"  {status_emoji} {input_text}"


def format_incident(incident: Dict) -> str:
    """Format a single incident for the report."""
    severity_emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨",
    }.get(incident["severity"], "•")
    
    return f"  {severity_emoji} [{incident['severity'].upper()}] {incident['message']}"


def generate_suggestions(
    completed_tasks: List[Dict],
    failed_tasks: List[Dict],
    incidents: List[Dict],
    pending_tasks: List[Dict]
) -> List[str]:
    """
    Generate actionable suggestions based on recent activity.
    """
    suggestions = []
    
    # Check for failed tasks that need retry
    if failed_tasks:
        suggestions.append(f"🔄 {len(failed_tasks)} task(s) failed - review and retry?")
    
    # Check for pending tasks
    if pending_tasks:
        high_priority = [t for t in pending_tasks if t.get("priority", 5) <= 3]
        if high_priority:
            suggestions.append(f"⚡ {len(high_priority)} high-priority task(s) waiting")
        else:
            suggestions.append(f"📋 {len(pending_tasks)} task(s) in queue")
    
    # Check for recurring errors
    error_incidents = [i for i in incidents if i["severity"] in ("error", "critical")]
    if len(error_incidents) >= 3:
        suggestions.append("🔧 Multiple errors detected - investigate system health")
    
    # Check for inactivity
    if not completed_tasks and not failed_tasks:
        suggestions.append("💤 No tasks completed - is everything working?")
    
    # Default suggestion
    if not suggestions:
        suggestions.append("✨ All systems nominal - carry on!")
    
    return suggestions


def generate_report(
    period_hours: int = 24,
    include_suggestions: bool = True
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate the daily report text and stats.
    
    Returns (report_text, stats_dict).
    """
    now = datetime.now()
    since = now - timedelta(hours=period_hours)
    hostname = get_hostname()
    
    # Gather data
    completed_tasks = state.get_tasks_since(since, status="done")
    failed_tasks = state.get_tasks_since(since, status="failed")
    incidents = state.get_incidents_since(since)
    pending_tasks = state.get_pending_tasks()
    
    # Get last report date
    last_report = state.get_last_report_date()
    
    # Stats
    stats = {
        "period_hours": period_hours,
        "tasks_completed": len(completed_tasks),
        "tasks_failed": len(failed_tasks),
        "incidents_count": len(incidents),
        "pending_count": len(pending_tasks),
        "generated_at": now.isoformat(),
        "hostname": hostname,
    }
    
    # Build report
    lines = []
    
    # Header
    lines.append(f"🌙 NOCTEM DAILY REPORT")
    lines.append(f"   {hostname} | {now.strftime('%Y-%m-%d %H:%M')}")
    if last_report:
        lines.append(f"   Last report: {last_report.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("=" * 50)
    
    # Tasks completed
    lines.append("")
    lines.append(f"📊 TASKS COMPLETED ({len(completed_tasks)})")
    lines.append("-" * 30)
    if completed_tasks:
        for task in completed_tasks[:10]:  # Limit to 10
            lines.append(format_task_summary(task))
        if len(completed_tasks) > 10:
            lines.append(f"  ... and {len(completed_tasks) - 10} more")
    else:
        lines.append("  (none)")
    
    # Failed tasks
    if failed_tasks:
        lines.append("")
        lines.append(f"❌ TASKS FAILED ({len(failed_tasks)})")
        lines.append("-" * 30)
        for task in failed_tasks[:5]:
            lines.append(format_task_summary(task))
            if task.get("result"):
                lines.append(f"     Error: {task['result'][:50]}...")
    
    # Incidents
    lines.append("")
    lines.append(f"🚨 INCIDENTS ({len(incidents)})")
    lines.append("-" * 30)
    if incidents:
        # Group by severity
        critical = [i for i in incidents if i["severity"] == "critical"]
        errors = [i for i in incidents if i["severity"] == "error"]
        warnings = [i for i in incidents if i["severity"] == "warning"]
        infos = [i for i in incidents if i["severity"] == "info"]
        
        for incident_list in [critical, errors, warnings, infos]:
            for incident in incident_list[:3]:  # Limit per severity
                lines.append(format_incident(incident))
        
        total_shown = min(len(critical), 3) + min(len(errors), 3) + min(len(warnings), 3) + min(len(infos), 3)
        if len(incidents) > total_shown:
            lines.append(f"  ... and {len(incidents) - total_shown} more")
    else:
        lines.append("  (none)")
    
    # Suggestions
    if include_suggestions:
        suggestions = generate_suggestions(completed_tasks, failed_tasks, incidents, pending_tasks)
        lines.append("")
        lines.append("💡 SUGGESTED ACTIONS")
        lines.append("-" * 30)
        for suggestion in suggestions:
            lines.append(f"  {suggestion}")
    
    # Footer
    lines.append("")
    lines.append("=" * 50)
    lines.append(f"Generated by Noctem on {hostname}")
    lines.append("")
    
    report_text = "\n".join(lines)
    return report_text, stats


def send_daily_report(
    recipient: Optional[str] = None,
    period_hours: int = 24
) -> Tuple[bool, str, Dict]:
    """
    Generate and send the daily report.
    
    Returns (success, message, stats).
    """
    # Generate report
    report_text, stats = generate_report(period_hours)
    
    # Get recipient
    recipient = recipient or get_credential("email_recipient") or get_credential("email_user")
    if not recipient:
        return False, "No recipient configured", stats
    
    # Save report to database
    now = datetime.now()
    state.save_daily_report(
        report_date=now,
        tasks_completed=stats["tasks_completed"],
        tasks_failed=stats["tasks_failed"],
        incidents_count=stats["incidents_count"],
        report_text=report_text
    )
    
    # Send email
    hostname = get_hostname()
    subject = f"🌙 Noctem Daily Report - {hostname} - {now.strftime('%Y-%m-%d')}"
    
    success, message = send_email_smtp(
        to=recipient,
        subject=subject,
        body=report_text
    )
    
    if success:
        state.mark_report_sent(now)
        # Acknowledge incidents that were included
        state.acknowledge_incidents()
    
    return success, message, stats


@register_skill  
class DailyReportSkill(Skill):
    """Generate and send daily status reports."""
    
    name = "daily_report"
    description = "Generate and optionally send a daily status report"
    parameters = {
        "send": "Send report via email (optional, default: true)",
        "period_hours": "Hours to look back (optional, default: 24)",
        "recipient": "Override recipient email (optional)",
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        send = params.get("send", True)
        period_hours = params.get("period_hours", 24)
        recipient = params.get("recipient")
        
        try:
            if send:
                success, message, stats = send_daily_report(recipient, period_hours)
                
                if success:
                    return SkillResult(
                        success=True,
                        output=f"Daily report sent to {recipient or 'configured recipient'}",
                        data={"sent": True, "stats": stats}
                    )
                else:
                    # Still return the report even if send failed
                    report_text, _ = generate_report(period_hours)
                    return SkillResult(
                        success=False,
                        output=report_text,
                        error=f"Report generated but send failed: {message}",
                        data={"sent": False, "stats": stats}
                    )
            else:
                # Just generate, don't send
                report_text, stats = generate_report(period_hours)
                return SkillResult(
                    success=True,
                    output=report_text,
                    data={"sent": False, "stats": stats}
                )
                
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Report generation failed: {e}"
            )


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Noctem Daily Report")
    parser.add_argument("--generate", "-g", action="store_true", 
                        help="Generate report (print to stdout)")
    parser.add_argument("--send", "-s", action="store_true",
                        help="Generate and send report via email")
    parser.add_argument("--hours", "-H", type=int, default=24,
                        help="Hours to look back (default: 24)")
    parser.add_argument("--to", help="Recipient email override")
    args = parser.parse_args()
    
    if args.generate:
        report, stats = generate_report(args.hours)
        print(report)
        print(f"\nStats: {stats}")
        
    elif args.send:
        print("Generating and sending daily report...")
        success, message, stats = send_daily_report(args.to, args.hours)
        print(f"{'✓' if success else '✗'} {message}")
        print(f"Stats: completed={stats['tasks_completed']}, failed={stats['tasks_failed']}, incidents={stats['incidents_count']}")
        sys.exit(0 if success else 1)
        
    else:
        parser.print_help()
