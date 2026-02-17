"""
Slow Mode Loop for Noctem v0.6.0.

Background thread that processes the slow work queue when user is idle.
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from ..config import Config
from ..db import get_db
from .ollama import GracefulDegradation
from .queue import SlowWorkQueue, WorkType
from .task_analyzer import analyze_and_save as analyze_task, get_tasks_needing_analysis
from .project_analyzer import analyze_and_save as analyze_project, get_projects_needing_analysis
from ..services import task_service, project_service
from ..voice.journals import (
    get_pending_journals, mark_transcribing, complete_transcription, fail_transcription
)
from ..fast.capture import process_voice_transcription

logger = logging.getLogger(__name__)

# Global state for tracking user activity
_last_user_activity = datetime.now()
_loop_instance: Optional['SlowModeLoop'] = None


def record_user_activity():
    """Call this whenever user sends a message to reset idle timer."""
    global _last_user_activity
    _last_user_activity = datetime.now()


def get_last_activity() -> datetime:
    """Get timestamp of last user activity."""
    return _last_user_activity


class SlowModeLoop:
    """
    Background loop that processes slow work when user is idle.
    
    Runs in a separate thread, checking every minute:
    1. Is user idle (no messages in X minutes)?
    2. Is LLM available?
    3. Is there work to do?
    
    If all yes, process one item from the queue.
    """
    
    def __init__(self, check_interval: int = 60):
        """
        Args:
            check_interval: How often to check for work (seconds)
        """
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the background loop."""
        if self._running:
            logger.warning("Slow mode loop already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Slow mode loop started")
    
    def stop(self):
        """Stop the background loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Slow mode loop stopped")
    
    def _run(self):
        """Main loop."""
        while self._running:
            try:
                self._check_and_process()
            except Exception as e:
                logger.error(f"Error in slow mode loop: {e}")
            
            time.sleep(self.check_interval)
    
    def _check_and_process(self):
        """Check conditions and process work if appropriate."""
        # Check if slow mode is enabled
        if not Config.get("slow_mode_enabled", True):
            return
        
        # Check if user is idle
        if not self._user_is_idle():
            logger.debug("User not idle, skipping slow mode processing")
            return
        
        # Voice transcription doesn't need LLM - process even if Ollama unavailable
        self._process_voice_transcriptions()
        
        # Check if LLM is available for other work
        if not GracefulDegradation.can_run_slow_mode():
            logger.debug("LLM unavailable, skipping LLM-based processing")
            return
        
        # Queue new work if needed
        self._queue_pending_work()
        
        # Process one item
        self._process_one_item()
    
    def _user_is_idle(self) -> bool:
        """Check if user hasn't sent messages recently."""
        idle_minutes = Config.get("slow_idle_minutes", 5)
        idle_threshold = timedelta(minutes=idle_minutes)
        
        time_since_activity = datetime.now() - _last_user_activity
        return time_since_activity >= idle_threshold
    
    def _queue_pending_work(self):
        """Check for tasks/projects that need analysis and queue them."""
        # Queue tasks needing analysis
        tasks = get_tasks_needing_analysis(limit=5)
        for task in tasks:
            SlowWorkQueue.queue_task_analysis(task.id)
        
        # Queue projects needing analysis
        projects = get_projects_needing_analysis(limit=3)
        for project in projects:
            SlowWorkQueue.queue_project_analysis(project.id)
    
    def _process_one_item(self) -> bool:
        """Process one item from the queue. Returns True if item processed."""
        item = SlowWorkQueue.get_next_item()
        if not item:
            return False
        
        logger.info(f"Processing slow work item {item.id}: {item.work_type}")
        SlowWorkQueue.mark_processing(item.id)
        
        try:
            if item.work_type == WorkType.TASK_COMPUTER_HELP.value:
                task = task_service.get_task(item.target_id)
                if task:
                    success = analyze_task(task)
                    if success:
                        SlowWorkQueue.mark_completed(item.id, "Task analyzed")
                    else:
                        SlowWorkQueue.mark_failed(item.id, "Analysis failed")
                else:
                    SlowWorkQueue.mark_failed(item.id, "Task not found")
            
            elif item.work_type == WorkType.PROJECT_NEXT_ACTION.value:
                project = project_service.get_project(item.target_id)
                if project:
                    success = analyze_project(project)
                    if success:
                        SlowWorkQueue.mark_completed(item.id, "Project analyzed")
                    else:
                        SlowWorkQueue.mark_failed(item.id, "Analysis failed")
                else:
                    SlowWorkQueue.mark_failed(item.id, "Project not found")
            
            else:
                SlowWorkQueue.mark_failed(item.id, f"Unknown work type: {item.work_type}")
                
        except Exception as e:
            logger.error(f"Error processing item {item.id}: {e}")
            SlowWorkQueue.mark_failed(item.id, str(e))
        
        return True
    
    def _process_voice_transcriptions(self, max_items: int = 1) -> int:
        """
        Process pending voice journal transcriptions.
        Uses Whisper (local, no LLM needed).
        After transcription, routes through capture system for task creation.
        Returns count of items processed.
        """
        pending = get_pending_journals()
        if not pending:
            return 0
        
        # Lazy import to avoid loading Whisper unless needed
        from .whisper import get_whisper_service
        
        count = 0
        for journal in pending[:max_items]:
            journal_id = journal["id"]
            audio_path = journal["audio_path"]
            
            logger.info(f"Transcribing voice journal {journal_id}: {audio_path}")
            mark_transcribing(journal_id)
            
            try:
                whisper = get_whisper_service()
                text, metadata = whisper.transcribe(audio_path)
                
                # Complete the transcription record
                complete_transcription(
                    journal_id,
                    transcription=text,
                    duration_seconds=metadata.get("duration"),
                    language=metadata.get("language"),
                )
                
                # Route through capture system (voice → task pipeline)
                if text and text.strip():
                    capture_result = process_voice_transcription(text, journal_id)
                    logger.info(
                        f"Voice journal {journal_id} processed: "
                        f"kind={capture_result.kind.value}, "
                        f"confidence={capture_result.confidence:.2f}, "
                        f"task_id={capture_result.task.id if capture_result.task else None}"
                    )
                
                count += 1
                logger.info(f"Voice journal {journal_id} transcribed and routed successfully")
                
            except Exception as e:
                logger.error(f"Failed to transcribe voice journal {journal_id}: {e}")
                fail_transcription(journal_id, str(e))
        
        return count
    
    def process_queue_once(self, max_items: int = 5) -> int:
        """Process queue manually (for CLI). Returns count of items processed."""
        # Process voice transcriptions first
        voice_count = self._process_voice_transcriptions(max_items=3)
        
        # Queue any pending work
        self._queue_pending_work()
        
        count = voice_count
        for _ in range(max_items - voice_count):
            if self._process_one_item():
                count += 1
            else:
                break  # No more items
        return count


