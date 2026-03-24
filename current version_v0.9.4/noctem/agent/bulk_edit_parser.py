"""Structured parser for bulk-edit task commands."""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Optional

import requests

from ..parser.natural_date import parse_datetime


ACTION_VERBS = (
    "move",
    "reschedule",
    "reassign",
    "shift",
    "delay",
    "postpone",
    "push",
    "set",
)

DELAY_VERBS = {"delay", "postpone", "push"}


@dataclass
class BulkEditParseResult:
    action: Optional[str] = None
    scope_type: str = "unknown"  # project | all | task_names | due_date | overdue | unknown
    source_project_name: Optional[str] = None
    source_due_date: Optional[date] = None
    task_names: list[str] = field(default_factory=list)
    target_due_date: Optional[date] = None
    target_due_time: Optional[time] = None
    target_project_name: Optional[str] = None
    selector_text: str = ""
    target_text: str = ""
    confidence: float = 0.0
    parser: str = "heuristic"
    errors: list[str] = field(default_factory=list)

    def has_scope(self) -> bool:
        if self.scope_type == "project":
            return bool(self.source_project_name)
        if self.scope_type == "due_date":
            return self.source_due_date is not None
        if self.scope_type == "overdue":
            return True
        if self.scope_type == "task_names":
            return bool(self.task_names)
        if self.scope_type == "all":
            return True
        return False

    def has_updates(self) -> bool:
        return (
            self.target_due_date is not None
            or self.target_due_time is not None
            or bool(self.target_project_name)
        )


def split_bulk_edit_clauses(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:~|;)\s*", cleaned)
        if part and part.strip()
    ]
    return parts or [cleaned]


