"""Model-first chat orchestration with deterministic execution safeguards."""
import json
import logging
import re
import threading
import time
from typing import Any, Callable

import requests

from ..config import Config
from ..db import get_db
from ..parser.command import CommandType, parse_command
from ..services.conversation_service import (
    get_thread_context,
    record_message,
    resolve_thread_id,
)
from .memory_pack import assemble_memory_pack
from .router import IntentType, classify_intent
from .workflow import submit_input, resume_workflow

logger = logging.getLogger(__name__)

_DETAIL_HINT_RE = re.compile(
    r"\b(explain|details?|walk\s+me\s+through|expand|longer|in[\s-]?depth|step[\s-]?by[\s-]?step)\b",
    re.IGNORECASE,
)
_SPLIT_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_TASK_QUERY_HINT_RE = re.compile(
    r"\b(task|tasks|today|due|overdue|inbox|unassigned|schedule|calendar)\b",
    re.IGNORECASE,
)
_DEFAULT_FALLBACK_REPLY = "✓ Done."
_APPROVAL_REPLY_RE = re.compile(
    r"^(?:y|yes|yep|yeah|ok|okay|confirm|confirmed|proceed|sure|n|no|nope|cancel|stop|abort)\b",
    re.IGNORECASE,
)
_MODEL_PROGRESS_HEARTBEAT_SECONDS = 5.0


def _emit_model_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(payload)
    except Exception as exc:
        logger.debug("Model progress callback failed: %s", exc)


def _wants_detailed_reply(text: str) -> bool:
    return bool(_DETAIL_HINT_RE.search(text or ""))


def _enforce_brief_reply(text: str, *, allow_long: bool) -> str:
    raw = (text or "").strip()
    if not raw:
        return _DEFAULT_FALLBACK_REPLY
    if allow_long or not Config.chat_brief_mode():
        return raw

    compact = " ".join(raw.split())
    if len(compact) <= 220:
        return compact

    parts = _SPLIT_SENTENCE_RE.split(compact)
    shortlist = " ".join(parts[:2]).strip() if parts else compact
    if not shortlist:
        shortlist = compact
    if len(shortlist) > 220:
        shortlist = shortlist[:217].rstrip() + "..."
    return shortlist


