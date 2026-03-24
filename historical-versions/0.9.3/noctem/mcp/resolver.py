"""Phase 2 resolver engine for task targeting and bulk scope resolution."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..parser.command import parse_command
from ..services import project_service, task_service

_PUNCT_RE = re.compile(r"[^a-z0-9\s]+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_TRAILING_TASK_RE = re.compile(r"\s+tasks?(?:\b.*)?$", re.IGNORECASE)
_POLITE_PREFIX_RE = re.compile(
    r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?",
    re.IGNORECASE,
)
_ACTION_PREFIX_RE = re.compile(
    r"^(?:done|complete|finish|skip|defer|delete|remove)\s+",
    re.IGNORECASE,
)
_INACTIVE_STATUSES = {"done", "canceled"}


def _normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []
    return [t for t in normalized.split(" ") if t]


def _clean_target_phrase(value: str) -> str:
    cleaned = (value or "").strip().rstrip("?.!")
    cleaned = _LEADING_ARTICLE_RE.sub("", cleaned).strip()
    cleaned = _TRAILING_TASK_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+from\s+(?:today|tomorrow|yesterday)\b.*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _parse_created_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None
    return None


def _active_status_bonus(status: str | None) -> tuple[float, str]:
    if (status or "").lower() in _INACTIVE_STATUSES:
        return -0.08, "inactive_status"
    return 0.04, "active_status"


def _score_name_match(query: str, target_name: str, status: str | None) -> tuple[float, list[str]]:
    q_norm = _normalize_text(query)
    name_norm = _normalize_text(target_name)
    if not q_norm or not name_norm:
        return 0.0, []

    score = 0.0
    signals: list[str] = []
    if q_norm == name_norm:
        score = max(score, 1.0)
        signals.append("exact_name")
    elif name_norm.startswith(q_norm):
        score = max(score, 0.92)
        signals.append("prefix_name")
    elif q_norm in name_norm:
        coverage = min(1.0, len(q_norm) / max(len(name_norm), 1))
        score = max(score, 0.75 + (0.12 * coverage))
        signals.append("substring_name")

    q_tokens = set(_tokenize(q_norm))
    name_tokens = set(_tokenize(name_norm))
    if q_tokens and name_tokens:
        overlap = len(q_tokens & name_tokens) / max(len(q_tokens), 1)
        if overlap > 0:
            token_score = 0.45 + (0.45 * overlap)
            score = max(score, token_score)
            if overlap >= 0.999:
                signals.append("full_token_overlap")
            else:
                signals.append("partial_token_overlap")

    bonus, status_signal = _active_status_bonus(status)
    score += bonus
    if status_signal not in signals:
        signals.append(status_signal)
    score = max(0.0, min(1.0, score))
    return score, signals


def _extract_query_variants(text: str) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return []

    variants: list[str] = []
    command = parse_command(stripped)
    if command.target_name:
        variants.append(command.target_name)
        cleaned_name = _clean_target_phrase(command.target_name)
        if cleaned_name and cleaned_name != command.target_name:
            variants.append(cleaned_name)

    polite_stripped = _POLITE_PREFIX_RE.sub("", stripped, count=1).strip()
    action_match = _ACTION_PREFIX_RE.match(polite_stripped)
    if action_match:
        target_candidate = polite_stripped[action_match.end():].strip().rstrip("?.!")
        if target_candidate:
            variants.append(target_candidate)
            cleaned_candidate = _clean_target_phrase(target_candidate)
            if cleaned_candidate and cleaned_candidate != target_candidate:
                variants.append(cleaned_candidate)

    parts = stripped.split(maxsplit=1)
    if len(parts) > 1:
        remainder = parts[1].strip()
        if remainder:
            variants.append(remainder)
            cleaned_remainder = _clean_target_phrase(remainder)
            if cleaned_remainder and cleaned_remainder != remainder:
                variants.append(cleaned_remainder)

    variants.append(stripped)
    cleaned_stripped = _clean_target_phrase(stripped)
    if cleaned_stripped and cleaned_stripped != stripped:
        variants.append(cleaned_stripped)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in variants:
        key = _normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value.strip())
    return deduped


def _rank_candidates_for_queries(
    queries: list[str],
    items: list,
    *,
    id_attr: str,
    name_attr: str,
    status_attr: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not queries or not items:
        return []

    ranked_by_id: dict[int, dict[str, Any]] = {}
    for item in items:
        item_id = getattr(item, id_attr, None)
        if item_id is None:
            continue
        item_name = getattr(item, name_attr, "") or ""
        item_status = getattr(item, status_attr, None) if status_attr else None
        best_score = 0.0
        best_signals: list[str] = []
        best_query = None
        for query in queries:
            score, signals = _score_name_match(query, item_name, item_status)
            if score > best_score:
                best_score = score
                best_signals = signals
                best_query = query
        if best_score <= 0:
            continue
        ranked_by_id[int(item_id)] = {
            "item": item,
            "id": int(item_id),
            "name": item_name,
            "status": item_status,
            "score": round(best_score, 4),
            "signals": best_signals,
            "matched_query": best_query,
            "created_at": getattr(item, "created_at", None),
        }

    ranked = sorted(
        ranked_by_id.values(),
        key=lambda row: (
            float(row["score"]),
            _parse_created_at(row.get("created_at")) or datetime.min,
            -int(row["id"]),
        ),
        reverse=True,
    )
    return ranked[:max(1, limit)]


def _select_top_candidate(
    ranked: list[dict[str, Any]],
    *,
    min_score: float = 0.45,
    ambiguity_gap: float = 0.08,
    ambiguity_floor: float = 0.55,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    if not ranked:
        return None, False, "no_candidates"
    top = ranked[0]
    top_score = float(top.get("score", 0.0))
    if top_score < min_score:
        return None, False, "low_confidence"
    if len(ranked) == 1:
        return top, False, None

    second = ranked[1]
    second_score = float(second.get("score", 0.0))
    gap = top_score - second_score
    if second_score >= ambiguity_floor and gap <= ambiguity_gap:
        return None, True, "top_candidates_too_close"
    return top, False, None


def _candidate_public_view(candidate: dict[str, Any], *, id_key: str = "task_id") -> dict[str, Any]:
    item = candidate.get("item")
    return {
        id_key: candidate.get("id"),
        "name": candidate.get("name"),
        "status": candidate.get("status"),
        "project_id": getattr(item, "project_id", None) if item else None,
        "due_date": getattr(item, "due_date", None).isoformat() if item and getattr(item, "due_date", None) else None,
        "score": candidate.get("score"),
        "signals": list(candidate.get("signals") or []),
        "matched_query": candidate.get("matched_query"),
    }


def resolve_task_target(
    text: str,
    *,
    include_done: bool = False,
    priority_index_limit: int = 20,
    candidate_limit: int = 5,
) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        return {
            "query": text,
            "query_variants": [],
            "resolution": "no_match",
            "ambiguous": False,
            "ambiguity_reason": "empty_query",
            "confidence": 0.0,
            "selected_task": None,
            "selected_task_id": None,
            "selected_method": None,
            "candidates": [],
        }

    if stripped.isdigit():
        numeric_target = int(stripped)
        exact = task_service.get_task(numeric_target)
        if exact and (include_done or exact.status not in _INACTIVE_STATUSES):
            return {
                "query": text,
                "query_variants": [stripped],
                "resolution": "selected",
                "ambiguous": False,
                "ambiguity_reason": None,
                "confidence": 1.0,
                "selected_task": exact,
                "selected_task_id": exact.id,
                "selected_method": "task_id",
                "candidates": [_candidate_public_view({"id": exact.id, "name": exact.name, "status": exact.status, "item": exact, "score": 1.0, "signals": ["exact_id"], "matched_query": stripped})],
            }

        ranked_priority = task_service.get_priority_tasks(priority_index_limit)
        idx = numeric_target - 1
        if 0 <= idx < len(ranked_priority):
            indexed = ranked_priority[idx]
            return {
                "query": text,
                "query_variants": [stripped],
                "resolution": "selected",
                "ambiguous": False,
                "ambiguity_reason": None,
                "confidence": 0.95,
                "selected_task": indexed,
                "selected_task_id": indexed.id,
                "selected_method": "priority_index",
                "candidates": [_candidate_public_view({"id": indexed.id, "name": indexed.name, "status": indexed.status, "item": indexed, "score": 0.95, "signals": ["priority_index"], "matched_query": stripped})],
            }

    command = parse_command(stripped)
    if command.target_id:
        direct = task_service.get_task(command.target_id)
        if direct and (include_done or direct.status not in _INACTIVE_STATUSES):
            return {
                "query": text,
                "query_variants": [str(command.target_id)],
                "resolution": "selected",
                "ambiguous": False,
                "ambiguity_reason": None,
                "confidence": 1.0,
                "selected_task": direct,
                "selected_task_id": direct.id,
                "selected_method": "command_target_id",
                "candidates": [_candidate_public_view({"id": direct.id, "name": direct.name, "status": direct.status, "item": direct, "score": 1.0, "signals": ["command_target_id"], "matched_query": str(command.target_id)})],
            }

    query_variants = _extract_query_variants(stripped)
    tasks = task_service.get_all_tasks(include_done=include_done)
    ranked = _rank_candidates_for_queries(
        query_variants,
        tasks,
        id_attr="id",
        name_attr="name",
        status_attr="status",
        limit=max(candidate_limit, 5),
    )
    selected, ambiguous, ambiguity_reason = _select_top_candidate(ranked)
    candidates = [_candidate_public_view(item) for item in ranked[:candidate_limit]]

    if selected is None:
        return {
            "query": text,
            "query_variants": query_variants,
            "resolution": "ambiguous" if ambiguous else "no_match",
            "ambiguous": ambiguous,
            "ambiguity_reason": ambiguity_reason,
            "confidence": float(ranked[0]["score"]) if ranked else 0.0,
            "selected_task": None,
            "selected_task_id": None,
            "selected_method": None,
            "candidates": candidates,
        }

    selected_task = selected["item"]
    return {
        "query": text,
        "query_variants": query_variants,
        "resolution": "selected",
        "ambiguous": False,
        "ambiguity_reason": None,
        "confidence": float(selected["score"]),
        "selected_task": selected_task,
        "selected_task_id": int(selected["id"]),
        "selected_method": "ranked_match",
        "candidates": candidates,
    }


def resolve_project_target(name: str, *, candidate_limit: int = 5) -> dict[str, Any]:
    query = (name or "").strip()
    if not query:
        return {
            "query": name,
            "resolution": "no_match",
            "ambiguous": False,
            "ambiguity_reason": "empty_query",
            "confidence": 0.0,
            "selected_project": None,
            "selected_project_id": None,
            "candidates": [],
        }

    projects = project_service.get_all_projects()
    ranked = _rank_candidates_for_queries(
        [query, _clean_target_phrase(query)],
        projects,
        id_attr="id",
        name_attr="name",
        status_attr="status",
        limit=max(candidate_limit, 5),
    )
    selected, ambiguous, ambiguity_reason = _select_top_candidate(
        ranked,
        min_score=0.4,
        ambiguity_gap=0.08,
        ambiguity_floor=0.5,
    )
    candidates = [
        {
            "project_id": candidate["id"],
            "name": candidate["name"],
            "status": candidate["status"],
            "score": candidate["score"],
            "signals": list(candidate.get("signals") or []),
            "matched_query": candidate.get("matched_query"),
        }
        for candidate in ranked[:candidate_limit]
    ]

    if selected is None:
        return {
            "query": name,
            "resolution": "ambiguous" if ambiguous else "no_match",
            "ambiguous": ambiguous,
            "ambiguity_reason": ambiguity_reason,
            "confidence": float(ranked[0]["score"]) if ranked else 0.0,
            "selected_project": None,
            "selected_project_id": None,
            "candidates": candidates,
        }

    return {
        "query": name,
        "resolution": "selected",
        "ambiguous": False,
        "ambiguity_reason": None,
        "confidence": float(selected["score"]),
        "selected_project": selected["item"],
        "selected_project_id": int(selected["id"]),
        "candidates": candidates,
    }


def resolve_scope(
    *,
    scope_type: str,
    source_project_name: str | None = None,
    source_due_date: date | None = None,
    task_names: list[str] | None = None,
) -> dict[str, Any]:
    scope = (scope_type or "unknown").strip().lower()
    matched_tasks: list = []
    scope_ref = "unknown"
    unresolved_names: list[str] = []
    ambiguous_names: list[dict[str, Any]] = []
    candidate_map: dict[str, list[dict[str, Any]]] = {}
    ambiguity_reason = None

    if scope == "project" and source_project_name:
        project_resolution = resolve_project_target(source_project_name)
        if project_resolution.get("ambiguous"):
            ambiguity_reason = "ambiguous_project"
        selected_project = project_resolution.get("selected_project")
        if selected_project:
            scope_ref = f"project::{selected_project.name}"
            matched_tasks = [
                task
                for task in task_service.get_project_tasks(selected_project.id)
                if (task.status or "").lower() not in _INACTIVE_STATUSES
            ]
        return {
            "scope_type": scope,
            "scope_ref": scope_ref,
            "matched_count": len(matched_tasks),
            "matched_task_ids": [task.id for task in matched_tasks],
            "unresolved_names": unresolved_names,
            "ambiguous": bool(project_resolution.get("ambiguous")),
            "ambiguity_reason": ambiguity_reason,
            "ambiguity_details": project_resolution.get("candidates") if project_resolution.get("ambiguous") else [],
            "candidates_by_name": candidate_map,
            "_task_objects": matched_tasks,
        }

    if scope == "due_date" and source_due_date:
        matched_tasks = [
            task
            for task in task_service.get_tasks_due_on(source_due_date)
            if (task.status or "").lower() not in _INACTIVE_STATUSES
        ]
        return {
            "scope_type": scope,
            "scope_ref": f"due_date::{source_due_date.isoformat()}",
            "matched_count": len(matched_tasks),
            "matched_task_ids": [task.id for task in matched_tasks],
            "unresolved_names": unresolved_names,
            "ambiguous": False,
            "ambiguity_reason": None,
            "ambiguity_details": [],
            "candidates_by_name": candidate_map,
            "_task_objects": matched_tasks,
        }
    if scope == "overdue":
        matched_tasks = [
            task
            for task in task_service.get_overdue_tasks()
            if (task.status or "").lower() not in _INACTIVE_STATUSES
        ]
        return {
            "scope_type": scope,
            "scope_ref": "overdue",
            "matched_count": len(matched_tasks),
            "matched_task_ids": [task.id for task in matched_tasks],
            "unresolved_names": unresolved_names,
            "ambiguous": False,
            "ambiguity_reason": None,
            "ambiguity_details": [],
            "candidates_by_name": candidate_map,
            "_task_objects": matched_tasks,
        }

    if scope == "all":
        matched_tasks = task_service.get_all_tasks(include_done=False)
        return {
            "scope_type": scope,
            "scope_ref": "all",
            "matched_count": len(matched_tasks),
            "matched_task_ids": [task.id for task in matched_tasks],
            "unresolved_names": unresolved_names,
            "ambiguous": False,
            "ambiguity_reason": None,
            "ambiguity_details": [],
            "candidates_by_name": candidate_map,
            "_task_objects": matched_tasks,
        }

    if scope == "task_names":
        seen_ids: set[int] = set()
        matched_tasks = []
        for raw_name in task_names or []:
            query = (raw_name or "").strip()
            if not query:
                continue
            resolution = resolve_task_target(query, include_done=False)
            candidate_map[query] = list(resolution.get("candidates") or [])
            if resolution.get("ambiguous"):
                ambiguous_names.append(
                    {
                        "query": query,
                        "reason": resolution.get("ambiguity_reason"),
                        "candidates": list(resolution.get("candidates") or []),
                    }
                )
                continue
            selected = resolution.get("selected_task")
            if not selected:
                unresolved_names.append(query)
                continue
            if selected.id in seen_ids:
                continue
            seen_ids.add(selected.id)
            matched_tasks.append(selected)

        return {
            "scope_type": scope,
            "scope_ref": "task_names",
            "matched_count": len(matched_tasks),
            "matched_task_ids": [task.id for task in matched_tasks],
            "unresolved_names": unresolved_names,
            "ambiguous": bool(ambiguous_names),
            "ambiguity_reason": "ambiguous_task_names" if ambiguous_names else None,
            "ambiguity_details": ambiguous_names,
            "candidates_by_name": candidate_map,
            "_task_objects": matched_tasks,
        }

    return {
        "scope_type": scope,
        "scope_ref": "unknown",
        "matched_count": 0,
        "matched_task_ids": [],
        "unresolved_names": [],
        "ambiguous": False,
        "ambiguity_reason": "unknown_scope",
        "ambiguity_details": [],
        "candidates_by_name": {},
        "_task_objects": [],
    }
