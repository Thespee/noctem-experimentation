"""
Skill Executor - Execute skills with logging, approval flow, and stats tracking.

Execution stages:
1. trigger → detected skill match
2. load → loaded full instructions
3. approve → (if required) approval granted
4. execute → skill running
5. complete → success/failure
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from noctem.db import get_db
from noctem.models import Skill, SkillExecution
from noctem.skills.loader import SkillLoader
from noctem.skills.registry import SkillRegistry


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""
    pass


class SkillApprovalRequired(Exception):
    """Raised when skill requires user approval before execution."""
    def __init__(self, skill_name: str, execution_id: int, message: str = None):
        self.skill_name = skill_name
        self.execution_id = execution_id
        self.message = message or f"Skill '{skill_name}' requires approval before execution"
        super().__init__(self.message)


class SkillExecutor:
    """
    Executes skills with full logging and approval workflow.
    
    Usage:
        executor = SkillExecutor(registry)
        
        # Execute a skill (may raise SkillApprovalRequired)
        try:
            execution = executor.execute_skill(
                "my-skill",
                context={"input": "user input"},
                trigger_type="pattern_match",
                trigger_confidence=0.85
            )
        except SkillApprovalRequired as e:
            # Handle approval flow
            print(f"Approval needed for execution {e.execution_id}")
    """
    
    def __init__(self, registry: SkillRegistry):
        """
        Initialize executor with a skill registry.
        
        Args:
            registry: SkillRegistry for skill lookups and stats
        """
        self.registry = registry
        self.loader = SkillLoader()
    
    def execute_skill(
        self,
        skill_name: str,
        context: dict = None,
        trigger_type: str = "explicit",
        trigger_input: str = None,
        trigger_confidence: float = 1.0,
        approval_callback: Optional[Callable[[SkillExecution], bool]] = None,
    ) -> SkillExecution:
        """
        Execute a skill with full logging and approval flow.
        
        Args:
            skill_name: Name of the skill to execute
            context: Execution context (input, source, etc.)
            trigger_type: 'explicit' or 'pattern_match'
            trigger_input: The input that triggered the skill
            trigger_confidence: Confidence score (0.0-1.0)
            approval_callback: Optional sync callback for approval
                              (return True to approve, False to reject)
        
        Returns:
            SkillExecution record with results
            
        Raises:
            SkillExecutionError: If skill not found or execution fails
            SkillApprovalRequired: If skill needs approval and no callback provided
        """
        context = context or {}
        trace_id = context.get("trace_id") or str(uuid.uuid4())
        
        # Get skill
        skill = self.registry.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")
        
        if not skill.enabled:
            raise ValueError(f"Skill '{skill_name}' is disabled")
        
        # Create execution record
        execution_id = self._create_execution_record(
            skill=skill,
            trace_id=trace_id,
            trigger_type=trigger_type,
            trigger_input=trigger_input,
            trigger_confidence=trigger_confidence,
        )
        
        # Log trigger stage
        self._log_stage(trace_id, "trigger", skill.id, {
            "skill_name": skill_name,
            "trigger_type": trigger_type,
            "trigger_confidence": trigger_confidence,
        })
        
        # Check if approval is required
        if skill.requires_approval:
            self._update_execution_status(execution_id, "pending")
            
            if approval_callback:
                # Sync approval
                execution = self._get_execution(execution_id)
                approved = approval_callback(execution)
                
                if approved:
                    self._approve_execution(execution_id, approved_by="user")
                else:
                    self._reject_execution(execution_id)
                    return self._get_execution(execution_id)
            else:
                # Async approval needed - raise exception
                raise SkillApprovalRequired(skill_name, execution_id)
        else:
            # Auto-approve
            self._approve_execution(execution_id, approved_by="auto")
        
        # Load instructions
        self._log_stage(trace_id, "load", skill.id, {"skill_path": skill.skill_path})
        
        try:
            skill_path = Path(skill.skill_path)
            metadata = self.loader.parse_skill_yaml(skill_path)
            instructions = self.loader.load_instructions(metadata, skill_path)
        except Exception as e:
            self._fail_execution(execution_id, str(e))
            self.registry.update_skill_stats(skill_name, success=False)
            raise SkillExecutionError(f"Failed to load skill instructions: {e}")
        
        # Execute
        self._update_execution_status(execution_id, "running")
        self._log_stage(trace_id, "execute", skill.id, {
            "instructions_length": len(instructions),
        })
        
        try:
            # v0.9.1: Resolve {{wiki:query}} placeholders in instructions
            instructions, wiki_context = self._resolve_wiki_placeholders(instructions)
            if wiki_context:
                context["wiki_context"] = wiki_context
            
            # For now, execution just returns the instructions
            # Future: could invoke LLM with instructions, run scripts, etc.
            result = {
                "instructions": instructions,
                "skill_name": skill_name,
                "skill_version": skill.version,
                "context": context,
            }
            
            # Complete successfully
            self._complete_execution(execution_id, output_summary=f"Loaded {len(instructions)} chars of instructions")
            self.registry.update_skill_stats(skill_name, success=True)
            
            self._log_stage(trace_id, "complete", skill.id, {
                "status": "success",
                "instructions_length": len(instructions),
            })
            
            return self._get_execution(execution_id)
            
        except Exception as e:
            self._fail_execution(execution_id, str(e))
            self.registry.update_skill_stats(skill_name, success=False)
            
            self._log_stage(trace_id, "complete", skill.id, {
                "status": "failure",
                "error": str(e),
            })
            
            raise SkillExecutionError(f"Skill execution failed: {e}")
    
    def approve_pending_execution(self, execution_id: int, approved_by: str = "user") -> SkillExecution:
        """
        Approve a pending execution and continue execution.
        
        Args:
            execution_id: ID of the pending execution
            approved_by: Who approved ('user' or 'auto')
            
        Returns:
            Completed SkillExecution record
        """
        execution = self._get_execution(execution_id)
        if not execution:
            raise SkillExecutionError(f"Execution not found: {execution_id}")
        
        if execution.status != "pending":
            raise SkillExecutionError(f"Execution is not pending: {execution.status}")
        
        # Get skill and continue execution
        skill = self.registry.get_skill_by_id(execution.skill_id) if hasattr(self.registry, 'get_skill_by_id') else None
        if not skill:
            # Fallback: query by skill_id
            with get_db() as conn:
                row = conn.execute("SELECT * FROM skills WHERE id = ?", (execution.skill_id,)).fetchone()
                if row:
                    skill = Skill.from_row(row)
        
        if not skill:
            raise SkillExecutionError(f"Skill not found for execution {execution_id}")
        
        # Mark as approved
        self._approve_execution(execution_id, approved_by)
        
        # Continue with the approved execution (don't create new one)
        # Load instructions
        trace_id = execution.trace_id
        self._log_stage(trace_id, "load", skill.id, {"skill_path": skill.skill_path})
        
        try:
            skill_path = Path(skill.skill_path)
            metadata = self.loader.parse_skill_yaml(skill_path)
            instructions = self.loader.load_instructions(metadata, skill_path)
        except Exception as e:
            self._fail_execution(execution_id, str(e))
            self.registry.update_skill_stats(skill.name, success=False)
            raise SkillExecutionError(f"Failed to load skill instructions: {e}")
        
        # Execute
        self._update_execution_status(execution_id, "running")
        self._log_stage(trace_id, "execute", skill.id, {"instructions_length": len(instructions)})
        
        # Complete successfully
        self._complete_execution(execution_id, output_summary=f"Loaded {len(instructions)} chars of instructions")
        self.registry.update_skill_stats(skill.name, success=True)
        
        self._log_stage(trace_id, "complete", skill.id, {"status": "success"})
        
        return self._get_execution(execution_id)
    
    def reject_pending_execution(self, execution_id: int) -> SkillExecution:
        """
        Reject a pending execution.
        
        Args:
            execution_id: ID of the pending execution
            
        Returns:
            Rejected SkillExecution record
        """
        self._reject_execution(execution_id)
        return self._get_execution(execution_id)
    
    def get_pending_approvals(self) -> list[SkillExecution]:
        """Get all executions waiting for approval."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT e.*, s.name as skill_name
                FROM skill_executions e
                LEFT JOIN skills s ON e.skill_id = s.id
                WHERE e.status = 'pending'
                ORDER BY e.created_at
            """).fetchall()
            return [SkillExecution.from_row(row) for row in rows]
    
    # === Private methods ===
    
    def _create_execution_record(
        self,
        skill: Skill,
        trace_id: str,
        trigger_type: str,
        trigger_input: str,
        trigger_confidence: float,
    ) -> int:
        """Create a new execution record in the database."""
        now = datetime.now().isoformat()
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO skill_executions (
                    skill_id, trace_id, trigger_type, trigger_input,
                    trigger_confidence, skill_version, status,
                    approval_required, started_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """, (
                skill.id,
                trace_id,
                trigger_type,
                trigger_input,
                trigger_confidence,
                skill.version,
                1 if skill.requires_approval else 0,
                now,
                now,
            ))
            return cursor.lastrowid
    
    def _get_execution(self, execution_id: int) -> Optional[SkillExecution]:
        """Get an execution record by ID with skill_name."""
        with get_db() as conn:
            row = conn.execute("""
                SELECT e.*, s.name as skill_name
                FROM skill_executions e
                LEFT JOIN skills s ON e.skill_id = s.id
                WHERE e.id = ?
            """, (execution_id,)).fetchone()
            
            if row:
                return SkillExecution.from_row(row)
            return None
    
    def _update_execution_status(self, execution_id: int, status: str):
        """Update execution status."""
        with get_db() as conn:
            conn.execute(
                "UPDATE skill_executions SET status = ? WHERE id = ?",
                (status, execution_id)
            )
    
    def _approve_execution(self, execution_id: int, approved_by: str):
        """Mark execution as approved."""
        with get_db() as conn:
            conn.execute("""
                UPDATE skill_executions SET
                    status = 'approved',
                    approved_by = ?,
                    approved_at = ?
                WHERE id = ?
            """, (approved_by, datetime.now().isoformat(), execution_id))
    
    def _reject_execution(self, execution_id: int):
        """Mark execution as rejected."""
        with get_db() as conn:
            conn.execute("""
                UPDATE skill_executions SET
                    status = 'rejected',
                    completed_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), execution_id))
    
    def _complete_execution(self, execution_id: int, output_summary: str = None):
        """Mark execution as successfully completed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE skill_executions SET
                    status = 'completed',
                    output_summary = ?,
                    completed_at = ?
                WHERE id = ?
            """, (output_summary, datetime.now().isoformat(), execution_id))
    
    def _fail_execution(self, execution_id: int, error_message: str):
        """Mark execution as failed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE skill_executions SET
                    status = 'failure',
                    error_message = ?,
                    completed_at = ?
                WHERE id = ?
            """, (error_message, datetime.now().isoformat(), execution_id))
    
    # v0.9.1: Wiki Bridge
    WIKI_PLACEHOLDER_RE = re.compile(r'\{\{wiki:(.+?)\}\}')
    
    def _resolve_wiki_placeholders(self, instructions: str) -> tuple:
        """
        Scan instructions for {{wiki:query}} placeholders and replace them
        with wiki search results.
        
        Returns:
            Tuple of (resolved_instructions, wiki_context_list)
            wiki_context_list is a list of dicts with query + results.
        """
        wiki_context = []
        matches = list(self.WIKI_PLACEHOLDER_RE.finditer(instructions))
        
        if not matches:
            return instructions, wiki_context
        
        resolved = instructions
        for match in reversed(matches):  # reverse to preserve positions
            query = match.group(1).strip()
            try:
                from noctem.wiki.retrieval import get_context_for_query
                context_text, results = get_context_for_query(query, n_chunks=3)
                
                if context_text:
                    replacement = f"[Wiki context for '{query}']:\n{context_text}"
                    wiki_context.append({
                        "query": query,
                        "results_count": len(results),
                        "context_preview": context_text[:200],
                    })
                else:
                    replacement = f"[No wiki results for '{query}']"
                    wiki_context.append({
                        "query": query,
                        "results_count": 0,
                        "context_preview": None,
                    })
            except Exception as e:
                replacement = f"[Wiki lookup failed for '{query}': {e}]"
                wiki_context.append({
                    "query": query,
                    "results_count": 0,
                    "error": str(e),
                })
            
            resolved = resolved[:match.start()] + replacement + resolved[match.end():]
        
        return resolved, wiki_context
    
    def _log_stage(self, trace_id: str, stage: str, skill_id: int, data: dict):
        """Log execution stage to execution_logs table."""
        import json
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO execution_logs (
                    trace_id, timestamp, stage, component,
                    input_data, metadata
                ) VALUES (?, ?, ?, 'skill', ?, ?)
            """, (
                trace_id,
                datetime.now().isoformat(),
                stage,
                json.dumps(data),
                json.dumps({"skill_id": skill_id}),
            ))
