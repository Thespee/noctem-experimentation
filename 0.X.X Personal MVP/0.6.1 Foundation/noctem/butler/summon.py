"""
Butler Summon Command for Noctem v0.6.1.

The /summon command bypasses fast-mode interpretation and sends a message
directly to the slow system (Butler) for immediate handling.

This is the "human correction loop" - when the user needs to:
- Override a fast-mode decision
- Get slow-mode analysis immediately
- Execute a correction or clarification
- Query system state directly
"""
import json
import logging
from datetime import datetime
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from ..db import get_db
from ..config import Config
from ..logging.execution_logger import ExecutionLogger
from ..services import task_service, project_service
from ..fast.capture import get_thought, get_pending_ambiguous_thoughts

logger = logging.getLogger(__name__)

# Timeout for slow-mode processing (seconds)
SUMMON_TIMEOUT = 30


def handle_summon(message: str, source: str = "cli") -> Tuple[str, dict]:
    """
    Handle a /summon command.
    
    Bypasses fast-mode classification and routes directly to slow processing.
    Has a 30-second timeout; if exceeded, queues for next slow cycle.
    
    Args:
        message: The user's message (after /summon prefix removed)
        source: Input source ('cli', 'telegram', 'web')
        
    Returns:
        Tuple of (response_text, metadata_dict)
    """
    message = message.strip()
    
    # Start execution trace
    with ExecutionLogger(component="summon", source=source) as trace:
        trace.log_stage("input", input_data={
            "message": message,
            "source": source,
        })
        
        # Parse summon intent
        intent, parsed = _parse_summon_intent(message)
        trace.log_stage("parse", output_data={
            "intent": intent,
            "parsed": parsed,
        })
        
        # Handle different intents
        if intent == "status":
            response = _handle_status_query(parsed)
        elif intent == "correct":
            response = _handle_correction(parsed, trace)
        elif intent == "query":
            response = _handle_query(parsed)
        elif intent == "help":
            response = _get_summon_help()
        else:
            # General summon - try to process with slow mode
            response = _handle_general_summon(message, trace)
        
        trace.log_stage("complete", output_data={
            "intent": intent,
            "response_length": len(response),
        })
        
        return response, {
            "trace_id": trace.trace_id,
            "intent": intent,
            "parsed": parsed,
        }


def _parse_summon_intent(message: str) -> Tuple[str, dict]:
    """
    Parse the intent from a summon message.
    
    Supported intents:
    - status: Query system status ("status", "how are you", etc.)
    - correct <id>: Correct a previous thought/task
    - query <what>: Query system state
    - help: Show summon help
    - general: Anything else
    """
    message_lower = message.lower().strip()
    
    # Help intent
    if message_lower in ("help", "?", "commands"):
        return "help", {}
    
    # Status queries
    status_keywords = ["status", "how are you", "health", "state", "overview"]
    if any(kw in message_lower for kw in status_keywords):
        return "status", {"query": message}
    
    # Correction intent
    if message_lower.startswith("correct ") or message_lower.startswith("fix "):
        parts = message.split(maxsplit=1)
        target = parts[1] if len(parts) > 1 else ""
        return "correct", {"target": target}
    
    # Query intent
    query_starters = ["what", "show", "list", "get", "find", "where"]
    if any(message_lower.startswith(q) for q in query_starters):
        return "query", {"query": message}
    
    # General intent
    return "general", {"message": message}


def _handle_status_query(parsed: dict) -> str:
    """Handle status query intent."""
    from ..butler.protocol import get_butler_status
    from ..slow.loop import get_slow_mode_status
    
    butler = get_butler_status()
    slow = get_slow_mode_status()
    
    lines = [
        "🤖 **Noctem Status**",
        "",
        f"**Butler**: {butler['remaining']}/{butler['budget']} contacts remaining this week",
        f"**Slow Mode**: {'Active' if slow['enabled'] else 'Disabled'}",
        f"  • Queue: {slow['queue']['pending']} pending, {slow['queue']['completed']} completed",
        f"  • User idle: {'Yes' if slow['user_idle'] else 'No'} ({slow['minutes_since_activity']} min)",
    ]
    
    # Add pending clarifications
    pending = get_pending_ambiguous_thoughts()
    if pending:
        lines.append(f"**Pending clarifications**: {len(pending)}")
    
    # Add recent activity
    from ..logging.execution_logger import get_execution_stats
    stats = get_execution_stats(hours=24)
    if stats["trace_count"] > 0:
        lines.append(f"**24h activity**: {stats['trace_count']} traces, avg {stats['avg_duration_ms']}ms")
    
    return "\n".join(lines)


def _handle_correction(parsed: dict, trace: ExecutionLogger) -> str:
    """Handle correction intent."""
    target = parsed.get("target", "").strip()
    
    if not target:
        return ("❌ Please specify what to correct.\n"
                "Examples:\n"
                "  `/summon correct thought 123`\n"
                "  `/summon correct last task`")
    
    # Try to parse target
    parts = target.lower().split()
    
    if "thought" in parts:
        # Correct a thought
        try:
            idx = parts.index("thought")
            thought_id = int(parts[idx + 1]) if idx + 1 < len(parts) else None
            if thought_id:
                return _correct_thought(thought_id, trace)
        except (ValueError, IndexError):
            pass
        return "❌ Could not parse thought ID. Use: `/summon correct thought <id>`"
    
    if "last" in parts:
        # Correct last item
        pending = get_pending_ambiguous_thoughts()
        if pending:
            return _correct_thought(pending[0].id, trace)
        return "No pending thoughts to correct."
    
    return f"❌ Don't know how to correct: {target}"


