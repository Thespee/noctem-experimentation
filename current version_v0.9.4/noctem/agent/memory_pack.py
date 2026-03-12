"""Deterministic bounded memory pack assembly for model-first chat."""
from __future__ import annotations

from typing import Any

from ..db import get_db
from ..services.conversation_service import get_thread_context

TOTAL_CONTEXT_BUDGET = 32000
RESERVED_FOR_TOOLS_AND_OUTPUT = 10000
RECENT_CHATS_BUDGET = 4000
RECENT_COMMITS_BUDGET = 5000
CONTEXT_DOCS_BUDGET = 7000
WIKI_CONTEXT_BUDGET = 6000
ACTIVE_MEMORY_BUDGET = TOTAL_CONTEXT_BUDGET - RESERVED_FOR_TOOLS_AND_OUTPUT


def _estimate_tokens(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return max(1, len(cleaned) // 4)


def _tail_lines_to_budget(lines: list[str], budget_tokens: int) -> tuple[list[str], int]:
    selected: list[str] = []
    used = 0
    for line in reversed(lines):
        line_tokens = _estimate_tokens(line)
        if line_tokens <= 0:
            continue
        if used + line_tokens > budget_tokens:
            break
        selected.append(line)
        used += line_tokens
    selected.reverse()
    return selected, used


def _recent_chat_section(thread_id: str, budget_tokens: int = RECENT_CHATS_BUDGET) -> tuple[str, int]:
    turns = get_thread_context(thread_id, limit=80, include_system=False)
    lines: list[str] = []
    for turn in turns:
        role = "User" if turn.role == "user" else "Assistant"
        content = " ".join((turn.content or "").split())
        if content:
            lines.append(f"{role}: {content}")
    selected, used = _tail_lines_to_budget(lines, budget_tokens)
    if not selected:
        return "(no recent thread messages)", 0
    return "\n".join(selected), used


def _recent_commit_section(budget_tokens: int = RECENT_COMMITS_BUDGET) -> tuple[str, int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT operation, summary, created_at
            FROM object_events
            ORDER BY created_at DESC
            LIMIT 80
            """
        ).fetchall()

    lines: list[str] = []
    for row in rows:
        summary = str(row["summary"] or "").strip()
        operation = str(row["operation"] or "").strip()
        created_at = str(row["created_at"] or "").strip()
        if not operation and not summary:
            continue
        line = f"{created_at} {operation}"
        if summary:
            line += f": {summary}"
        lines.append(line.strip())

    selected, used = _tail_lines_to_budget(lines, budget_tokens)
    if not selected:
        return "(no recent commits)", 0
    return "\n".join(selected), used


def _context_docs_section(budget_tokens: int = CONTEXT_DOCS_BUDGET) -> tuple[str, int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT object_id, summary, markdown, generated_at
            FROM object_context_docs
            ORDER BY datetime(generated_at) DESC
            LIMIT 30
            """
        ).fetchall()

    chunks: list[str] = []
    used = 0
    for row in rows:
        header = f"[{row['object_id']}] {row['summary'] or ''}".strip()
        markdown = str(row["markdown"] or "").strip()
        snippet = markdown[:900].strip() if markdown else ""
        block = header if not snippet else f"{header}\n{snippet}"
        block_tokens = _estimate_tokens(block)
        if block_tokens <= 0:
            continue
        if used + block_tokens > budget_tokens:
            break
        chunks.append(block)
        used += block_tokens

    if not chunks:
        return "(no context docs available)", 0
    return "\n\n".join(chunks), used


def _wiki_section(query_text: str, budget_tokens: int = WIKI_CONTEXT_BUDGET) -> tuple[str, int, list[dict[str, Any]]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT file_name, title, trust_level
            FROM sources
            WHERE status = 'indexed'
            ORDER BY datetime(COALESCE(last_verified, ingested_at, created_at)) DESC
            LIMIT 12
            """
        ).fetchall()
    if not rows:
        return "(no indexed wiki sources)", 0, []

    lines: list[str] = [f"Query focus: {query_text}"]
    references: list[dict[str, Any]] = []
    for row in rows:
        file_name = str(row["file_name"] or "source").strip()
        title = str(row["title"] or "").strip()
        trust_level = int(row["trust_level"] or 1)
        label = file_name if not title else f"{file_name} — {title}"
        lines.append(f"- {label} (trust {trust_level})")
        references.append({"citation": label, "trust_level": trust_level})

    selected, used = _tail_lines_to_budget(lines, budget_tokens)
    if not selected:
        return "(wiki context budget exhausted)", 0, references
    return "\n".join(selected), used, references


def assemble_memory_pack(query_text: str, thread_id: str) -> dict[str, Any]:
    chats_text, chats_tokens = _recent_chat_section(thread_id, RECENT_CHATS_BUDGET)
    commits_text, commits_tokens = _recent_commit_section(RECENT_COMMITS_BUDGET)
    docs_text, docs_tokens = _context_docs_section(CONTEXT_DOCS_BUDGET)
    wiki_text, wiki_tokens, wiki_refs = _wiki_section(query_text, WIKI_CONTEXT_BUDGET)

    token_usage = {
        "recent_chats": chats_tokens,
        "recent_commits": commits_tokens,
        "context_docs": docs_tokens,
        "wiki": wiki_tokens,
    }
    total_tokens = sum(token_usage.values())

    return {
        "budget": {
            "total_context": TOTAL_CONTEXT_BUDGET,
            "reserved_for_tools_and_output": RESERVED_FOR_TOOLS_AND_OUTPUT,
            "active_memory_budget": ACTIVE_MEMORY_BUDGET,
            "recent_chats": RECENT_CHATS_BUDGET,
            "recent_commits": RECENT_COMMITS_BUDGET,
            "context_docs": CONTEXT_DOCS_BUDGET,
            "wiki": WIKI_CONTEXT_BUDGET,
        },
        "token_usage": token_usage,
        "total_tokens": total_tokens,
        "sections": {
            "recent_chats": chats_text,
            "recent_commits": commits_text,
            "context_docs": docs_text,
            "wiki": wiki_text,
        },
        "wiki_references": wiki_refs,
    }
