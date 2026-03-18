"""Deterministic context compaction for dropped conversation lines.

Extracts structured facts from conversation history using pure regex —
no model calls. Facts are stored in conversation_compactions and used
to prepend a summary header when truncation occurs in memory_pack.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..db import get_db

# ── Fact extraction patterns ──

_TASK_MENTION_RE = re.compile(
    r"(?:task|todo)[:\s]+['\"]?(.{3,60}?)['\"]?\s*(?:\(|$|—|–|-|\.|,)",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"(?:decided|chose|agreed|confirmed|approved|rejected|set)\s+(?:to\s+)?(.{5,80}?)(?:\.|$)",
    re.IGNORECASE,
)
_DUE_DATE_RE = re.compile(
    r"(?:due|deadline|by|scheduled for)\s+(\d{4}-\d{2}-\d{2}|\w+day|tomorrow|today)",
    re.IGNORECASE,
)
_PROJECT_RE = re.compile(
    r"(?:project|in project)\s+['\"]?(.{2,40}?)['\"]?\s*(?:\.|$|,|\()",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"(?:completed|done|finished|failed|skipped|deferred)\s*[:\s]+(.{3,60}?)(?:\.|$|,)",
    re.IGNORECASE,
)


def extract_facts(lines: list[str]) -> list[dict[str, str]]:
    """Extract structured facts from conversation lines using regex.

    Returns a list of dicts with keys: type, value, source_line (truncated).
    """
    facts: list[dict[str, str]] = []
    seen_values: set[str] = set()

    for line in lines:
        stripped = (line or "").strip()
        if not stripped:
            continue
        source_preview = stripped[:80]

        for pattern, fact_type in (
            (_TASK_MENTION_RE, "task_mention"),
            (_DECISION_RE, "decision"),
            (_DUE_DATE_RE, "due_date"),
            (_PROJECT_RE, "project_ref"),
            (_STATUS_RE, "status_change"),
        ):
            for match in pattern.finditer(stripped):
                value = match.group(1).strip()
                if not value or len(value) < 3:
                    continue
                dedup_key = f"{fact_type}:{value.lower()}"
                if dedup_key in seen_values:
                    continue
                seen_values.add(dedup_key)
                facts.append({
                    "type": fact_type,
                    "value": value,
                    "source_line": source_preview,
                })

    return facts


def merge_compaction_facts(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Merge facts from multiple compaction records, deduplicating by type+value."""
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        raw_facts = record.get("facts") or []
        if isinstance(raw_facts, str):
            try:
                raw_facts = json.loads(raw_facts)
            except Exception:
                continue
        if not isinstance(raw_facts, list):
            continue
        for fact in raw_facts:
            if not isinstance(fact, dict):
                continue
            dedup_key = f"{fact.get('type', '')}:{(fact.get('value') or '').lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            merged.append(fact)
    return merged


def format_compaction_header(facts: list[dict[str, str]]) -> str:
    """Format a compaction summary header from extracted facts."""
    if not facts:
        return "(earlier conversation context was compacted)"

    lines = ["[Compacted context summary]"]
    for fact in facts[:15]:
        fact_type = fact.get("type", "note")
        value = fact.get("value", "")
        if not value:
            continue
        label = fact_type.replace("_", " ").title()
        lines.append(f"• {label}: {value}")

    return "\n".join(lines)


def store_compaction(
    thread_id: str,
    dropped_lines: list[str],
    facts: list[dict[str, str]],
) -> int:
    """Store a compaction record and return its ID."""
    facts_json = json.dumps(facts, ensure_ascii=False, default=str)
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversation_compactions (thread_id, dropped_line_count, facts_json)
            VALUES (?, ?, ?)
            """,
            (str(thread_id), len(dropped_lines), facts_json),
        )
        return cursor.lastrowid


def get_recent_compactions(thread_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Get the most recent compaction records for a thread."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, thread_id, dropped_line_count, facts_json, created_at
            FROM conversation_compactions
            WHERE thread_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(thread_id), max(1, min(int(limit), 50))),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        facts_raw = row["facts_json"]
        try:
            facts = json.loads(facts_raw) if facts_raw else []
        except Exception:
            facts = []
        results.append({
            "id": int(row["id"]),
            "thread_id": row["thread_id"],
            "dropped_line_count": int(row["dropped_line_count"]),
            "facts": facts,
            "created_at": row["created_at"],
        })
    return results
