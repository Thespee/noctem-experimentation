#!/usr/bin/env python3
"""
Scheduled babysitting and self-improvement.

Runs periodic tasks:
- Generate babysitting reports
- Analyze patterns for training data
- Suggest improvements based on accumulated errors

Can be run as:
1. Standalone script (via cron/systemd timer)
2. Background thread within Noctem daemon
"""

import argparse
import json
import logging
import subprocess
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger("noctem.parent.scheduler")


class BabysittingScheduler:
    """
    Runs babysitting tasks on schedule.
    
    When idle (no tasks being processed), analyzes past performance
    and generates training data for self-improvement.
    """
    
    def __init__(self, working_dir: Path, db_path: Path):
        self.working_dir = working_dir
        self.db_path = db_path
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
        # Configuration
        self.report_interval_hours = 6  # Generate report every 6 hours
        self.analysis_interval_hours = 24  # Deep analysis daily
        self.idle_check_seconds = 60  # Check for idle every minute
        
        self._last_report = None
        self._last_analysis = None
    
    def is_idle(self) -> bool:
        """Check if Noctem is idle (no active tasks)."""
        try:
            import state
            running = state.get_running_tasks()
            pending = state.get_pending_tasks()
            return len(running) == 0 and len(pending) == 0
        except Exception as e:
            logger.error(f"Error checking idle state: {e}")
            return False
    
    def generate_report(self, send_signal: bool = False) -> Dict[str, Any]:
        """Generate a babysitting report."""
        from .child_handler import ChildHandler
        
        handler = ChildHandler(self.db_path, self.working_dir)
        result = handler._handle_report({})
        
        if send_signal:
            self._send_signal_report(result.get("report", ""))
        
        return result
    
    def analyze_for_improvements(self) -> List[Dict]:
        """
        Analyze accumulated data and generate improvement suggestions.
        This is the "self-improvement" loop.
        """
        import state
        from .improve import analyze_problems, ImprovementManager
        
        # Get recent reports
        reports = state.get_recent_reports("babysitting", limit=7)
        
        # Aggregate problems
        all_problems = []
        for report in reports:
            problems = report.get("problems_json")
            if isinstance(problems, list):
                all_problems.extend(problems)
            elif isinstance(problems, str):
                try:
                    all_problems.extend(json.loads(problems))
                except json.JSONDecodeError:
                    pass
        
        # Analyze patterns
        suggestions = analyze_problems(all_problems)
        
        # Create improvements for significant patterns
        manager = ImprovementManager()
        created = []
        
        for suggestion in suggestions:
            imp_id = manager.create(
                title=suggestion["title"],
                description=suggestion["description"],
                priority=suggestion.get("priority", 3),
                source="babysitter"
            )
            created.append({
                "id": imp_id,
                "title": suggestion["title"]
            })
            logger.info(f"Created improvement suggestion: {suggestion['title']}")
        
        # Store analysis as training data
        if all_problems:
            state.create_report(
                report_type="analysis",
                content=f"Analyzed {len(all_problems)} problems, created {len(created)} suggestions",
                metrics={
                    "problems_analyzed": len(all_problems),
                    "suggestions_created": len(created)
                },
                problems=all_problems,
                solutions=suggestions
            )
        
        return created
    
    def _send_signal_report(self, report: str):
        """Send report via Signal."""
        try:
            from skill_runner import load_config
            config = load_config()
            phone = config.get("signal_phone")
            
            if not phone:
                logger.warning("No signal_phone configured, skipping notification")
                return
            
            from skills.signal_send import SignalSendSkill
            from skills.base import SkillContext
            
            skill = SignalSendSkill()
            ctx = SkillContext(config=config)
            skill.execute({"message": report}, ctx)
            logger.info("Sent babysitting report via Signal")
            
        except Exception as e:
            logger.error(f"Failed to send Signal report: {e}")
    
    def _should_generate_report(self) -> bool:
        """Check if it's time to generate a report."""
        if self._last_report is None:
            return True
        
        elapsed = datetime.now() - self._last_report
        return elapsed >= timedelta(hours=self.report_interval_hours)
    
    def _should_run_analysis(self) -> bool:
        """Check if it's time to run deep analysis."""
        if self._last_analysis is None:
            return True
        
        elapsed = datetime.now() - self._last_analysis
        return elapsed >= timedelta(hours=self.analysis_interval_hours)
    
    def run_once(self, force_report: bool = False, force_analysis: bool = False):
        """Run one iteration of scheduled tasks."""
        # Generate report if needed
        if force_report or self._should_generate_report():
            logger.info("Generating babysitting report")
            self.generate_report(send_signal=True)
            self._last_report = datetime.now()
        
        # Run analysis if idle and time
        if self.is_idle() and (force_analysis or self._should_run_analysis()):
            logger.info("Running self-improvement analysis")
            suggestions = self.analyze_for_improvements()
            self._last_analysis = datetime.now()
            
            if suggestions:
                # Notify about new suggestions
                msg = f"🧠 Self-improvement: Created {len(suggestions)} improvement suggestions"
                for s in suggestions[:3]:
                    msg += f"\n  • {s['title']}"
                self._send_signal_report(msg)
    
    def _loop(self):
        """Main scheduler loop."""
        logger.info("Babysitting scheduler started")
        
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logger.exception(f"Error in scheduler loop: {e}")
            
            # Sleep until next check
            time.sleep(self.idle_check_seconds)
        
        logger.info("Babysitting scheduler stopped")
    
    def start(self):
        """Start the scheduler in a background thread."""
        if self.running:
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)


# Global scheduler instance
_scheduler: Optional[BabysittingScheduler] = None


def get_scheduler() -> Optional[BabysittingScheduler]:
    """Get the scheduler instance."""
    return _scheduler


def init_scheduler(working_dir: Path, db_path: Path) -> BabysittingScheduler:
    """Initialize the global scheduler."""
    global _scheduler
    _scheduler = BabysittingScheduler(working_dir, db_path)
    return _scheduler


def main():
    """CLI entry point for manual/cron execution."""
    parser = argparse.ArgumentParser(description="Noctem Babysitting Scheduler")
    parser.add_argument("--report", action="store_true", help="Generate and send report")
    parser.add_argument("--analyze", action="store_true", help="Run improvement analysis")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--working-dir", type=Path, default=Path(__file__).parent.parent,
                        help="Noctem working directory")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # Ensure we can import state
    sys.path.insert(0, str(args.working_dir))
    
    db_path = args.working_dir / "data" / "noctem.db"
    scheduler = init_scheduler(args.working_dir, db_path)
    
    if args.daemon:
        print("Starting babysitting daemon...")
        scheduler.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
            print("Stopped.")
    else:
        # One-shot mode
        scheduler.run_once(
            force_report=args.report,
            force_analysis=args.analyze
        )
        
        if not args.report and not args.analyze:
            print("Use --report to generate a report, --analyze to run analysis")
            print("Or --daemon to run continuously")


if __name__ == "__main__":
    main()