def get_slow_mode_status() -> dict:
    """Get current slow mode status."""
    queue_status = SlowWorkQueue.get_queue_status()
    system_status = GracefulDegradation.get_system_status()
    
    idle_minutes = Config.get("slow_idle_minutes", 5)
    time_since_activity = datetime.now() - _last_user_activity
    user_idle = time_since_activity >= timedelta(minutes=idle_minutes)
    
    return {
        "enabled": Config.get("slow_mode_enabled", True),
        "system_status": system_status,
        "can_run": GracefulDegradation.can_run_slow_mode(),
        "user_idle": user_idle,
        "minutes_since_activity": int(time_since_activity.total_seconds() / 60),
        "queue": queue_status,
    }


def get_slow_mode_status_message() -> str:
    """Get human-readable slow mode status."""
    status = get_slow_mode_status()
    
    lines = [
        "🐢 **Slow Mode Status**",
        "",
        GracefulDegradation.get_status_message(),
        "",
    ]
    
    if status["enabled"]:
        lines.append(f"Queue: {status['queue']['pending']} pending, {status['queue']['completed']} completed")
        
        if status["user_idle"]:
            lines.append(f"User idle ({status['minutes_since_activity']} min) - processing enabled")
        else:
            lines.append(f"User active ({status['minutes_since_activity']} min ago) - waiting")
    else:
        lines.append("Slow mode is disabled")
    
    return "\n".join(lines)


def start_slow_mode():
    """Start the slow mode loop."""
    global _loop_instance
    
    if _loop_instance is not None:
        logger.warning("Slow mode already started")
        return
    
    _loop_instance = SlowModeLoop()
    _loop_instance.start()


def stop_slow_mode():
    """Stop the slow mode loop."""
    global _loop_instance
    
    if _loop_instance:
        _loop_instance.stop()
        _loop_instance = None