def _normalize_fast_path_input(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    parts = cleaned.split(maxsplit=1)
    head = parts[0].lower()
    tail = parts[1] if len(parts) > 1 else ""

    if head == "d" and tail:
        return f"done {tail}".strip()
    if head == "s" and tail:
        return f"skip {tail}".strip()
    if head == "t" and tail:
        return tail.strip()
    return cleaned


def _resolve_mode(message: str) -> tuple[str, str]:
    """
    Returns:
        (mode, text)
        mode in {"fast", "model"}
    """
    if message.startswith(".."):
        # Escape for literal dot-leading model messages.
        return "model", message[1:]
    if message.startswith("."):
        stripped = message[1:]
        if stripped.startswith(" "):
            stripped = stripped[1:]
        return "fast", _normalize_fast_path_input(stripped)
    return "model", message


def _is_fast_path_command(text: str) -> bool:
    parsed = parse_command((text or "").strip())
    return parsed.type != CommandType.NEW_TASK


def _public_workflow_fields(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {}
    keep = (
        "workflow_id",
        "status",
        "interrupt",
        "review",
        "task",
        "updated_count",
        "updated_task_ids",
        "deleted_task_id",
        "today_count",
        "overdue_count",
        "overdue_task_ids",
        "unassigned_count",
        "intent",
        "intent_classifier",
        "intent_confidence",
        "error",
    )
    out = {}
    for key in keep:
        if key in result:
            out[key] = result[key]
    return out


def _is_grounded_task_query(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return bool(_TASK_QUERY_HINT_RE.search(cleaned))


def _looks_like_approval_reply(text: str) -> bool:
    return bool(_APPROVAL_REPLY_RE.match((text or "").strip()))


def _latest_interrupted_workflow(thread_id: str) -> tuple[int, str] | None:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, metadata
            FROM conversations
            WHERE session_id = ? AND role != 'system'
            ORDER BY id DESC
            LIMIT 80
            """,
            (thread_id,),
        ).fetchall()

    saw_latest_user = False
    for row in rows:
        role = str(row["role"] or "").strip().lower()
        if not saw_latest_user:
            if role == "user":
                saw_latest_user = True
            continue
        if role != "assistant":
            continue
        metadata_raw = row["metadata"]
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        if not metadata and isinstance(metadata_raw, str):
            try:
                loaded = json.loads(metadata_raw)
                if isinstance(loaded, dict):
                    metadata = loaded
            except Exception:
                metadata = {}
        workflow_id = metadata.get("workflow_id")
        status = str(metadata.get("status") or "").strip().lower()
        interrupt_payload = metadata.get("interrupt") if isinstance(metadata.get("interrupt"), dict) else {}
        interrupt_type = str(interrupt_payload.get("type") or "").strip().lower()
        if isinstance(workflow_id, int) and status == "interrupted":
            return workflow_id, interrupt_type
        return None
    return None


def _maybe_resume_interrupted_workflow(thread_id: str, resolution_text: str) -> dict | None:
    pending = _latest_interrupted_workflow(thread_id)
    if not pending:
        return None

    workflow_id, interrupt_type = pending
    if interrupt_type == "approve" and not _looks_like_approval_reply(resolution_text):
        return None

    try:
        return resume_workflow(workflow_id, resolution_text)
    except ValueError:
        return None


def _context_block(thread_id: str, limit: int = 20) -> str:
    turns = get_thread_context(thread_id, limit=limit, include_system=False)
    if not turns:
        return "(no prior messages)"

    lines: list[str] = []
    for msg in turns[-16:]:
        role = "User" if msg.role == "user" else "Assistant"
        content = " ".join((msg.content or "").split())
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


def _memory_pack_prompt(user_text: str, memory_pack: dict[str, Any]) -> str:
    token_usage = memory_pack.get("token_usage") or {}
    budget = memory_pack.get("budget") or {}
    sections = memory_pack.get("sections") or {}
    return (
        "Memory pack (deterministic bounded context):\n"
        f"- total_context_budget: {budget.get('total_context')}\n"
        f"- reserved_for_tools_output: {budget.get('reserved_for_tools_and_output')}\n"
        f"- active_memory_budget: {budget.get('active_memory_budget')}\n"
        f"- token_usage_recent_chats: {token_usage.get('recent_chats', 0)}\n"
        f"- token_usage_recent_commits: {token_usage.get('recent_commits', 0)}\n"
        f"- token_usage_context_docs: {token_usage.get('context_docs', 0)}\n"
        f"- token_usage_wiki: {token_usage.get('wiki', 0)}\n\n"
        "Recent chat context:\n"
        f"{sections.get('recent_chats') or '(none)'}\n\n"
        "Recent mutation commits:\n"
        f"{sections.get('recent_commits') or '(none)'}\n\n"
        "Context docs:\n"
        f"{sections.get('context_docs') or '(none)'}\n\n"
        "Wiki context:\n"
        f"{sections.get('wiki') or '(none)'}\n\n"
        "Latest user message:\n"
        f"{user_text}\n"
    )


def _build_model_system_prompt() -> str:
    assistant_name = Config.chat_assistant_name()
    brevity_rule = (
        "Keep replies as brief as possible (ideally one short sentence) unless the user explicitly asks for details."
    )
    return (
        f"You are {assistant_name}, a personal assistant for planning and task execution.\n"
        "You must return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "reply": string,\n'
        '  "requires_action": boolean,\n'
        '  "fast_path_input": string|null,\n'
        '  "clarification_question": string|null,\n'
        '  "memory_update": string|null\n'
        "}\n"
        "Rules:\n"
        "- Set requires_action=true for task operations (create/update/complete/skip/delete/move).\n"
        "- When requires_action=true, set fast_path_input to a concise deterministic command.\n"
        "- For purely conversational replies, set requires_action=false and fast_path_input=null.\n"
        f"- {brevity_rule}\n"
        "- Do not include markdown fences."
    )


def _parse_model_payload(payload: Any) -> dict[str, Any] | None:
    candidate = payload
    if isinstance(candidate, str):
        candidate = candidate.strip()
        if not candidate:
            return None
        candidate = json.loads(candidate)
    if not isinstance(candidate, dict):
        return None

    reply = candidate.get("reply")
    requires_action = bool(candidate.get("requires_action", False))
    fast_path_input = candidate.get("fast_path_input")
    clarification = candidate.get("clarification_question")
    memory_update = candidate.get("memory_update")

    reply_text = str(reply).strip() if isinstance(reply, str) else ""
    fast_text = str(fast_path_input).strip() if isinstance(fast_path_input, str) else None
    clarify_text = str(clarification).strip() if isinstance(clarification, str) else None
    memory_text = str(memory_update).strip() if isinstance(memory_update, str) else None

    if fast_text == "":
        fast_text = None
    if clarify_text == "":
        clarify_text = None
    if memory_text == "":
        memory_text = None

    if fast_text:
        requires_action = True

    return {
        "reply": reply_text,
        "requires_action": requires_action,
        "fast_path_input": fast_text,
        "clarification_question": clarify_text,
        "memory_update": memory_text,
    }


def _call_ollama_model(
    user_text: str,
    thread_id: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    started_at = time.monotonic()
    elapsed_seconds = lambda: round(max(0.0, time.monotonic() - started_at), 3)
    memory_pack = assemble_memory_pack(user_text, thread_id)
    payload_prompt = _memory_pack_prompt(user_text, memory_pack)
    chunk_count = 0
    chars_received = 0
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    _emit_model_progress(
        progress_callback,
        {
            "stage": "started",
            "elapsed_seconds": elapsed_seconds(),
            "model": Config.chat_ollama_model(),
            "thread_id": thread_id,
        },
    )

    def _heartbeat() -> None:
        while not heartbeat_stop.wait(_MODEL_PROGRESS_HEARTBEAT_SECONDS):
            _emit_model_progress(
                progress_callback,
                {
                    "stage": "heartbeat",
                    "elapsed_seconds": elapsed_seconds(),
                    "model": Config.chat_ollama_model(),
                    "thread_id": thread_id,
                    "chunk_count": chunk_count,
                    "chars_received": chars_received,
                },
            )

    heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
    heartbeat_thread.start()
    try:
        response = requests.post(
            f"{Config.chat_ollama_base_url()}/api/generate",
            json={
                "model": Config.chat_ollama_model(),
                "prompt": payload_prompt,
                "system": _build_model_system_prompt(),
                "stream": True,
                "format": "json",
                "options": {"temperature": 0.2},
            },
            stream=True,
        )
        response.raise_for_status()
        parsed: dict[str, Any] | None = None
        iter_lines = getattr(response, "iter_lines", None)
        used_streaming = callable(iter_lines)
        if used_streaming:
            stream_parts: list[str] = []
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = str(raw_line).strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                if not isinstance(chunk, dict):
                    continue
                chunk_text = chunk.get("response")
                if isinstance(chunk_text, str) and chunk_text:
                    stream_parts.append(chunk_text)
                    chunk_count += 1
                    chars_received += len(chunk_text)
                    if chunk_count == 1 or chunk_count % 20 == 0:
                        _emit_model_progress(
                            progress_callback,
                            {
                                "stage": "chunk_received",
                                "elapsed_seconds": elapsed_seconds(),
                                "model": Config.chat_ollama_model(),
                                "thread_id": thread_id,
                                "chunk_count": chunk_count,
                                "chars_received": chars_received,
                            },
                        )
                if chunk.get("done") is True:
                    break
            if stream_parts:
                parsed = _parse_model_payload("".join(stream_parts))
        if parsed is None and not used_streaming:
            data = response.json()
            parsed = _parse_model_payload(data.get("response"))
        if parsed:
            parsed["_memory_pack"] = {
                "budget": memory_pack.get("budget"),
                "token_usage": memory_pack.get("token_usage"),
                "total_tokens": memory_pack.get("total_tokens"),
                "wiki_references": memory_pack.get("wiki_references"),
            }
            _emit_model_progress(
                progress_callback,
                {
                    "stage": "completed",
                    "elapsed_seconds": elapsed_seconds(),
                    "model": Config.chat_ollama_model(),
                    "thread_id": thread_id,
                    "chunk_count": chunk_count,
                    "chars_received": chars_received,
                },
            )
            return parsed
    except Exception as exc:
        _emit_model_progress(
            progress_callback,
            {
                "stage": "failed",
                "elapsed_seconds": elapsed_seconds(),
                "model": Config.chat_ollama_model(),
                "thread_id": thread_id,
                "chunk_count": chunk_count,
                "chars_received": chars_received,
                "error": str(exc),
            },
        )
        logger.debug("Model-first chat call failed: %s", exc)
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=0.2)
    return None


def _should_force_action(user_text: str, fast_path_input: str | None) -> bool:
    probe_text = fast_path_input or user_text
    decision = classify_intent(probe_text)
    if decision.intent in {
        IntentType.COMPLETE_TASK,
        IntentType.SKIP_TASK,
        IntentType.DELETE_TASK,
        IntentType.BULK_ADD,
        IntentType.BULK_EDIT,
    }:
        return True
    if decision.intent == IntentType.QUERY and _is_grounded_task_query(probe_text):
        return True
    return False


def _record_assistant_reply(
    *,
    source: str,
    thread_id: str,
    response_text: str,
    metadata: dict | None = None,
) -> None:
    record_message(
        content=response_text,
        role="assistant",
        source=source,
        session_id=thread_id,
        metadata=metadata,
    )


def process_chat_message(
    message: str,
    *,
    source: str = "web",
    thread_id: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    """
    Process chat input with model-first orchestration.

    Behavior:
    - "." prefix (single) => deterministic fast path.
    - ".." prefix => escape literal dot, still model path.
    - bare/slash command text => deterministic fast path.
    - default => model-first with deterministic fallback.
    """
    raw_message = (message or "").strip()
    if not raw_message:
        raise ValueError("Empty message")

    resolved_thread_id = resolve_thread_id(source=source, thread_id=thread_id)
    mode, effective_text = _resolve_mode(raw_message)
    effective_text = (effective_text or "").strip()
    if not effective_text:
        raise ValueError("No message content to process")

    allow_long = _wants_detailed_reply(raw_message)
    record_message(
        content=raw_message,
        role="user",
        source=source,
        session_id=resolved_thread_id,
        metadata={"mode": mode, "thread_id": resolved_thread_id},
    )

    if mode == "model":
        resumed_result = _maybe_resume_interrupted_workflow(resolved_thread_id, effective_text)
        if resumed_result is not None:
            response_text = _enforce_brief_reply(
                resumed_result.get("response", _DEFAULT_FALLBACK_REPLY),
                allow_long=allow_long,
            )
            metadata = {
                "mode": "resume",
                "thread_id": resolved_thread_id,
                "requires_action": True,
                **_public_workflow_fields(resumed_result),
            }
            _record_assistant_reply(
                source=source,
                thread_id=resolved_thread_id,
                response_text=response_text,
                metadata=metadata,
            )
            return {
                "response": response_text,
                "thread_id": resolved_thread_id,
                "mode": "resume",
                "requires_action": True,
                **_public_workflow_fields(resumed_result),
            }

        if _is_fast_path_command(effective_text):
            workflow_result = submit_input(effective_text, source=source)
            response_text = _enforce_brief_reply(
                workflow_result.get("response", _DEFAULT_FALLBACK_REPLY),
                allow_long=allow_long,
            )
            metadata = {
                "mode": "fast",
                "thread_id": resolved_thread_id,
                "forced_fast_command": True,
                **_public_workflow_fields(workflow_result),
            }
            _record_assistant_reply(
                source=source,
                thread_id=resolved_thread_id,
                response_text=response_text,
                metadata=metadata,
            )
            return {
                "response": response_text,
                "thread_id": resolved_thread_id,
                "mode": "fast",
                "forced_fast_command": True,
                **_public_workflow_fields(workflow_result),
            }

    if mode == "fast":
        workflow_result = submit_input(effective_text, source=source)
        response_text = _enforce_brief_reply(
            workflow_result.get("response", _DEFAULT_FALLBACK_REPLY),
            allow_long=allow_long,
        )
        metadata = {
            "mode": "fast",
            "thread_id": resolved_thread_id,
            **_public_workflow_fields(workflow_result),
        }
        _record_assistant_reply(
            source=source,
            thread_id=resolved_thread_id,
            response_text=response_text,
            metadata=metadata,
        )
        return {
            "response": response_text,
            "thread_id": resolved_thread_id,
            "mode": "fast",
            **_public_workflow_fields(workflow_result),
        }
    if not Config.chat_model_first_enabled():
        workflow_result = submit_input(effective_text, source=source)
        response_text = _enforce_brief_reply(
            workflow_result.get("response", _DEFAULT_FALLBACK_REPLY),
            allow_long=allow_long,
        )
        metadata = {
            "mode": "deterministic",
            "thread_id": resolved_thread_id,
            **_public_workflow_fields(workflow_result),
        }
        _record_assistant_reply(
            source=source,
            thread_id=resolved_thread_id,
            response_text=response_text,
            metadata=metadata,
        )
        return {
            "response": response_text,
            "thread_id": resolved_thread_id,
            "mode": "deterministic",
            **_public_workflow_fields(workflow_result),
        }

    model_payload = _call_ollama_model(
        effective_text,
        resolved_thread_id,
        progress_callback=progress_callback,
    )
    memory_pack_meta = {}
    if isinstance(model_payload, dict):
        memory_pack_meta = dict(model_payload.pop("_memory_pack", {}) or {})
    if not model_payload:
        workflow_result = submit_input(effective_text, source=source)
        response_text = _enforce_brief_reply(
            workflow_result.get("response", _DEFAULT_FALLBACK_REPLY),
            allow_long=allow_long,
        )
        metadata = {
            "mode": "fallback_fast",
            "thread_id": resolved_thread_id,
            "fallback_reason": "model_unavailable_or_malformed",
            **_public_workflow_fields(workflow_result),
        }
        _record_assistant_reply(
            source=source,
            thread_id=resolved_thread_id,
            response_text=response_text,
            metadata=metadata,
        )
        return {
            "response": response_text,
            "thread_id": resolved_thread_id,
            "mode": "fallback_fast",
            "fallback_reason": "model_unavailable_or_malformed",
            **_public_workflow_fields(workflow_result),
        }

    reply = model_payload.get("reply") or model_payload.get("clarification_question") or ""
    requires_action = bool(model_payload.get("requires_action"))
    action_input = model_payload.get("fast_path_input")
    forced_action = False

    if not requires_action and _should_force_action(effective_text, action_input):
        requires_action = True
        forced_action = True
        action_input = action_input or effective_text

    workflow_result: dict | None = None
    if requires_action:
        workflow_result = submit_input((action_input or effective_text).strip(), source=source)
        reply = workflow_result.get("response", _DEFAULT_FALLBACK_REPLY)

    response_text = _enforce_brief_reply(reply or _DEFAULT_FALLBACK_REPLY, allow_long=allow_long)
    metadata = {
        "mode": "model",
        "thread_id": resolved_thread_id,
        "requires_action": requires_action,
        "model": Config.chat_ollama_model(),
        "memory_update": model_payload.get("memory_update"),
        "memory_pack": memory_pack_meta or None,
        **_public_workflow_fields(workflow_result),
    }
    _record_assistant_reply(
        source=source,
        thread_id=resolved_thread_id,
        response_text=response_text,
        metadata=metadata,
    )

    return {
        "response": response_text,
        "thread_id": resolved_thread_id,
        "mode": "model",
        "requires_action": requires_action,
        "model": Config.chat_ollama_model(),
        "memory_pack": memory_pack_meta or None,
        **_public_workflow_fields(workflow_result),
    }
