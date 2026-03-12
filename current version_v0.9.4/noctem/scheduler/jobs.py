"""Inactivity-budgeted passive scheduler for v0.9.4."""
from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..services.ics_import import get_saved_urls, refresh_all_urls
from ..services.object_context_docs import has_stale_context_docs, synthesize_stale_context_docs
from ..voice.journals import get_pending_journals
from ..voice.processing import process_pending_voice_journals

logger = logging.getLogger(__name__)

IDLE_TRIGGER = timedelta(minutes=15)
DEFAULT_SAFETY_MARGIN = timedelta(minutes=5)
DISPATCH_INTERVAL_SECONDS = 60
MAX_RUNTIME_SAMPLES = 30


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
    run: Callable[[], Any]
    fallback_runtime_seconds: float
    min_interval: timedelta = timedelta(minutes=1)
    value_score: float = 1.0


class IdleCoordinator:
    def __init__(self, *, idle_trigger: timedelta = IDLE_TRIGGER, safety_margin: timedelta = DEFAULT_SAFETY_MARGIN):
        self._idle_trigger = idle_trigger
        self._safety_margin = safety_margin
        self._last_user_activity_at = datetime.utcnow()
        self._idle_mode_entered = False
        self._stats: dict[str, JobRuntimeStats] = {}
        self._lock = RLock()

        self._jobs: list[PassiveJob] = [
            PassiveJob(
                name="voice_transcription",
                has_work=_has_pending_voice,
                run=_run_voice,
                fallback_runtime_seconds=90.0,
                min_interval=timedelta(minutes=1),
                value_score=1.2,
            ),
            PassiveJob(
                name="context_doc_refresh",
                has_work=_has_stale_context_docs,
                run=_run_context_doc_refresh,
                fallback_runtime_seconds=45.0,
                min_interval=timedelta(minutes=5),
                value_score=1.0,
            ),
            PassiveJob(
                name="ics_refresh",
                has_work=_has_saved_ics_urls,
                run=_run_ics_refresh,
                fallback_runtime_seconds=30.0,
                min_interval=timedelta(minutes=10),
                value_score=0.7,
            ),
        ]

    def record_user_activity(self, source: str | None = None):
        with self._lock:
            self._last_user_activity_at = datetime.utcnow()
            self._idle_mode_entered = False
        if source:
            logger.debug("Scheduler activity heartbeat from %s", source)

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = datetime.utcnow()
            idle_for_seconds = max(0.0, (now - self._last_user_activity_at).total_seconds())
            return {
                "idle_for_seconds": idle_for_seconds,
                "idle_mode_entered": self._idle_mode_entered,
                "idle_trigger_seconds": self._idle_trigger.total_seconds(),
                "safety_margin_seconds": self._safety_margin.total_seconds(),
                "job_stats": {
                    name: {
                        "runs": stat.runs,
                        "failures": stat.failures,
                        "expected_runtime_seconds": stat.expected_runtime_seconds(job.fallback_runtime_seconds),
                        "last_error": stat.last_error,
                        "last_run_at": stat.last_run_at.isoformat() if stat.last_run_at else None,
                    }
                    for name, stat in self._stats.items()
                    for job in self._jobs
                    if job.name == name
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
        with self._lock:
            now = datetime.utcnow()
            idle_for = now - self._last_user_activity_at
            if idle_for < self._idle_trigger:
                self._idle_mode_entered = False
                return 0.0

            if not self._idle_mode_entered:
                self._idle_mode_entered = True
                return max(0.0, idle_for.total_seconds())

            budget = idle_for - self._safety_margin
            return max(0.0, budget.total_seconds())

    def _eligible_jobs(self, budget_seconds: float) -> list[tuple[float, float, PassiveJob]]:
        now = datetime.utcnow()
        eligible: list[tuple[float, float, PassiveJob]] = []
        for job in self._jobs:
            stats = self._get_stats(job.name)
            if stats.last_run_at and (now - stats.last_run_at) < job.min_interval:
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

    async def tick(self):
        budget_seconds = self._current_budget_seconds()
        if budget_seconds <= 0:
            return

        remaining = budget_seconds
        ran_any = False
        for _score, expected, job in self._eligible_jobs(remaining):
            if expected > remaining:
                continue
            stats = self._get_stats(job.name)
            start = time.monotonic()
            ok = True
            err = None
            try:
                result = job.run()
                logger.info("Passive job '%s' completed: %s", job.name, result)
            except Exception as exc:
                ok = False
                err = str(exc)
                logger.exception("Passive job '%s' failed", job.name)
            duration = max(0.0, time.monotonic() - start)
            stats.record(duration_seconds=duration, ok=ok, error=err)
            remaining -= duration
            ran_any = True
            if remaining <= 0:
                break

        if not ran_any:
            logger.debug("Idle coordinator tick: no eligible jobs within %.1fs budget", budget_seconds)


def _has_pending_voice() -> bool:
    return len(get_pending_journals()) > 0


def _run_voice() -> int:
    return process_pending_voice_journals(max_items=2)


def _has_saved_ics_urls() -> bool:
    return len(get_saved_urls()) > 0

def _has_stale_context_docs() -> bool:
    return has_stale_context_docs()


def _run_ics_refresh() -> dict:
    return refresh_all_urls()

def _run_context_doc_refresh() -> dict:
    return synthesize_stale_context_docs(max_items=6)


scheduler: AsyncIOScheduler | None = None
_coordinator = IdleCoordinator()


def record_user_activity(source: str | None = None):
    _coordinator.record_user_activity(source=source)


def get_scheduler_status() -> dict[str, Any]:
    return _coordinator.status()


async def _idle_dispatch_tick():
    await _coordinator.tick()


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
        "Passive scheduler configured (idle trigger=%sm, safety margin=%sm, poll=%ss)",
        int(IDLE_TRIGGER.total_seconds() / 60),
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
