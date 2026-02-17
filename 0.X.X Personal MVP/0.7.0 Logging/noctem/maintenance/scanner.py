"""
Maintenance Scanner for Noctem v0.6.1.

Periodic "building maintenance" that:
- Discovers and benchmarks available models
- Checks queue health and system status
- Aggregates project insights
- Generates actionable reports for Butler delivery
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from ..db import get_db
from ..config import Config
from ..models import MaintenanceInsight
from ..slow.model_registry import get_registry, ModelInfo
from ..slow.queue import SlowWorkQueue

logger = logging.getLogger(__name__)


class MaintenanceScanner:
    """
    Scans system health and generates maintenance insights.
    
    Scan types:
    - models: Discover/benchmark available LLM models
    - queue: Check slow work queue health
    - projects: Aggregate project agent suggestions
    - full: All of the above
    """
    
    def __init__(self):
        self.registry = get_registry()
    
    # =========================================================================
    # MODEL SCANNING
    # =========================================================================
    
    def scan_models(self) -> List[MaintenanceInsight]:
        """
        Discover and benchmark models, generate insights.
        
        Returns:
            List of generated insights
        """
        insights = []
        
        # Discover models
        models = self.registry.discover_models()
        
        if not models:
            insight = self._create_insight(
                insight_type="blocker",
                source="model_scan",
                title="No models available",
                details={"message": "Ollama not running or no models installed"},
                priority=5,
            )
            insights.append(insight)
            return insights
        
        logger.info(f"Found {len(models)} models, benchmarking...")
        
        # Benchmark each model
        current_model = Config.get("slow_model")
        current_tps = None
        best_model = None
        best_tps = 0
        
        for model in models:
            info = self.registry.benchmark_and_save(model.name, model.backend)
            if info and info.tokens_per_sec:
                if info.name == current_model or info.name.startswith(current_model.split(":")[0]):
                    current_tps = info.tokens_per_sec
                if info.tokens_per_sec > best_tps:
                    best_tps = info.tokens_per_sec
                    best_model = info
        
        # Generate insights
        if best_model and current_tps and best_tps > current_tps * 1.2:
            # Found faster model (20% improvement threshold)
            insight = self._create_insight(
                insight_type="model_upgrade",
                source="model_scan",
                title=f"Faster model available: {best_model.name}",
                details={
                    "current_model": current_model,
                    "current_tps": current_tps,
                    "suggested_model": best_model.name,
                    "suggested_tps": best_tps,
                    "improvement": f"{((best_tps / current_tps) - 1) * 100:.1f}%",
                },
                priority=3,
            )
            insights.append(insight)
        
        # Check for slow models
        slow_models = [m for m in self.registry.get_all_models() if m.health == "slow"]
        if slow_models:
            insight = self._create_insight(
                insight_type="recommendation",
                source="model_scan",
                title=f"{len(slow_models)} model(s) performing slowly",
                details={
                    "slow_models": [m.name for m in slow_models],
                    "recommendation": "Consider using smaller quantized versions",
                },
                priority=2,
            )
            insights.append(insight)
        
        return insights
    
    # =========================================================================
    # QUEUE HEALTH
    # =========================================================================
    
    def scan_queue_health(self) -> List[MaintenanceInsight]:
        """
        Check slow work queue health, generate insights.
        
        Returns:
            List of generated insights
        """
        insights = []
        
        status = SlowWorkQueue.get_queue_status()
        
        # Check for backlog
        if status["pending"] > 10:
            insight = self._create_insight(
                insight_type="blocker",
                source="queue_health",
                title=f"Large queue backlog: {status['pending']} items pending",
                details={
                    "pending": status["pending"],
                    "processing": status["processing"],
                    "completed_24h": status["completed"],
                    "recommendation": "Consider faster model or longer idle threshold",
                },
                priority=4,
            )
            insights.append(insight)
        
        # Check for failures
        if status["failed"] > 3:
            insight = self._create_insight(
                insight_type="blocker",
                source="queue_health",
                title=f"Multiple queue failures: {status['failed']} items failed",
                details={
                    "failed": status["failed"],
                    "recommendation": "Check Ollama stability or model compatibility",
                },
                priority=5,
            )
            insights.append(insight)
        
        # Check processing rate
        if status["completed"] == 0 and status["pending"] > 0:
            insight = self._create_insight(
                insight_type="recommendation",
                source="queue_health",
                title="No items processed recently",
                details={
                    "pending": status["pending"],
                    "recommendation": "Queue may be stalled - check slow mode status",
                },
                priority=3,
            )
            insights.append(insight)
        
        return insights
    
    # =========================================================================
    # PROJECT SUGGESTIONS
    # =========================================================================
    
    def scan_project_suggestions(self) -> List[MaintenanceInsight]:
        """
        Aggregate project-level suggestions and patterns.
        
        Returns:
            List of generated insights
        """
        insights = []
        
        with get_db() as conn:
            # Get active projects with suggestions
            rows = conn.execute("""
                SELECT id, name, next_action_suggestion, suggestion_generated_at
                FROM projects
                WHERE status = 'in_progress'
                  AND next_action_suggestion IS NOT NULL
            """).fetchall()
        
        if not rows:
            return insights
        
        # Check for stale suggestions (>14 days old)
        stale_projects = []
        now = datetime.now()
        
        for row in rows:
            if row["suggestion_generated_at"]:
                try:
                    gen_at = datetime.fromisoformat(str(row["suggestion_generated_at"]))
                    if (now - gen_at).days > 14:
                        stale_projects.append(row["name"])
                except (ValueError, TypeError):
                    pass
        
        if len(stale_projects) >= len(rows) * 0.5:  # >50% stale
            insight = self._create_insight(
                insight_type="recommendation",
                source="project_agents",
                title="Project insights going stale",
                details={
                    "stale_count": len(stale_projects),
                    "total_projects": len(rows),
                    "stale_projects": stale_projects[:5],
                    "recommendation": "Increase analysis frequency",
                },
                priority=2,
            )
            insights.append(insight)
        
        return insights
    
    # =========================================================================
    # BUTLER BUDGET
    # =========================================================================
    
    def scan_butler_budget(self) -> List[MaintenanceInsight]:
        """
        Check Butler contact budget usage.
        
        Returns:
            List of generated insights
        """
        insights = []
        
        from ..butler.protocol import ButlerProtocol
        status = ButlerProtocol.get_budget_status()
        
        # Check if budget exhausted early in week
        today = datetime.now()
        day_of_week = today.weekday()  # 0 = Monday
        
        if status["total_remaining"] == 0 and day_of_week < 4:  # Before Friday
            insight = self._create_insight(
                insight_type="recommendation",
                source="butler_budget",
                title="Contact budget exhausted early",
                details={
                    "day_of_week": today.strftime("%A"),
                    "week": status["week"],
                    "recommendation": "Review urgency thresholds or increase budget",
                },
                priority=2,
            )
            insights.append(insight)
        
        return insights
    
    # =========================================================================
    # FULL SCAN
    # =========================================================================
    
    def run_full_scan(self) -> List[MaintenanceInsight]:
        """
        Run all maintenance scans.
        
        Returns:
            Combined list of insights from all scans
        """
        all_insights = []
        
        logger.info("Starting full maintenance scan...")
        
        # Model scan
        try:
            insights = self.scan_models()
            all_insights.extend(insights)
            logger.info(f"Model scan: {len(insights)} insights")
        except Exception as e:
            logger.error(f"Model scan failed: {e}")
        
        # Queue health
        try:
            insights = self.scan_queue_health()
            all_insights.extend(insights)
            logger.info(f"Queue health scan: {len(insights)} insights")
        except Exception as e:
            logger.error(f"Queue health scan failed: {e}")
        
        # Project suggestions
        try:
            insights = self.scan_project_suggestions()
            all_insights.extend(insights)
            logger.info(f"Project scan: {len(insights)} insights")
        except Exception as e:
            logger.error(f"Project scan failed: {e}")
        
        # Butler budget
        try:
            insights = self.scan_butler_budget()
            all_insights.extend(insights)
            logger.info(f"Butler scan: {len(insights)} insights")
        except Exception as e:
            logger.error(f"Butler scan failed: {e}")
        
        logger.info(f"Full maintenance scan complete: {len(all_insights)} total insights")
        
        return all_insights
    
    # =========================================================================
    # REPORT GENERATION
    # =========================================================================
    
    def generate_report(self, insights: List[MaintenanceInsight] = None) -> str:
        """
        Generate a maintenance report for Butler delivery.
        
        Args:
            insights: Pre-generated insights, or None to run fresh scan
            
        Returns:
            Formatted report string
        """
        if insights is None:
            insights = self.get_pending_insights()
        
        if not insights:
            return "🔧 **System Maintenance Report**\n\n✅ All systems healthy. No issues to report."
        
        lines = [
            "🔧 **System Maintenance Report**",
            "",
        ]
        
        # Model status
        models = self.registry.get_all_models()
        current = Config.get("slow_model")
        current_info = self.registry.get_model(current)
        
        lines.append("**Model Status**")
        if current_info:
            lines.append(f"• Current: {current} ({current_info.tokens_per_sec or '?'} tok/s)")
        else:
            lines.append(f"• Current: {current} (not benchmarked)")
        lines.append(f"• Available: {len(models)} models")
        lines.append("")
        
        # Queue status
        queue_status = SlowWorkQueue.get_queue_status()
        lines.append("**Queue Status**")
        lines.append(f"• Pending: {queue_status['pending']}")
        lines.append(f"• Completed (24h): {queue_status['completed']}")
        if queue_status['failed'] > 0:
            lines.append(f"• ⚠️ Failed: {queue_status['failed']}")
        lines.append("")
        
        # Insights by priority
        high_priority = [i for i in insights if i.priority >= 4]
        medium_priority = [i for i in insights if 2 <= i.priority < 4]
        
        if high_priority:
            lines.append("**⚠️ High Priority**")
            for i in high_priority:
                lines.append(f"• {i.title}")
            lines.append("")
        
        if medium_priority:
            lines.append("**Recommendations**")
            for i in medium_priority:
                lines.append(f"• {i.title}")
            lines.append("")
        
        # Actions
        lines.append("**Actions**")
        for idx, i in enumerate(insights[:5], 1):
            lines.append(f"{idx}. {i.title}")
        
        lines.append("")
        lines.append("Reply with number to action, or 'dismiss' to acknowledge.")
        
        return "\n".join(lines)
    
    def preview_report(self) -> str:
        """
        Generate a preview report (doesn't mark as reported).
        
        Returns:
            Formatted report string
        """
        # Get pending or generate new
        insights = self.get_pending_insights()
        if not insights:
            insights = self.run_full_scan()
        
        return self.generate_report(insights)
    
    # =========================================================================
    # INSIGHT MANAGEMENT
    # =========================================================================
    
    def get_pending_insights(self) -> List[MaintenanceInsight]:
        """Get all pending (unreported) insights."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM maintenance_insights
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
            """).fetchall()
            return [MaintenanceInsight.from_row(row) for row in rows]
    
    def get_all_insights(self, limit: int = 50) -> List[MaintenanceInsight]:
        """Get all insights, sorted by recency."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM maintenance_insights
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [MaintenanceInsight.from_row(row) for row in rows]
    
    def mark_reported(self, insight_ids: List[int]):
        """Mark insights as reported to user."""
        with get_db() as conn:
            conn.executemany("""
                UPDATE maintenance_insights
                SET status = 'reported', reported_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [(id,) for id in insight_ids])
    
    def mark_actioned(self, insight_id: int):
        """Mark an insight as actioned by user."""
        with get_db() as conn:
            conn.execute("""
                UPDATE maintenance_insights
                SET status = 'actioned', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (insight_id,))
    
    def mark_dismissed(self, insight_id: int):
        """Mark an insight as dismissed by user."""
        with get_db() as conn:
            conn.execute("""
                UPDATE maintenance_insights
                SET status = 'dismissed', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (insight_id,))
    
    def _create_insight(self, insight_type: str, source: str, title: str,
                       details: dict, priority: int) -> MaintenanceInsight:
        """Create and save an insight to the database."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO maintenance_insights 
                (insight_type, source, title, details, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (insight_type, source, title, json.dumps(details), priority))
            insight_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        return MaintenanceInsight(
            id=insight_id,
            insight_type=insight_type,
            source=source,
            title=title,
            details=details,
            priority=priority,
            status="pending",
            created_at=datetime.now(),
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_scanner_instance: Optional[MaintenanceScanner] = None


def get_scanner() -> MaintenanceScanner:
    """Get the global maintenance scanner instance."""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = MaintenanceScanner()
    return _scanner_instance


def run_maintenance_scan(scan_type: str = "full") -> List[MaintenanceInsight]:
    """
    Run a maintenance scan.
    
    Args:
        scan_type: 'models', 'queue', 'projects', 'butler', or 'full'
        
    Returns:
        List of generated insights
    """
    scanner = get_scanner()
    
    if scan_type == "models":
        return scanner.scan_models()
    elif scan_type == "queue":
        return scanner.scan_queue_health()
    elif scan_type == "projects":
        return scanner.scan_project_suggestions()
    elif scan_type == "butler":
        return scanner.scan_butler_budget()
    else:
        return scanner.run_full_scan()


def preview_maintenance_report() -> str:
    """Generate a preview of the maintenance report."""
    return get_scanner().preview_report()


def get_maintenance_summary() -> dict:
    """Get a quick summary of maintenance status."""
    scanner = get_scanner()
    pending = scanner.get_pending_insights()
    
    return {
        "pending_insights": len(pending),
        "high_priority": len([i for i in pending if i.priority >= 4]),
        "last_scan": None,  # TODO: Track last scan time in config
    }