def _correct_thought(thought_id: int, trace: ExecutionLogger) -> str:
    """Show options to correct a specific thought."""
    thought = get_thought(thought_id)
    if not thought:
        return f"❌ Thought #{thought_id} not found."
    
    trace.set_thought_id(thought_id)
    
    lines = [
        f"📝 **Thought #{thought_id}**",
        f"Text: \"{thought.raw_text}\"",
        f"Kind: {thought.kind or 'unknown'}",
        f"Status: {thought.status}",
        "",
        "**Options:**",
        "• Reply `task` to create as task",
        "• Reply `note` to keep as note",
        "• Reply `dismiss` to discard",
        "• Reply with new text to reinterpret",
    ]
    
    return "\n".join(lines)


def _handle_query(parsed: dict) -> str:
    """Handle query intent."""
    query = parsed.get("query", "").lower()
    
    if "task" in query:
        # List tasks
        tasks = task_service.get_priority_tasks(max_count=5)
        if not tasks:
            return "No pending tasks."
        lines = ["**Top 5 Tasks:**"]
        for i, t in enumerate(tasks, 1):
            due = f" (due {t.due_date})" if t.due_date else ""
            lines.append(f"{i}. {t.name}{due}")
        return "\n".join(lines)
    
    if "project" in query:
        # List projects
        projects = project_service.get_active_projects()
        if not projects:
            return "No active projects."
        lines = ["**Active Projects:**"]
        for p in projects:
            lines.append(f"• {p.name}")
        return "\n".join(lines)
    
    if "thought" in query or "pending" in query or "ambiguous" in query:
        # List pending thoughts
        pending = get_pending_ambiguous_thoughts()
        if not pending:
            return "No pending thoughts needing clarification."
        lines = ["**Pending Thoughts:**"]
        for t in pending[:5]:
            lines.append(f"• #{t.id}: \"{t.raw_text[:40]}...\" ({t.ambiguity_reason or 'unclear'})")
        return "\n".join(lines)
    
    return (f"❓ I can help you query:\n"
            f"• `tasks` - Show top tasks\n"
            f"• `projects` - Show active projects\n"
            f"• `thoughts` / `pending` - Show pending clarifications")


def _handle_general_summon(message: str, trace: ExecutionLogger) -> str:
    """
    Handle a general summon message.
    
    Try to process immediately with slow mode (with timeout).
    If timeout, queue for later.
    """
    from ..slow.ollama import OllamaClient, GracefulDegradation
    
    # Check if slow mode available
    if not GracefulDegradation.can_run_slow_mode():
        return ("⏳ Slow mode unavailable (Ollama not running).\n"
                "Your message has been noted. Try `/summon status` for system state.")
    
    # Try to process with timeout
    client = OllamaClient()
    
    try:
        # Use thread pool for timeout support
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_slow_process_message, message, client)
            result = future.result(timeout=SUMMON_TIMEOUT)
            trace.log_stage("slow_process", output_data={"result": result[:100]})
            return result
    except FuturesTimeoutError:
        trace.log_stage("timeout", metadata={"timeout_seconds": SUMMON_TIMEOUT})
        # Queue for later
        _queue_summon_for_later(message)
        return (f"⏱️ Processing timed out after {SUMMON_TIMEOUT}s.\n"
                f"Your message has been queued for the next slow cycle.")
    except Exception as e:
        trace.log_error(str(e))
        logger.error(f"Summon processing error: {e}")
        return f"❌ Error processing summon: {e}"


def _slow_process_message(message: str, client) -> str:
    """Process a message with the slow LLM."""
    system_prompt = """You are Noctem's Butler, a helpful assistant for task and project management.
The user has summoned you directly with a message. Help them with whatever they need.
Be concise and actionable. If you're unsure, ask clarifying questions."""
    
    response = client.generate(message, system=system_prompt, temperature=0.7)
    
    if response:
        return f"🎩 **Butler says:**\n\n{response}"
    else:
        return "❌ Failed to generate response from slow mode."


def _queue_summon_for_later(message: str):
    """Queue a summon message for later processing."""
    # Create a thought with summon_mode flag
    with get_db() as conn:
        conn.execute("""
            INSERT INTO thoughts (source, raw_text, kind, status, summon_mode)
            VALUES ('summon', ?, 'ambiguous', 'pending', 1)
        """, (message,))
    logger.info(f"Queued summon message for later: {message[:50]}...")


def _get_summon_help() -> str:
    """Return summon command help."""
    return """🎩 **Summon Commands**

`/summon` bypasses fast-mode and talks directly to the Butler.

**Status & Queries:**
• `/summon status` - System overview
• `/summon what tasks` - List top tasks
• `/summon what projects` - List projects
• `/summon what pending` - List pending clarifications

**Corrections:**
• `/summon correct thought <id>` - Correct a specific thought
• `/summon correct last` - Correct most recent pending item

**General:**
• `/summon <message>` - Send anything to the Butler directly

The Butler will respond within 30 seconds or queue for later."""


def create_summon_thought(message: str, source: str = "cli") -> int:
    """
    Create a thought record marked as summon_mode.
    
    Returns:
        The thought ID
    """
    with get_db() as conn:
        conn.execute("""
            INSERT INTO thoughts (source, raw_text, kind, status, summon_mode)
            VALUES (?, ?, 'ambiguous', 'pending', 1)
        """, (source, message))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_pending_summon_thoughts() -> list:
    """Get all pending thoughts marked as summon_mode."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM thoughts
            WHERE summon_mode = 1 AND status = 'pending'
            ORDER BY created_at DESC
        """).fetchall()
        from ..models import Thought
        return [Thought.from_row(row) for row in rows]
