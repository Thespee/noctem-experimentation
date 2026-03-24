"""Inactivity-budgeted queue-producer scheduler for v0.9.4."""
from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import Config
from ..db import get_db
from ..services.execution_queue import (
    enqueue_scheduled_job,
    has_retryable_queue_items,
    queue_metrics,
)
from ..services.ics_import import get_saved_urls
from ..services.object_context_docs import has_stale_context_docs
from ..voice.journals import get_pending_journals

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 120
DEFAULT_SAFETY_MARGIN = timedelta(minutes=5)
DISPATCH_INTERVAL_SECONDS = 60
MAX_RUNTIME_SAMPLES = 30

SCHEDULER_JOB_DEFAULTS = {
    "voice_transcription": {"interval_minutes": 1440, "enabled": True},
    "context_doc_refresh": {"interval_minutes": 5, "enabled": True},
    "ics_refresh": {"interval_minutes": 1440, "enabled": True},
    "queue_retry_scan": {"interval_minutes": 240, "enabled": True},
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _normalize_job_config(raw: Any) -> dict[str, dict[str, Any]]:
    normalized = {
        name: {
            "interval_minutes": int(defaults["interval_minutes"]),
            "enabled": bool(defaults["enabled"]),
        }
        for name, defaults in SCHEDULER_JOB_DEFAULTS.items()
    }
    if not isinstance(raw, dict):
        return normalized
    for name, value in raw.items():
        if name not in normalized or not isinstance(value, dict):
            continue
        interval_raw = value.get("interval_minutes")
        try:
            interval_minutes = int(interval_raw)
        except Exception:
            interval_minutes = normalized[name]["interval_minutes"]
        normalized[name]["interval_minutes"] = max(1, min(interval_minutes, 10080))
        if "enabled" in value:
            normalized[name]["enabled"] = bool(value.get("enabled"))
    return normalized


def _load_scheduler_config() -> dict[str, dict[str, Any]]:
    try:
        raw = Config.get("scheduler_job_config", SCHEDULER_JOB_DEFAULTS)
    except Exception:
        raw = SCHEDULER_JOB_DEFAULTS
    return _normalize_job_config(raw)


def _save_scheduler_config(config: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized = _normalize_job_config(config)
    try:
        Config.set("scheduler_job_config", normalized)
    except Exception:
        return normalized
    return normalized


def _record_scheduler_run(
    *,
    job_name: str,
    started_at: str,
    duration_seconds: float,
    ok: bool,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO scheduler_runs (job_name, started_at, duration_seconds, ok, summary_json, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(job_name),
                str(started_at),
                float(max(0.0, duration_seconds)),
                1 if ok else 0,
                _json_dumps(summary or {}),
                error,
            ),
        )


def _queue_job_idempotency_key(job_name: str) -> str:
    bucket = datetime.utcnow().strftime("%Y%m%d%H%M")
    return f"scheduler:{job_name}:{bucket}"


def _enqueue_job(job_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    queued = enqueue_scheduled_job(
        job_name=job_name,
        payload=payload,
        idempotency_key=_queue_job_idempotency_key(job_name),
    )
    return {
        "status": "enqueued",
        "job_name": job_name,
        "queue_item_id": queued.get("id"),
    }


@dataclass
class JobRuntimeStats:
    name: str
    runs: int = 0
    failures: int = 0
    durations: list[float] = field(default_factory=list)
    last_run_at: datetime | None = None
    last_error: str | None = None

    def expected_runtime_seconds(self, fallback_seconds: float) -> float:
        if self.durations:
            return float(statistics.median(self.durations))
        return float(fallback_seconds)

    def record(self, *, duration_seconds: float, ok: bool, error: str | None = None):
        self.runs += 1
        if not ok:
            self.failures += 1
            self.last_error = error
        else:
            self.last_error = None
        self.last_run_at = datetime.utcnow()
        self.durations.append(float(duration_seconds))
        if len(self.durations) > MAX_RUNTIME_SAMPLES:
            self.durations = self.durations[-MAX_RUNTIME_SAMPLES:]


@dataclass(frozen=True)
class PassiveJob:
    name: str
    has_work: Callable[[], bool]
    produce: Callable[[], dict[str, Any]]
    fallback_runtime_seconds: float
    value_score: float = 1.0


class IdleCoordinator:
    def __init__(self, *, cooldown_seconds: float = COOLDOWN_SECONDS, safety_margin: timedelta = DEFAULT_SAFETY_MARGIN):
        self._cooldown_seconds = float(cooldown_seconds)
        self._safety_margin = safety_margin
        self._last_user_activity_at = datetime.utcnow()
        self._idle_mode_entered = False
        self._stats: dict[str, JobRuntimeStats] = {}
        self._lock = RLock()
        self._jobs: list[PassiveJob] = [
            PassiveJob(
                name="voice_transcription",
                has_work=_has_pending_voice,
                produce=_run_voice,
                fallback_runtime_seconds=30.0,
                value_score=1.2,
            ),
            PassiveJob(
                name="context_doc_refresh",
                has_work=_has_stale_context_docs,
                produce=_run_context_doc_refresh,
                fallback_runtime_seconds=20.0,
                value_score=1.0,
            ),
            PassiveJob(
                name="ics_refresh",
                has_work=_has_saved_ics_urls,
                produce=_run_ics_refresh,
                fallback_runtime_seconds=20.0,
                value_score=0.8,
            ),
            PassiveJob(
                name="queue_retry_scan",
                has_work=_has_retryable_queue_items,
                produce=_run_queue_retry_scan,
                fallback_runtime_seconds=12.0,
                value_score=1.1,
            ),
        ]
        self._jobs_by_name: dict[str, PassiveJob] = {job.name: job for job in self._jobs}
        self._job_config = _load_scheduler_config()

    def reload_config(self):
        with self._lock:
            self._job_config = _load_scheduler_config()

    def _job_interval(self, job_name: str) -> timedelta:
        with self._lock:
            cfg = self._job_config.get(job_name) or SCHEDULER_JOB_DEFAULTS.get(job_name) or {}
            minutes = int(cfg.get("interval_minutes") or 1)
        return timedelta(minutes=max(1, minutes))

    def _job_enabled(self, job_name: str) -> bool:
        with self._lock:
            cfg = self._job_config.get(job_name) or SCHEDULER_JOB_DEFAULTS.get(job_name) or {}
            return bool(cfg.get("enabled", True))

    def record_user_activity(self, source: str | None = None):
        with self._lock:
            self._last_user_activity_at = datetime.utcnow()
            self._idle_mode_entered = False
        if source:
            logger.debug("Scheduler activity heartbeat from %s", source)

    def _gate_check(self) -> tuple[bool, dict[str, Any]]:
        """3-condition gate: no queued, no processing, user idle ≥ cooldown."""
        metrics = queue_metrics()
        queued_count = int(metrics.get("queued_count") or 0)
        processing_count = int(metrics.get("processing_count") or 0)
        with self._lock:
            idle_for = max(0.0, (datetime.utcnow() - self._last_user_activity_at).total_seconds())
        user_idle = idle_for >= self._cooldown_seconds
        gate_open = queued_count == 0 and processing_count == 0 and user_idle
        details = {
            "queued_count": queued_count,
            "processing_count": processing_count,
            "idle_for_seconds": round(idle_for, 1),
            "cooldown_seconds": self._cooldown_seconds,
            "user_idle": user_idle,
            "gate_open": gate_open,
        }
        return gate_open, details

    def status(self) -> dict[str, Any]:
        gate_open, gate_details = self._gate_check()
        with self._lock:
            config_snapshot = {name: dict(value) for name, value in self._job_config.items()}
            stats_snapshot = dict(self._stats)
        return {
            "idle_for_seconds": gate_details["idle_for_seconds"],
            "idle_mode_entered": self._idle_mode_entered,
            "cooldown_seconds": self._cooldown_seconds,
            "safety_margin_seconds": self._safety_margin.total_seconds(),
            "gate": gate_details,
            "job_config": config_snapshot,
            "job_stats": {
                name: {
                    "runs": stat.runs,
                    "failures": stat.failures,
                    "expected_runtime_seconds": stat.expected_runtime_seconds(
                        self._jobs_by_name[name].fallback_runtime_seconds
                    ),
                    "last_error": stat.last_error,
                    "last_run_at": stat.last_run_at.isoformat() if stat.last_run_at else None,
                    "enabled": bool((config_snapshot.get(name) or {}).get("enabled", True)),
                    "interval_minutes": int((config_snapshot.get(name) or {}).get("interval_minutes") or 1),
                }
                for name, stat in stats_snapshot.items()
                if name in self._jobs_by_name
            },
        }

    def _get_stats(self, job_name: str) -> JobRuntimeStats:
        with self._lock:
            existing = self._stats.get(job_name)
            if existing:
                return existing
            created = JobRuntimeStats(name=job_name)
            self._stats[job_name] = created
            return created

    def _current_budget_seconds(self) -> float:
        gate_open, gate_details = self._gate_check()
        if not gate_open:
            with self._lock:
                self._idle_mode_entered = False
            return 0.0
        idle_for_seconds = gate_details["idle_for_seconds"]
        with self._lock:
            if not self._idle_mode_entered:
                self._idle_mode_entered = True
                return max(0.0, idle_for_seconds)
            budget = idle_for_seconds - self._safety_margin.total_seconds()
            return max(0.0, budget)

    def _eligible_jobs(self, budget_seconds: float) -> list[tuple[float, float, PassiveJob]]:
        now = datetime.utcnow()
        eligible: list[tuple[float, float, PassiveJob]] = []
        for job in self._jobs:
            if not self._job_enabled(job.name):
                continue
            stats = self._get_stats(job.name)
            min_interval = self._job_interval(job.name)
            if stats.last_run_at and (now - stats.last_run_at) < min_interval:
                continue
            try:
                if not job.has_work():
                    continue
            except Exception as exc:
                logger.debug("Passive job '%s' has_work probe failed: %s", job.name, exc)
                continue
            expected = stats.expected_runtime_seconds(job.fallback_runtime_seconds)
            if expected > budget_seconds:
                continue
            score = job.value_score / max(expected, 1.0)
            eligible.append((score, expected, job))
        eligible.sort(key=lambda item: item[0], reverse=True)
        return eligible

    def _run_job(self, job: PassiveJob) -> dict[str, Any]:
        stats = self._get_stats(job.name)
        started_at = _now_iso()
        start = time.monotonic()
        ok = True
        err = None
        summary: dict[str, Any]
        try:
            produced = job.produce()
            summary = produced if isinstance(produced, dict) else {"result": produced}
        except Exception as exc:
            ok = False
            err = str(exc)
            summary = {}
            logger.exception("Passive job '%s' failed", job.name)
        duration = max(0.0, time.monotonic() - start)
        stats.record(duration_seconds=duration, ok=ok, error=err)
        _record_scheduler_run(
            job_name=job.name,
            started_at=started_at,
            duration_seconds=duration,
            ok=ok,
            summary=summary,
            error=err,
        )
        if ok:
            logger.info("Passive job '%s' enqueued work: %s", job.name, summary)
        return {
            "job_name": job.name,
            "ok": ok,
            "duration_seconds": duration,
            "summary": summary,
            "error": err,
        }

    async def tick(self) -> dict[str, Any]:
        self.reload_config()
        budget_seconds = self._current_budget_seconds()
        if budget_seconds <= 0:
            return {
                "idle_active": False,
                "budget_seconds": 0.0,
                "remaining_seconds": 0.0,
                "ran_any": False,
                "ran_jobs": [],
            }

        remaining = budget_seconds
        ran_jobs: list[dict[str, Any]] = []
        for _score, expected, job in self._eligible_jobs(remaining):
            if expected > remaining:
                continue
            result = self._run_job(job)
            remaining -= result["duration_seconds"]
            ran_jobs.append(result)
            if remaining <= 0:
                break

        if not ran_jobs:
            logger.debug("Idle coordinator tick: no eligible jobs within %.1fs budget", budget_seconds)
        return {
            "idle_active": True,
            "budget_seconds": budget_seconds,
            "remaining_seconds": max(0.0, remaining),
            "ran_any": len(ran_jobs) > 0,
            "ran_jobs": ran_jobs,
        }

    def run_job_now(self, job_name: str) -> dict[str, Any]:
        self.reload_config()
        job = self._jobs_by_name.get(str(job_name or "").strip())
        if job is None:
            raise ValueError(f"Unknown scheduler job: {job_name}")
        try:
            has_work = bool(job.has_work())
        except Exception:
            has_work = True
        if not has_work:
            started_at = _now_iso()
            _record_scheduler_run(
                job_name=job.name,
                started_at=started_at,
                duration_seconds=0.0,
                ok=True,
                summary={"status": "no_work"},
                error=None,
            )
            return {
                "job_name": job.name,
                "ok": True,
                "duration_seconds": 0.0,
                "summary": {"status": "no_work"},
                "error": None,
            }
        return self._run_job(job)


def _has_pending_voice() -> bool:
    return len(get_pending_journals()) > 0


def _has_saved_ics_urls() -> bool:
    return len(get_saved_urls()) > 0


def _has_stale_context_docs() -> bool:
    return has_stale_context_docs()


def _has_retryable_queue_items() -> bool:
    return has_retryable_queue_items()


def _run_voice() -> dict[str, Any]:
    return _enqueue_job("voice_transcription", {"max_items": 2})


def _run_ics_refresh() -> dict[str, Any]:
    return _enqueue_job("ics_refresh", {})


def _run_context_doc_refresh() -> dict[str, Any]:
    return _enqueue_job("context_doc_refresh", {"max_items": 6})


def _run_queue_retry_scan() -> dict[str, Any]:
    return _enqueue_job("queue_retry_scan", {"max_items": 80})


scheduler: AsyncIOScheduler | None = None
_coordinator = IdleCoordinator()


def record_user_activity(source: str | None = None):
    _coordinator.record_user_activity(source=source)


def get_job_run_history(job_name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit or 20), 500))
    params: list[Any] = []
    where = ""
    if job_name:
        where = "WHERE job_name = ?"
        params.append(str(job_name).strip())
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, job_name, started_at, duration_seconds, ok, summary_json, error
            FROM scheduler_runs
            {where}
            ORDER BY datetime(started_at) DESC, id DESC
            LIMIT ?
            """,
            [*params, bounded_limit],
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "job_name": row["job_name"],
            "started_at": row["started_at"],
            "duration_seconds": float(row["duration_seconds"] or 0.0),
            "ok": bool(int(row["ok"] or 0)),
            "summary": _json_loads(row["summary_json"], {}),
            "error": row["error"],
        }
        for row in rows
    ]


def update_job_config(
    job_name: str,
    *,
    interval_minutes: int | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    normalized_name = str(job_name or "").strip()
    if normalized_name not in SCHEDULER_JOB_DEFAULTS:
        raise ValueError(f"Unknown scheduler job: {job_name}")
    config = _load_scheduler_config()
    target = dict(config.get(normalized_name) or SCHEDULER_JOB_DEFAULTS[normalized_name])
    if interval_minutes is not None:
        target["interval_minutes"] = max(1, min(int(interval_minutes), 10080))
    if enabled is not None:
        target["enabled"] = bool(enabled)
    config[normalized_name] = target
    saved = _save_scheduler_config(config)
    _coordinator.reload_config()
    return dict(saved.get(normalized_name) or {})


def run_job_now(job_name: str) -> dict[str, Any]:
    return _coordinator.run_job_now(job_name)


def get_scheduler_status() -> dict[str, Any]:
    status = _coordinator.status()
    status["queue_metrics"] = queue_metrics()
    status["recent_runs"] = get_job_run_history(limit=20)
    return status


async def _idle_dispatch_tick():
    tick_result = await _coordinator.tick()
    if not tick_result.get("idle_active"):
        return
    queued_count = int((queue_metrics().get("queued_count") or 0))
    if queued_count <= 0:
        return
    try:
        from ..agent.execution_queue_runtime import process_execution_queue

        process_execution_queue(
            worker_id="scheduler-idle",
            max_items=max(1, min(queued_count, 20)),
        )
    except Exception:
        logger.exception("Scheduler idle queue drain failed")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the inactivity-budgeted scheduler."""
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _idle_dispatch_tick,
        "interval",
        seconds=DISPATCH_INTERVAL_SECONDS,
        id="idle_passive_dispatch",
        name="Idle Passive Dispatch",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    logger.info(
        "Passive scheduler configured (cooldown=%ss, safety margin=%sm, poll=%ss)",
        COOLDOWN_SECONDS,
        int(DEFAULT_SAFETY_MARGIN.total_seconds() / 60),
        DISPATCH_INTERVAL_SECONDS,
    )
    return scheduler


def start_scheduler():
    """Start the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
