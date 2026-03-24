"""Intent routing for v0.9.3 agent workflows."""
import json
import os
import re
from dataclasses import dataclass
from enum import Enum

import requests
from ..config import Config
from .bulk_edit_parser import looks_like_bulk_edit_request


class IntentType(str, Enum):
    ADD_TASK = "add_task"
    BULK_ADD = "bulk_add"
    BULK_EDIT = "bulk_edit"
    COMPLETE_TASK = "complete_task"
    SKIP_TASK = "skip_task"
    DELETE_TASK = "delete_task"
    QUERY = "query"


@dataclass
class RouteDecision:
    intent: IntentType
    confidence: float
    reasoning: str
    classifier: str = "heuristic"


_POLITE_PREFIX_RE = re.compile(
    r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?",
    re.IGNORECASE,
)
_QUERY_PREFIX_RE = re.compile(
    r"^(?:what|how|when|why|show|list|which|help|can you|do i|did i|is there|are there)\b",
    re.IGNORECASE,
)


def _strip_polite_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    return _POLITE_PREFIX_RE.sub("", cleaned, count=1).strip()


def _looks_like_query(text: str) -> bool:
    cleaned = (text or "").strip()
    lower = cleaned.lower()
    if not lower:
        return False
    if cleaned.endswith("?"):
        return True
    if _QUERY_PREFIX_RE.match(cleaned):
        return True
    if "what do i have on for today" in lower:
        return True
    return False


def _coerce_intent(value: str | None) -> IntentType | None:
    if not value:
        return None
    try:
        return IntentType(value.strip().lower())
    except Exception:
        return None


def _classify_with_ollama(text: str) -> RouteDecision | None:
    """
    Optional local-model classifier.
    Uses NOCTEM_AGENT_INTENT_MODEL / NOCTEM_OLLAMA_BASE_URL when set,
    otherwise falls back to configured chat Ollama settings.
    Enabled only when NOCTEM_AGENT_INTENT_MODEL is set.
    """
    model = (
        os.environ.get("NOCTEM_AGENT_INTENT_MODEL")
        or Config.chat_ollama_model()
        or ""
    ).strip()
    if not model:
        return None

    base_url = (
        os.environ.get("NOCTEM_OLLAMA_BASE_URL")
        or Config.chat_ollama_base_url()
        or "http://localhost:11434"
    ).rstrip("/")
    timeout_seconds = float(os.environ.get("NOCTEM_OLLAMA_INTENT_TIMEOUT_SECONDS", "3"))
    prompt = (
        "Classify the user text into one intent: "
        "add_task, bulk_add, bulk_edit, complete_task, skip_task, delete_task, query.\n"
        "Return JSON ONLY with keys: intent, confidence, reasoning.\n"
        "confidence must be a number 0.0 to 1.0.\n"
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
        intent = _coerce_intent(payload.get("intent") if isinstance(payload, dict) else None)
        if not intent:
            return None

        confidence_raw = payload.get("confidence", 0.6) if isinstance(payload, dict) else 0.6
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except Exception:
            confidence = 0.6

        reasoning = (
            payload.get("reasoning")
            if isinstance(payload, dict) and isinstance(payload.get("reasoning"), str)
            else "Classified by local Ollama model"
        )

        return RouteDecision(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            classifier=f"ollama:{model}",
        )
    except Exception:
        return None


def classify_intent(text: str) -> RouteDecision:
    """Classify user text into a minimal intent set."""
    cleaned = (text or "").strip()
    lower = cleaned.lower()
    normalized = _strip_polite_prefix(lower)

    if lower.startswith(("done ", "complete ", "completed ", "finish ")) or normalized.startswith(("done ", "complete ", "completed ", "finish ")):
        return RouteDecision(IntentType.COMPLETE_TASK, 0.95, "Completion verb prefix matched")
    if lower.startswith(("skip ", "defer ")) or normalized.startswith(("skip ", "defer ")):
        return RouteDecision(IntentType.SKIP_TASK, 0.95, "Skip/defer prefix matched")
    if lower.startswith(("delete ", "remove ")) or normalized.startswith(("delete ", "remove ")):
        return RouteDecision(IntentType.DELETE_TASK, 0.95, "Delete/remove prefix matched")
    if looks_like_bulk_edit_request(cleaned):
        return RouteDecision(IntentType.BULK_EDIT, 0.9, "Bulk edit phrasing detected")

    if "\n" in cleaned or cleaned.count(";") >= 2:
        return RouteDecision(IntentType.BULK_ADD, 0.85, "Batch delimiter pattern detected")

    # Optional local-model classification (with fallback if unavailable).
    model_decision = _classify_with_ollama(cleaned)
    if model_decision and model_decision.confidence >= 0.5:
        return model_decision
    if _looks_like_query(cleaned):
        return RouteDecision(IntentType.QUERY, 0.8, "Question/query phrasing matched")

    return RouteDecision(IntentType.ADD_TASK, 0.7, "Default to task capture intent")