def should_use_model_parser(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False

    try:
        min_chars = int(os.environ.get("NOCTEM_AGENT_PARSE_MODEL_MIN_CHARS", "90"))
    except Exception:
        min_chars = 90
    try:
        min_words = int(os.environ.get("NOCTEM_AGENT_PARSE_MODEL_MIN_WORDS", "14"))
    except Exception:
        min_words = 14

    words = [w for w in re.split(r"\s+", cleaned) if w]
    if len(cleaned) >= min_chars or len(words) >= min_words:
        return True
    if re.search(r"[~;\n]", cleaned):
        return True
    if re.search(r"\b(?:then|after that|also|and then)\b", cleaned, flags=re.IGNORECASE):
        return True
    return False


def looks_like_bulk_edit_request(text: str) -> bool:
    normalized = _normalize_prefix(text).lower()
    action = _detect_action(normalized)
    if not action:
        return False

    bulk_markers = (
        " all ",
        " all of ",
        " everything ",
        " every thing ",
        " multiple ",
        " tasks ",
        " items ",
        " ones ",
        " from ",
        " in project ",
        " in the ",
    )
    padded = f" {normalized} "
    has_bulk_scope = any(marker in padded for marker in bulk_markers) or "," in normalized or " and " in normalized
    if not has_bulk_scope:
        return False

    if action in DELAY_VERBS:
        return True

    return any(token in normalized for token in (" to ", " into ", " for "))


def parse_bulk_edit_request(text: str) -> BulkEditParseResult:
    heuristic = _parse_with_heuristics(text)
    model = _parse_with_ollama(text) if should_use_model_parser(text) else None
    if not model:
        return heuristic

    merged = _merge_parse_results(heuristic, model)
    return merged


def _merge_parse_results(
    heuristic: BulkEditParseResult,
    model: BulkEditParseResult,
) -> BulkEditParseResult:
    merged = BulkEditParseResult(
        action=heuristic.action or model.action,
        scope_type=heuristic.scope_type,
        source_project_name=heuristic.source_project_name,
        source_due_date=heuristic.source_due_date,
        task_names=list(heuristic.task_names),
        target_due_date=heuristic.target_due_date,
        target_due_time=heuristic.target_due_time,
        target_project_name=heuristic.target_project_name,
        selector_text=heuristic.selector_text or model.selector_text,
        target_text=heuristic.target_text or model.target_text,
        confidence=max(heuristic.confidence, model.confidence),
        parser="hybrid",
        errors=list(heuristic.errors),
    )

    if not merged.has_scope() and model.has_scope():
        merged.scope_type = model.scope_type
        merged.source_project_name = model.source_project_name
        merged.source_due_date = model.source_due_date
        merged.task_names = list(model.task_names)
    if not merged.has_updates() and model.has_updates():
        merged.target_due_date = model.target_due_date
        merged.target_due_time = model.target_due_time
        merged.target_project_name = model.target_project_name
    if model.action and not merged.action:
        merged.action = model.action

    if merged.has_scope() and merged.has_updates():
        merged.errors = []
    return merged


def _parse_with_heuristics(text: str) -> BulkEditParseResult:
    cleaned = _normalize_prefix(text)
    result = BulkEditParseResult(parser="heuristic", confidence=0.55)

    action = _detect_action(cleaned)
    result.action = action
    if not action:
        result.errors.append("no_action_verb")
        return result

    body = _remove_action_prefix(cleaned, action)
    selector, target = _split_selector_target(body)
    if selector is None:
        selector = body.strip(" .")
        target = ""
    result.selector_text = selector or ""
    result.target_text = target or ""

    _parse_scope(selector or "", result)
    _parse_target(target or "", result)
    _apply_delay_defaults(result)

    if result.has_scope():
        result.confidence += 0.2
    else:
        result.errors.append("scope_not_resolved")
    if result.has_updates():
        result.confidence += 0.2
    else:
        result.errors.append("update_not_resolved")
    result.confidence = max(0.0, min(1.0, result.confidence))
    return result


def _parse_with_ollama(text: str) -> Optional[BulkEditParseResult]:
    model = (os.environ.get("NOCTEM_AGENT_BULK_EDIT_PARSE_MODEL") or "").strip()
    if not model:
        return None

    base_url = (os.environ.get("NOCTEM_OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    timeout_seconds = float(os.environ.get("NOCTEM_OLLAMA_PARSE_TIMEOUT_SECONDS", "5"))
    prompt = (
        "Extract structured fields for a task bulk-edit command. "
        "Return JSON only with keys: action, scope_type, source_project_name, source_due_phrase, "
        "task_names, target_due_phrase, target_project_name, confidence. "
        "scope_type must be one of: project, all, task_names, due_date, overdue, unknown. "
        "If missing, use null (or [] for task_names). "
        f"Text: {text}"
    )

    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None

    result = BulkEditParseResult(parser=f"ollama:{model}", confidence=0.6)
    result.action = _normalize_action(payload.get("action"))
    scope_type = (payload.get("scope_type") or "").strip().lower() if isinstance(payload.get("scope_type"), str) else ""
    if scope_type in {"project", "all", "task_names", "due_date", "overdue"}:
        result.scope_type = scope_type

    source_project = payload.get("source_project_name")
    if isinstance(source_project, str) and source_project.strip():
        result.source_project_name = _clean_phrase(source_project)

    source_due_phrase = payload.get("source_due_phrase")
    if isinstance(source_due_phrase, str) and source_due_phrase.strip():
        parsed_source_due = parse_datetime(source_due_phrase.strip())
        result.source_due_date = parsed_source_due.date
        if result.source_due_date is not None and result.scope_type == "unknown":
            result.scope_type = "due_date"

    raw_names = payload.get("task_names")
    if isinstance(raw_names, str):
        result.task_names = [n.strip(" .") for n in re.split(r"\s*(?:,|;|\band\b)\s*", raw_names) if n and n.strip(" .")]
    elif isinstance(raw_names, list):
        result.task_names = [str(n).strip(" .") for n in raw_names if str(n).strip(" .")]
    if result.task_names and result.scope_type == "unknown":
        result.scope_type = "task_names"

    target_due_phrase = payload.get("target_due_phrase")
    if isinstance(target_due_phrase, str) and target_due_phrase.strip():
        parsed_target_due = parse_datetime(target_due_phrase.strip())
        result.target_due_date = parsed_target_due.date
        result.target_due_time = parsed_target_due.time

    target_project = payload.get("target_project_name")
    if isinstance(target_project, str) and target_project.strip():
        result.target_project_name = _clean_phrase(target_project)

    confidence_raw = payload.get("confidence", 0.6)
    try:
        result.confidence = max(0.0, min(1.0, float(confidence_raw)))
    except Exception:
        pass

    _apply_delay_defaults(result)
    if not result.has_scope() and not result.has_updates():
        return None
    return result


def _normalize_prefix(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value

    patterns = (
        r"^\s*(?:hey|hi|hello)\s+",
        r"^\s*(?:can|could|would)\s+you\s+",
        r"^\s*please\s+",
        r"^\s*i\s+need\s+you\s+to\s+",
        r"^\s*let'?s\s+",
    )
    for pattern in patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+please\s*[.!?]*$", "", value, flags=re.IGNORECASE)
    return value.strip()


def _detect_action(text: str) -> Optional[str]:
    match = re.search(r"\b(" + "|".join(ACTION_VERBS) + r")\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _normalize_action(match.group(1))


def _normalize_action(action: Optional[str]) -> Optional[str]:
    if not action:
        return None
    lowered = action.strip().lower()
    if lowered in DELAY_VERBS:
        return "delay"
    if lowered in {"move", "reschedule", "reassign", "shift", "set"}:
        return "move"
    return lowered


def _remove_action_prefix(text: str, action: str) -> str:
    pattern = r"^.*?\b" + re.escape(action) + r"\b\s*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()


def _split_selector_target(body: str) -> tuple[Optional[str], Optional[str]]:
    if not body:
        return None, None
    lowered = body.lower()
    positions: list[tuple[int, str]] = []
    for token in (" to ", " into ", " for "):
        idx = lowered.rfind(token)
        if idx != -1:
            positions.append((idx, token))
    if not positions:
        return None, None

    idx, token = max(positions, key=lambda item: item[0])
    selector = body[:idx].strip(" .")
    target = body[idx + len(token):].strip(" .")
    if not selector:
        return None, None
    return selector, target


def _parse_scope(selector: str, result: BulkEditParseResult) -> None:
    selector_clean = selector.strip()
    selector_lower = selector_clean.lower()
    if not selector_clean:
        return

    due_scope_match = re.search(r"\bfrom\s+(.+)$", selector_clean, flags=re.IGNORECASE)
    if due_scope_match:
        due_phrase = due_scope_match.group(1).strip(" .")
        parsed_due = parse_datetime(due_phrase)
        if parsed_due.date is not None and not parsed_due.remaining_text.strip():
            result.scope_type = "due_date"
            result.source_due_date = parsed_due.date
            return
        if "overdue" in due_phrase.lower():
            result.scope_type = "overdue"
            return

    if re.search(r"\boverdue\b", selector_lower):
        result.scope_type = "overdue"
        return

    project_match = re.search(
        r"\b(?:from|in|under)\s+(?:the\s+)?(.+?)\s+project\b",
        selector_clean,
        flags=re.IGNORECASE,
    )
    if project_match:
        result.scope_type = "project"
        result.source_project_name = _clean_phrase(project_match.group(1))
        return

    project_match = re.search(
        r"\b(?:from|in|under)\s+(?:the\s+)?(?:project\s+)?(.+)$",
        selector_clean,
        flags=re.IGNORECASE,
    )
    if project_match:
        candidate = _clean_phrase(project_match.group(1))
        parsed_candidate = parse_datetime(candidate)
        if parsed_candidate.date is None:
            result.scope_type = "project"
            result.source_project_name = candidate
            return

    if re.search(r"\b(?:all|everything|every\s*thing)\b", selector_lower):
        result.scope_type = "all"
        return

    names_blob = re.sub(
        r"^(?:all(?:\s+of)?\s+)?(?:the\s+)?(?:tasks?|items?|things?|every\s*thing|ones?|multiple)\s+",
        "",
        selector_clean,
        flags=re.IGNORECASE,
    ).strip()
    raw_names = [
        n.strip(" .")
        for n in re.split(r"\s*(?:,|;|\band\b)\s*", names_blob, flags=re.IGNORECASE)
        if n and n.strip(" .")
    ]
    if raw_names:
        result.scope_type = "task_names"
        result.task_names = raw_names


def _parse_target(target: str, result: BulkEditParseResult) -> None:
    target_clean = target.strip(" .")
    if not target_clean:
        return

    parsed_target = parse_datetime(target_clean)
    result.target_due_date = parsed_target.date
    result.target_due_time = parsed_target.time

    explicit_project_match = re.search(
        r"^(?:the\s+)?project\s+(.+)$",
        target_clean,
        flags=re.IGNORECASE,
    )
    if explicit_project_match:
        result.target_project_name = _clean_phrase(explicit_project_match.group(1))
        return

    if target_clean.startswith("/") or target_clean.startswith("+"):
        result.target_project_name = _clean_phrase(target_clean[1:])
        return

    remaining = parsed_target.remaining_text.strip(" .")
    if not remaining:
        return

    remaining = re.sub(r"^(?:to|in|into|for)\s+", "", remaining, flags=re.IGNORECASE).strip()
    remaining = re.sub(r"^(?:the\s+)?project\s+", "", remaining, flags=re.IGNORECASE).strip()
    remaining = remaining.lstrip("/+").strip()
    if remaining:
        result.target_project_name = _clean_phrase(remaining)


def _apply_delay_defaults(result: BulkEditParseResult) -> None:
    if result.action != "delay":
        return
    if result.target_due_date is not None:
        return
    if result.source_due_date is not None:
        result.target_due_date = result.source_due_date + timedelta(days=1)
        return
    result.target_due_date = date.today() + timedelta(days=1)


def _clean_phrase(value: str) -> str:
    cleaned = (value or "").strip().strip(" .!?")
    cleaned = cleaned.strip("'\"")
    return cleaned
